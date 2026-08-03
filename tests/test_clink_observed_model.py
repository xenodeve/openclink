import asyncio
import json
import shutil
from pathlib import Path

import pytest

from clink.agents.claude import ClaudeAgent
from clink.agents.codex import CodexAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole
from clink.parsers.claude import ClaudeJSONParser
from tools.clink import MAX_RESPONSE_CHARS, CLinkTool, _names_one_model


@pytest.mark.parametrize(
    ("resolved", "observed", "same"),
    [
        # An alias against the dated canonical id — the shipped claude config.
        ("sonnet", "claude-sonnet-4-5-20250929", True),
        # antigravity names a model with spaces, dots and a parenthesised tier,
        # while a backend reports a hyphenated id. Punctuation is the only
        # difference, and without normalising it this reads as a substitution.
        ("Gemini 3.1 Pro (High)", "gemini-3.1-pro", True),
        ("GPT-5.6-Sol", "gpt_5_6_sol", True),
        # Two real models must stay distinguishable — the normalisation must not
        # be so loose that the flag can never fire.
        ("sonnet", "claude-opus-4-6-20260112", False),
        ("gemini-3.1-pro", "gemini-3.5-flash", False),
    ],
)
def test_which_name_pairs_denote_one_model(resolved, observed, same):
    assert _names_one_model(resolved, observed) is same


class DummyProcess:
    def __init__(self, *, stdout: bytes, stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self, _input):
        return self._stdout, self._stderr


def _role() -> ResolvedCLIRole:
    return ResolvedCLIRole(
        name="default",
        prompt_path=Path("systemprompts/clink/default.txt").resolve(),
        role_args=[],
    )


def _claude_agent() -> tuple[ClaudeAgent, ResolvedCLIRole]:
    role = _role()
    client = ResolvedCLIClient(
        name="claude",
        executable=["claude"],
        internal_args=["--print", "--output-format", "json"],
        config_args=["--model", "configured-model"],
        env={},
        timeout_seconds=30,
        parser="claude_json",
        runner="claude",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return ClaudeAgent(client), role


def _codex_agent() -> tuple[CodexAgent, ResolvedCLIRole]:
    role = _role()
    client = ResolvedCLIClient(
        name="codex",
        executable=["codex"],
        internal_args=["exec"],
        config_args=["--json", "-m", "configured-model"],
        env={},
        timeout_seconds=30,
        parser="codex_jsonl",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return CodexAgent(client), role


def _claude_payload(content: str, model_used: str) -> bytes:
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": content,
            "modelUsage": {model_used: {"inputTokens": 1, "outputTokens": 1}},
        }
    ).encode()


def _codex_payload() -> bytes:
    return (
        b'{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"OK"}}\n'
        b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n'
    )


async def _execute_with_agent(monkeypatch, agent, *, cli_name: str, model: str | None = None):
    async def fake_create_subprocess_exec(*_args, **_kwargs):
        stdout = _claude_payload("Hello", "backend-model") if cli_name == "claude" else _codex_payload()
        return DummyProcess(stdout=stdout)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("tools.clink.create_agent", lambda _client: agent)

    results = await CLinkTool().execute(
        {
            "prompt": "Summarize the project",
            "cli_name": cli_name,
            "role": "default",
            "absolute_file_paths": [],
            "images": [],
            "model": model,
        }
    )
    return json.loads(results[0].text)["metadata"]


@pytest.mark.asyncio
async def test_real_backend_disagreement_sets_model_substituted(monkeypatch):
    agent, _ = _claude_agent()

    metadata = await _execute_with_agent(monkeypatch, agent, cli_name="claude", model="requested-model")

    assert metadata["requested_model"] == "requested-model"
    assert metadata["resolved_model"] == "requested-model"
    assert metadata["observed_model"] == "backend-model"
    assert metadata["model_substituted"] is True


@pytest.mark.asyncio
async def test_backend_agreement_does_not_emit_model_substituted(monkeypatch):
    agent, _ = _claude_agent()

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return DummyProcess(stdout=_claude_payload("Hello", "requested-model"))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("tools.clink.create_agent", lambda _client: agent)

    results = await CLinkTool().execute(
        {
            "prompt": "Summarize the project",
            "cli_name": "claude",
            "role": "default",
            "absolute_file_paths": [],
            "images": [],
            "model": "requested-model",
        }
    )
    metadata = json.loads(results[0].text)["metadata"]

    assert metadata["resolved_model"] == "requested-model"
    assert metadata["observed_model"] == "requested-model"
    assert "model_substituted" not in metadata


