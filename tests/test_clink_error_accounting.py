"""A failed run is still accountable for which model it ran (#41).

`finalize_output` resolves the model and then raises, so the model accounting
never reached `_build_error_metadata` — a failed run reported its token usage but
not what produced it. A wrong-model run is a plausible reason for a failure at
all, which makes this accounting most valuable exactly where it was missing.

Also pins the absence convention: `observed_model` is omitted when the backend
reported nothing, rather than carrying the literal string "unknown". The latter is
truthy and string-typed, so a caller could not tell "not observed" from "a model
named unknown" — and it contradicted `_call_accounting`'s own docstring, which
says a key is absent when the client reported nothing for it.
"""

from __future__ import annotations

import json

import pytest

from clink.agents import AgentOutput, CLIAgentError
from clink.parsers.base import ParsedCLIResponse
from tools.clink import CLinkTool
from tools.shared.exceptions import ToolExecutionError


def _args(cli_name: str = "gemini") -> dict:
    return {
        "prompt": "hi",
        "cli_name": cli_name,
        "role": "default",
        "absolute_file_paths": [],
        "images": [],
        # #29 landed after this file and makes an omitted model a refusal, so every
        # call through the tool now carries one. Irrelevant to what these tests
        # assert — the model accounting they check comes from the raised
        # CLIAgentError, not from the request.
        "model": "gemini-3.1-pro",
    }


def _parsed(model_used: str | None) -> ParsedCLIResponse:
    metadata: dict = {}
    if model_used is not None:
        metadata["model_used"] = model_used
    return ParsedCLIResponse(content="partial output", metadata=metadata)


async def _error_metadata(monkeypatch, exc: CLIAgentError) -> dict:
    class DummyAgent:
        async def run(self, **_kwargs):
            raise exc

    monkeypatch.setattr("tools.clink.create_agent", lambda _client: DummyAgent())
    with pytest.raises(ToolExecutionError) as excinfo:
        await CLinkTool().execute(_args())
    return json.loads(excinfo.value.payload)["metadata"]


@pytest.mark.asyncio
async def test_a_failed_run_reports_which_model_it_ran(monkeypatch):
    metadata = await _error_metadata(
        monkeypatch,
        CLIAgentError(
            "CLI failed",
            returncode=1,
            parsed=_parsed("gemini-3.5-flash"),
            requested_model="gemini-3.1-pro",
            resolved_model="gemini-3.1-pro",
            observed_model="gemini-3.5-flash",
        ),
    )
    assert metadata["requested_model"] == "gemini-3.1-pro"
    assert metadata["resolved_model"] == "gemini-3.1-pro"
    assert metadata["observed_model"] == "gemini-3.5-flash"
    # The substitution is the reason to care: a run that failed under a model the
    # caller did not ask for is a different diagnosis from one that failed under
    # the model it requested.
    assert metadata["model_substituted"] is True


@pytest.mark.asyncio
async def test_an_unobserved_model_is_omitted_not_reported_as_unknown_on_error(monkeypatch):
    metadata = await _error_metadata(
        monkeypatch,
        CLIAgentError(
            "CLI failed",
            returncode=1,
            parsed=_parsed(None),
            requested_model="gemini-3.1-pro",
            resolved_model="gemini-3.1-pro",
            observed_model=None,
        ),
    )
    assert "observed_model" not in metadata
    assert "unknown" not in json.dumps(metadata)


@pytest.mark.asyncio
async def test_an_unobserved_model_is_omitted_on_success_too(monkeypatch):
    class DummyAgent:
        async def run(self, **_kwargs):
            return AgentOutput(
                parsed=_parsed(None),
                sanitized_command=["gemini"],
                returncode=0,
                stdout="",
                stderr="",
                duration_seconds=0.1,
                parser_name="gemini_json",
                requested_model="gemini-3.1-pro",
                resolved_model="gemini-3.1-pro",
                observed_model=None,
            )

    monkeypatch.setattr("tools.clink.create_agent", lambda _client: DummyAgent())
    result = await CLinkTool().execute(_args())
    metadata = json.loads(result[0].text)["metadata"]
    assert "observed_model" not in metadata
