"""PTY-path behavioral regression test for GitHub issue #144.

The pipe runner (`base.py`, covered by `tests/test_clink_process_tree.py`) is
one of the two spawn sites #144 calls out. The other is the PTY runner used
by the Antigravity CLI agent (`clink/agents/antigravity.py:190`, per the
issue's own change-inventory table: "a PTY-path test, skipped where
`pywinpty` is absent").

This test drives `AntigravityAgent._run_in_pty` for real, through an actual
ConPTY via `pywinpty` -- no mocking of the OS layer -- with a child that
spawns its own grandchild, then asserts the grandchild does not survive a
timeout. This is the direct evidence that the PTY runner joined the same
process-group ownership model as the pipe runner, rather than a per-runner
accident (#20 story 35).
"""

from __future__ import annotations

import ctypes
import sys
import textwrap
import time

import pytest

pytest.importorskip("winpty")

from clink.agents.antigravity import AntigravityAgent  # noqa: E402
from clink.agents.base import CLIAgentError  # noqa: E402
from clink.models import ResolvedCLIClient  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="ConPTY/pywinpty is Windows-only")

CHILD_SCRIPT = textwrap.dedent("""
    import subprocess
    import sys
    import time

    pidfile = sys.argv[1]
    # CREATE_BREAKAWAY_FROM_JOB | DETACHED_PROCESS: deliberately escape both
    # the Job Object and the console this process was placed in, simulating
    # a real coding-CLI descendant that outlives the console/job it was born
    # under (a background daemon, a detached language server). Without this,
    # Windows' own "kill everything attached to this console" behavior on
    # ConPTY close incidentally cleans up a plain child regardless of
    # whether the fix under test does anything at all -- which would make
    # this test pass even against unfixed code.
    grandchild = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=subprocess.CREATE_BREAKAWAY_FROM_JOB | subprocess.DETACHED_PROCESS,
    )
    with open(pidfile, "w") as f:
        f.write(str(grandchild.pid))
    # Emit periodic output, like a real CLI streaming progress to its
    # terminal, so a PTY reader polling for a timeout actually gets to run
    # (a silent child would leave `proc.read()` blocked on the pipe).
    for _ in range(600):
        print(".", flush=True)
        time.sleep(0.1)
    """)


def _pid_alive(pid: int) -> bool:
    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    exit_code = ctypes.c_ulong(0)
    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    ctypes.windll.kernel32.CloseHandle(handle)
    still_active = 259
    return exit_code.value == still_active


@pytest.fixture()
def antigravity_agent():
    client = ResolvedCLIClient(
        name="antigravity",
        executable=["agy"],
        internal_args=[],
        config_args=[],
        env={},
        timeout_seconds=30,
        parser="antigravity_text",
        runner="antigravity",
        roles={},
        output_to_file=None,
        working_dir=None,
    )
    return AntigravityAgent(client)


def test_pty_runner_kills_grandchild_and_confirms_before_returning(tmp_path, antigravity_agent):
    script_path = tmp_path / "spawn_grandchild.py"
    script_path.write_text(CHILD_SCRIPT)
    pidfile = tmp_path / "grandchild.pid"

    command = [sys.executable, str(script_path), str(pidfile)]

    with pytest.raises(CLIAgentError, match="timed out"):
        antigravity_agent._run_in_pty(command, env={}, cwd=None, timeout=1)

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

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _pid_alive(grandchild_pid):
        time.sleep(0.05)

    assert not _pid_alive(grandchild_pid), (
        "grandchild process survived PTY-runner timeout -- the PTY path did not "
        "join the same process-group ownership model as the pipe runner"
    )
