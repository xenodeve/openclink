"""Parser metadata must not reach the caller unbounded (#37).

`content` is capped at MAX_RESPONSE_CHARS on the success path and the failure
diagnostics are capped on the error path, but the parsers store their entire
decoded payload beside them under `raw` / `raw_events`, and nothing bounded it.
A large CLI response was therefore bounded in the field a caller reads and
unbounded in the field next to it.

Nothing in the tool reads either value — verified by grep 2026-08-04, the only
reads are parser-level test assertions — so they are dropped rather than capped,
once, in `_prune_metadata`, which is the one place both paths already pass through.
"""

from __future__ import annotations

import json

import pytest

from clink.agents import AgentOutput, CLIAgentError
from clink.parsers.claude import ClaudeJSONParser
from clink.parsers.gemini import GeminiJSONParser
from tools.clink import CLinkTool
from tools.shared.exceptions import ToolExecutionError

HUGE = "x" * (2 * 1024 * 1024)


def _args(cli_name: str) -> dict:
    return {
        "prompt": "summarize",
        "cli_name": cli_name,
        "role": "default",
        "absolute_file_paths": [],
        "images": [],
    }


@pytest.mark.asyncio
async def test_a_multi_megabyte_raw_payload_does_not_reach_the_caller_on_success(monkeypatch):
    parsed = GeminiJSONParser().parse(stdout=json.dumps({"response": "ok", "transcript": HUGE}), stderr="")

    class DummyAgent:
        async def run(self, **_kwargs):
            return AgentOutput(
                parsed=parsed,
                sanitized_command=["gemini", "-o", "json"],
                returncode=0,
                stdout="",
                stderr="",
                duration_seconds=0.1,
                parser_name="gemini_json",
                output_file_content=None,
            )

    monkeypatch.setattr("tools.clink.create_agent", lambda _client: DummyAgent())

    result = await CLinkTool().execute(_args("gemini"))
    response = json.loads(result[0].text)
    assert "raw" not in response["metadata"]


@pytest.mark.asyncio
async def test_a_multi_megabyte_raw_payload_does_not_reach_the_caller_on_error(monkeypatch):
    events = [
        {"type": "assistant", "message": "partial", "transcript": HUGE},
        {"type": "result", "is_error": True, "result": "failure details"},
    ]
    parsed = ClaudeJSONParser().parse(stdout=json.dumps(events), stderr="")

    class DummyAgent:
        async def run(self, **_kwargs):
            raise CLIAgentError("CLI failed", returncode=1, parsed=parsed)

    monkeypatch.setattr("tools.clink.create_agent", lambda _client: DummyAgent())

    with pytest.raises(ToolExecutionError) as excinfo:
        await CLinkTool().execute(_args("claude"))

    metadata = json.loads(excinfo.value.payload)["metadata"]
    assert "raw" not in metadata
    assert "raw_events" not in metadata
