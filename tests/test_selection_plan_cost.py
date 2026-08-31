"""A budget bounds the whole plan, not one seat (#138).

#109 compared the budget against one seat's `cost_per_task`, which was exactly
right while the count was fixed at one — #109's own docstring said so. #111 made
the count a variable and made that comparison wrong without touching #109's code.

**The arithmetic is not "seat cost times seats".** The read is PARTITIONED across
the seats (#113), so the input term is paid once no matter how many seats there
are. Each seat emits its own answer, so the output term multiplies. A total that
multiplied the whole per-seat cost would overstate a read-heavy plan, which is
the direction that refuses work the caller could afford.

**And the ranking has to use the same figure.** Budgeting on the plan total while
ranking on the per-seat cost would leave the "cheapest qualifying" rule choosing a
candidate that is not the cheapest plan — the incoherence #138 exists to remove,
reintroduced one function along. #96 wants "the figure I optimise" to be "the
figure I spend"; there is one such figure, so there is one figure.
"""

from __future__ import annotations

import pytest

from tools.selection import Candidate, choose, plan_cost, rank, width


def _candidate(model: str, *, window: int, score: float = 70.0, in_price: float = 1.0, out_price: float = 1.0):
    return Candidate(
        model=model,
        effort="max",
        context_window=window,
        axes={"coding": score},
        input_price_per_mtok=in_price,
        output_price_per_mtok=out_price,
        output_tokens_per_task=10_000,
    )


SCOPE = {"read_volume_tokens": 100_000, "item_count": 100, "output_ceiling_tokens": 8_000}


def test_one_seat_costs_exactly_what_the_per_task_figure_always_said():
    """A generalisation, not a reversal — the same guard #111 put on the window.

    At a single seat the plan IS the task, so the new figure must agree with the
    old one. If this stops holding, #104's arithmetic was replaced rather than
    extended, and nothing else would say so.
    """
    roomy = _candidate("roomy", window=1_000_000)

    assert width(roomy, **SCOPE).count == 1
    assert plan_cost(roomy, **SCOPE) == pytest.approx(roomy.cost_per_task(SCOPE["read_volume_tokens"]))


def test_the_input_term_is_paid_once_however_many_seats_there_are():
    """The read is partitioned, not repeated (#113) — so it does not multiply.

    This is the case that separates the right arithmetic from the plausible one.
    `cramped` needs ten seats. Multiplying its whole per-seat cost by ten would
    charge the read ten times over; the correct total charges it once and
    multiplies only the ten answers.
    """
    cramped = _candidate("cramped", window=18_000)
    seats = width(cramped, **SCOPE).count

    assert seats == 10

    naive = cramped.cost_per_task(SCOPE["read_volume_tokens"]) * seats
    correct = (
        SCOPE["read_volume_tokens"] * cramped.input_price_per_mtok
        + seats * cramped.output_tokens_per_task * cramped.output_price_per_mtok
    ) / 1_000_000

    assert plan_cost(cramped, **SCOPE) == pytest.approx(correct)
    assert plan_cost(cramped, **SCOPE) < naive, "the read was charged more than once"


def test_more_seats_cost_more_than_fewer_on_the_same_scope():
    """The whole reason the figure has to change: seats are not free.

    A model that needs ten passes emits ten answers. Under the per-seat figure
    those two candidates could be priced identically, which is what let a plan
    pass a budget it exceeds.
    """
    roomy = _candidate("roomy", window=1_000_000)
    cramped = _candidate("cramped", window=18_000)

    assert plan_cost(cramped, **SCOPE) > plan_cost(roomy, **SCOPE)


def test_a_candidate_that_fits_per_seat_and_not_in_total_is_priced_out():
    """#138's own criterion, and the failure it was filed for.

    `cramped` costs 0.11 per seat and needs ten of them, for 0.20 in total — the
    read is charged once and the ten answers ten times. Under #109's comparison a
    budget of 0.15 admitted it and the run cost 0.20; now the budget sees the
    total and prices it out.

    **The first version of this docstring said 0.2 per seat and a 0.5 budget, and
    the assertion disagreed.** The figures are the whole point of the case, so a
    comment that computes them is worth exactly what the assertion checking it is
    worth — the fourth time this epic has proved that, and the fourth time the
    assertion won.
    """
    cramped = _candidate("cramped", window=18_000)
    roomy = _candidate("roomy", window=1_000_000, score=60.0)
    budget = 0.15

    assert cramped.cost_per_task(SCOPE["read_volume_tokens"]) == pytest.approx(0.11)
    assert plan_cost(cramped, **SCOPE) == pytest.approx(0.20)
    assert cramped.cost_per_task(SCOPE["read_volume_tokens"]) < budget < plan_cost(cramped, **SCOPE)

    ordered = rank([cramped, roomy], kind_of_work="implementation", **SCOPE).ordered
    result = choose(ordered, axis="coding", budget_usd=budget, **SCOPE)

    assert "cramped" in result.excluded_by_budget
    assert result.winner.model == "roomy"


def test_the_cheapest_rule_ranks_on_the_plan_total_too():
    """One figure, or the layer optimises one thing and spends another.

    `cramped` is cheaper per seat and dearer per plan. With no budget in force,
    "cheapest qualifying" must pick the cheaper PLAN — ranking on the per-seat
    figure here would recommend the candidate the budget rule would refuse, from
    the same data, in the same call.
    """
    cramped = _candidate("cramped", window=18_000, in_price=0.9, out_price=0.9)
    roomy = _candidate("roomy", window=1_000_000, score=60.0)

    assert cramped.cost_per_task(SCOPE["read_volume_tokens"]) < roomy.cost_per_task(SCOPE["read_volume_tokens"])
    assert plan_cost(cramped, **SCOPE) > plan_cost(roomy, **SCOPE)

    ordered = rank([cramped, roomy], kind_of_work="implementation", **SCOPE).ordered
    result = choose(ordered, axis="coding", budget_usd=None, **SCOPE)

    assert result.winner.model == "roomy"


def test_a_budget_nothing_fits_in_total_still_refuses():
    """The refusal path must survive the change of figure, not only the admission one."""
    cramped = _candidate("cramped", window=18_000)

    ordered = rank([cramped], kind_of_work="implementation", **SCOPE).ordered
    result = choose(ordered, axis="coding", budget_usd=0.0001, **SCOPE)

    assert result.winner is None
    assert result.excluded_by_budget == ["cramped"]
