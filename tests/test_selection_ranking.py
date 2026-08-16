"""Ranking on cost per task, one axis, from a committed fixture (#104).

The arithmetic half of #96, tested by assertion because it is arithmetic. The
language half — mapping a described task onto an axis — is deliberately not here.

`rank()` returns a `Ranking` rather than a list as of #108: the survivors alone
were not enough, because a plan chosen from two candidates out of five must not
read like one chosen from five. These tests read `.ordered`; the exclusions are
covered in `test_selection_context_filter.py`.

**The case this slice exists for is the disagreement.** Price per token and cost
per task order the same candidates differently on real data, and a layer that
ranked by price would recommend the loser. Every other test in this file supports
that one.
"""

from __future__ import annotations

import json

import pytest

from tools.selection import AXIS_FOR_KIND, Candidate, DatasetError, axis_for, load_candidates, rank


def _candidate(model: str, *, axes: dict, in_price: float, out_price: float, out_tokens: int, window: int = 1_000_000):
    return Candidate(
        model=model,
        effort="max",
        context_window=window,
        axes=axes,
        input_price_per_mtok=in_price,
        output_price_per_mtok=out_price,
        output_tokens_per_task=out_tokens,
    )


def test_price_per_token_and_cost_per_task_disagree_and_cost_per_task_wins():
    """#104's whole reason for existing, as a single assertion.

    `cheap_per_token` is **2.5x cheaper per token** and still costs MORE per task,
    because it emits 2.5x the output to finish the same work. It also scores
    lower on the axis. A layer ranking on price recommends it; this one must not.

    Computed by hand at a 1,000-token read, so the figures can be checked without
    running anything:
      cheap: (1_000 * 0.4 + 30_000 * 1.6) / 1e6 = 0.0004 + 0.0480 = 0.0484
      dear:  (1_000 * 1.0 + 10_000 * 4.0) / 1e6 = 0.0010 + 0.0400 = 0.0410

    The first version of this docstring used different figures and asserted the
    same conclusion — and the test caught it: at those numbers the two output
    costs were identical and the input term decided, so the cheap model still won.
    A comment that computes the answer is worth exactly as much as the assertion
    that checks it.
    """
    cheap = _candidate("cheap-per-token", axes={"coding": 71.4}, in_price=0.4, out_price=1.6, out_tokens=30_000)
    dear = _candidate("dear-per-token", axes={"coding": 76.7}, in_price=1.0, out_price=4.0, out_tokens=10_000)

    # 2.5x cheaper on both input and output, and 3x more output emitted per task.
    assert cheap.price_per_token() < dear.price_per_token()

    # A small read: output volume dominates, and the cheap-per-token model loses.
    ordered = rank([cheap, dear], kind_of_work="implementation", read_volume_tokens=1_000).ordered

    assert ordered[0].model == "dear-per-token", (
        "ranked by price per token, not cost per task — the model that emits more "
        "output to finish the same work was recommended because its tokens are cheaper"
    )


def test_the_same_pair_flips_when_the_read_volume_dominates():
    """The disagreement is not a constant, and pretending it is would be a lie.

    On a large read the input term swamps the output term and the cheap-per-token
    model genuinely is cheaper per task. Pinned so nobody "fixes" the ranking into
    always preferring the terser model — the point is that the arithmetic decides,
    not a rule of thumb in either direction.
    """
    cheap = _candidate("cheap-per-token", axes={"coding": 71.4}, in_price=0.4, out_price=1.6, out_tokens=30_000)
    dear = _candidate("dear-per-token", axes={"coding": 76.7}, in_price=1.0, out_price=4.0, out_tokens=10_000)

    #   cheap: (200_000 * 0.4 + 48_000) / 1e6 = 0.128
    #   dear:  (200_000 * 1.0 + 40_000) / 1e6 = 0.240
    ordered = rank([cheap, dear], kind_of_work="implementation", read_volume_tokens=200_000).ordered

    assert ordered[0].model == "cheap-per-token"


