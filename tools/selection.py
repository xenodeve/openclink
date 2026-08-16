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


def required_window(*, read_volume_tokens: int, output_ceiling_tokens: int) -> int:
    """What a candidate must be able to hold: the input AND its own answer.

    Sizing on the read alone looks conservative and is not — a model sized
    exactly to the input has nowhere to put the output, and the truncation lands
    in the result rather than in an error.
    """
    return read_volume_tokens + output_ceiling_tokens


@dataclass(frozen=True)
class Choice:
    """Who won, under which rule, and who the budget priced out.

    `rule` is carried rather than inferred because the two rules answer different
    questions and a caller cannot tell which one ran from the winner alone.
    """

    winner: Candidate | None
    rule: str
    excluded_by_budget: list[str]


def choose(
    ordered: list[Candidate],
    *,
    axis: str,
    read_volume_tokens: int,
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

    Scope boundary, stated because it will not stay true: with the agent count
    fixed at one, the plan costs what the winner costs, so bounding the winner
    bounds the plan. **#111 makes the count a variable and this comparison has to
    become count x cost.** Until then a budget bounds one seat.
    """
    if budget_usd is None:
        return Choice(
            winner=ordered[0] if ordered else None,
            rule="cheapest_qualifying",
            excluded_by_budget=[],
        )

    affordable = [c for c in ordered if c.cost_per_task(read_volume_tokens) <= budget_usd]
    priced_out = [c.model for c in ordered if c.cost_per_task(read_volume_tokens) > budget_usd]

    # Highest on the axis; ties to the cheaper seat, because cost is always
    # weighted (#96) and "either" would make the layer non-deterministic. Any
    # remaining tie falls to `max` returning the first maximal element, which
    # `rank` has already ordered by name and effort — so the tiebreak is not
    # restated here, where it could drift from the one that decides `ordered`.
    winner = max(
        affordable,
        key=lambda c: (c.score_on(axis) or 0.0, -c.cost_per_task(read_volume_tokens)),
        default=None,
    )
    return Choice(winner=winner, rule="best_within_budget", excluded_by_budget=priced_out)


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
    needed = required_window(read_volume_tokens=read_volume_tokens, output_ceiling_tokens=output_ceiling_tokens)

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
