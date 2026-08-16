"""The input contract: fixed fields, a closed kind-of-work list, one description (#101).

The closed list is the substance. A caller that can invent its own category moves
the mapping from work to capability axis out of tested code and into an agent's
head — which is the thing #96 exists to stop. So the enumeration is declared in
the schema, checked at the edge, and a rejection names what was allowed.

**Why the description is a field at all.** No set of fixed fields describes what
the work *is* well enough to pick a capability axis, and #96 splits the problem
deliberately: mapping a described task onto an axis is a language task, ranking
candidates once the axis is fixed is arithmetic. The description feeds only the
first. It must never reach the second, or the arithmetic stops being
reproducible from the recorded fields.
"""

from __future__ import annotations

import json

import pytest

from tools.selectagents import KIND_OF_WORK, VERIFICATION, SelectAgentsTool

VALID = {
    "kind_of_work": "implementation",
    "item_count": 12,
    "read_volume_tokens": 40_000,
    "already_in_context": False,
    "output_ceiling_tokens": 8_000,
    "verification": "automated_tests",
    "description": "Port twelve call sites onto the new registry helper.",
}


@pytest.fixture()
def tool():
    return SelectAgentsTool()


def _response(tool, arguments):
    import asyncio

    result = asyncio.get_event_loop().run_until_complete(tool.execute(arguments))
    return json.loads(result[0].text)


@pytest.mark.asyncio
async def test_a_complete_scope_is_accepted(tool):
    response = json.loads((await tool.execute(dict(VALID)))[0].text)

    assert response["status"] == "success"


@pytest.mark.asyncio
async def test_the_accepted_scope_is_echoed_back(tool):
    """A caller must be able to see what the tool understood.

    #96 wants the criteria a plan rested on returned with it so the caller can
    disagree with a reason. The scope is the first half of that: a silently
    coerced field would otherwise be invisible until the plan looked wrong.
    """
    response = json.loads((await tool.execute(dict(VALID)))[0].text)

    assert response["metadata"]["scope"]["kind_of_work"] == "implementation"
    assert response["metadata"]["scope"]["item_count"] == 12
    assert response["metadata"]["scope"]["already_in_context"] is False


def test_the_schema_declares_every_fixed_field(tool):
    """Advertised incompletely, the contract is one a client cannot satisfy."""
    properties = tool.get_input_schema()["properties"]

    assert set(properties) == set(VALID)


def test_the_schema_publishes_the_closed_list_rather_than_describing_it(tool):
    """`enum` in the schema, not prose in a description.

    A client validates against the schema; a sentence saying "one of: ..." is
    read by nobody but a human. The closed list only closes anything if the
    machine can see it.
    """
    kind = tool.get_input_schema()["properties"]["kind_of_work"]

    assert set(kind["enum"]) == set(KIND_OF_WORK)
    assert set(tool.get_input_schema()["properties"]["verification"]["enum"]) == set(VERIFICATION)


def test_every_fixed_field_is_required(tool):
    """Nothing is defaulted, because every default is a decision made silently.

    An omitted `item_count` defaulting to 1 turns a fan-out into a single agent
    and nothing in the response says the caller never asked for that.
    """
    assert set(tool.get_input_schema()["required"]) == set(VALID)


@pytest.mark.asyncio
async def test_a_kind_of_work_outside_the_list_is_refused_and_the_list_is_named(tool):
    """Rejection has to be actionable, or the closed list is just an obstacle."""
    response = json.loads((await tool.execute({**VALID, "kind_of_work": "vibes"}))[0].text)

    assert response["status"] == "error"
    for allowed in KIND_OF_WORK:
        assert allowed in response["content"], f"the refusal does not name {allowed!r} as an option"


@pytest.mark.asyncio
async def test_an_unknown_verification_is_refused_and_named(tool):
    response = json.loads((await tool.execute({**VALID, "verification": "trust me"}))[0].text)

    assert response["status"] == "error"
    for allowed in VERIFICATION:
        assert allowed in response["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", sorted(VALID))
async def test_a_missing_field_is_refused_rather_than_defaulted(tool, missing):
    """Parametrized over every field, because one silently-defaulted field is enough.

    Checking a single omission would leave the other six untested, and the field
    that acquires a default later is exactly the one nobody wrote a case for.
    """
    arguments = {k: v for k, v in VALID.items() if k != missing}

    response = json.loads((await tool.execute(arguments))[0].text)

    assert response["status"] == "error"
    assert missing in response["content"]


@pytest.mark.asyncio
async def test_a_nonsensical_count_is_refused(tool):
    """Zero items is not a small job, it is a malformed request."""
    response = json.loads((await tool.execute({**VALID, "item_count": 0}))[0].text)

    assert response["status"] == "error"


@pytest.mark.asyncio
async def test_the_description_is_free_text(tool):
    """No shape is imposed on it — the caller describes the work in its own words."""
    response = json.loads(
        (await tool.execute({**VALID, "description": "แปลง call site สิบสองจุด — ไม่ใช่ภาษาอังกฤษ"}))[0].text
    )

    assert response["status"] == "success"


@pytest.mark.asyncio
async def test_the_description_reaches_nothing_that_is_computed(tool):
    """The rule #101 exists to hold, pinned before there is anything to compute.

    Two requests differing ONLY in the description must produce identical output
    apart from the echo of that description. Written now rather than with #104,
    because by then the coupling it forbids would already be in place and the
    test would be documenting it instead of preventing it.
    """
    first = json.loads((await tool.execute({**VALID, "description": "alpha"}))[0].text)
    second = json.loads((await tool.execute({**VALID, "description": "omega"}))[0].text)

    first["metadata"]["scope"].pop("description")
    second["metadata"]["scope"].pop("description")

    assert first == second
