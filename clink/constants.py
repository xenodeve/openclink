"""Internal defaults and constants for clink."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_STREAM_LIMIT = 10 * 1024 * 1024  # 10MB per stream

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUILTIN_PROMPTS_DIR = PROJECT_ROOT / "systemprompts" / "clink"
CONFIG_DIR = PROJECT_ROOT / "conf" / "cli_clients"
USER_CONFIG_DIR = Path.home() / ".pal" / "cli_clients"


@dataclass(frozen=True)
class CLIInternalDefaults:
    """Internal defaults applied to a CLI client during registry load."""

    parser: str
    additional_args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    default_role_prompt: str | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    runner: str | None = None


INTERNAL_DEFAULTS: dict[str, CLIInternalDefaults] = {
    "gemini": CLIInternalDefaults(
        parser="gemini_json",
        additional_args=["-o", "json"],
        default_role_prompt="systemprompts/clink/default.txt",
        runner="gemini",
    ),
    "codex": CLIInternalDefaults(
        parser="codex_jsonl",
        additional_args=["exec"],
        default_role_prompt="systemprompts/clink/default.txt",
        runner="codex",
    ),
    "claude": CLIInternalDefaults(
        parser="claude_json",
        additional_args=["--print", "--output-format", "json"],
        default_role_prompt="systemprompts/clink/default.txt",
        runner="claude",
    ),
    "claude-9arm": CLIInternalDefaults(
        parser="claude_json",
        additional_args=["--print", "--output-format", "json"],
        default_role_prompt="systemprompts/clink/default.txt",
        runner="claude",
    ),
    "antigravity": CLIInternalDefaults(
        parser="antigravity_text",
        additional_args=["--print"],
        default_role_prompt="systemprompts/clink/default.txt",
        runner="antigravity",
    ),
    "cursor": CLIInternalDefaults(
        # `cursor-agent -p` reads the prompt from stdin and writes a plain-text
        # reply to stdout, so the ANSI-stripping antigravity_text parser fits.
        # Its JSON shape differs from Claude Code's, so claude_json is not usable.
        # `--trust` is required for non-interactive runs in an untrusted directory.
        parser="antigravity_text",
        additional_args=["-p", "--trust", "--output-format", "text"],
        default_role_prompt="systemprompts/clink/default.txt",
        # No dedicated runner: BaseCLIAgent already emits `--model <model>`, and
        # cursor bakes reasoning effort into the model name (e.g. `-high`/`-xhigh`).
        runner=None,
    ),
}
