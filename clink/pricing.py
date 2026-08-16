"""Price a normalised token account against a client's rate card (#25).

Pure by construction: no subprocess, no network, no clock, no config lookup —
everything it needs arrives as an argument. That is what makes a cost figure
reproducible from a recorded account, and what lets the tests pin exact numbers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from clink.models import RateCard

if TYPE_CHECKING:  # `agents.base` imports this module, so the account type is
    # referenced for typing only — importing it at runtime would close the cycle.
    from clink.agents.base import TokenUsage

# Normalised account field -> the rate that prices it. Declared once so a new
# token class cannot be added to the account and silently priced at zero.
_CLASS_RATES: dict[str, str] = {
    "input_tokens": "input",
    "cached_input_tokens": "cached_input",
    "output_tokens": "output",
    "reasoning_output_tokens": "reasoning_output",
}


@dataclass(frozen=True)
class CallCost:
    """A cost figure that carries its unit, and admits what it left out."""

    value: float
    unit: str
    # Classes the CLI *did* report but the card does not price. Named rather
    # than folded in at zero: a total that silently omits a reported class is
    # wrong in a way no caller can see.
    unpriced_classes: tuple[str, ...] = ()


# Named because the tool treats this reason differently from the others: it is a
# fact about OpenClink's configuration rather than about the CLI or the call, so it is
# not projected to the caller. A literal spelled in two files would drift.
NO_RATE_CARD = "no_rate_card"


@dataclass(frozen=True)
class CostUnavailable:
    """Why no figure could be produced. Never an exception, never a guess.

    A model released this morning is the ordinary case here, not an error: it
    must not turn every delegation into a failure, and must not be priced at
    zero either.
    """

    reason: str


def sum_thread_accounts(accounts: list[dict]) -> dict:
    """Add up the per-call accounts already stored on a thread.

    Pure: it takes accounting blocks and returns one. Absence is preserved
    rather than filled — a turn that reported nothing makes the total
    *incomplete* rather than smaller, because a total that quietly drops a turn
    is wrong in a way no caller can see.

    **Mixed units are never summed.** A subscription backend prices in credits
    and a token-billed one in currency; a thread that used both has no total and
    says so, instead of adding two different things.

    **What it produces:** `cumulative_usage` (+ `_incomplete`), and TWO cost
    totals that are never merged — `cumulative_cost` from what OpenClink priced
    against a rate card, and `cumulative_cli_reported_cost` from what a CLI
    metered itself (#126; opencode is currently the only one). Each may instead
    appear as `<key>_unavailable: "mixed_units"`, and each carries its own
    `<key>_incomplete` when some turn did not report.

    Keeping them apart matters most on a mixed thread, which is the case that
    made #129 visible: reading only `cost` meant a thread of opencode calls
    returned usage and complete silence about money, while every turn in it
    carried a measured figure.
    """
    totals: dict[str, int] = {}
    incomplete_usage = False

    for account in accounts:
        usage = account.get("normalized_usage")
        if isinstance(usage, dict):
            for name, value in usage.items():
                if isinstance(value, int):
                    totals[name] = totals.get(name, 0) + value
        else:
            # The turn ran and reported nothing accountable. Its tokens are not
            # zero; they are unknown.
            incomplete_usage = True

    out: dict = {}
    if totals:
        out["cumulative_usage"] = totals
    if incomplete_usage and totals:
        out["cumulative_usage_incomplete"] = True

    # Two cost totals, kept apart on purpose. `cost` is what OpenClink computed
    # from a rate card; `cli_reported_cost` is what the CLI metered itself (#126,
    # opencode is currently the only one). The per-call view keeps those claims
    # under different keys so a consumer can tell which a figure is, and
    # collapsing them here would undo that one layer up — a mixed thread is
    # exactly where it matters (#129).
    #
    # One accumulator, called twice, rather than the rule written twice: the
    # mixed-unit refusal and the incomplete marker must behave identically for
    # both, and a second implementation is how they stop doing so.
    out.update(_total_cost(accounts, "cost", "cumulative_cost"))
    out.update(_total_cost(accounts, "cli_reported_cost", "cumulative_cli_reported_cost"))
    return out


def _total_cost(accounts: Sequence[dict], key: str, out_key: str) -> dict:
    """Sum one cost key across turns, refusing to mix units.

    `Sequence`, not `Iterable`, and that is load-bearing: `sum_thread_accounts`
    now walks `accounts` three times — once for usage and once per cost key — so
    a one-shot iterator would be exhausted by the first pass and the remaining
    two would silently total nothing. A zero that should have been a figure, with
    no error to notice. The public signature is already `list[dict]` and the only
    caller passes a comprehension, so nothing can hit this today; the annotation
    is here to keep it that way.

    `is not None` on the value, not truthiness: a call that genuinely cost zero
    reported something, and demoting it to "uncovered" would mark the total
    incomplete while every turn in it was accounted for.
    """
    value = 0.0
    units: set[str] = set()
    covered = 0
    uncovered = 0

    for account in accounts:
        figure = account.get(key)
        if isinstance(figure, dict) and isinstance(figure.get("value"), (int, float)):
            value += float(figure["value"])
            units.add(str(figure.get("unit")))
            covered += 1
        else:
            uncovered += 1

    if not covered:
        return {}
    if len(units) > 1:
        # A reason travels instead of a number: credits and currency have no
        # common unit, so no total is valid.
        return {f"{out_key}_unavailable": "mixed_units"}
    out = {out_key: {"value": value, "unit": next(iter(units))}}
    if uncovered:
        out[f"{out_key}_incomplete"] = True
    return out


def price_call(card: RateCard | None, model: str | None, account: TokenUsage | None) -> CallCost | CostUnavailable:
    if card is None:
        return CostUnavailable(reason=NO_RATE_CARD)
    if model is None:
        return CostUnavailable(reason="model_unresolved")
    if account is None:
        return CostUnavailable(reason="no_usage_reported")
    rates = card.models.get(model)
    if rates is None:
        return CostUnavailable(reason="model_not_priced")

    total = 0.0
    unpriced: list[str] = []
    for account_field, rate_field in _CLASS_RATES.items():
        tokens = getattr(account, account_field)
        if tokens is None:
            continue
        rate = getattr(rates, rate_field)
        if rate is None:
            unpriced.append(account_field)
            continue
        total += tokens / card.per_tokens * rate

    return CallCost(value=total, unit=card.unit, unpriced_classes=tuple(unpriced))
