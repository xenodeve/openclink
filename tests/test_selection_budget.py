"""An optional budget, and frugality as the default without one (#109).

**Two rules, and which one runs is the whole slice.** With no budget the layer
takes the cheapest qualifying candidate — #96 wants frugality to be the default
"rather than a setting the caller has to remember". With a budget, the caller has
already said what it is willing to spend, so the layer spends it: the best
candidate on the axis that fits.

**That reading is forced, not preferred.** #109 requires both "no budget yields
the cheapest qualifying candidate" and "a fixture case exists where supplying a
budget changes the winner". If a budget were only a ceiling, the cheapest
candidate would still win whenever anything fits and refuse when nothing does —
the winner could never change, and the second criterion would be unsatisfiable.
Only "cheapest by default, best affordable when told the ceiling" satisfies both.

**A budget that nothing fits refuses.** It does not quietly hand back the
cheapest and let the caller discover the overrun after the run — "says so rather
than exceeding it" is the criterion, and exceeding it silently is the failure the
whole layer exists to remove.
"""

from __future__ import annotations

import pytest

from tools.selection import Candidate, axis_for, choose, load_candidates, rank


def _candidate(model: str, *, score: float, in_price: float, out_price: float, out_tokens: int):
    return Candidate(
        model=model,
        effort="max",
        context_window=1_000_000,
        axes={"coding": score},
        input_price_per_mtok=in_price,
        output_price_per_mtok=out_price,
        output_tokens_per_task=out_tokens,
    )


def _ranked(candidates: list[Candidate], *, read: int) -> list[Candidate]:
    return rank(
        candidates, kind_of_work="implementation", read_volume_tokens=read, output_ceiling_tokens=0, item_count=1
    ).ordered


# cost per task at a 10,000-token read:
#   thrifty (0.1/0.1, 1_000 out) = (10_000*0.1 + 1_000*0.1) / 1e6 = 0.0011
#   middling(1.0/1.0, 1_000 out) = (10_000*1.0 + 1_000*1.0) / 1e6 = 0.0110
#   lavish  (5.0/5.0, 1_000 out) = (10_000*5.0 + 1_000*5.0) / 1e6 = 0.0550
THRIFTY = _candidate("thrifty", score=50.0, in_price=0.1, out_price=0.1, out_tokens=1_000)
MIDDLING = _candidate("middling", score=70.0, in_price=1.0, out_price=1.0, out_tokens=1_000)
LAVISH = _candidate("lavish", score=90.0, in_price=5.0, out_price=5.0, out_tokens=1_000)
READ = 10_000


def test_the_hand_computed_costs_are_what_the_code_computes():
    """The three figures every case below reasons from, checked once.

    Every other test in this file states a budget that sits between two of these
    costs. If the arithmetic in the comment above drifted from the arithmetic in
    `cost_per_task`, those budgets would land in the wrong gaps and the cases
    would still pass — asserting the wrong thing, quietly.
    """
    assert THRIFTY.cost_per_task(READ) == pytest.approx(0.0011)
    assert MIDDLING.cost_per_task(READ) == pytest.approx(0.0110)
    assert LAVISH.cost_per_task(READ) == pytest.approx(0.0550)


def test_no_budget_takes_the_cheapest_qualifying_candidate():
    """Frugality is the default, not a setting to remember (#96, story 8)."""
    result = choose(
        _ranked([THRIFTY, MIDDLING, LAVISH], read=READ), axis="coding", read_volume_tokens=READ, budget_usd=None
    )

    assert result.winner is not None
    assert result.winner.model == "thrifty"
    assert result.rule == "cheapest_qualifying"
    assert result.excluded_by_budget == []


def test_a_budget_changes_the_winner():
    """#109's own criterion, and the one that fixes what a budget MEANS.

    A budget of 0.02 admits `thrifty` and `middling` and prices out `lavish`. The
    winner becomes `middling` — the best on the axis that fits — where with no
    budget it was `thrifty`. A ceiling-only budget would leave `thrifty` winning
    and this assertion could never be made to hold.
    """
    ordered = _ranked([THRIFTY, MIDDLING, LAVISH], read=READ)

    unbudgeted = choose(ordered, axis="coding", read_volume_tokens=READ, budget_usd=None)
    budgeted = choose(ordered, axis="coding", read_volume_tokens=READ, budget_usd=0.02)

    assert unbudgeted.winner.model == "thrifty"
    assert budgeted.winner.model == "middling"
    assert budgeted.rule == "best_within_budget"


