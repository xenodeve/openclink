"""Turning a normalised account into a cost figure that carries its unit (#25).

The expected figures below are worked out **by hand** from the rate card and
written as literals, per the issue's own acceptance criterion. A test that
recomputes the expectation the way the implementation does can never disagree
with it — it would pass under any consistent-but-wrong formula, including one
that priced cached input at the full input rate, which is the single largest
error this slice exists to prevent.

The rates in these cards are **fictional and deliberately round**, so the
arithmetic is checkable by eye. No real vendor rate is shipped anywhere in this
change: none was fetched and verified in the session that wrote it, and putting
an unverified price into `conf/` would be publishing a number nobody checked.
"""

from __future__ import annotations

import pytest

from clink.agents.base import TokenUsage
from clink.models import ModelRate, RateCard
from clink.pricing import CostUnavailable, price_call

# $10 per 1M input, $1 per 1M cached input (a tenth, as measured on real
# backends), $30 per 1M output, $30 per 1M reasoning output.
CARD = RateCard(
    unit="USD",
    per_tokens=1_000_000,
    models={
        "gpt-5.6-luna": ModelRate(input=10.0, cached_input=1.0, output=30.0, reasoning_output=30.0),
        # A model priced only on the two classes its CLI reports.
        "cheap-only-io": ModelRate(input=2.0, output=4.0),
    },
)


def test_a_priced_call_reports_a_figure_and_its_unit():
    #   input           100_000 / 1e6 * 10 = 1.00
    #   cached input    900_000 / 1e6 *  1 = 0.90
    #   output           20_000 / 1e6 * 30 = 0.60
    #   reasoning        10_000 / 1e6 * 30 = 0.30
    #                                      = 2.80
    account = TokenUsage(
        input_tokens=100_000,
        cached_input_tokens=900_000,
        output_tokens=20_000,
        reasoning_output_tokens=10_000,
    )
    cost = price_call(CARD, "gpt-5.6-luna", account)
    assert cost.value == pytest.approx(2.80)
    assert cost.unit == "USD"
    assert cost.unpriced_classes == ()


def test_cached_input_is_priced_at_its_own_rate_not_the_input_rate():
    # The whole call is cached input. Folding it into input would give 10.00
    # instead of 1.00 — a 10x overstatement, and the dominant correction found
    # when reconciling computed against reported figures in #21.
    account = TokenUsage(input_tokens=0, cached_input_tokens=1_000_000)
    cost = price_call(CARD, "gpt-5.6-luna", account)
    assert cost.value == pytest.approx(1.00)


def test_a_class_the_card_does_not_price_is_named_rather_than_treated_as_free():
    #   input     50_000 / 1e6 * 2 = 0.10
    #   output    50_000 / 1e6 * 4 = 0.20
    #                              = 0.30, with reasoning reported but unpriced
    account = TokenUsage(input_tokens=50_000, output_tokens=50_000, reasoning_output_tokens=7_000)
    cost = price_call(CARD, "cheap-only-io", account)
    assert cost.value == pytest.approx(0.30)
    assert cost.unpriced_classes == ("reasoning_output_tokens",)


def test_an_unreported_class_is_not_an_unpriced_one():
    # Absent from the account entirely — the CLI never reported it, so there is
    # nothing to warn about. Only a class that WAS reported and could not be
    # priced is a gap in the figure.
    account = TokenUsage(input_tokens=50_000, output_tokens=50_000)
    cost = price_call(CARD, "cheap-only-io", account)
    assert cost.unpriced_classes == ()


@pytest.mark.parametrize(
    "card,model,account,reason",
    [
        pytest.param(None, "gpt-5.6-luna", TokenUsage(input_tokens=1), "no_rate_card", id="client-has-no-card"),
        pytest.param(CARD, "gpt-9-unreleased", TokenUsage(input_tokens=1), "model_not_priced", id="unknown-model"),
        pytest.param(CARD, None, TokenUsage(input_tokens=1), "model_unresolved", id="model-unknown-to-openclink"),
        pytest.param(CARD, "gpt-5.6-luna", None, "no_usage_reported", id="nothing-to-price"),
    ],
)
def test_an_unpriceable_call_gives_a_reason_rather_than_a_number_or_an_error(card, model, account, reason):
    # A model released this morning must not turn every delegation into a
    # failure, and must not be quietly priced at zero either.
    result = price_call(card, model, account)
    assert isinstance(result, CostUnavailable)
    assert result.reason == reason


def test_a_zero_token_call_is_priced_at_zero_rather_than_reported_unavailable():
    # Control: zero is a real, reported figure. Reporting it as "unavailable"
    # would make a genuinely free call indistinguishable from an unpriceable
    # one — the same conflation slice 4 of #24 removed from usage.
    cost = price_call(CARD, "gpt-5.6-luna", TokenUsage(input_tokens=0, output_tokens=0))
    assert cost.value == 0.0
    assert cost.unit == "USD"
