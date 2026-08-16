"""Context window is a hard filter, applied before anything is priced (#108).

A candidate whose window cannot hold the share it would be given is **removed**,
not ranked lower. #96 is explicit that context is "a hard filter rather than a
weight", and the difference is not pedantry: a weight lets a cheap-enough model
outrank the constraint and be handed work it will silently truncate.

**Filtering before pricing is the load-bearing order.** #110 returns the ranked
alternatives from the same list; a candidate excluded only at the end would
reappear there as a fallback route, which is where a truncating model would
actually get used — after the first choice's lane went down and nobody looked
again.

**And the exclusion has to be visible.** A plan chosen from two survivors of five
must not read like a plan chosen from five.
"""

from __future__ import annotations

import pytest

from tools.selection import Candidate, rank, required_window


def _candidate(model: str, *, window: int, axes: dict, in_price: float, out_price: float, out_tokens: int):
    return Candidate(
        model=model,
        effort="max",
        context_window=window,
        axes=axes,
        input_price_per_mtok=in_price,
        output_price_per_mtok=out_price,
        output_tokens_per_task=out_tokens,
    )


def test_the_required_window_is_what_is_read_plus_what_is_written():
    """A model must hold the input AND its own answer.

    Sizing on the read alone is the mistake that looks conservative and is not:
    a candidate sized exactly to the input has nowhere to put the output, and the
    truncation lands in the result rather than in an error.
    """
    assert required_window(read_volume_tokens=40_000, output_ceiling_tokens=8_000) == 48_000


def test_a_candidate_that_cannot_hold_its_share_disappears_entirely():
    small = _candidate(
        "small-window", window=32_000, axes={"coding": 80.0}, in_price=0.1, out_price=0.1, out_tokens=1_000
    )
    big = _candidate(
        "big-window", window=1_000_000, axes={"coding": 60.0}, in_price=9.0, out_price=9.0, out_tokens=1_000
    )

    result = rank(
        [small, big],
        kind_of_work="implementation",
        read_volume_tokens=100_000,
        output_ceiling_tokens=8_000,
    )

    assert [c.model for c in result.ordered] == ["big-window"]


def test_the_cheapest_candidate_losing_to_the_filter_is_the_case_that_matters():
    """#108's own criterion, and the one a weight would get wrong.

    `small-window` is cheaper on every axis of price and scores higher. Ranked
    with context as a weight it wins comfortably; filtered, it is not a candidate
    at all — it cannot hold the work.
    """
    small = _candidate(
        "small-window", window=32_000, axes={"coding": 90.0}, in_price=0.01, out_price=0.01, out_tokens=500
    )
    big = _candidate(
        "big-window", window=1_000_000, axes={"coding": 50.0}, in_price=20.0, out_price=80.0, out_tokens=20_000
    )

    result = rank(
        [small, big],
        kind_of_work="implementation",
        read_volume_tokens=200_000,
        output_ceiling_tokens=8_000,
    )

    assert small.cost_per_task(200_000) < big.cost_per_task(200_000)
    assert [c.model for c in result.ordered] == ["big-window"]


def test_a_window_that_holds_the_read_but_not_the_answer_is_still_too_small():
    """The output half of the requirement, pinned by who survives — not by arithmetic.

    `required_window` has its own unit test and it is **not enough**: drop the
    ceiling term from that function and every other test in this file still
    passes, because each candidate here is either comfortably over the
    requirement or far under it. The mutation reddened one hand-checked identity
    and no behaviour at all — which is what a coverage gap looks like from the
    inside.

    This is the case that sits in the gap. 44_000 clears the 40_000 read and
    fails the 48_000 the answer also needs, and `snug` is the cheaper of the two,
    so a requirement sized on the read alone hands it the work.
    """
    snug = _candidate("snug", window=44_000, axes={"coding": 80.0}, in_price=0.1, out_price=0.1, out_tokens=1_000)
    roomy = _candidate("roomy", window=1_000_000, axes={"coding": 60.0}, in_price=9.0, out_price=9.0, out_tokens=1_000)

    result = rank(
        [snug, roomy],
        kind_of_work="implementation",
        read_volume_tokens=40_000,
        output_ceiling_tokens=8_000,
    )

    assert snug.cost_per_task(40_000) < roomy.cost_per_task(40_000)
    assert [c.model for c in result.ordered] == ["roomy"]
    assert result.excluded_by_window == ["snug"]


