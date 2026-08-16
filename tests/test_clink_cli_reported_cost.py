"""A CLI that measures its own cost has that figure reach the caller (#126).

Every other client needs OpenClink to price it: `price_call` multiplies a
normalised account by a `rate_card`, and no bundled config declares one, so
`cost` is never emitted (#77, finding 1). OpenCode is the exception — `opencode
run --format json` reports `part.cost` on each `step_finish`, and
`clink/parsers/opencode.py` accumulates it into `metadata["cost"]`.

That number was then discarded: `AgentOutput.cost` is `CostUnavailable("no_rate_card")`,
and `tools/clink.py` suppresses that reason deliberately, so the caller was told
nothing while the true figure sat unused one attribute away.

**Provenance is the whole design.** A number computed from a rate card and a
number reported by the CLI are different claims — one is OpenClink's arithmetic,
the other is the vendor's meter. Filing both under `cost` would make them
indistinguishable to every future consumer, so the reported one gets its own key.
"""

from __future__ import annotations

from pathlib import Path

from clink.agents.codex import CodexAgent
from clink.agents.opencode import OpenCodeAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole
from clink.parsers.base import ParsedCLIResponse
from tools.clink import CLinkTool

USAGE = {"input": 116_984, "output": 2, "reasoning": 11}


def _agent(cls, name: str, parser: str):
    role = ResolvedCLIRole(
        name="default",
        prompt_path=Path("systemprompts/clink/default.txt").resolve(),
        role_args=[],
    )
    client = ResolvedCLIClient(
        name=name,
        executable=[name],
        internal_args=[],
        config_args=[],
        env={},
        timeout_seconds=30,
        parser=parser,
        runner=None,
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return cls(client)


def _accounting(agent, metadata: dict) -> dict:
    output = agent.finalize_output(
        parsed=ParsedCLIResponse(content="OK", metadata=metadata),
        sanitized_command=[agent.client.name],
        returncode=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
    )
    return CLinkTool()._call_accounting(output)


def test_the_cost_opencode_measured_reaches_the_caller():
    """The figure is real, from a real run, and it was going nowhere.

    `0.007392` is the accumulated cost of the two-step file-read recorded in
    `CHANGES-FORK.md` — the same run whose per-step trap #85 documents.
    """
    accounting = _accounting(
        _agent(OpenCodeAgent, "opencode", "opencode_jsonl"),
        {"tokens": USAGE, "cost": 0.007392, "cost_unit": "USD"},
    )

    assert "cli_reported_cost" in accounting, (
        "opencode measured the cost of its own call and the caller was told nothing — "
        "the figure is in parsed.metadata['cost'] and never projected (#126)"
    )
    assert accounting["cli_reported_cost"]["value"] == 0.007392


def test_the_reported_cost_names_where_it_came_from():
    """Without provenance a consumer cannot tell a meter from a multiplication.

    Asserted as a distinct key rather than folded into `cost`, because `cost` is
    the rate-card figure and a caller comparing two clients must be able to see
    that one number was computed here and the other was not.
    """
    accounting = _accounting(
        _agent(OpenCodeAgent, "opencode", "opencode_jsonl"),
        {"tokens": USAGE, "cost": 0.007392, "cost_unit": "USD"},
    )

    assert accounting["cli_reported_cost"]["unit"] == "USD"
    # The parser name, because that is what actually produced the figure. A
    # `cli_name` would be a looser claim: two clients can share a parser, and the
    # provenance being asserted is "this specific reader read it off the CLI".
    assert accounting["cli_reported_cost"]["source"] == "opencode_jsonl"
    assert "cost" not in accounting, "the rate-card key must stay absent — nothing priced this call"


def test_a_reported_cost_of_zero_is_emitted_rather_than_swallowed():
    """`deepseek-v4-flash-free` genuinely reports `cost: 0`.

    Verified 2026-08-16 against the real binary: three runs on the free model all
    reported `"cost":0`. A truthiness check would drop it and turn *this call was
    free* into *cost unknown* — a different and worse claim, and exactly the
    distinction this module's docstring exists to protect. The parser already
    gets this right with `if cost is not None`; the projection must too.
    """
    accounting = _accounting(
        _agent(OpenCodeAgent, "opencode", "opencode_jsonl"),
        {"tokens": USAGE, "cost": 0, "cost_unit": "USD"},
    )

    assert "cli_reported_cost" in accounting, "a free call reported 0 and the projection swallowed it"
    assert accounting["cli_reported_cost"]["value"] == 0


def test_a_cost_with_no_declared_unit_is_not_reported():
    """The other half of "the unit travels with the number" (#25).

    A bare figure is worse than none: a caller routing across a dollar-metered
    client and a credit-metered one cannot sum them, and nothing in the payload
    would warn it. So a parser that publishes `cost` without `cost_unit` gets
    silence, not a guessed currency.
    """
    accounting = _accounting(
        _agent(OpenCodeAgent, "opencode", "opencode_jsonl"),
        {"tokens": USAGE, "cost": 0.5},
    )

    assert "cli_reported_cost" not in accounting


def test_a_client_that_reports_no_cost_is_unaffected():
    """The guard must be the presence of the key, not the name of the client.

    codex reports no cost at all, so nothing may appear for it. Asserted rather
    than reasoned: a projection keyed on `cli_name` would pass every test above
    and put an empty or zero figure on every other client.
    """
    accounting = _accounting(
        _agent(CodexAgent, "codex", "codex_jsonl"),
        {"usage": {"input_tokens": 100, "output_tokens": 5}},
    )

    assert "cli_reported_cost" not in accounting
    assert "cost" not in accounting
    assert "cost_unavailable" not in accounting
