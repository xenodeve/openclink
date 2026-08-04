"""Price a normalised token account against a client's rate card (#25).

Pure by construction: no subprocess, no network, no clock, no config lookup —
everything it needs arrives as an argument. That is what makes a cost figure
reproducible from a recorded account, and what lets the tests pin exact numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from clink.agents.base import TokenUsage
from clink.models import RateCard

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
    unpriced_classes: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class CostUnavailable:
    """Why no figure could be produced. Never an exception, never a guess.

    A model released this morning is the ordinary case here, not an error: it
    must not turn every delegation into a failure, and must not be priced at
    zero either.
    """

    reason: str


def price_call(card: RateCard | None, model: str | None, account: TokenUsage | None) -> CallCost | CostUnavailable:
    if card is None:
        return CostUnavailable(reason="no_rate_card")
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
