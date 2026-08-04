"""A rate card declared in config reaches the caller as a cost figure (#25).

Three seams, each pinned separately because a break in any one of them looks
identical from the others: the config loads the card, the agent prices the call,
and the tool projects the figure with its unit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clink.agents.codex import CodexAgent
from clink.models import ModelRate, RateCard, ResolvedCLIClient, ResolvedCLIRole
from clink.parsers.base import ParsedCLIResponse
from clink.registry import ClinkRegistry
from tools.clink import CLinkTool

CARD = RateCard(
    unit="USD",
    per_tokens=1_000_000,
    models={"gpt-5.6-luna": ModelRate(input=10.0, cached_input=1.0, output=30.0, reasoning_output=30.0)},
)

# The account codex reports for this payload, priced by hand against CARD:
#   input          100_000 / 1e6 * 10 = 1.00
#   cached input   900_000 / 1e6 *  1 = 0.90
#   output          20_000 / 1e6 * 30 = 0.60
#   reasoning       10_000 / 1e6 * 30 = 0.30
#                                     = 2.80
USAGE = {
    "input_tokens": 100_000,
    "cached_input_tokens": 900_000,
    "output_tokens": 20_000,
    "reasoning_output_tokens": 10_000,
}
EXPECTED_COST = 2.80


def _codex(rate_card: RateCard | None) -> CodexAgent:
    role = ResolvedCLIRole(
        name="default",
        prompt_path=Path("systemprompts/clink/default.txt").resolve(),
        role_args=[],
    )
    client = ResolvedCLIClient(
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
        rate_card=rate_card,
    )
    return CodexAgent(client)


def _accounting(agent: CodexAgent, metadata: dict, command: list[str]) -> dict:
    output = agent.finalize_output(
        parsed=ParsedCLIResponse(content="OK", metadata=metadata),
        sanitized_command=command,
        returncode=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
    )
    return CLinkTool()._call_accounting(output)


def test_a_declared_rate_card_survives_config_loading(tmp_path, monkeypatch):
    # The card has to come off DISK through the real loader, not out of a
    # constructor - a schema field the loader drops on the floor would pass
    # every other test in this file.
    config = {
        "name": "codex",
        "command": "codex",
        "roles": {"default": {"prompt_path": "systemprompts/clink/default.txt"}},
        "rate_card": {
            "unit": "USD",
            "per_tokens": 1_000_000,
            "models": {"gpt-5.6-luna": {"input": 10.0, "cached_input": 1.0, "output": 30.0}},
        },
    }
    (tmp_path / "codex.json").write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("CLI_CLIENTS_CONFIG_PATH", str(tmp_path))

    client = ClinkRegistry().get_client("codex")

    assert client.rate_card is not None
    assert client.rate_card.unit == "USD"
    assert client.rate_card.models["gpt-5.6-luna"].cached_input == 1.0


def test_a_client_with_no_rate_card_still_loads_and_runs():
    # Control: the card is optional, and its absence must not be an error.
    accounting = _accounting(_codex(None), {"usage": USAGE}, ["codex", "-m", "gpt-5.6-luna"])
    assert accounting["normalized_usage"]["input_tokens"] == 100_000
    assert "cost" not in accounting
    # And SILENT, not marked unavailable. "Nobody has configured a rate card"
    # is a fact about PAL, exactly like "nobody has written this adapter" in
    # #24 slice 4 - and that was deliberately left silent so that a marker
    # always means a fact about the CLI or the call. Marking it here would put
    # `cost_unavailable` on every response of every client, which is how a
    # signal stops being one.
    assert "cost_unavailable" not in accounting


def test_the_cost_reaches_the_caller_with_its_unit():
    accounting = _accounting(_codex(CARD), {"usage": USAGE}, ["codex", "-m", "gpt-5.6-luna"])
    assert accounting["cost"]["value"] == pytest.approx(EXPECTED_COST)
    assert accounting["cost"]["unit"] == "USD"


def test_an_unpriceable_call_reports_why_instead_of_a_number():
    # A model released this morning. Not an error, not zero, not silence.
    accounting = _accounting(_codex(CARD), {"usage": USAGE}, ["codex", "-m", "gpt-9-unreleased"])
    assert "cost" not in accounting
    assert accounting["cost_unavailable"] == "model_not_priced"


def test_a_client_whose_cli_reports_no_usage_says_so_rather_than_pricing_nothing():
    # Reaches through #24's marker: antigravity reports no usage at all, so
    # there is nothing to price and the reason must say that, not "unknown
    # model".
    accounting = _accounting(_codex(CARD), {}, ["codex", "-m", "gpt-5.6-luna"])
    assert accounting["cost_unavailable"] == "no_usage_reported"
