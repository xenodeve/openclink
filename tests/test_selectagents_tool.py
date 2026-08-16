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

# A complete scope. These tests predate #101 and originally called with `{}`,
# which the contract now correctly refuses — the skeleton accepted anything
# because there was nothing to accept. Kept as one constant so #101's contract
# and #99's reachability checks cannot drift apart.
SCOPE = {
    "kind_of_work": "implementation",
    "item_count": 3,
    "read_volume_tokens": 10_000,
    "already_in_context": False,
    "output_ceiling_tokens": 4_000,
    "verification": "automated_tests",
    "description": "A small, well-specified change.",
}


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
    result = await tool.execute(dict(SCOPE))

    assert len(result) == 1
    assert isinstance(result[0], TextContent)

    response = json.loads(result[0].text)
    assert response["status"] == "success"
    assert response["metadata"]["tool_name"] == "selectagents"


@pytest.mark.asyncio
async def test_the_response_declares_that_it_is_incomplete(tool):
    """A partial answer that reads like a finished one is worse than an error.

    This test pinned "stub" until #104; now there IS a plan, computed by real
    arithmetic, and the honesty requirement gets harder rather than easier. A
    caller can no longer tell from the shape of the response that six of the
    layer's promises are unbuilt, so the response has to say so.
    """
    response = json.loads((await tool.execute(dict(SCOPE)))[0].text)

    assert response["metadata"]["partial"] is True
    assert "incomplete" in response["content"].lower()


@pytest.mark.asyncio
async def test_the_response_names_what_is_still_missing(tool):
    """ "Incomplete" without a list is a disclaimer; with one it is information.

    Each of these is a promise #96 makes that a caller might otherwise assume the
    plan already honours — alternatives it does not return, a count it does not
    compute, a partition it does not make.
    """
    content = json.loads((await tool.execute(dict(SCOPE)))[0].text)["content"]

    for unbuilt in ("#102", "#111", "#113"):
        assert unbuilt in content, f"the response does not disclose that {unbuilt} is unbuilt"


@pytest.mark.asyncio
async def test_the_response_stops_naming_a_slice_once_it_ships(tool):
    """The list must SHRINK, and nothing was checking that it did.

    It went one merge stale: #108 shipped the context-window filter and the
    disclosure still called it unbuilt. That is the same defect as an overstated
    capability, pointing the other way — a caller reads "the context window is not
    applied" and splits a scope by hand that the layer had already filtered for.

    The half above only ever failed when the list was too SHORT. This half fails
    when it is too long, which is the direction a list nobody prunes actually
    drifts.
    """
    content = json.loads((await tool.execute(dict(SCOPE)))[0].text)["content"]

    for shipped in ("#98", "#99", "#101", "#104", "#108", "#109", "#110"):
        assert shipped not in content, f"{shipped} has shipped, but the response still calls it unbuilt"


@pytest.mark.asyncio
async def test_a_plan_names_one_model_and_effort_from_the_dataset(tool):
    """#104's first criterion, at the tool seam rather than the pure one."""
    response = json.loads((await tool.execute(dict(SCOPE)))[0].text)
    agents = response["metadata"]["plan"]["agents"]

    assert len(agents) == 1
    assert agents[0]["model"]
    assert agents[0]["effort"]
    assert agents[0]["cost_per_task"] > 0


@pytest.mark.asyncio
async def test_the_plan_carries_the_criteria_it_rested_on(tool):
    """#96: the criteria come back with the plan, so a caller can disagree with a reason.

    `candidates_ranked` next to `candidates_considered` is the part that matters
    most — it says how much of the dataset was actually eligible, so a plan chosen
    from two of five candidates does not read like one chosen from five.

    That key was `candidates_scored_on_axis` until #108 added a second exclusion
    reason, at which point the name described one of the two filters and counted
    both. Renamed rather than left: a count whose name says "on axis" while it
    also excludes for context window is a label that will be believed.
    """
    response = json.loads((await tool.execute(dict(SCOPE)))[0].text)
    criteria = response["metadata"]["plan"]["criteria"]

    assert criteria["axis"] == "coding"  # SCOPE declares implementation
    assert criteria["ranked_on"] == "cost_per_task"
    assert criteria["axis_score"] is not None
    assert criteria["candidates_ranked"] <= criteria["candidates_considered"]


@pytest.mark.asyncio
async def test_a_budget_reaches_the_ranking_and_says_which_rule_it_put_in_play(tool):
    """#109 at the tool seam: the criteria must state the budget in force.

    Both fields, because the winner alone cannot say which rule ran — `null` with
    `cheapest_qualifying` is a caller that named no ceiling, and a figure with
    `best_within_budget` is one that did and got the best seat that fit.
    """
    unbudgeted = json.loads((await tool.execute(dict(SCOPE)))[0].text)["metadata"]["plan"]["criteria"]

    assert unbudgeted["budget_usd"] is None
    assert unbudgeted["selection_rule"] == "cheapest_qualifying"

    # 0.12 clears the whole committed fixture at this read volume, so the best on
    # the coding axis is affordable and the cheapest is not the winner.
    budgeted_scope = dict(SCOPE) | {"budget_usd": 0.12}
    budgeted = json.loads((await tool.execute(budgeted_scope))[0].text)["metadata"]["plan"]["criteria"]

    assert budgeted["budget_usd"] == 0.12
    assert budgeted["selection_rule"] == "best_within_budget"
    assert budgeted["axis_score"] > unbudgeted["axis_score"]


