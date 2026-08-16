"""Five ranked routes, priced against each other, and a count of what was cut (#110).

**Nothing qualifying is culled.** #96 is explicit: a candidate another beats on
every axis in play is still the only route when the winner's lane is down, and
availability is not one of the axes being compared. So the set is bounded **by
rank** rather than filtered on merit, and whatever falls outside the bound is
counted — "a truncated list read as the whole list is the failure this criterion
exists to prevent".

**The alternatives follow the rule that picked the winner, not the price list.**
Once #109's budget is in force those two orders diverge: the winner is the best
that fits, while cost order still leads with the cheapest. Alternatives ranked by
cost would then be a fallback list for a decision nobody made — the caller falls
back from a capability choice onto a frugality choice without being told the
basis changed underneath it.

**The delta is signed.** Falling back can be cheaper, and reporting the magnitude
alone would tell a caller a saving and a surcharge apart only by luck.
"""

from __future__ import annotations

from tools.selection import ALTERNATIVE_LIMIT, Candidate, choose, load_candidates, rank, slate


def _candidate(model: str, *, score: float, in_price: float, out_price: float, out_tokens: int = 1_000):
    return Candidate(
        model=model,
        effort="max",
        context_window=1_000_000,
        axes={"coding": score},
        input_price_per_mtok=in_price,
        output_price_per_mtok=out_price,
        output_tokens_per_task=out_tokens,
    )


READ = 10_000


def _field(count: int) -> list[Candidate]:
    """`count` candidates, each dearer and better than the last."""
    return [_candidate(f"m{i}", score=50.0 + i, in_price=float(i + 1), out_price=float(i + 1)) for i in range(count)]


def _slate_of(candidates: list[Candidate], *, budget_usd: float | None = None, limit: int = ALTERNATIVE_LIMIT):
    ordered = rank(
        candidates, kind_of_work="implementation", read_volume_tokens=READ, output_ceiling_tokens=0, item_count=1
    ).ordered
    choice = choose(ordered, axis="coding", read_volume_tokens=READ, budget_usd=budget_usd)
    return choice, slate(choice, read_volume_tokens=READ, limit=limit)


def test_the_bound_is_five_and_the_overflow_is_counted():
    """Eight qualify, five are offered, and the caller is told three were cut.

    The count is the criterion. Without it a caller reading five entries has no
    way to tell a field of exactly five from a field of eighty, and would rule
    out routes it was never shown.
    """
    _, result = _slate_of(_field(8))

    assert len(result.entries) == 5
    assert result.dropped == 3


def test_a_field_smaller_than_the_bound_returns_what_there_is_and_drops_nothing():
    """ "Fewer when fewer qualify" — and `dropped` must be 0, not merely small.

    A non-zero drop count on a field nothing was cut from would send a caller
    looking for routes that do not exist.
    """
    _, result = _slate_of(_field(3))

    assert len(result.entries) == 3
    assert result.dropped == 0


def test_the_winner_leads_the_slate():
    """The routes are the winner and its runners-up, in that order.

    A list of alternatives that omits the chosen route makes the deltas
    unanchored: "cost delta to the one above it" has nothing above the first
    entry to be a delta to.
    """
    choice, result = _slate_of(_field(8))

    assert result.entries[0].candidate.model == choice.winner.model
    assert result.entries[0].cost_delta_usd is None


def test_each_route_is_priced_against_the_one_above_it():
    """The delta is to the PREDECESSOR, not to the winner.

    Both readings produce the same number for the second entry and diverge from
    the third onwards, so a test that stopped at the second would not tell them
    apart. #96 says "the cost delta to the one above it", which is what makes a
    chain of fallbacks individually priced rather than all measured from the top.
    """
    _, result = _slate_of(_field(8))

    for above, entry in zip(result.entries, result.entries[1:]):
        expected = entry.candidate.cost_per_task(READ) - above.candidate.cost_per_task(READ)
        assert entry.cost_delta_usd == round(expected, 6)


