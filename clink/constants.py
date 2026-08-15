"""Internal defaults and constants for clink."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_STREAM_LIMIT = 10 * 1024 * 1024  # 10MB per stream

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUILTIN_PROMPTS_DIR = PROJECT_ROOT / "systemprompts" / "clink"
CONFIG_DIR = PROJECT_ROOT / "conf" / "cli_clients"
USER_CONFIG_DIR = Path.home() / ".openclink" / "cli_clients"
# Where user overrides lived before the rename (#94). Still searched, because this
# directory is outside the repository and no sweep can migrate it: pointing only at
# the new path does not error, it silently stops applying whatever the user wrote.
# On this fork that is concrete — the documented Windows fix for cursor
# (`"env": {"SHELL": "cmd.exe"}`) lives in such a file, and losing it turns every
# cursor delegation into a text-only responder that answers with exit 0.
LEGACY_USER_CONFIG_DIR = Path.home() / ".pal" / "cli_clients"


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
    "opencode": CLIInternalDefaults(
        # `opencode run <message> --format json` writes one JSON event per line;
        # the reply is `part.text` on `type:"text"`. Close to codex's JSONL but a
        # different shape, so it gets its own parser (see clink/parsers/opencode.py).
        #
        # `--auto` is deliberately NOT passed. Verified 2026-08-11 against
        # opencode 1.18.15: a real `run` call without it exits 0. Its own docs say
        # most permissions already default to `allow`, and that `--auto` only
        # flips what would otherwise ask — so passing it buys little and gives up
        # the ability to deny anything specific. A declared `permission` block in
        # the user's `opencode.json` is the reviewable instrument; see #85.
        parser="opencode_jsonl",
        additional_args=["run", "--format", "json"],
        default_role_prompt="systemprompts/clink/default.txt",
        # No dedicated runner: opencode takes `-m provider/model`, which the base
        # already emits as `--model`. Its reasoning effort is a separate
        # `--variant` flag whose values are per-provider and unverified, so no
        # call sets it yet.
        runner=None,
    ),
}
