"""A plan has an identity, and it is on disk before anyone is told (#103).

**The order is the criterion, and #103 says "asserted, not assumed".** An
identity handed to a caller that does not yet exist on disk is one an external
gate cannot validate — and the gate in the paired repository is the whole reason
the identity exists. So the ordering is checked by recording when each step
happens, not by looking at the store afterwards and finding the record there:
after the call, both orders look identical.

That distinction is not theoretical here. #98's concurrency test passed 3 runs
out of 3 against a fully non-atomic implementation, because it inspected the
store only after the writers had finished. Same shape, same slice family.
"""

from __future__ import annotations

import json

import pytest

from tools import plan_record
from tools.selectagents import SelectAgentsTool
from utils.record_store import RecordStore

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
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLINK_STORE_DIR", str(tmp_path / "store"))
    return tmp_path / "store"


def test_an_identity_is_acceptable_to_the_store_without_transformation():
    """The store refuses anything outside `[a-z0-9][a-z0-9._-]*`, and lowercase only.

    Generated identities must satisfy that as generated. An identity the caller
    receives but the store cannot key on is one that fails at write time, in the
    slice that has to happen before the response.
    """
    identity = plan_record.new_identity()

    assert RecordStore("/tmp/x").path_for(identity).name == f"{identity}.json"


def test_two_plans_never_share_an_identity():
    """Two identical scopes are two separate authorisations.

    Deriving the identity from the scope would let one plan's identity authorise
    a different plan's run — the identity ties a spawn to the decision that
    permitted it, not to the shape of the request.
    """
    assert plan_record.new_identity() != plan_record.new_identity()


def test_the_provenance_fingerprints_the_bytes_the_ranking_actually_read(tmp_path):
    """A fingerprint that does not change with the content cannot reproduce anything."""
    first = tmp_path / "a.json"
    first.write_text('{"candidates": []}', encoding="utf-8")
    second = tmp_path / "b.json"
    second.write_text('{"candidates": [1]}', encoding="utf-8")

    assert (
        plan_record.dataset_provenance(first)["fingerprint_sha256"]
        != plan_record.dataset_provenance(second)["fingerprint_sha256"]
    )
    # Named for what it is. When #102 starts fetching, `fetched_at` keeps its
    # name, and a file mtime silently becoming a claim about a network call is
    # exactly the drift this field guards against.
    assert plan_record.dataset_provenance(first)["source"] == "committed_fixture"


def test_an_unknown_identity_refuses_rather_than_resolving_to_an_empty_plan(store_dir):
    """#103's own criterion. `{}` and "never authorised" must not look alike.

    A gate reading a missing plan as an empty one cannot tell "this spawn was
    never authorised" from "this spawn was authorised to do nothing", and the two
    demand opposite responses.
    """
    with pytest.raises(plan_record.PlanNotFound) as refusal:
        plan_record.fetch("plan-deadbeef")

    assert "plan-deadbeef" in str(refusal.value)


def test_a_plan_survives_the_process_that_wrote_it(store_dir):
    """Retrievable after a restart — which is what "on disk" has to mean.

    Simulated by reading through a store object built after the write, with no
    shared state: an in-memory cache would satisfy a same-object read and lose
    everything the moment the server stopped, which is the failure #98 exists to
    remove.
    """
    identity = plan_record.new_identity()
    plan_record.save(identity, {"agents": [{"model": "m"}]}, {"source": "committed_fixture"})

    restored = json.loads((store_dir / f"{identity}.json").read_text(encoding="utf-8"))

    assert restored["plan"]["agents"][0]["model"] == "m"
    assert plan_record.fetch(identity)["identity"] == identity


@pytest.mark.asyncio
async def test_the_returned_plan_carries_an_identity_that_is_already_stored(store_dir):
    """The seam: what a caller receives must resolve, not merely look plausible."""
    response = json.loads((await SelectAgentsTool().execute(dict(SCOPE)))[0].text)
    identity = response["metadata"]["plan"]["identity"]

    assert identity
    stored = plan_record.fetch(identity)
    assert stored["plan"]["agents"] == response["metadata"]["plan"]["agents"]
    assert stored["dataset"]["fingerprint_sha256"]


@pytest.mark.asyncio
async def test_the_plan_is_written_before_the_response_is_built(store_dir, monkeypatch):
    """#103: "asserted, not assumed" — so the ORDER is recorded, not inferred.

    Looking in the store after the call proves only that both happened. Both
    orders leave the same directory behind, and the one that writes late has a
    window in which a spawn can quote an identity that resolves to nothing —
    which is precisely when a fast caller acts.

    So each step appends to a log as it runs, and the log is asserted. The
    response object is the marker for "the caller could have been told", because
    it is the first thing in this path that carries the identity outward.
    """
    from tools import selectagents

    order: list[str] = []

    real_save = selectagents.save
    real_output = selectagents.ToolOutput

    def spy_save(*args, **kwargs):
        order.append("save")
        return real_save(*args, **kwargs)

    def spy_output(*args, **kwargs):
        order.append("response")
        return real_output(*args, **kwargs)

    monkeypatch.setattr(selectagents, "save", spy_save)
    monkeypatch.setattr(selectagents, "ToolOutput", spy_output)

    await SelectAgentsTool().execute(dict(SCOPE))

    assert order == ["save", "response"], f"the plan was not stored before the response was built: {order}"


@pytest.mark.asyncio
async def test_a_store_that_cannot_be_written_refuses_rather_than_returning_a_plan(store_dir, monkeypatch):
    """An identity that was never stored must never reach a caller.

    If the write fails and the plan comes back anyway, the caller holds an
    identity the gate will reject — and the failure surfaces at spawn time, in a
    different process, with nothing pointing back here.
    """
    from tools import selectagents

    def refuse(*args, **kwargs):
        raise OSError("disk is full")

    monkeypatch.setattr(selectagents, "save", refuse)

    response = json.loads((await SelectAgentsTool().execute(dict(SCOPE)))[0].text)

    assert response["status"] == "error"
    assert "plan" not in response["metadata"] or not response["metadata"].get("plan")
