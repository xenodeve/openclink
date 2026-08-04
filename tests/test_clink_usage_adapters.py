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

from clink.agents.base import BaseCLIAgent, TokenUsage
from clink.agents.gemini import GeminiAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole
from clink.parsers.base import ParsedCLIResponse


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