def test_a_budget_that_admits_everything_buys_the_best_on_the_axis():
    """The rule is "spend the ceiling", so a generous budget reaches the top.

    Pinned separately from the case above because an implementation that merely
    walked one rank up from the cheapest would pass that one and fail this.
    """
    result = choose(
        _ranked([THRIFTY, MIDDLING, LAVISH], read=READ), axis="coding", read_volume_tokens=READ, budget_usd=1.0
    )

    assert result.winner.model == "lavish"
    assert result.excluded_by_budget == []


def test_a_candidate_priced_out_is_named_rather_than_counted():
    """Same reason as #108's exclusions: "over budget" is actionable, a number is not.

    A caller told two candidates were priced out learns nothing it can act on. A
    caller told `lavish` was priced out can raise the budget deliberately.
    """
    result = choose(
        _ranked([THRIFTY, MIDDLING, LAVISH], read=READ), axis="coding", read_volume_tokens=READ, budget_usd=0.02
    )

    assert result.excluded_by_budget == ["lavish"]


def test_a_budget_nothing_fits_refuses_instead_of_overrunning():
    """ "Says so rather than exceeding it" — the criterion, and the failure mode.

    Returning the cheapest anyway would hand back a plan the caller's own stated
    ceiling forbids, and nothing in the response would say so until the bill
    arrived. `winner is None` is what the tool turns into a refusal.
    """
    result = choose(
        _ranked([THRIFTY, MIDDLING, LAVISH], read=READ), axis="coding", read_volume_tokens=READ, budget_usd=0.0001
    )

    assert result.winner is None
    assert result.excluded_by_budget == ["thrifty", "middling", "lavish"]


def test_a_budget_exactly_equal_to_a_cost_still_affords_it():
    """The boundary, in the direction that would otherwise drift silently.

    A caller that budgets exactly what a candidate costs has budgeted for it.
    `<` instead of `<=` here rejects the candidate the caller priced the run
    against, and the plan simply names a cheaper one without saying why.
    """
    result = choose(_ranked([THRIFTY, MIDDLING], read=READ), axis="coding", read_volume_tokens=READ, budget_usd=0.0110)

    assert result.winner.model == "middling"


def test_a_tie_on_the_axis_within_budget_goes_to_the_cheaper():
    """Cost is always weighted, so it decides whatever the axis leaves open (#96).

    Two candidates equally good on the axis are not interchangeable once one is
    dearer, and "either" is the answer that makes the layer non-deterministic.
    """
    frugal_twin = _candidate("frugal-twin", score=70.0, in_price=0.1, out_price=0.1, out_tokens=1_000)
    result = choose(_ranked([MIDDLING, frugal_twin], read=READ), axis="coding", read_volume_tokens=READ, budget_usd=1.0)

    assert result.winner.model == "frugal-twin"


def test_the_tie_goes_to_the_cheaper_even_when_it_is_handed_over_last():
    """The rule has to live in `choose`, not be inherited from the caller's order.

    Deleting the cost term from `choose`'s key reddened **nothing**: `max` returns
    the first maximal element and `rank` had already put the cheaper candidate
    first, so the rule was enforced by an incidental property of the input rather
    than by the code claiming to enforce it. That is a rule one refactor away from
    silently leaving — anything that hands `choose` a differently-ordered list
    would flip the winner with no test to notice.

    So the list here is deliberately NOT ranked, and the dearer twin goes first.
    """
    frugal_twin = _candidate("frugal-twin", score=70.0, in_price=0.1, out_price=0.1, out_tokens=1_000)

    result = choose([MIDDLING, frugal_twin], axis="coding", read_volume_tokens=READ, budget_usd=1.0)

    assert MIDDLING.cost_per_task(READ) > frugal_twin.cost_per_task(READ)
    assert result.winner.model == "frugal-twin"


def test_the_committed_fixture_carries_a_case_where_a_budget_changes_the_winner():
    """#109 asks for a FIXTURE case, not only a hand-built one.

    A rule that only reverses on candidates the test invented has not been shown
    to reverse on the data the tool actually ships with. On the committed dataset
    at a 10,000-token read, `gpt-5.6-terra` is cheapest and `gpt-5.6-sol` leads
    the coding axis at roughly twice the cost.
    """
    ordered = rank(
        load_candidates(), kind_of_work="implementation", read_volume_tokens=READ, output_ceiling_tokens=0, item_count=1
    ).ordered
    axis = axis_for("implementation")

    cheapest = choose(ordered, axis=axis, read_volume_tokens=READ, budget_usd=None)
    afforded = choose(ordered, axis=axis, read_volume_tokens=READ, budget_usd=0.12)

    assert cheapest.winner.model != afforded.winner.model
    assert afforded.winner.score_on(axis) > cheapest.winner.score_on(axis)
