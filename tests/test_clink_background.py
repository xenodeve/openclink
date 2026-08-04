"""A background clink call returns before its child finishes (#15, slice 1).

The blocking call is the whole problem: a `clink` delegation takes 45-190s here
(measured 2026-08-04), and for all of it the caller can do nothing. Claude Code
moves a long MCP call to a background task at a threshold, but that is a property
of one host, it has no per-server form, and it does not apply to a call made from
inside a subagent — so a mechanism that only works there is not a mechanism.

This slice makes it PAL's own behaviour, which every client gets identically:
`background=True` registers a session, starts the child on the server's event
loop, and returns a session id immediately. `clink_status` collects.

The gate on this issue was #12 Q1 — "does the HOST issue a follow-up call?" That
asks about the wrong actor. The follow-up call is emitted by the model, from the
instruction in the response, exactly like any other multi-step tool use.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from clink.agents import AgentOutput
from clink.parsers.base import ParsedCLIResponse
from tools.clink import CLinkStatusTool, CLinkTool

BACKGROUND_ARGS = {
    "prompt": "summarize",
    "cli_name": "gemini",
    "role": "default",
    "absolute_file_paths": [],
    "images": [],
    "model": "gemini-3.1-pro",
    "background": True,
}


class _BlockingAgent:
    """An agent that will not finish until the test releases it."""

    def __init__(self, release: asyncio.Event):
        self._release = release
        self.started = asyncio.Event()

    async def run(self, **_kwargs) -> AgentOutput:
        self.started.set()
        await self._release.wait()
        return AgentOutput(
            parsed=ParsedCLIResponse(content="the delegated answer", metadata={}),
            sanitized_command=["gemini"],
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=0.2,
            parser_name="gemini_json",
            requested_model="gemini-3.1-pro",
            resolved_model="gemini-3.1-pro",
        )


def _payload(result) -> dict:
    return json.loads(result[0].text)


@pytest.mark.asyncio
async def test_a_background_call_returns_while_its_child_is_still_running(monkeypatch):
    # The property under test is *not* "returns fast" — a fast return could just be
    # a fast child. It is that the call returns while the child is provably still
    # in flight, which is what makes the caller free.
    release = asyncio.Event()
    agent = _BlockingAgent(release)
    monkeypatch.setattr("tools.clink.create_agent", lambda _client: agent)

    payload = _payload(await CLinkTool().execute(dict(BACKGROUND_ARGS)))

    await asyncio.wait_for(agent.started.wait(), timeout=2)
    assert not release.is_set()
    assert payload["metadata"]["status"] == "running"
    assert payload["metadata"]["session_id"]
    # Actionable, per #27's rule: the caller must be told how to collect, or the
    # session is a handle nobody knows to use.
    assert "clink_status" in payload["content"]

    release.set()


@pytest.mark.asyncio
async def test_status_reports_running_first_and_then_the_terminal_payload(monkeypatch):
    release = asyncio.Event()
    agent = _BlockingAgent(release)
    monkeypatch.setattr("tools.clink.create_agent", lambda _client: agent)

    session_id = _payload(await CLinkTool().execute(dict(BACKGROUND_ARGS)))["metadata"]["session_id"]
    await asyncio.wait_for(agent.started.wait(), timeout=2)

    status = _payload(await CLinkStatusTool().execute({"session_id": session_id}))
    assert status["metadata"]["status"] == "running"

    release.set()
    for _ in range(200):  # let the task reach its own completion
        await asyncio.sleep(0.01)
        done = _payload(await CLinkStatusTool().execute({"session_id": session_id}))
        if done["metadata"]["status"] != "running":
            break
    assert done["metadata"]["status"] == "succeeded"
    assert "the delegated answer" in done["content"]
    # The terminal payload carries the same accounting a blocking call would.
    assert done["metadata"]["resolved_model"] == "gemini-3.1-pro"


@pytest.mark.asyncio
async def test_the_session_registry_holds_the_task_so_it_cannot_be_collected(monkeypatch):
    # asyncio only keeps a weak reference to a running task. A task nobody holds
    # can be garbage-collected mid-flight, and the failure is a delegation that
    # silently never finishes — indistinguishable from a slow one. The registry is
    # what holds it, which makes it load-bearing rather than bookkeeping.
    from tools.clink import _SESSIONS

    release = asyncio.Event()
    monkeypatch.setattr("tools.clink.create_agent", lambda _client: _BlockingAgent(release))

    session_id = _payload(await CLinkTool().execute(dict(BACKGROUND_ARGS)))["metadata"]["session_id"]
    assert isinstance(_SESSIONS[session_id].task, asyncio.Task)

    release.set()


@pytest.mark.asyncio
async def test_an_unknown_session_id_is_refused_and_names_what_it_looked_for():
    from tools.shared.exceptions import ToolExecutionError

    with pytest.raises(ToolExecutionError) as excinfo:
        await CLinkStatusTool().execute({"session_id": "no-such-session"})
    message = json.loads(excinfo.value.payload)["content"]
    assert "no-such-session" in message
