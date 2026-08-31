"""Which metadata key a client publishes its usage under is per-client (#24, slice 1).

`_extract_token_usage` hardcoded `metadata.get("usage")`. Codex and claude do
publish under that name, but **gemini publishes under `token_usage`** — verified
2026-08-05 at `clink/parsers/gemini.py:40`, which writes `metadata["token_usage"]`
and never writes `usage` at all. So a field map alone can never reach gemini's
account: the map describes the *fields inside* the payload, and the payload is
found under a key the base class was not looking at.

That makes the key the prerequisite slice. Written the other way round — adapters
first — every adapter after codex would be a correct map hung off a key that
never appears, and the tests would pass only because `None` is also what "no
adapter yet" returns. Absence and wrongness would be the same value.

Seam: `BaseCLIAgent.finalize_output`, the documented single construction site for
`AgentOutput` — so this pins what a *caller* receives, not how the extraction is
spelled internally.
"""

from __future__ import annotations

from pathlib import Path

from clink.agents.base import BaseCLIAgent, TokenUsage
from clink.agents.codex import CodexAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole
from clink.parsers.base import ParsedCLIResponse

FIELD_MAP = {"input_tokens": "input_tokens", "output_tokens": "output_tokens"}

# Shaped like gemini's — the payload is identical, only the key differs.
PAYLOAD = {"input_tokens": 4210, "output_tokens": 77}
EXPECTED = TokenUsage(input_tokens=4210, output_tokens=77)


class _KeyedAgent(BaseCLIAgent):
    """A client that publishes usage under its own key, as gemini does."""

    USAGE_METADATA_KEY = "token_usage"
    USAGE_FIELD_MAP = FIELD_MAP


class _DefaultKeyAgent(BaseCLIAgent):
    """A client that declares no key — must keep reading `usage`."""

    USAGE_FIELD_MAP = FIELD_MAP


def _client(name: str) -> tuple[ResolvedCLIClient, ResolvedCLIRole]:
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
        parser="codex_jsonl",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return client, role


def _finalize(agent: BaseCLIAgent, metadata: dict) -> TokenUsage | None:
    output = agent.finalize_output(
        parsed=ParsedCLIResponse(content="OK", metadata=metadata),
        sanitized_command=[agent.client.name],
        returncode=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
    )
    return output.token_usage


def test_a_client_can_declare_the_metadata_key_its_cli_publishes_usage_under():
    client, _ = _client("gemini-like")
    assert _finalize(_KeyedAgent(client), {"token_usage": PAYLOAD}) == EXPECTED


def test_the_declared_key_is_the_only_one_read():
    # Not merely "either key works". If the base kept falling back to `usage`,
    # a client whose CLI publishes both — claude does, under `usage` and
    # `model_usage` — would silently account the wrong one, and slice 3 would
    # inherit a bug that looks like a passing test.
    client, _ = _client("gemini-like")
    metadata = {"token_usage": PAYLOAD, "usage": {"input_tokens": 1, "output_tokens": 1}}
    assert _finalize(_KeyedAgent(client), metadata) == EXPECTED


def test_a_client_that_declares_no_key_still_reads_usage():
    # Control: passes before and after. The default must not move, or this slice
    # stops being preparation and becomes a behaviour change to every client.
    client, _ = _client("codex-like")
    assert _finalize(_DefaultKeyAgent(client), {"usage": PAYLOAD}) == EXPECTED


def test_the_shipped_codex_adapter_is_unaffected():
    # Control: the one adapter that already works, exercised through its real
    # class rather than a stub, so a regression in it cannot hide behind one.
    client, _ = _client("codex")
    usage = {"input_tokens": 20252, "cached_input_tokens": 0, "output_tokens": 5, "reasoning_output_tokens": 0}
    assert _finalize(CodexAgent(client), {"usage": usage}) == TokenUsage(
        input_tokens=20252,
        cached_input_tokens=0,
        output_tokens=5,
        reasoning_output_tokens=0,
    )