def test_the_output_ceiling_cannot_be_left_unsaid():
    """A hard filter must not have a fail-open default.

    `output_ceiling_tokens` defaulted to 0, which sized the requirement on the
    read alone — the exact mistake this module's docstring warns about, reachable
    by omission. A fail-open default on a safety filter lets MORE candidates
    through, so the failure is silent: nothing errors, a truncating model is
    simply eligible.

    Pinned as a `TypeError` rather than trusted to review, because the default
    that has to stay absent is one keyword away from coming back.
    """
    candidate = _candidate("any", window=1_000_000, axes={"coding": 60.0}, in_price=1.0, out_price=1.0, out_tokens=1)

    with pytest.raises(TypeError):
        rank([candidate], kind_of_work="implementation", read_volume_tokens=1_000)


def test_a_candidate_sized_exactly_to_the_requirement_still_fits():
    """The boundary, pinned in the direction that would otherwise drift.

    `>=` versus `>` here decides whether a model sized precisely for the job is
    used or discarded, and an off-by-one that discards it is invisible: the plan
    simply names a dearer model and nothing says why.
    """
    exact = _candidate("exact", window=48_000, axes={"coding": 70.0}, in_price=1.0, out_price=1.0, out_tokens=1_000)

    result = rank([exact], kind_of_work="implementation", read_volume_tokens=40_000, output_ceiling_tokens=8_000)

    assert [c.model for c in result.ordered] == ["exact"]


def test_the_exclusions_are_reported_rather_than_silent():
    """A plan chosen from two of five must not read like one chosen from five.

    Both reasons are counted separately because they mean different things to a
    caller: "your scope is too large for most of the field" is actionable — split
    it — while "nobody measured these on your axis" is not.
    """
    small = _candidate("small", window=32_000, axes={"coding": 80.0}, in_price=1.0, out_price=1.0, out_tokens=1_000)
    unmeasured = _candidate(
        "unmeasured", window=1_000_000, axes={"index": 40.0}, in_price=1.0, out_price=1.0, out_tokens=1_000
    )
    usable = _candidate(
        "usable", window=1_000_000, axes={"coding": 60.0}, in_price=1.0, out_price=1.0, out_tokens=1_000
    )

    result = rank(
        [small, unmeasured, usable],
        kind_of_work="implementation",
        read_volume_tokens=100_000,
        output_ceiling_tokens=8_000,
    )

    assert [c.model for c in result.ordered] == ["usable"]
    assert result.excluded_by_window == ["small"]
    assert result.excluded_by_axis == ["unmeasured"]


def test_the_window_filter_runs_before_the_axis_filter_is_not_assumed():
    """Order between the two exclusions must not change who survives.

    A candidate failing both is reported once, under whichever reason is checked
    first — but it must never survive because the two filters disagreed about
    whose job it was.
    """
    doomed = _candidate("doomed", window=1_000, axes={"index": 10.0}, in_price=0.01, out_price=0.01, out_tokens=100)
    usable = _candidate(
        "usable", window=1_000_000, axes={"coding": 60.0}, in_price=1.0, out_price=1.0, out_tokens=1_000
    )

    result = rank(
        [doomed, usable],
        kind_of_work="implementation",
        read_volume_tokens=100_000,
        output_ceiling_tokens=8_000,
    )

    assert [c.model for c in result.ordered] == ["usable"]
    assert "doomed" in result.excluded_by_window + result.excluded_by_axis


def test_nothing_surviving_the_filter_is_distinguishable_from_nothing_measured():
    """Two empty results that mean different things must not look alike.

    "Your scope is bigger than every context window we know about" tells a caller
    to split the work. "Nobody has measured any of these on your axis" tells them
    nothing of the sort. Collapsing both into an empty list throws away the only
    actionable half.
    """
    small = _candidate("small", window=1_000, axes={"coding": 80.0}, in_price=1.0, out_price=1.0, out_tokens=100)

    result = rank([small], kind_of_work="implementation", read_volume_tokens=100_000, output_ceiling_tokens=8_000)

    assert result.ordered == []
    assert result.excluded_by_window == ["small"]
    assert result.excluded_by_axis == []


@pytest.mark.asyncio
async def test_the_tool_reports_the_exclusions_in_its_criteria():
    """Visible to the caller, not only inside the pure layer."""
    import json

    from tools.selectagents import SelectAgentsTool

    scope = {
        "kind_of_work": "implementation",
        "item_count": 1,
        # Larger than the smallest window in the committed fixture, so at least
        # one candidate is genuinely excluded rather than the assertion passing
        # against a zero that means "nothing was filtered".
        "read_volume_tokens": 200_000,
        "already_in_context": False,
        "output_ceiling_tokens": 8_000,
        "verification": "automated_tests",
        "description": "A large read.",
    }

    response = json.loads((await SelectAgentsTool().execute(scope))[0].text)
    criteria = response["metadata"]["plan"]["criteria"]

    assert criteria["excluded_by_context_window"], "no candidate was reported as excluded by the window"
    assert "excluded_by_axis" in criteria