def test_a_candidate_beaten_on_every_axis_is_still_offered():
    """#110's own criterion, and the one a "sensible" cull would break.

    `dominated` is dearer AND lower-scoring than every other candidate — beaten
    on both axes in play, which is exactly the candidate a merit filter drops.
    It stays, because when the lanes above it are down it is the only route left,
    and availability is not one of the axes being compared.
    """
    field = _field(3)
    dominated = _candidate("dominated", score=10.0, in_price=99.0, out_price=99.0)

    _, result = _slate_of(field + [dominated])

    assert "dominated" in [entry.candidate.model for entry in result.entries]


def test_the_slate_follows_the_budget_rule_rather_than_the_price_list():
    """Under a budget the winner is not the cheapest, and the routes must agree.

    Ranked by cost, the slate would lead with the cheapest candidate while the
    plan named a different one — a fallback list for a decision nobody made. The
    caller would drop from a capability choice to a frugality choice without
    being told the basis had changed.
    """
    field = _field(6)
    choice, result = _slate_of(field, budget_usd=1.0)

    models = [entry.candidate.model for entry in result.entries]

    assert models[0] == choice.winner.model
    assert choice.rule == "best_within_budget"
    # Descending on the axis, which is the budget rule's own preference order —
    # and the reverse of the cost order the unbudgeted slate would use.
    scores = [entry.candidate.score_on("coding") for entry in result.entries]
    assert scores == sorted(scores, reverse=True)


def test_a_candidate_priced_out_is_not_offered_as_a_route():
    """Excluded is excluded; a fallback the budget forbids is not a fallback.

    "Nothing qualifying is culled" is about merit, not about the caller's own
    stated constraints — the same distinction #108 draws for the context window.
    A route the budget rules out would be one the caller cannot take.
    """
    affordable = _candidate("affordable", score=60.0, in_price=0.1, out_price=0.1)
    unaffordable = _candidate("unaffordable", score=99.0, in_price=500.0, out_price=500.0)

    choice, result = _slate_of([affordable, unaffordable], budget_usd=0.01)

    assert [entry.candidate.model for entry in result.entries] == ["affordable"]
    assert choice.excluded_by_budget == ["unaffordable"]


def test_falling_back_can_be_cheaper_and_the_delta_says_so():
    """A signed delta, because a saving and a surcharge are different news.

    Under a budget the slate descends the axis, so a later route is often the
    cheaper one. Reporting a magnitude would leave a caller unable to tell "this
    fallback saves you money" from "this fallback costs you more".
    """
    dear_and_good = _candidate("dear-and-good", score=90.0, in_price=5.0, out_price=5.0)
    cheap_and_weak = _candidate("cheap-and-weak", score=50.0, in_price=0.1, out_price=0.1)

    _, result = _slate_of([dear_and_good, cheap_and_weak], budget_usd=1.0)

    assert result.entries[0].candidate.model == "dear-and-good"
    assert result.entries[1].cost_delta_usd < 0


def test_the_committed_dataset_produces_a_slate_rather_than_only_invented_ones():
    """The bound has to hold on the data the tool actually ships with.

    The fixture carries five candidates and one is unmeasured on the coding axis,
    so four qualify: under the bound, nothing dropped. Asserted against the
    ranking rather than against the literal 4, so #102 replacing the dataset
    changes the expectation instead of breaking the test for the wrong reason.
    """
    ordered = rank(
        load_candidates(), kind_of_work="implementation", read_volume_tokens=READ, output_ceiling_tokens=0, item_count=1
    ).ordered
    choice = choose(ordered, axis="coding", read_volume_tokens=READ, budget_usd=None)
    result = slate(choice, read_volume_tokens=READ)

    assert len(result.entries) == min(len(ordered), ALTERNATIVE_LIMIT)
    assert result.dropped == max(0, len(ordered) - ALTERNATIVE_LIMIT)
    assert result.entries[0].candidate.model == choice.winner.model
