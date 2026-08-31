"""Per-client usage adapters onto the normalised account (#24).

One table per client. Each adapter maps the CLI's own spelling onto
`TokenUsage`; a class the CLI does not report stays `None`, because an
unreported field and a reported zero are different facts and only the first may
be filled in later.

**Provenance of the gemini payload, stated because the issue asks for recorded
runs.** The *shape* is recorded: `clink/parsers/gemini.py:38` reads
`stats.models[<model>].tokens`, and `tests/test_clink_gemini_parser.py` carries a
verbatim `gemini -o json` envelope whose token block is
`{"prompt", "candidates", "total", "cached", "thoughts", "tool"}`. The
*magnitudes* here are not recorded, and could not be: that captured run was
rate-limited, so every count in it is `0` — and a fixture of all zeros cannot
tell a correct map from any permutation of itself. The gemini CLI is not
installed on this machine (`Get-Command gemini` → not found, 2026-08-05), so a
fresh run was not available to record. Distinct values are therefore chosen so
the mapping is falsifiable; the field names are the part taken from reality.

**Search boundary:** a token class that appears only in some other gemini run
would not be in that envelope and so is not mapped here. The failure direction
is the safe one — an unmapped key stays absent rather than landing in the wrong
field.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clink.agents.antigravity import AntigravityAgent
from clink.agents.base import BaseCLIAgent, TokenUsage
from clink.agents.claude import ClaudeAgent
from clink.agents.cursor import CursorAgent
from clink.agents.gemini import GeminiAgent
from clink.agents.opencode import OpenCodeAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole
from clink.parsers.base import ParsedCLIResponse
from tools.clink import CLinkTool


def _agent(cls: type[BaseCLIAgent], name: str, parser: str) -> BaseCLIAgent:
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
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return cls(client)


def _account(agent: BaseCLIAgent, metadata: dict) -> TokenUsage | None:
    return agent.finalize_output(
        parsed=ParsedCLIResponse(content="OK", metadata=metadata),
        sanitized_command=[agent.client.name],
        returncode=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
    ).token_usage


GEMINI_CASES = [
    pytest.param(
        {"prompt": 8123, "candidates": 214, "total": 8337, "cached": 4096, "thoughts": 61, "tool": 0},
        TokenUsage(input_tokens=8123, cached_input_tokens=4096, output_tokens=214, reasoning_output_tokens=61),
        id="all-classes-reported",
    ),
    pytest.param(
        # `thoughts` absent entirely - a non-thinking model's block.
        {"prompt": 512, "candidates": 33, "total": 545, "cached": 0, "tool": 0},
        TokenUsage(input_tokens=512, cached_input_tokens=0, output_tokens=33, reasoning_output_tokens=None),
        id="no-thinking-tokens-reported",
    ),
    pytest.param(
        # The recorded rate-limited envelope, kept for the shape rather than the
        # numbers: zeros must survive as zeros, not collapse to absent.
        {"prompt": 0, "candidates": 0, "total": 0, "cached": 0, "thoughts": 0, "tool": 0},
        TokenUsage(input_tokens=0, cached_input_tokens=0, output_tokens=0, reasoning_output_tokens=0),
        id="recorded-rate-limited-run",
    ),
]


@pytest.mark.parametrize("tokens,expected", GEMINI_CASES)
def test_gemini_usage_maps_onto_the_normalised_account(tokens, expected):
    agent = _agent(GeminiAgent, "gemini", "gemini_json")
    assert _account(agent, {"token_usage": tokens}) == expected


def test_gemini_totals_are_not_mapped_anywhere():
    # `total` and `tool` have no normalised counterpart. Landing either in a
    # real field would make the account silently wrong rather than incomplete,
    # and `total` is the tempting one because it is numerically plausible in
    # `input_tokens`.
    agent = _agent(GeminiAgent, "gemini", "gemini_json")
    account = _account(agent, {"token_usage": {"total": 9999, "tool": 7}})
    assert account is None


def test_gemini_reads_its_own_key_not_usage():
    # gemini's parser never writes `usage`. If the base default were still in
    # force this would report nothing, which is the bug slice 1 exists to stop.
    agent = _agent(GeminiAgent, "gemini", "gemini_json")
    assert _account(agent, {"usage": {"prompt": 1, "candidates": 2}}) is None


# Recorded verbatim from `claude -p "Reply with exactly: OK" --output-format json`
# on 2026-08-05. Both blocks come from the SAME run, which is the point of
# keeping them together: for a single-model call they agree exactly, so no
# fixture taken from such a run can tell the two sources apart. The choice
# between them is pinned by its own test below, not by this payload.
CLAUDE_RECORDED_USAGE = {
    "input_tokens": 2,
    "cache_creation_input_tokens": 24477,
    "cache_read_input_tokens": 20327,
    "output_tokens": 4,
    "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
    "service_tier": "standard",
    "cache_creation": {"ephemeral_1h_input_tokens": 24477, "ephemeral_5m_input_tokens": 0},
}
CLAUDE_RECORDED_MODEL_USAGE = {
    "claude-opus-5[1m]": {
        "inputTokens": 2,
        "outputTokens": 4,
        "cacheReadInputTokens": 20327,
        "cacheCreationInputTokens": 24477,
        "webSearchRequests": 0,
        "costUSD": 0.2550435,
        "contextWindow": 1000000,
    }
}

CLAUDE_CASES = [
    pytest.param(
        CLAUDE_RECORDED_USAGE,
        TokenUsage(input_tokens=2, cached_input_tokens=20327, output_tokens=4, reasoning_output_tokens=None),
        id="recorded-real-run",
    ),
    pytest.param(
        # A run with nothing read from cache. Zero is a reported fact here and
        # must survive as zero.
        {"input_tokens": 1500, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 88},
        TokenUsage(input_tokens=1500, cached_input_tokens=0, output_tokens=88, reasoning_output_tokens=None),
        id="no-cache-read",
    ),
]


@pytest.mark.parametrize("usage,expected", CLAUDE_CASES)
def test_claude_usage_maps_onto_the_normalised_account(usage, expected):
    agent = _agent(ClaudeAgent, "claude", "claude_json")
    assert _account(agent, {"usage": usage}) == expected


def test_claude_reads_the_flat_usage_block_not_the_per_model_one():
    # claude publishes both. They agree on a single-model run, so this case
    # makes them disagree on purpose - otherwise the design choice would be
    # untested and slice 4 would inherit it as an assumption.
    agent = _agent(ClaudeAgent, "claude", "claude_json")
    metadata = {
        "usage": {"input_tokens": 2, "cache_read_input_tokens": 20327, "output_tokens": 4},
        "model_usage": {"claude-opus-5[1m]": {"inputTokens": 999, "outputTokens": 999}},
    }
    account = _account(agent, metadata)
    assert account == TokenUsage(input_tokens=2, cached_input_tokens=20327, output_tokens=4)


def test_claude_cache_creation_tokens_are_not_folded_into_cache_reads():
    # A KNOWN GAP, pinned so it cannot be closed by accident and cannot be
    # mistaken for an oversight. `cache_creation_input_tokens` is billed and the
    # normalised account has no field for it - in the recorded run it was 24477
    # against 2 input tokens, so dropping it under-reports by four orders of
    # magnitude. Folding it into `cached_input_tokens` would be worse than
    # dropping it: that field means cache *reads* everywhere else, so the
    # account would be wrong rather than incomplete. Adding a field changes the
    # account #23 shipped, so it is parked as its own decision.
    agent = _agent(ClaudeAgent, "claude", "claude_json")
    account = _account(agent, {"usage": CLAUDE_RECORDED_USAGE})
    assert 24477 not in vars(account).values()


# Recorded verbatim from `opencode run --format json -m opencode-go/deepseek-v4-flash`
# on 2026-08-11 (opencode 1.18.15) — the `part.tokens` block of the `step_finish`
# event. Unlike the gemini fixture the magnitudes here are real: the 121702 input
# against 3 output is OpenCode's own agent context, not the one-sentence prompt.
OPENCODE_RECORDED_TOKENS = {
    "total": 121705,
    "input": 121702,
    "output": 3,
    "reasoning": 0,
    "cache": {"write": 0, "read": 0},
}

OPENCODE_CASES = [
    pytest.param(
        OPENCODE_RECORDED_TOKENS,
        # `cached_input_tokens=0` rather than `None` since #127: this run really
        # did read nothing from cache, and a REPORTED ZERO is a different fact
        # from an unreported class. Before #127 both read as `None`, which is
        # exactly the confusion the account's absence convention exists to avoid.
        TokenUsage(input_tokens=121702, cached_input_tokens=0, output_tokens=3, reasoning_output_tokens=0),
        id="recorded-real-run",
    ),
    pytest.param(
        # A reasoning model's block, with cache actually used. Chosen distinct so
        # the map is falsifiable — the recorded run has 0 in three places, and a
        # fixture cannot tell a correct map from a permutation of its own zeros.
        {"total": 9000, "input": 8000, "output": 900, "reasoning": 100, "cache": {"write": 500, "read": 7000}},
        TokenUsage(input_tokens=8000, cached_input_tokens=7000, output_tokens=900, reasoning_output_tokens=100),
        id="reasoning-and-cache-used",
    ),
]


@pytest.mark.parametrize("tokens,expected", OPENCODE_CASES)
def test_opencode_usage_maps_onto_the_normalised_account(tokens, expected):
    agent = _agent(OpenCodeAgent, "opencode", "opencode_jsonl")
    assert _account(agent, {"tokens": tokens}) == expected


def test_opencode_reads_its_own_key_not_usage():
    # opencode's parser writes `tokens`; nothing writes `usage`. If the base
    # default were still in force this client would report nothing at all while
    # the CLI was reporting a full account.
    agent = _agent(OpenCodeAgent, "opencode", "opencode_jsonl")
    assert _account(agent, {"usage": OPENCODE_RECORDED_TOKENS}) is None


def test_opencode_totals_are_not_mapped_anywhere():
    # `total` is the tempting one: it is numerically plausible in `input_tokens`
    # and would make the account silently wrong rather than incomplete.
    agent = _agent(OpenCodeAgent, "opencode", "opencode_jsonl")
    assert _account(agent, {"tokens": {"total": 121705}}) is None


def test_opencode_cache_read_lands_in_cached_input_tokens():
    """The half of the old gap that never needed #56's decision (#127).

    This test used to assert the opposite, and the reasoning that put it there
    bundled two different problems: `cache.write` has no field on the account at
    all — a SCHEMA question, and #56's to answer — while `cache.read` has exactly
    the right field and merely could not be *reached*, because the field map was
    flat and `cache` is a dict. The second is a traversal problem, so it waited
    on a decision it never required.

    Worth more than "incomplete": on the real two-step run recorded in
    `CHANGES-FORK.md` the dropped class was **larger than the reported one** —
    102,535 input against 144,256 cache-read. Anyone reasoning about cache
    effectiveness from that account was wrong by more than a factor of two, with
    nothing in the payload to say so.
    """
    agent = _agent(OpenCodeAgent, "opencode", "opencode_jsonl")
    account = _account(
        agent,
        {"tokens": {"input": 8000, "output": 900, "cache": {"write": 500, "read": 7000}}},
    )
    assert account.cached_input_tokens == 7000


def test_opencode_cache_write_still_has_nowhere_to_go():
    """The other half, and it stays pinned — #56 is unanswered.

    Kept as its own test rather than deleted with the split, because the reason
    it is absent is now different from its neighbour's: not "cannot reach it" but
    "there is nothing to reach". Reporting an absent field is incomplete;
    inventing a home for it here would pre-empt the schema decision and make the
    account wrong instead.
    """
    agent = _agent(OpenCodeAgent, "opencode", "opencode_jsonl")
    account = _account(
        agent,
        {"tokens": {"input": 8000, "output": 900, "cache": {"write": 500, "read": 7000}}},
    )
    assert 500 not in vars(account).values()


def test_a_nested_key_whose_parent_is_missing_or_not_a_dict_yields_no_field():
    """Traversal must fail to absence, never to an exception (#127).

    A CLI that stops reporting a block, or reports it as a scalar in some mode,
    must degrade to an incomplete account — not take down the call that produced
    it. Both shapes, because they fail at different steps of the walk.
    """
    agent = _agent(OpenCodeAgent, "opencode", "opencode_jsonl")

    missing = _account(agent, {"tokens": {"input": 8000, "output": 900}})
    assert missing.cached_input_tokens is None
    assert missing.input_tokens == 8000

    scalar = _account(agent, {"tokens": {"input": 8000, "output": 900, "cache": 12}})
    assert scalar.cached_input_tokens is None
    assert scalar.input_tokens == 8000


def test_a_boolean_in_a_usage_payload_is_not_counted_as_a_token():
    """`bool` is a subclass of `int`, so the obvious guard admits `True` as 1.

    The same trap was already fixed once in `clink/parsers/opencode.py::_accumulate`
    for the same reason. No CLI reports a boolean token count today; this costs
    one clause and removes a class of silently-wrong account.
    """
    agent = _agent(OpenCodeAgent, "opencode", "opencode_jsonl")
    account = _account(agent, {"tokens": {"input": True, "output": 900}})
    assert account.input_tokens is None
    assert account.output_tokens == 900


def test_every_configured_client_either_accounts_or_says_it_cannot():
    """The acceptance criterion in its own words, checked against the real registry.

    Every test above builds its agent by hand, so all of them would still pass
    if a client were wired to the wrong class — which is exactly the defect
    `cursor` had: no agent class at all, so it fell through to the same fallback
    an unknown client gets. This is the only test here that would notice.
    """
    from clink.agents import create_agent
    from clink.registry import get_registry

    registry = get_registry()
    names = registry.list_clients()
    assert names, "no clients configured — this test would pass vacuously"

    for name in names:
        agent_cls = type(create_agent(registry.get_client(name)))
        declares_adapter = bool(agent_cls.USAGE_FIELD_MAP)
        declares_unavailable = agent_cls.USAGE_UNAVAILABLE
        assert declares_adapter != declares_unavailable, (
            f"{name} ({agent_cls.__name__}) must do exactly one of the two: "
            f"map its CLI's usage, or declare that its CLI reports none. "
            f"adapter={declares_adapter} unavailable={declares_unavailable}"
        )


def _accounting(agent: BaseCLIAgent, metadata: dict) -> dict:
    output = agent.finalize_output(
        parsed=ParsedCLIResponse(content="OK", metadata=metadata),
        sanitized_command=[agent.client.name],
        returncode=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
    )
    return CLinkTool()._call_accounting(output)


class _NoAdapterYetAgent(BaseCLIAgent):
    """A client nobody has written an adapter for — the third state."""


def test_a_cli_that_reports_no_usage_says_so_explicitly():
    # Required case, not an edge case. Without it, `cursor` and `antigravity`
    # are indistinguishable from a client whose adapter was never written, and
    # a cost report cannot tell "this call was free to account for" from "this
    # call's cost is unknown".
    for cls, name, parser in (
        (AntigravityAgent, "antigravity", "antigravity_text"),
        (CursorAgent, "cursor", "codex_jsonl"),
    ):
        accounting = _accounting(_agent(cls, name, parser), {})
        assert accounting["usage_unavailable"] is True, name
        assert "normalized_usage" not in accounting, name


def test_an_unwritten_adapter_stays_silent_rather_than_claiming_unavailable():
    # The distinction the whole marker exists for. "No adapter yet" is a fact
    # about OpenClink; "the CLI reports nothing" is a fact about the CLI. Collapsing
    # them would let an unfinished adapter read as a finished one.
    accounting = _accounting(_agent(_NoAdapterYetAgent, "someone-new", "codex_jsonl"), {})
    assert "usage_unavailable" not in accounting
    assert "normalized_usage" not in accounting


def test_a_client_that_does_report_usage_carries_no_unavailable_marker():
    # Control: passes before and after. The marker must not leak onto clients
    # that account normally.
    accounting = _accounting(_agent(ClaudeAgent, "claude", "claude_json"), {"usage": CLAUDE_RECORDED_USAGE})
    assert "usage_unavailable" not in accounting
    assert accounting["normalized_usage"]["input_tokens"] == 2


def test_the_marker_is_not_zeros():
    # The AC's actual demand, checked a layer below the accounting dict: an
    # unavailable account must not be reported as an account OF ZERO, which
    # would be a false statement about a call that may have cost a great deal.
    account = _account(_agent(AntigravityAgent, "antigravity", "antigravity_text"), {})
    assert account is None


def test_claude_ignores_non_integer_members_of_the_usage_block():
    # The recorded block carries nested dicts and a string. A mapper that
    # forwarded them would produce a TokenUsage whose fields are not numbers.
    agent = _agent(ClaudeAgent, "claude", "claude_json")
    account = _account(agent, {"usage": CLAUDE_RECORDED_USAGE})
    assert all(v is None or isinstance(v, int) for v in vars(account).values())