@pytest.mark.asyncio
async def test_an_alias_and_its_canonical_id_are_not_a_substitution(monkeypatch):
    """The shipped claude config asks for `sonnet`; the CLI reports the dated id.

    Those are the same model written in two naming systems, and a raw `!=`
    calls it a substitution on **every ordinary run** of that client. A flag
    that fires constantly cannot carry the signal it exists for, so this is
    worse than not flagging: the one real substitution is lost in the noise.
    """
    agent, _ = _claude_agent()

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return DummyProcess(stdout=_claude_payload("Hello", "claude-sonnet-4-5-20250929"))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("tools.clink.create_agent", lambda _client: agent)

    results = await CLinkTool().execute(
        {
            "prompt": "Summarize the project",
            "cli_name": "claude",
            "role": "default",
            "absolute_file_paths": [],
            "images": [],
            "model": "sonnet",
        }
    )
    metadata = json.loads(results[0].text)["metadata"]

    # Both values still reach the caller unchanged — only the verdict is withheld.
    assert metadata["resolved_model"] == "sonnet"
    assert metadata["observed_model"] == "claude-sonnet-4-5-20250929"
    assert "model_substituted" not in metadata


@pytest.mark.asyncio
async def test_two_genuinely_different_models_are_still_a_substitution(monkeypatch):
    """The guard above must not swallow the case the flag exists for."""
    agent, _ = _claude_agent()

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return DummyProcess(stdout=_claude_payload("Hello", "claude-opus-4-6-20260112"))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("tools.clink.create_agent", lambda _client: agent)

    results = await CLinkTool().execute(
        {
            "prompt": "Summarize the project",
            "cli_name": "claude",
            "role": "default",
            "absolute_file_paths": [],
            "images": [],
            "model": "sonnet",
        }
    )
    metadata = json.loads(results[0].text)["metadata"]

    assert metadata["model_substituted"] is True


@pytest.mark.asyncio
async def test_codex_payload_without_observed_model_is_unknown_without_substitution(monkeypatch):
    agent, _ = _codex_agent()

    metadata = await _execute_with_agent(monkeypatch, agent, cli_name="codex")

    assert metadata["resolved_model"] == "configured-model"
    assert metadata["observed_model"] == "unknown"
    assert "requested_model" not in metadata
    assert "model_substituted" not in metadata


@pytest.mark.asyncio
async def test_all_model_values_survive_the_output_limiter(monkeypatch):
    content = "x" * (MAX_RESPONSE_CHARS + 1)
    parsed = ClaudeJSONParser().parse(_claude_payload(content, "backend-model").decode(), "")
    agent, _ = _claude_agent()
    result = agent.finalize_output(
        parsed=parsed,
        sanitized_command=["claude", "--model", "resolved-model"],
        returncode=0,
        stdout=content,
        stderr="",
        duration_seconds=0.1,
        requested_model="requested-model",
    )

    class DummyAgent:
        async def run(self, **_kwargs):
            return result

    monkeypatch.setattr("tools.clink.create_agent", lambda _client: DummyAgent())
    results = await CLinkTool().execute(
        {
            "prompt": "Summarize the project",
            "cli_name": "claude",
            "role": "default",
            "absolute_file_paths": [],
            "images": [],
        }
    )
    payload = json.loads(results[0].text)
    metadata = payload["metadata"]

    assert metadata["output_truncated"] is True
    assert metadata["requested_model"] == "requested-model"
    assert metadata["resolved_model"] == "resolved-model"
    assert metadata["observed_model"] == "backend-model"
    assert metadata["model_substituted"] is True


@pytest.mark.asyncio
async def test_requested_model_is_reported_when_different_from_resolved(monkeypatch):
    parsed = ClaudeJSONParser().parse(_claude_payload("Hello", "backend-model").decode(), "")
    agent, _ = _claude_agent()
    result = agent.finalize_output(
        parsed=parsed,
        sanitized_command=["claude", "--model", "configured-model"],
        returncode=0,
        stdout="Hello",
        stderr="",
        duration_seconds=0.1,
        requested_model="caller-model",
    )

    class DummyAgent:
        async def run(self, **_kwargs):
            return result

    monkeypatch.setattr("tools.clink.create_agent", lambda _client: DummyAgent())
    results = await CLinkTool().execute(
        {
            "prompt": "Summarize the project",
            "cli_name": "claude",
            "role": "default",
            "absolute_file_paths": [],
            "images": [],
        }
    )
    metadata = json.loads(results[0].text)["metadata"]

    assert metadata["requested_model"] == "caller-model"
    assert metadata["resolved_model"] == "configured-model"
