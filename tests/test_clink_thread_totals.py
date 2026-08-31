"""Cumulative usage and cost across a continuation thread (#26).

Rewritten, not repaired. A delegated draft pinned a seam that was never chosen:
it set `output.continuation_id`, which only works because `AgentOutput` is a
plain dataclass, and it invented a storage shape. **The arithmetic in it was
correct and is kept** — every figure below was recomputed by hand.

The seam actually chosen, and why:

- **Write.** `CLinkTool._record_assistant_turn` is overridden, the way
  `tools/chat.py` overrides it. The base builds turn metadata only from a
  provider `model_response`, and clink has none — it spawns a CLI — so before
  this every clink turn was stored with `model_metadata=None` and a thread had
  nothing to sum. `model_metadata` is the documented home for it.
- **Read.** Tool-side. `CLinkTool` already holds the thread id; carrying it down
  into `AgentOutput` would add a field to the agent layer so the tool could
  learn something it was already told.

Rates are fictional and round so the arithmetic is checkable by eye:
$1 per 100 input tokens, $2 per 100 output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clink.agents.codex import CodexAgent
from clink.models import ModelRate, RateCard, ResolvedCLIClient, ResolvedCLIRole
from clink.parsers.base import ParsedCLIResponse
from tools.clink import CLinkTool


def _sum(accounts: list[dict]) -> dict:
    # Imported inside the call, not at module level. A module-level import of a
    # symbol that does not exist yet makes the WHOLE FILE uncollectable, so the
    # one test here whose red is behavioural could not run either — the vacuous
    # red this project has hit four times.
    from clink.pricing import sum_thread_accounts

    return sum_thread_accounts(accounts)


MODEL = "gpt-5.6-luna"


def _card(unit: str) -> RateCard:
    return RateCard(unit=unit, per_tokens=100, models={MODEL: ModelRate(input=1.0, output=2.0)})


def _agent(unit: str = "USD") -> CodexAgent:
    role = ResolvedCLIRole(name="default", prompt_path=Path("systemprompts/clink/default.txt").resolve(), role_args=[])
    return CodexAgent(
        ResolvedCLIClient(
            name="codex",
            executable=["codex"],
            internal_args=["exec"],
            config_args=[],
            env={},
            timeout_seconds=30,
            parser="codex_jsonl",
            runner="codex",
            roles={"default": role},
            output_to_file=None,
            working_dir=None,
            rate_card=_card(unit),
        )
    )


def _account(usage: dict | None, unit: str = "USD") -> dict:
    """The accounting block one call would produce, via the real projection."""
    metadata = {"usage": usage} if usage is not None else {}
    output = _agent(unit).finalize_output(
        parsed=ParsedCLIResponse(content="OK", metadata=metadata),
        sanitized_command=["codex", "-m", MODEL],
        returncode=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
    )
    return CLinkTool()._call_accounting(output)


def test_a_clink_turn_stores_its_own_account():
    """The write half, and the only red here that is behavioural rather than an import error.

    `_record_assistant_turn` already exists on the base, so this test is
    collectable against the unmodified tree and fails for a real reason: the
    base builds `model_metadata` solely from a provider `model_response`, which
    clink never has, so it stored `None` and the thread held nothing to sum.
    """
    from types import SimpleNamespace

    from utils.conversation_memory import create_thread, get_thread

    thread_id = create_thread("clink", {"prompt": "x"})
    account = _account({"input_tokens": 100, "output_tokens": 20})
    CLinkTool()._record_assistant_turn(
        thread_id,
        "OK",
        SimpleNamespace(absolute_file_paths=[], images=[], prompt="x", continuation_id=thread_id),
        {"provider": "codex", "model_name": MODEL, "accounting": account},
    )

    stored = get_thread(thread_id).turns[-1]
    assert stored.model_metadata is not None, "the turn stored no metadata, so a thread cannot be totalled"
    assert stored.model_metadata["accounting"]["normalized_usage"] == {"input_tokens": 100, "output_tokens": 20}


@pytest.mark.asyncio
async def test_the_totals_actually_reach_the_caller(monkeypatch):
    """The wiring, pinned — added by the pre-merge code-review gate, not the loop.

    Every other test here exercises `sum_thread_accounts` or
    `_record_assistant_turn` in isolation. **Deleting the one line in `execute`
    that joins them left all 1040 tests passing**, so the whole feature could
    have been removed silently. This drives the real `execute` and asserts the
    totals arrive in the response metadata.
    """
    import json

    from clink.agents import AgentOutput
    from clink.agents.base import TokenUsage
    from utils.conversation_memory import create_thread

    thread_id = create_thread("clink", {"prompt": "x"})

    class DummyAgent:
        async def run(self, **_kwargs):
            # `token_usage` is passed explicitly because this bypasses
            # `finalize_output`, which is what normally computes it. Building
            # AgentOutput directly and leaving it None was the first version of
            # this fixture, and it made the test fail against WORKING code —
            # the account had nothing to sum, so the totals were correctly empty.
            return AgentOutput(
                parsed=ParsedCLIResponse(content="OK", metadata={"usage": {"input_tokens": 100, "output_tokens": 20}}),
                sanitized_command=["codex", "-m", MODEL],
                returncode=0,
                stdout="",
                stderr="",
                duration_seconds=0.1,
                parser_name="codex_jsonl",
                resolved_model=MODEL,
                token_usage=TokenUsage(input_tokens=100, output_tokens=20),
            )

    monkeypatch.setattr("tools.clink.create_agent", lambda _client: DummyAgent())
    result = await CLinkTool().execute(
        {
            "prompt": "hi",
            "cli_name": "codex",
            "role": "default",
            "absolute_file_paths": [],
            "images": [],
            "model": MODEL,
            "continuation_id": thread_id,
        }
    )

    metadata = json.loads(result[0].text)["metadata"]
    assert metadata["cumulative_usage"] == {"input_tokens": 100, "output_tokens": 20}


def test_a_single_turn_thread_totals_that_turn():
    # 100/100*1 + 20/100*2 = 1.40
    totals = _sum([_account({"input_tokens": 100, "output_tokens": 20})])
    assert totals["cumulative_usage"] == {"input_tokens": 100, "output_tokens": 20}
    assert totals["cumulative_cost"] == {"value": pytest.approx(1.40), "unit": "USD"}


def test_totals_are_additive_across_turns():
    #   input   100 + 50 + 25 = 175  ->  175/100*1 = 1.75
    #   output   20 + 10 +  5 =  35  ->   35/100*2 = 0.70
    #                                                 2.45
    accounts = [
        _account({"input_tokens": 100, "output_tokens": 20}),
        _account({"input_tokens": 50, "output_tokens": 10}),
        _account({"input_tokens": 25, "output_tokens": 5}),
    ]
    totals = _sum(accounts)
    assert totals["cumulative_usage"] == {"input_tokens": 175, "output_tokens": 35}
    assert totals["cumulative_cost"] == {"value": pytest.approx(2.45), "unit": "USD"}


def test_a_new_thread_starts_from_nothing():
    # Reset is not a behaviour to implement — it falls out of totalling only the
    # turns the thread has. Pinned anyway, because "resets for a new thread" is
    # an acceptance criterion and an implementation that cached would break it.
    assert _sum([]) == {}
    # 7/100*1 + 3/100*2 = 0.13
    fresh = _sum([_account({"input_tokens": 7, "output_tokens": 3})])
    assert fresh["cumulative_cost"] == {"value": pytest.approx(0.13), "unit": "USD"}


def test_a_turn_that_reported_nothing_makes_the_total_incomplete_rather_than_smaller():
    # The AC's real demand. Dropping the unknown turn silently would produce a
    # total that is wrong in a way no caller can see, so the known subtotal
    # stands AND says it is partial.
    totals = _sum(
        [
            _account({"input_tokens": 100, "output_tokens": 20}),
            _account(None),
        ]
    )
    assert totals["cumulative_usage"] == {"input_tokens": 100, "output_tokens": 20}
    assert totals["cumulative_usage_incomplete"] is True
    assert totals["cumulative_cost_incomplete"] is True


def test_mixed_units_are_not_summed():
    # USD 1.40 and credits 0.70 have no common unit, so no total is valid and
    # none is offered — a reason travels instead of a number.
    totals = _sum(
        [
            _account({"input_tokens": 100, "output_tokens": 20}, unit="USD"),
            _account({"input_tokens": 50, "output_tokens": 10}, unit="credits"),
        ]
    )
    assert "cumulative_cost" not in totals
    assert totals["cumulative_cost_unavailable"] == "mixed_units"
    # Usage is unit-free, so it still totals.
    assert totals["cumulative_usage"] == {"input_tokens": 150, "output_tokens": 30}


def _reported(value: float | None, unit: str = "USD") -> dict:
    """The accounting block an opencode turn produces, via the real projection.

    Built through `OpenCodeAgent` and `_call_accounting` rather than hand-written,
    so a change to either key name reds these tests instead of leaving them
    passing against a shape nothing produces any more.
    """
    from clink.agents.opencode import OpenCodeAgent

    role = ResolvedCLIRole(name="default", prompt_path=Path("systemprompts/clink/default.txt").resolve(), role_args=[])
    client = ResolvedCLIClient(
        name="opencode",
        executable=["opencode"],
        internal_args=[],
        config_args=[],
        env={},
        timeout_seconds=30,
        parser="opencode_jsonl",
        runner=None,
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    metadata: dict = {"tokens": {"input": 100, "output": 20}}
    if value is not None:
        metadata["cli_cost"] = value
        metadata["cli_cost_unit"] = unit
    output = OpenCodeAgent(client).finalize_output(
        parsed=ParsedCLIResponse(content="OK", metadata=metadata),
        sanitized_command=["opencode"],
        returncode=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
    )
    return CLinkTool()._call_accounting(output)


def test_a_thread_of_opencode_turns_totals_the_cost_they_measured():
    """The figure existed per call and vanished at the thread (#129).

    `sum_thread_accounts` read only `account["cost"]` — the rate-card figure.
    #126 filed opencode's measured cost under `cli_reported_cost` deliberately,
    and the aggregator had never heard of it, so every opencode turn fell to
    `unpriced_turns`. With `priced_turns == 0` the cost branch never ran at all:
    a thread of opencode calls returned usage and **complete silence about
    money**, while every turn in it carried a real measured number.
    """
    totals = _sum([_reported(0.0071), _reported(0.0077)])

    assert totals["cumulative_cli_reported_cost"] == {"value": pytest.approx(0.0148), "unit": "USD"}


def test_the_measured_total_is_kept_apart_from_the_priced_one():
    """Collapsing them at the thread level throws away what #126 preserved.

    The per-call view keeps a vendor's meter and OpenClink's own multiplication
    under different keys precisely so a consumer can tell which a figure is.
    Summing them one layer up would undo that, and a mixed thread is exactly
    where it matters — each total must say what it covers.
    """
    totals = _sum([_account({"input_tokens": 100, "output_tokens": 20}), _reported(0.0071)])

    assert totals["cumulative_cost"] == {"value": pytest.approx(1.40), "unit": "USD"}
    assert totals["cumulative_cli_reported_cost"] == {"value": pytest.approx(0.0071), "unit": "USD"}


def test_mixed_units_among_measured_figures_are_refused_not_summed():
    """The module's existing rule, applied to the new total rather than restated.

    A subscription backend metering in credits and opencode metering in dollars
    have no common unit; adding them produces a number that is wrong in a way no
    caller can see.
    """
    totals = _sum([_reported(0.0071, unit="USD"), _reported(4.0, unit="credits")])

    assert "cumulative_cli_reported_cost" not in totals
    assert totals["cumulative_cli_reported_cost_unavailable"] == "mixed_units"


def test_a_turn_with_no_measured_cost_makes_the_measured_total_incomplete():
    """Absence is preserved, not filled — the docstring's own rule.

    A turn that reported nothing must leave the total partial rather than
    shrinking it, because a total that quietly drops a turn is wrong invisibly.
    """
    totals = _sum([_reported(0.0071), _reported(None)])

    assert totals["cumulative_cli_reported_cost"] == {"value": pytest.approx(0.0071), "unit": "USD"}
    assert totals["cumulative_cli_reported_cost_incomplete"] is True


def test_a_measured_zero_counts_as_a_covered_turn():
    """The free tier bills nothing, and that is a fact, not a missing one.

    A truthiness check would move this turn into the uncovered pile and mark the
    total incomplete — turning "every turn was free" into "some turns are
    unknown". Same trap #126 closed one layer down.
    """
    totals = _sum([_reported(0.0), _reported(0.0)])

    assert totals["cumulative_cli_reported_cost"] == {"value": pytest.approx(0.0), "unit": "USD"}
    assert "cumulative_cli_reported_cost_incomplete" not in totals


def test_the_per_call_figures_are_not_replaced_by_the_cumulative_ones():
    # Control: passes before and after. The AC says "alongside", not "instead
    # of" — a caller must still see what THIS call cost.
    account = _account({"input_tokens": 100, "output_tokens": 20})
    assert account["normalized_usage"] == {"input_tokens": 100, "output_tokens": 20}
    assert account["cost"] == {"value": pytest.approx(1.40), "unit": "USD"}
    assert "cumulative_usage" not in account


def test_a_stored_class_that_is_not_an_integer_is_skipped_rather_than_summed():
    """Added because a mutation survived — the isinstance guard was untested.

    These accounts come back out of conversation memory, so they have been
    through JSON. A float or a string arriving where a token count belongs must
    not enter the total: a count is a count, and `1.5 tokens` or `"many"` added
    to an integer is a number nobody can act on. Skipping is right, and it has
    to be pinned or the guard can be deleted without a test noticing.
    """
    stored = [
        {"normalized_usage": {"input_tokens": 100, "output_tokens": 2.5, "cached_input_tokens": "many"}},
    ]
    assert _sum(stored)["cumulative_usage"] == {"input_tokens": 100}


def test_a_thread_of_unaccountable_turns_offers_no_total_at_all():
    # Control on the empty direction: nothing reported means no total, not a
    # total of zero. Same rule as #24 slice 4 and #25.
    assert _sum([_account(None), _account(None)]) == {}