def test_a_candidate_with_no_score_on_the_axis_is_excluded_not_zeroed():
    """A blank is *not published*, not a measurement of zero.

    Scoring it zero would rank it last on quality while its cheapness pulled it
    first on cost — and on this dataset the unmeasured candidates are exactly the
    cheap ones, so a zero-fill would systematically recommend the models nobody
    measured.
    """
    measured = _candidate("measured", axes={"coding": 60.0}, in_price=10.0, out_price=40.0, out_tokens=10_000)
    unmeasured = _candidate("unmeasured", axes={"index": 14.9}, in_price=0.05, out_price=0.2, out_tokens=30_000)

    ordered = rank([measured, unmeasured], kind_of_work="implementation", read_volume_tokens=40_000).ordered

    assert [c.model for c in ordered] == ["measured"]


def test_a_tie_on_cost_is_broken_by_the_axis_score():
    """Two candidates that cost the same are not interchangeable."""
    worse = _candidate("worse", axes={"coding": 50.0}, in_price=1.0, out_price=1.0, out_tokens=1_000)
    better = _candidate("better", axes={"coding": 70.0}, in_price=1.0, out_price=1.0, out_tokens=1_000)

    ordered = rank([worse, better], kind_of_work="implementation", read_volume_tokens=10_000).ordered

    assert [c.model for c in ordered] == ["better", "worse"]


@pytest.mark.parametrize("kind", sorted(AXIS_FOR_KIND))
def test_every_kind_of_work_in_the_contract_has_an_axis(kind):
    """The contract's closed list and this map must not drift apart.

    A kind of work with no axis is a request the tool accepts and cannot rank —
    an error at ranking time for input the edge already blessed.
    """
    from tools.selectagents import KIND_OF_WORK

    assert set(AXIS_FOR_KIND) == set(KIND_OF_WORK)
    assert axis_for(kind)


def test_the_axis_comes_from_the_kind_of_work_and_not_from_the_caller():
    """Different declared work ranks on different axes, from the same candidates.

    #96: "a caller able to set the weights could set cost to nothing and turn the
    layer into a rubber stamp". The axis is the same lever one step earlier — a
    caller that picked it could pick the one its preferred model leads.
    """
    coding_only = _candidate("coder", axes={"coding": 80.0}, in_price=9.0, out_price=9.0, out_tokens=10_000)
    agentic_only = _candidate("agent", axes={"agentic": 80.0}, in_price=1.0, out_price=1.0, out_tokens=10_000)
    pool = [coding_only, agentic_only]

    assert [c.model for c in rank(pool, kind_of_work="implementation", read_volume_tokens=1_000).ordered] == ["coder"]
    assert [c.model for c in rank(pool, kind_of_work="research", read_volume_tokens=1_000).ordered] == ["agent"]


def test_the_committed_dataset_loads_and_carries_what_the_ranking_needs():
    """The fixture is real input, not a shape the tests invented for themselves."""
    candidates = load_candidates()

    assert len(candidates) >= 4
    for candidate in candidates:
        assert candidate.output_tokens_per_task > 0
        assert candidate.context_window > 0


def test_the_dataset_declares_which_of_its_numbers_are_measured():
    """Half this fixture is constructed and it has to say so.

    The axis scores come from a published table; the per-token prices and output
    volumes do not exist in that table and were built to make the disagreement
    expressible. A fixture that presented both as measured would put invented
    numbers into a decision that #96 exists to base on measured ones — and #102
    replaces it wholesale, so the provenance must survive until then.
    """
    raw = json.loads(
        (__import__("tools.selection", fromlist=["DATASET_PATH"]).DATASET_PATH).read_text(encoding="utf-8")
    )

    provenance = raw["_provenance"]
    assert "CONSTRUCTED" in provenance["prices_and_output_volume"]
    assert "NOT PUBLISHED" in provenance["axis_scores"]


def test_a_missing_dataset_is_an_error_rather_than_an_empty_ranking(tmp_path):
    """With no prices there is nothing to compute, and #96 refuses at once.

    An empty list would make every scope return "no candidate", which reads as a
    scope nothing can serve rather than as a layer that cannot answer.
    """
    with pytest.raises(DatasetError):
        load_candidates(tmp_path / "absent.json")


def test_a_dataset_with_no_candidates_is_an_error(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"candidates": []}), encoding="utf-8")

    with pytest.raises(DatasetError):
        load_candidates(path)
