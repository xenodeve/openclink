"""The selection tool exists end to end and returns nothing interesting yet (#99).

A tracer bullet: the whole path is proven before anything worth computing runs
through it. Registered, advertised, dispatched by name, returns a constant.
No ranking, no dataset, no HTTP — those are #101 onward.

**Why the advertise check reads the server rather than the tool.** A tool that
passes its own unit tests has been shown to work, not to be *reachable*. `#99`
says so directly, and this repository has the scar: `tools/clink.py` accepted an
`images` parameter that no runner ever consumed, so calls returned exit 0 with a
plausible answer while nothing reached the CLI. A registration is exactly that
shape of defect — invisible from inside the unit.
"""

from __future__ import annotations

import json

import pytest
from mcp.types import TextContent

from tools.selectagents import SelectAgentsTool


@pytest.fixture()
def tool():
    return SelectAgentsTool()


def test_the_tool_answers_to_its_name(tool):
    assert tool.name == "selectagents"


def test_the_description_says_what_it_computes(tool):
    """An MCP client shows this to the model that has to decide whether to call it.

    Asserted on substance rather than exact wording: the caller needs to learn
    that it returns a plan of agents and that the decision comes from data.
    """
    description = tool.get_description().lower()

    assert "plan" in description
    assert "delegat" in description


def test_it_declares_that_it_needs_no_model(tool):
    """The whole point of the layer: the decision is computed, not asked for.

    A tool that reports `requires_model()` as True is routed through model
    resolution before dispatch, so getting this wrong would make the selection
    layer depend on the very judgement it exists to replace.
    """
    assert tool.requires_model() is False


def test_it_publishes_an_input_schema_a_client_can_read(tool):
    """Advertised without a schema, a tool is discoverable and uncallable."""
    schema = tool.get_input_schema()

    assert schema["type"] == "object"
    assert "properties" in schema


@pytest.mark.asyncio
async def test_calling_it_returns_a_constant_rather_than_an_error(tool):
    """#99's own criterion, and the one that proves dispatch works.

    The payload is deliberately uninteresting — what is being pinned is that the
    call completes and reports success, not what it says.
    """
    result = await tool.execute({})

    assert len(result) == 1
    assert isinstance(result[0], TextContent)

    response = json.loads(result[0].text)
    assert response["status"] == "success"
    assert response["metadata"]["tool_name"] == "selectagents"


@pytest.mark.asyncio
async def test_the_stub_says_it_is_a_stub(tool):
    """A placeholder that reads like a real answer is worse than an error.

    Until #104 there is no ranking behind this. A caller that received a
    confident-looking plan would act on one that was never computed, and #96's
    whole argument is that a delegation must not rest on something nobody
    measured.
    """
    response = json.loads((await tool.execute({}))[0].text)

    assert response["metadata"]["stub"] is True
    assert "not implemented" in response["content"].lower()


def test_the_server_advertises_it(monkeypatch):
    """Registered, not merely importable.

    Reads `server.TOOLS` — the same dictionary `handle_list_tools` iterates — so
    a tool exported from `tools/__init__.py` and never wired in fails here.
    """
    import server

    assert "selectagents" in server.TOOLS
    assert server.TOOLS["selectagents"].name == "selectagents"


@pytest.mark.asyncio
async def test_it_is_dispatched_through_the_server_by_name():
    """The end-to-end leg #99 asks for, at the server's own dispatch seam.

    `handle_call_tool` is what an MCP client actually reaches. Going through it
    covers the wiring a direct `SelectAgentsTool().execute()` cannot: the name
    lookup, the disabled-tools filter, and the server's argument handling.
    """
    from server import handle_call_tool

    result = await handle_call_tool("selectagents", {})

    assert len(result) == 1
    assert json.loads(result[0].text)["status"] == "success"
