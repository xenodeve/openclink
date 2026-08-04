"""Call accounting on the clink agent result (#23, slice 1 of #21).

The usage payloads below were recorded from real `codex exec --json` runs on
2026-08-03; each `id` names the invocation that produced it. They are the
independent source of truth for the expected values — nothing here recomputes
them the way the normaliser does.
"""

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from clink.agents.base import MAX_DRAINED_OUTPUT_CHARS, AgentOutput, CLIAgentError, TokenUsage
from clink.agents.codex import CodexAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole
from clink.parsers.base import ParsedCLIResponse
from tools.clink import MAX_RESPONSE_CHARS, CLinkTool


class DummyProcess:
    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self, _input):
        return self._stdout, self._stderr


def _codex_agent(*, config_args: list[str] | None = None):
    prompt_path = Path("systemprompts/clink/codex_default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
    client = ResolvedCLIClient(
        name="codex",
        executable=["codex"],
        internal_args=["exec"],
        config_args=config_args if config_args is not None else ["--json"],
        env={},
        timeout_seconds=30,
        parser="codex_jsonl",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return CodexAgent(client), role


async def _run(monkeypatch, agent, role, process, **kwargs):
    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    return await agent.run(role=role, prompt="do something", files=[], images=[], **kwargs)


def _stdout(turn_completed: str) -> bytes:
    message = '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"OK"}}'
    return f"{message}\n{turn_completed}\n".encode()


# Recorded verbatim from the `turn.completed` event of a real `codex exec --json` run.
RECORDED_USAGE = [
    pytest.param(
        '{"type":"turn.completed","usage":{"input_tokens":20252,"cached_input_tokens":0,'
        '"output_tokens":5,"reasoning_output_tokens":0}}',
        TokenUsage(input_tokens=20252, cached_input_tokens=0, output_tokens=5, reasoning_output_tokens=0),
        id="gpt-5.6-luna-effort-low",
    ),
    pytest.param(
        '{"type":"turn.completed","usage":{"input_tokens":20256,"cached_input_tokens":0,'
        '"output_tokens":5,"reasoning_output_tokens":0}}',
        TokenUsage(input_tokens=20256, cached_input_tokens=0, output_tokens=5, reasoning_output_tokens=0),
        id="gpt-5.6-luna-effort-medium",
    ),
    pytest.param(
        '{"type":"turn.completed","usage":{"input_tokens":20267,"cached_input_tokens":8960,'
        '"output_tokens":279,"reasoning_output_tokens":200}}',
        TokenUsage(input_tokens=20267, cached_input_tokens=8960, output_tokens=279, reasoning_output_tokens=200),
        id="gpt-5.6-luna-effort-xhigh-every-field-nonzero",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("turn_completed,expected", RECORDED_USAGE)
async def test_codex_run_reports_normalised_usage(monkeypatch, turn_completed, expected):
    agent, role = _codex_agent()
    result = await _run(monkeypatch, agent, role, DummyProcess(stdout=_stdout(turn_completed)))

    assert result.token_usage == expected


@pytest.mark.asyncio
async def test_usage_is_absent_when_the_cli_reports_none(monkeypatch):
    """A turn with no usage event leaves the account absent rather than zeroed."""
    agent, role = _codex_agent()
    stdout = b'{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"OK"}}\n'
    result = await _run(monkeypatch, agent, role, DummyProcess(stdout=stdout))

    assert result.token_usage is None


# `resolved` means what the command asks for once per-call overrides, config and
# role arguments have been merged. It is not proof the backend complied — that is
# the observed value, and codex's JSONL does not report one.
RESOLVED_TUPLE = [
    pytest.param(
        ["--json"],
        {"model": "gpt-5.6-luna", "reasoning_effort": "xhigh"},
        ("gpt-5.6-luna", "xhigh"),
        id="from-the-per-call-parameter",
    ),
    pytest.param(
        ["--json", "-m", "gpt-5.6-sol", "-c", "model_reasoning_effort=medium"],
        {},
        ("gpt-5.6-sol", "medium"),
        id="from-client-config",
    ),
    pytest.param(
        ["--json", "-m", "gpt-5.6-sol", "-c", "model_reasoning_effort=medium"],
        {"model": "gpt-5.6-luna", "reasoning_effort": "low"},
        ("gpt-5.6-luna", "low"),
        id="per-call-overrides-config",
    ),
    pytest.param(
        ["--json"],
        {},
        (None, None),
        id="neither-leaves-both-absent",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("config_args,overrides,expected", RESOLVED_TUPLE)
async def test_codex_run_reports_the_resolved_tuple(monkeypatch, config_args, overrides, expected):
    agent, role = _codex_agent(config_args=config_args)
    turn = '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}'
    result = await _run(monkeypatch, agent, role, DummyProcess(stdout=_stdout(turn)), **overrides)

    assert (result.resolved_model, result.resolved_effort) == expected


@pytest.mark.asyncio
async def test_a_non_zero_exit_still_reports_what_it_consumed(monkeypatch):
    """A call that spent tokens and then failed must still account for them.

    #13 made a non-zero exit a failure rather than a recovered success, so the
    account travels on the error now. The guarantee is unchanged — only its
    address is. If this ever stops holding, a failed delegation becomes free in
    the caller's books while still costing real quota.
    """
    agent, role = _codex_agent()
    turn = (
        '{"type":"turn.completed","usage":{"input_tokens":20267,"cached_input_tokens":8960,'
        '"output_tokens":279,"reasoning_output_tokens":200}}'
    )
    process = DummyProcess(stdout=_stdout(turn), returncode=124)

    with pytest.raises(CLIAgentError) as excinfo:
        await _run(monkeypatch, agent, role, process, model="gpt-5.6-luna", reasoning_effort="xhigh")

    assert excinfo.value.returncode == 124
    assert excinfo.value.token_usage == TokenUsage(
        input_tokens=20267, cached_input_tokens=8960, output_tokens=279, reasoning_output_tokens=200
    )
    assert excinfo.value.parsed is not None


@pytest.mark.asyncio
async def test_a_timeout_preserves_what_the_cli_had_already_emitted(monkeypatch):
    """A timeout must not throw away the partial transcript.

    Normalised usage stays empty here by construction, not by omission: codex
    reports usage on `turn.completed`, the last event of a turn, and a turn that
    timed out never emitted it. What was observed is the partial stdout, so that
    is what the error carries.
    """
    agent, role = _codex_agent()
    partial = b'{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"partway"}}\n'

    class HangingProcess:
        returncode = None

        def __init__(self):
            self._drained = False

        async def communicate(self, _input=None):
            if not self._drained:
                self._drained = True
                raise asyncio.TimeoutError
            return partial, b"killed"

        def kill(self):
            pass

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return HangingProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    with pytest.raises(CLIAgentError) as excinfo:
        await agent.run(role=role, prompt="do something", files=[], images=[])

    assert "partway" in excinfo.value.stdout
    assert "killed" in excinfo.value.stderr


@pytest.mark.asyncio
async def test_a_timeout_keeps_only_the_tail_of_a_large_transcript(monkeypatch):
    """Preserving the transcript must not mean returning megabytes of it.

    The error path does not run through the tool's output limiter, so what is
    captured here is what a caller receives. A long run is exactly the one that
    times out, so the cap belongs at capture. The tail is kept because that is
    where the CLI was when it died.
    """
    agent, role = _codex_agent()
    huge = (b"noise\n" * 200_000) + b"LAST-THING-IT-SAID"

    class HangingProcess:
        returncode = None

        def __init__(self):
            self._drained = False

        async def communicate(self, _input=None):
            if not self._drained:
                self._drained = True
                raise asyncio.TimeoutError
            return huge, b""

        def kill(self):
            pass

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return HangingProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    with pytest.raises(CLIAgentError) as excinfo:
        await agent.run(role=role, prompt="do something", files=[], images=[])

    assert len(excinfo.value.stdout) <= MAX_DRAINED_OUTPUT_CHARS
    assert "LAST-THING-IT-SAID" in excinfo.value.stdout


def test_error_metadata_caps_every_diagnostic_it_carries():
    """The cap belongs to the *class* of diagnostic, not to the fields we happened to name.

    The timeout path was bounded first (`MAX_DRAINED_OUTPUT_CHARS`) and the
    non-zero-exit path was left open — fixing the instance rather than the kind.
    So this pins all three strings a failed run carries, and any fourth added
    later has to join them or this test is the wrong shape.
    """
    agent, _role = _codex_agent()
    error = CLIAgentError(
        "CLI failed",
        returncode=1,
        stdout="S" * (MAX_RESPONSE_CHARS + 1),
        stderr="E" * (MAX_RESPONSE_CHARS + 1),
        parsed=ParsedCLIResponse(content="P" * (MAX_RESPONSE_CHARS + 1), metadata={}),
    )

    metadata = CLinkTool()._build_error_metadata(agent.client, error)

    assert metadata["salvaged_content"] == "P" * MAX_RESPONSE_CHARS
    assert metadata["stdout"] == "S" * MAX_RESPONSE_CHARS
    assert metadata["stderr"] == "E" * MAX_RESPONSE_CHARS
    assert metadata["truncated_fields"] == ["salvaged_content", "stderr", "stdout"]


def test_the_bounded_diagnostic_wins_over_parser_metadata_of_the_same_name():
    """Parser metadata is merged wholesale, so it must not be able to unbound a bounded field.

    No parser writes `salvaged_content` today. That is the reason to pin it now:
    the cap is only worth anything if nothing downstream can quietly replace it.
    """
    agent, _role = _codex_agent()
    error = CLIAgentError(
        "CLI failed",
        returncode=1,
        parsed=ParsedCLIResponse(
            content="P" * (MAX_RESPONSE_CHARS + 1),
            metadata={"salvaged_content": "Z" * (MAX_RESPONSE_CHARS + 1)},
        ),
    )

    metadata = CLinkTool()._build_error_metadata(agent.client, error)

    assert metadata["salvaged_content"] == "P" * MAX_RESPONSE_CHARS


# --- the tool seam: what a caller actually receives -------------------------


async def _execute_with_content(monkeypatch, content: str):
    tool = CLinkTool()

    class DummyAgent:
        async def run(self, **_kwargs):
            return AgentOutput(
                parsed=ParsedCLIResponse(content=content, metadata={}),
                sanitized_command=["codex", "exec", "--json"],
                returncode=0,
                stdout="",
                stderr="",
                duration_seconds=0.42,
                parser_name="codex_jsonl",
                output_file_content=None,
                resolved_model="gpt-5.6-luna",
                resolved_effort="xhigh",
                token_usage=TokenUsage(
                    input_tokens=20267,
                    cached_input_tokens=8960,
                    output_tokens=279,
                    reasoning_output_tokens=200,
                ),
            )

    monkeypatch.setattr("tools.clink.create_agent", lambda client: DummyAgent())

    results = await tool.execute(
        {
            "prompt": "Summarize the project",
            "cli_name": "codex",
            "role": "default",
            "absolute_file_paths": [],
            "images": [],
            "model": "gpt-5.6-luna",
        }
    )
    return json.loads(results[0].text).get("metadata", {})


@pytest.mark.asyncio
async def test_tool_surfaces_the_account_in_response_metadata(monkeypatch):
    metadata = await _execute_with_content(monkeypatch, "Hello from Codex")

    assert metadata.get("resolved_model") == "gpt-5.6-luna"
    assert metadata.get("resolved_effort") == "xhigh"
    assert metadata.get("normalized_usage") == {
        "input_tokens": 20267,
        "cached_input_tokens": 8960,
        "output_tokens": 279,
        "reasoning_output_tokens": 200,
    }


@pytest.mark.asyncio
async def test_the_account_survives_the_output_limiter(monkeypatch):
    """The limiter suppresses the output — the cost of producing it still stands."""
    metadata = await _execute_with_content(monkeypatch, "x" * (MAX_RESPONSE_CHARS + 1))

    assert metadata.get("output_truncated") is True
    assert metadata.get("resolved_model") == "gpt-5.6-luna"
    assert metadata.get("resolved_effort") == "xhigh"
    assert metadata.get("normalized_usage", {}).get("input_tokens") == 20267


@pytest.mark.asyncio
async def test_end_to_end_a_real_codex_payload_reaches_the_caller(monkeypatch):
    """The whole pipe: recorded CLI bytes in, accounted metadata out.

    Nothing is hand-assembled here — the real parser and the real CodexAgent run,
    so a break anywhere between stdout and response metadata fails this test.
    """
    turn = (
        '{"type":"turn.completed","usage":{"input_tokens":20267,"cached_input_tokens":8960,'
        '"output_tokens":279,"reasoning_output_tokens":200}}'
    )
    agent, _ = _codex_agent(config_args=["--json", "-m", "gpt-5.6-luna", "-c", "model_reasoning_effort=xhigh"])

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return DummyProcess(stdout=_stdout(turn))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("tools.clink.create_agent", lambda client: agent)

    results = await CLinkTool().execute(
        {
            "prompt": "hi",
            "cli_name": "codex",
            "role": "default",
            "absolute_file_paths": [],
            "images": [],
            "model": "gpt-5.6-luna",
        }
    )
    metadata = json.loads(results[0].text).get("metadata", {})

    assert metadata.get("resolved_model") == "gpt-5.6-luna"
    assert metadata.get("resolved_effort") == "xhigh"
    assert metadata.get("normalized_usage") == {
        "input_tokens": 20267,
        "cached_input_tokens": 8960,
        "output_tokens": 279,
        "reasoning_output_tokens": 200,
    }


@pytest.mark.asyncio
async def test_the_account_does_not_squat_on_the_gemini_parsers_token_usage_key(monkeypatch):
    """`token_usage` is already taken, in a different shape.

    `clink/parsers/gemini.py` publishes that key carrying Gemini's own raw
    counters. Publishing the normalised account under the same name would leave
    one key meaning two schemas depending on which CLI ran, forcing every
    consumer to sniff. The raw key must survive untouched.
    """
    tool = CLinkTool()
    raw_gemini_shape = {"prompt": 11, "candidates": 22, "total": 33}

    class DummyAgent:
        async def run(self, **_kwargs):
            return AgentOutput(
                parsed=ParsedCLIResponse(content="Hello", metadata={"token_usage": raw_gemini_shape}),
                sanitized_command=["gemini", "--model", "gemini-3.6-flash"],
                returncode=0,
                stdout="",
                stderr="",
                duration_seconds=0.1,
                parser_name="gemini_json",
                output_file_content=None,
                resolved_model="gemini-3.6-flash",
                token_usage=TokenUsage(input_tokens=11, output_tokens=22),
            )

    monkeypatch.setattr("tools.clink.create_agent", lambda client: DummyAgent())

    results = await tool.execute(
        {
            "prompt": "hi",
            "cli_name": "gemini",
            "role": "default",
            "absolute_file_paths": [],
            "images": [],
            "model": "gemini-3.6-flash",
        }
    )
    metadata = json.loads(results[0].text).get("metadata", {})

    assert metadata["token_usage"] == raw_gemini_shape
    assert metadata["normalized_usage"] == {"input_tokens": 11, "output_tokens": 22}


@pytest.mark.asyncio
async def test_absent_fields_are_omitted_rather_than_reported_as_null(monkeypatch):
    """A client with no adapter yet reports nothing, not a zeroed account."""
    tool = CLinkTool()

    class DummyAgent:
        async def run(self, **_kwargs):
            return AgentOutput(
                parsed=ParsedCLIResponse(content="Hello", metadata={}),
                sanitized_command=["gemini"],
                returncode=0,
                stdout="",
                stderr="",
                duration_seconds=0.1,
                parser_name="gemini_json",
                output_file_content=None,
            )

    monkeypatch.setattr("tools.clink.create_agent", lambda client: DummyAgent())

    results = await tool.execute(
        {
            "prompt": "hi",
            "cli_name": "gemini",
            "role": "default",
            "absolute_file_paths": [],
            "images": [],
            "model": "gpt-5.6-luna",
        }
    )
    metadata = json.loads(results[0].text).get("metadata", {})

    assert "normalized_usage" not in metadata
    assert "resolved_model" not in metadata
    assert "resolved_effort" not in metadata
    assert "cost" not in metadata