@pytest.mark.asyncio
async def test_a_budget_nothing_fits_refuses_and_says_what_it_would_take(tool):
    """Refused rather than exceeded, and actionable rather than merely negative.

    A refusal that does not name the cheapest qualifying figure leaves the caller
    guessing at the next budget, which turns one refusal into several.

    The expected model and price are derived from the pure layer rather than
    written in, so #102 replacing the dataset cannot leave this test asserting a
    price nothing charges any more. The arithmetic itself is pinned in
    `test_selection_ranking.py`; what this checks is that the tool surfaces it.

    A first version also asserted the phrase "over budget" was ABSENT. That
    pinned wording, not behaviour — and it was wrong wording at that, since the
    refusal properly says it declined "rather than a plan returned over budget".
    """
    from tools.selection import load_candidates, rank

    cheapest = rank(
        load_candidates(),
        kind_of_work=SCOPE["kind_of_work"],
        read_volume_tokens=SCOPE["read_volume_tokens"],
        output_ceiling_tokens=SCOPE["output_ceiling_tokens"],
    ).ordered[0]

    scope = dict(SCOPE) | {"budget_usd": 0.000001}
    response = json.loads((await tool.execute(scope))[0].text)

    assert response["status"] == "error"
    assert cheapest.model in response["content"]
    assert f"${cheapest.cost_per_task(SCOPE['read_volume_tokens']):.4f}" in response["content"]


@pytest.mark.asyncio
async def test_a_budget_of_zero_is_refused_as_a_contract_violation(tool):
    """Absent and zero are different answers, and only one of them is frugality.

    Omitting the budget means "choose on cost"; zero means "spend nothing", which
    nothing can satisfy. Accepted, it would reach the ranking and come back as an
    over-budget refusal — a plausible typo reported as an empty field of
    candidates rather than as the bad input it is.
    """
    response = json.loads((await tool.execute(dict(SCOPE) | {"budget_usd": 0}))[0].text)

    assert response["status"] == "error"
    assert "budget_usd" in response["content"]
    assert "greater than 0" in response["content"]


@pytest.mark.asyncio
async def test_the_alternatives_carry_the_winners_fields_and_the_dropped_count(tool):
    """#110 at the tool seam: substituting must be decided on the same evidence.

    Asserted as "the winner's key set equals every alternative's key set" rather
    than by listing the keys, so a field added to one and forgotten on the other
    fails here — which is the drift the shared builder exists to prevent, checked
    rather than trusted.
    """
    plan = json.loads((await tool.execute(dict(SCOPE)))[0].text)["metadata"]["plan"]
    alternatives = plan["alternatives"]

    assert alternatives, "no routes were offered"
    assert alternatives[0]["model"] == plan["agents"][0]["model"], "the winner does not lead the slate"
    assert alternatives[0]["cost_delta_usd"] is None, "nothing is above the winner to be a delta to"

    shape = set(alternatives[0])
    for route in alternatives[1:]:
        assert set(route) == shape, "an alternative does not carry the same fields as the winner"
        assert route["cost_delta_usd"] is not None

    # Reported even when it is zero: a caller reading five routes cannot tell a
    # field of five from a field of eighty without it.
    assert "alternatives_dropped" in plan
    assert plan["alternatives_dropped"] >= 0


@pytest.mark.asyncio
async def test_the_server_advertises_it():
    """Registered, not merely importable — asserted on what a client is actually told.

    A first version read `server.TOOLS` and its docstring claimed that was "the
    same dictionary `handle_list_tools` iterates". True, and not the same claim:
    the handler filters and builds `Tool` objects, so a tool dropped there would
    have left that test green while no client could see it. The registration is
    the thing being pinned, so the assertion belongs on the advertised list.
    """
    from server import handle_list_tools

    advertised = {tool.name: tool for tool in await handle_list_tools()}

    assert "selectagents" in advertised
    # An advertised tool with no schema is discoverable and uncallable.
    assert advertised["selectagents"].inputSchema
    assert advertised["selectagents"].description


@pytest.mark.asyncio
async def test_it_is_dispatched_through_the_server_by_name():
    """The end-to-end leg #99 asks for, at the server's own dispatch seam.

    `handle_call_tool` is what an MCP client actually reaches, so this covers the
    name lookup a direct `SelectAgentsTool().execute()` cannot.

    It covers no more than that, and an earlier version of this docstring claimed
    it did. With `requires_model()` False the handler dispatches immediately, so
    model resolution is never reached; and the disabled-tools filter runs once at
    import rather than per call. Claiming coverage a test does not have is how a
    gap survives a green suite.
    """
    from server import handle_call_tool

    result = await handle_call_tool("selectagents", dict(SCOPE))

    assert len(result) == 1
    assert json.loads(result[0].text)["status"] == "success"
