"""Behavioral regression tests for GitHub issue #144.

`clink` must own the *entire* process tree it spawns for a subagent, not just
the direct child, and termination must be confirmed by the OS before the
caller proceeds.

`test_process_group_kills_grandchild_and_confirms_before_returning` is a real,
unmocked OS-level test: it spawns a child that spawns a grandchild, using the
exact spawn kwargs `clink.agents.process_tree` hands to subprocess creation,
then asserts the grandchild is gone only once `terminate_blocking()` returns.
This is the direct evidence for acceptance criteria 1-4 of #144.

The remaining tests wire the mechanism into `BaseCLIAgent.run()` using mocked
processes (matching the existing test style in this file's siblings) because
this repository's `tests/conftest.py` forces `WindowsSelectorEventLoopPolicy`
on Windows, and asyncio subprocess transports are only implemented under the
Proactor loop -- so a real end-to-end `asyncio.create_subprocess_exec` test
cannot run inside this suite on Windows. Production code does not force that
policy, so `asyncio.create_subprocess_exec` uses the default Proactor loop at
runtime.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import shutil
import subprocess
import sys
import textwrap
import time

import pytest

from clink.agents.base import CLIAgentError
from clink.agents.claude import ClaudeAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole

CHILD_SCRIPT = textwrap.dedent("""
    import subprocess
    import sys
    import time

    pidfile = sys.argv[1]
    grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    with open(pidfile, "w") as f:
        f.write(str(grandchild.pid))
    time.sleep(60)
    """)


def _pid_alive(pid: int) -> bool:
    """Cross-platform liveness check that does not depend on the code under test."""
    if sys.platform == "win32":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong(0)
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        still_active = 259
        return exit_code.value == still_active

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_process_group_kills_grandchild_and_confirms_before_returning(tmp_path):
    from clink.agents import process_tree

    script_path = tmp_path / "spawn_grandchild.py"
    script_path.write_text(CHILD_SCRIPT)
    pidfile = tmp_path / "grandchild.pid"

    child = subprocess.Popen(
        [sys.executable, str(script_path), str(pidfile)],
        **process_tree.spawn_kwargs(),
    )
    # Attach immediately after spawn, exactly like base.py does -- before the
    # child has had any chance to spawn its own descendants.
    group = process_tree.ProcessGroup(child.pid)
    try:
        deadline = time.monotonic() + 5
        grandchild_pid = None
        while time.monotonic() < deadline:
            if pidfile.exists():
                content = pidfile.read_text().strip()
                if content:
                    grandchild_pid = int(content)
                    break
            time.sleep(0.05)
        assert grandchild_pid is not None, "grandchild process never started"
        assert _pid_alive(grandchild_pid), "grandchild should be alive before termination"

        confirmed = group.terminate_blocking(timeout=5.0)
        group.close()

        assert confirmed, "termination was not confirmed by the OS within the timeout"
        assert not _pid_alive(grandchild_pid), (
            "grandchild process survived group termination -- only the direct "
            "child was targeted, leaving an orphan with write access to the "
            "working directory"
        )
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


class DummyProcessWithPid:
    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0, pid: int = 4242):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.pid = pid
        self.killed = False

    async def communicate(self, _input=None):
        if self.killed:
            return self._stdout, self._stderr
        raise asyncio.TimeoutError

    def kill(self):
        self.killed = True


class FakeProcessGroup:
    created_with: list[int] = []
    terminate_calls: list[float] = []
    closed: list[bool] = []
    terminate_delay = 0.2

    def __init__(self, pid):
        FakeProcessGroup.created_with.append(pid)

    async def terminate(self, timeout: float = 5.0) -> bool:
        await asyncio.sleep(FakeProcessGroup.terminate_delay)
        FakeProcessGroup.terminate_calls.append(timeout)
        return True

    def close(self):
        FakeProcessGroup.closed.append(True)


@pytest.fixture()
def claude_agent():
    from pathlib import Path

    prompt_path = Path("systemprompts/clink/default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
    client = ResolvedCLIClient(
        name="claude",
        executable=["claude"],
        internal_args=["--print", "--output-format", "json"],
        config_args=["--permission-mode", "acceptEdits"],
        env={},
        timeout_seconds=30,
        parser="claude_json",
        runner="claude",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return ClaudeAgent(client), role


@pytest.mark.asyncio
async def test_run_spawns_process_group_and_waits_for_confirmed_termination_on_timeout(monkeypatch, claude_agent):
    """base.py must own the whole tree (not a lone PID) and must not return
    until the OS confirms the group is gone -- acceptance criteria 1, 2 and 4.
    """
    from clink.agents import base as base_module

    agent, role = claude_agent
    process = DummyProcessWithPid(pid=9999)

    captured_kwargs: dict = {}

    async def fake_create_subprocess_exec(*_args, **kwargs):
        captured_kwargs.update(kwargs)
        return process

    FakeProcessGroup.created_with = []
    FakeProcessGroup.terminate_calls = []
    FakeProcessGroup.closed = []

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(agent.client, "timeout_seconds", 0)
    monkeypatch.setattr(base_module, "ProcessGroup", FakeProcessGroup)

    start = time.monotonic()
    with pytest.raises(CLIAgentError):
        await agent.run(role=role, prompt="hello", files=[], images=[])
    elapsed = time.monotonic() - start

    # The subagent is spawned into its own group/session -- never bare.
    expected_key = "creationflags" if sys.platform == "win32" else "start_new_session"
    assert expected_key in captured_kwargs

    # Termination targets the group (constructed from the child's pid), not the lone process handle.
    assert FakeProcessGroup.created_with == [9999]
    assert FakeProcessGroup.terminate_calls, "run() must terminate the process group on timeout"

    # The call must not return early: it blocks for at least as long as OS confirmation takes.
    assert elapsed >= FakeProcessGroup.terminate_delay

    # Resources are released regardless of outcome.
    assert FakeProcessGroup.closed == [True]


@pytest.mark.asyncio
async def test_run_closes_process_group_on_success(monkeypatch, claude_agent):
    """Cleanup must run on every exit path, including a clean success (#20 story 32)."""
    import json

    from clink.agents import base as base_module

    agent, role = claude_agent
    stdout_payload = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "42"}).encode()

    class SuccessProcess:
        pid = 555

        def __init__(self):
            self.returncode = 0

        async def communicate(self, _input=None):
            return stdout_payload, b""

    process = SuccessProcess()

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return process

    FakeProcessGroup.created_with = []
    FakeProcessGroup.closed = []

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(base_module, "ProcessGroup", FakeProcessGroup)

    result = await agent.run(role=role, prompt="hello", files=[], images=[])

    assert result.returncode == 0
    assert FakeProcessGroup.created_with == [555]
    assert FakeProcessGroup.closed == [True]
