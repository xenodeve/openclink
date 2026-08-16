"""Rank candidates on cost per task, one axis at a time (#104).

**Pure by construction** — no subprocess, no network, no clock, no config lookup.
#96 splits the problem deliberately: mapping a described task onto a capability
axis is a language task, and ranking candidates once the axis is fixed is
arithmetic. Keeping them apart is what makes this half testable by assertion.
`clink/pricing.py` is pure for the same reason and says so.

**Cost per task, not price per token, is the whole point of this slice.** The two
disagree, and the obvious heuristic loses: a mid tier that is 2.5x cheaper per
token can cost MORE per task, because it emits more output to finish the same
work — and score materially lower on the axis while doing it. A layer that ranked
by price would recommend it.

**And the disagreement is not a constant.** The same pair flips once the read
volume is large enough that the input term dominates. That is why this ranks by
arithmetic rather than by a rule of thumb in either direction: "prefer the terser
model" is as wrong as "prefer the cheaper token", just less often.

**A missing axis score excludes a candidate rather than scoring it zero.** The
source publishes only its top 25 per axis, so a blank is *not published* — the
absence of a measurement, not a measurement of absence. Ranking a candidate on an
axis nobody measured it on is the failure #96 names in its second bullet, one
level down.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Which capability axis a kind of work is ranked on. Declared here rather than
# accepted from the caller: #96 is explicit that "the capability axis is a
# function of the declared kind of work", because a caller able to choose the
# axis can choose the one its preferred model happens to lead.
#
# `agentic` for work that runs tools in a loop, `coding` for work that writes or
# changes code, `index` for work that is neither — the composite is the only
# figure published for reasoning-shaped tasks, and using it here is a deliberate
# fallback rather than an endorsement.
AXIS_FOR_KIND: dict[str, str] = {
    "implementation": "coding",
    "refactor": "coding",
    "bulk_transform": "agentic",
    "research": "agentic",
    "review": "coding",
    "analysis": "index",
}

DATASET_PATH = Path(__file__).parent.parent / "conf" / "selectagents_dataset.json"


@dataclass(frozen=True)
class Candidate:
    """One (model, effort) pair the dataset carries."""

    model: str
    effort: str
    context_window: int
    axes: dict[str, float]
    input_price_per_mtok: float
    output_price_per_mtok: float
    output_tokens_per_task: int

    def score_on(self, axis: str) -> float | None:
        """`None` means the source did not publish this axis for this candidate."""
        return self.axes.get(axis)

    def cost_per_task(self, read_volume_tokens: int) -> float:
        """What one task actually costs, rather than what a token costs.

        Output volume is a property of the CANDIDATE — a model that emits twice
        as much to finish the same work costs twice as much to finish it, whatever
        its per-token price says. That is the term price-per-token ranking drops,
        and dropping it is what makes the cheap-looking model win.

        The scope's `output_ceiling_tokens` is deliberately not applied here.
        #104 ranks on one axis and nothing else; a ceiling is a filter, and
        filters land in #108 with the context window.
        """
        return (
            read_volume_tokens * self.input_price_per_mtok + self.output_tokens_per_task * self.output_price_per_mtok
        ) / 1_000_000

    def price_per_token(self) -> float:
        """Published only so the disagreement with `cost_per_task` is expressible.

        Nothing ranks on this. It exists because a test has to be able to say
        "these two orderings differ", and because a reader comparing the two needs
        the losing figure in front of them.
        """
        return (self.input_price_per_mtok + self.output_price_per_mtok) / 2


class DatasetError(RuntimeError):
    """The dataset could not be read as one.

    Loud rather than empty: with no prices and no rankings there is nothing to
    compute, and #96 refuses at once rather than degrading. A silently empty
    dataset would make every ranking return "no candidate" — indistinguishable
    from a scope nothing can serve.
    """


def load_candidates(path: Path | None = None) -> list[Candidate]:
    source = path or DATASET_PATH
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DatasetError(f"model dataset missing at {source}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetError(f"model dataset at {source} is not readable JSON: {exc}") from exc

    entries = raw.get("candidates")
    if not isinstance(entries, list) or not entries:
        raise DatasetError(f"model dataset at {source} declares no candidates")

    return [
        Candidate(
            model=entry["model"],
            effort=entry["effort"],
            context_window=entry["context_window"],
            axes=dict(entry["axes"]),
            input_price_per_mtok=entry["input_price_per_mtok"],
            output_price_per_mtok=entry["output_price_per_mtok"],
            output_tokens_per_task=entry["output_tokens_per_task"],
        )
        for entry in entries
    ]


@dataclass(frozen=True)
class Ranking:
    """The survivors, and who was removed on the way — never only the survivors.

    A plan chosen from two candidates out of five must not read like one chosen
    from five (#108). The two exclusion reasons are kept apart because they mean
    different things to a caller: "your scope is larger than most context windows"
    is actionable — split it — while "nobody measured these on your axis" is not.
    """

    ordered: list[Candidate]
    excluded_by_window: list[str]
    excluded_by_axis: list[str]


def per_item_read(*, read_volume_tokens: int, item_count: int) -> int:
    """The read volume one item carries — the smallest share anyone can be given.

    An item is the atom: #113 partitions the scope across agents with no gap and
    no overlap, so nothing smaller than one item can be handed to a seat.
    """
    return -(-read_volume_tokens // item_count)  # ceiling division, no float


def required_window(*, read_volume_tokens: int, output_ceiling_tokens: int, item_count: int) -> int:
    """What a candidate must hold: **its share** of the input, and its own answer.

    Sizing on the read alone looks conservative and is not — a model sized
    exactly to the input has nowhere to put the output, and the truncation lands
    in the result rather than in an error.

    **The share, not the whole scope (#111).** #108 wrote this as the entire read
    because the agent count did not exist yet, and with one agent the whole read
    IS the share. Once the count is derived, that reading makes #111's own
    criterion unsatisfiable: filter every candidate that cannot hold the whole
    scope and no surviving candidate can ever need more than one agent, so "a
    smaller context window yields a higher count" could never be observed.

    So the bar is one item — the smallest share a seat can be given — and a
    window above it buys a coarser split rather than admission. #96: "a smaller
    window forces a finer split rather than a truncation nobody sees."

    This is a generalisation of #108 rather than a reversal: at `item_count=1` it
    returns exactly what #108 returned.
    """
    return per_item_read(read_volume_tokens=read_volume_tokens, item_count=item_count) + output_ceiling_tokens


def plan_cost(candidate: Candidate, *, read_volume_tokens: int, item_count: int, output_ceiling_tokens: int) -> float:
    """What the WHOLE plan costs, not what one seat costs (#138).

    #109 compared a budget against one seat, which was right while the count was
    fixed at one and wrong the moment #111 made it a variable — without touching
    #109's code, which is why nothing failed.

    **It is not "seat cost times seats".** The read is partitioned across the
    seats (#113), so the input term is paid ONCE however many seats there are;
    each seat emits its own answer, so only the output term multiplies.
    Multiplying the whole per-seat figure would overstate a read-heavy plan — the
    direction that refuses work the caller could comfortably afford.

    At one seat this returns exactly what `cost_per_task` returns, so #104's
    arithmetic is extended rather than replaced. A test pins that.
    """
    seats = width(
        candidate,
        read_volume_tokens=read_volume_tokens,
        item_count=item_count,
        output_ceiling_tokens=output_ceiling_tokens,
    ).count
    return (
        read_volume_tokens * candidate.input_price_per_mtok
        + seats * candidate.output_tokens_per_task * candidate.output_price_per_mtok
    ) / 1_000_000


@dataclass(frozen=True)
class Choice:
    """The eligible field in the applied rule's own order, best first.

    `ranked` rather than a lone winner, because #110 needs the runners-up ordered
    the way the WINNER was chosen. Once a budget is in force those two orders
    diverge — the cheapest is no longer the winner — and alternatives ranked by
    cost would then be a fallback list for a decision nobody made.

    `rule` is carried rather than inferred because the two rules answer different
    questions and a caller cannot tell which one ran from the winner alone.
    """

    ranked: list[Candidate]
    rule: str
    excluded_by_budget: list[str]

    @property
    def winner(self) -> Candidate | None:
        return self.ranked[0] if self.ranked else None


@dataclass(frozen=True)
class Alternative:
    """One route, and what taking it costs relative to the route above it."""

    candidate: Candidate
    cost_delta_usd: float | None


@dataclass(frozen=True)
class Slate:
    """The routes offered, and how many qualifying ones did not fit the bound.

    `dropped` is not decoration. #96 refuses to cull anything qualifying and
    bounds the set by rank instead, so the count is what stops a truncated list
    being read as the whole field.
    """

    entries: list[Alternative]
    dropped: int


# Five, from #96 directly. A bound rather than a filter: nothing qualifying is
# culled on merit, because a candidate beaten on every measured axis is still the
# only route when the winner's lane is down, and availability is not one of the
# axes being compared.
ALTERNATIVE_LIMIT = 5


def slate(
    choice: Choice,
    *,
    read_volume_tokens: int,
    item_count: int,
    output_ceiling_tokens: int,
    limit: int = ALTERNATIVE_LIMIT,
) -> Slate:
    """The winner and its runners-up, each priced against the route above it.

    **Bounded by rank, never culled on merit (#96, #110).** A candidate beaten on
    every axis in play is still the only route once the winner's lane is down,
    and availability is not one of the axes being compared — so nothing eligible
    is dropped for being worse, only for being further down than the bound
    reaches. What the bound cuts is COUNTED, because a truncated list read as the
    whole list is the failure the criterion exists to prevent.

    **The order is `choice.ranked`, which is the rule that picked the winner.**
    Under a budget that is descending capability, not ascending cost, and using
    cost order instead would offer fallbacks for a decision nobody made.

    **The delta is to the predecessor and it is signed.** Falling back is often
    cheaper — under the budget rule it usually is — and a magnitude would leave a
    caller unable to tell a saving from a surcharge.

    **It is a delta between PLAN totals (#138), not between seats.** A route that
    needs three seats costs three answers more than one that needs one, and a
    per-seat delta would price the fallback at a figure nobody is billed.
    """
    offered = choice.ranked[:limit]

    entries: list[Alternative] = []
    for position, candidate in enumerate(offered):
        if position == 0:
            # Nothing above the winner to be a delta to. `None` rather than 0.0,
            # which would read as "the same price as the route above".
            entries.append(Alternative(candidate=candidate, cost_delta_usd=None))
            continue
        above = offered[position - 1]
        scope = {
            "read_volume_tokens": read_volume_tokens,
            "item_count": item_count,
            "output_ceiling_tokens": output_ceiling_tokens,
        }
        delta = plan_cost(candidate, **scope) - plan_cost(above, **scope)
        entries.append(Alternative(candidate=candidate, cost_delta_usd=round(delta, 6)))

    return Slate(entries=entries, dropped=max(0, len(choice.ranked) - limit))


def choose(
    ordered: list[Candidate],
    *,
    axis: str,
    read_volume_tokens: int,
    item_count: int,
    output_ceiling_tokens: int,
    budget_usd: float | None,
) -> Choice:
    """Cheapest by default; the best that fits once a ceiling is named (#109).

    **Two rules, and which one applies is the substance of the slice.** With no
    budget, frugality — #96 wants that to be the default "rather than a setting
    the caller has to remember". With a budget, the caller has already declared
    what it will spend, so the layer spends it on capability rather than handing
    back change.

    **That reading is forced by the criteria, not chosen.** #109 requires both
    "no budget yields the cheapest qualifying candidate" and "a fixture case
    exists where supplying a budget changes the winner". Were a budget only a
    ceiling, the cheapest would still win whenever anything fit, and the winner
    could never change — the second criterion would be unsatisfiable.

    **Nothing fitting returns no winner rather than the cheapest anyway.** The
    criterion is "says so rather than exceeding it", and quietly returning a plan
    the caller's own ceiling forbids is the overrun it exists to prevent.

    **The figure is the PLAN total, not one seat (#138).** #109 compared against
    one seat, which was right while the count was fixed at one and wrong the
    moment #111 made it a variable. Budgeting on the total while ranking on the
    per-seat figure would put the incoherence back one function along: the
    "cheapest qualifying" rule would name a candidate the budget rule refuses,
    from the same data in the same call. #96 wants "the figure I optimise" to be
    "the figure I spend", and there is one such figure.
    """

    def cost(candidate: Candidate) -> float:
        return plan_cost(
            candidate,
            read_volume_tokens=read_volume_tokens,
            item_count=item_count,
            output_ceiling_tokens=output_ceiling_tokens,
        )

    if budget_usd is None:
        # Re-sorted on the plan total rather than trusting `ordered`, which #104
        # ranks on the per-seat figure. The two agree only while every candidate
        # needs one seat, and a rule named "cheapest" must be cheapest on the
        # figure the caller is actually billed.
        return Choice(ranked=sorted(ordered, key=cost), rule="cheapest_qualifying", excluded_by_budget=[])

    affordable = [c for c in ordered if cost(c) <= budget_usd]
    priced_out = [c.model for c in ordered if cost(c) > budget_usd]

    # Highest on the axis; ties to the cheaper seat, because cost is always
    # weighted (#96) and "either" would make the layer non-deterministic. The
    # whole field is sorted rather than only its maximum taken, so that #110's
    # alternatives are the runners-up under the rule that picked the winner —
    # ranking them by cost instead would offer fallbacks for a different
    # decision than the one made.
    ranked = sorted(
        affordable,
        key=lambda c: (-(c.score_on(axis) or 0.0), cost(c)),
    )
    return Choice(ranked=ranked, rule="best_within_budget", excluded_by_budget=priced_out)


@dataclass(frozen=True)
class Width:
    """How many seats, and every figure the count was derived from.

    The components travel with the count because #111 requires the derivation to
    appear in the criteria — a bare number is a number chosen in the moment as
    far as any caller can tell, which is the thing the slice exists to replace.
    """

    count: int
    per_item_read_tokens: int
    usable_window_tokens: int
    items_per_agent: int


def width(candidate: Candidate, *, read_volume_tokens: int, item_count: int, output_ceiling_tokens: int) -> Width:
    """How many seats this candidate needs for this scope, and why (#111).

    The count is a **consequence of the work**: how many item-shares the window
    holds at once decides how many passes the scope takes. A bigger window
    carries more items per seat and needs fewer; a smaller one forces a finer
    split, which is #96's whole point — the alternative to a finer split is a
    truncation nobody sees.

    **Precondition: the candidate survived `rank`.** That filter now requires a
    window of at least one item-share plus the answer, so `items_per_agent` is at
    least one here and the division below is safe. Stated rather than defended
    with a guard, because a guard for an unreachable case is dead code that reads
    like a live one.

    **Not an input yet: difficulty.** #111's prose names it alongside the item
    count and the scope, but #101 closed the request contract and no field
    carries it. Inventing a proxy — treating `verification` or `kind_of_work` as
    a difficulty scale — would be the unmeasured number this layer exists to
    remove. So the count derives from volume and window only, and the criteria
    say so rather than implying a factor that is not there.
    """
    share = per_item_read(read_volume_tokens=read_volume_tokens, item_count=item_count)
    usable = candidate.context_window - output_ceiling_tokens

    if share == 0:
        # Nothing to read means the window constrains nothing. One seat, and the
        # count does not silently become the item count.
        return Width(count=1, per_item_read_tokens=0, usable_window_tokens=usable, items_per_agent=item_count)

    items_per_agent = min(item_count, usable // share)
    count = -(-item_count // items_per_agent)  # ceiling division, no float

    return Width(
        count=count,
        per_item_read_tokens=share,
        usable_window_tokens=usable,
        items_per_agent=items_per_agent,
    )


@dataclass(frozen=True)
class Share:
    """One agent's part of the scope: which items, and how much reading."""

    first_item: int
    item_count: int
    read_volume_tokens: int


class PartitionError(RuntimeError):
    """The scope cannot be divided into the count asked for.

    Reported rather than silently rebalanced (#113). Quietly adjusting the count
    to something divisible would move the width decision out of the frozen phase
    and into the partitioner — the growth the per-phase freeze exists to prevent,
    arriving as a correction nobody asked for.
    """


def partition(*, item_count: int, read_volume_tokens: int, agent_count: int) -> list[Share]:
    """Divide the scope once, here, so each worker does not divide it again (#113).

    **Every item has exactly one owner and the shares sum to the whole**, on both
    axes. Coverage is what terminates a phase — never confidence — so the sum is
    the criterion rather than a check on it.

    **The read follows the items.** An agent holding four of ten items reads four
    tenths, because #111 sized its context window on the item share; splitting the
    read evenly across seats while the items divide unevenly would hand the
    largest seat the budget of an average one, and the shortfall lands as a
    truncation rather than as an error.

    **The boundaries are cumulative, not rounded per share.** Rounding each share
    independently leaks: 100 tokens over 3 seats is either three 33s that lose a
    token or three 34s that invent two, and neither is a scope anyone declared.
    Taking differences between cumulative marks makes the total telescope back to
    exactly the input, whatever the remainders do.

    **The remainder is spread from the front, not piled on the last seat.** The
    widest seat is the one a phase waits on, and putting the surplus on the last
    agent makes that the last one to start.
    """
    if agent_count > item_count:
        raise PartitionError(
            f"cannot divide {item_count} items among {agent_count} agents: "
            "an item is the smallest share there is, so some agent would own nothing. "
            "Nothing was rebalanced — the count is fixed when the phase starts."
        )

    base, remainder = divmod(item_count, agent_count)

    shares: list[Share] = []
    first_item = 0
    for position in range(agent_count):
        owned = base + (1 if position < remainder else 0)
        # Cumulative marks, so the differences sum to exactly `read_volume_tokens`.
        read_before = read_volume_tokens * first_item // item_count
        read_after = read_volume_tokens * (first_item + owned) // item_count
        shares.append(Share(first_item=first_item, item_count=owned, read_volume_tokens=read_after - read_before))
        first_item += owned

    return shares


def axis_for(kind_of_work: str) -> str:
    try:
        return AXIS_FOR_KIND[kind_of_work]
    except KeyError as exc:  # pragma: no cover - the contract closes this list
        raise DatasetError(f"no capability axis declared for kind of work {kind_of_work!r}") from exc


def rank(
    candidates: list[Candidate],
    *,
    kind_of_work: str,
    read_volume_tokens: int,
    output_ceiling_tokens: int,
    item_count: int,
) -> Ranking:
    """Filter hard, then rank what survives. Cheapest per task first.

    **`output_ceiling_tokens` has no default on purpose.** It defaulted to 0,
    which sized the requirement on the read alone — the mistake `required_window`
    exists to prevent, reachable by omission. A fail-open default on a hard
    filter lets MORE candidates through, so nothing errors and a model that
    cannot hold its own answer is simply eligible. Every caller says it.

    **Context window is a filter and not a weight (#96, #108).** A weight lets a
    cheap-enough model outrank the constraint and be handed work it will silently
    truncate; a filter removes it. And it runs BEFORE pricing, because #110
    returns the alternatives from this same list — a candidate excluded only at
    the end would reappear as a fallback route, which is exactly where a
    truncating model would get used: after the first choice's lane went down and
    nobody looked again.

    Ties broken by the axis score, higher first: two candidates that cost the
    same are not interchangeable, and the better-measured one is the only
    non-arbitrary pick. Then by name, so the order is stable enough to assert on.
    """
    axis = axis_for(kind_of_work)
    needed = required_window(
        read_volume_tokens=read_volume_tokens,
        output_ceiling_tokens=output_ceiling_tokens,
        item_count=item_count,
    )

    survivors: list[Candidate] = []
    by_window: list[str] = []
    by_axis: list[str] = []
    for candidate in candidates:
        if candidate.context_window < needed:
            by_window.append(candidate.model)
        elif candidate.score_on(axis) is None:
            by_axis.append(candidate.model)
        else:
            survivors.append(candidate)

    ordered = sorted(
        survivors,
        key=lambda c: (c.cost_per_task(read_volume_tokens), -(c.score_on(axis) or 0.0), c.model, c.effort),
    )
    return Ranking(ordered=ordered, excluded_by_window=by_window, excluded_by_axis=by_axis)
