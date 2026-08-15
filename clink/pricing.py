"""Price a normalised token account against a client's rate card (#25).

Pure by construction: no subprocess, no network, no clock, no config lookup —
everything it needs arrives as an argument. That is what makes a cost figure
reproducible from a recorded account, and what lets the tests pin exact numbers.
"""

from __future__ import annotations

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
    """
    totals: dict[str, int] = {}
    incomplete_usage = False
    cost_value = 0.0
    cost_units: set[str] = set()
    priced_turns = 0
    unpriced_turns = 0

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

        cost = account.get("cost")
        if isinstance(cost, dict) and isinstance(cost.get("value"), (int, float)):
            cost_value += float(cost["value"])
            cost_units.add(str(cost.get("unit")))
            priced_turns += 1
        else:
            unpriced_turns += 1

    out: dict = {}
    if totals:
        out["cumulative_usage"] = totals
    if incomplete_usage and totals:
        out["cumulative_usage_incomplete"] = True

    if priced_turns and len(cost_units) > 1:
        out["cumulative_cost_unavailable"] = "mixed_units"
    elif priced_turns:
        out["cumulative_cost"] = {"value": cost_value, "unit": next(iter(cost_units))}
        if unpriced_turns:
            out["cumulative_cost_incomplete"] = True
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
