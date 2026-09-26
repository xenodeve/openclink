"""A second Claude Code profile for a local Anthropic-compatible server (2026-09-26).

The developer runs Qwen3.8-27B on a local EXL3 server and wants it as a clink subagent
beside claude-9arm. The registry only accepts CLI names listed in INTERNAL_DEFAULTS, so a
user override named claude-exl3 failed with "CLI 'claude-exl3' is not supported by clink".
"""
import json

from clink.constants import INTERNAL_DEFAULTS
from clink.registry import ClinkRegistry


def test_claude_exl3_is_a_known_cli_with_claude_output_parsing():
    d = INTERNAL_DEFAULTS["claude-exl3"]
    assert d.parser == "claude_json" and d.runner == "claude"
    assert d.additional_args == INTERNAL_DEFAULTS["claude-9arm"].additional_args


def test_a_claude_exl3_user_override_loads(tmp_path, monkeypatch):
    cfg = {"name": "claude-exl3", "command": "claude",
           "additional_args": ["--settings", "~/.claude-xeno-exl3.json", "--model", "qwen3.8-27b-exl3"],
           "roles": {"default": {"prompt_path": "systemprompts/clink/default.txt", "role_args": []}}}
    (tmp_path / "claude-exl3.json").write_text(json.dumps(cfg))
    monkeypatch.setenv("CLI_CLIENTS_CONFIG_PATH", str(tmp_path))
    reg = ClinkRegistry()
    assert "claude-exl3" in reg.list_clients()
