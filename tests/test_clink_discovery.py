"""CLI executable discovery — bundled configs resolve bare commands with zero setup."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from clink.discovery import resolve_cli_command


def test_unknown_command_passes_through_unchanged():
    # An unresolvable CLI name is returned as-is → the agent's call-time
    # `shutil.which` check then produces a clear "not found in PATH" error.
    name = "definitely-not-a-real-cli-xyz-123"
    assert resolve_cli_command(name) == name


def test_command_with_separator_is_treated_as_a_path():
    # A value that already looks like a path is not looked up on PATH; it's just
    # user/env-expanded and returned.
    assert resolve_cli_command("/opt/tools/foo").endswith("foo")


def test_home_and_env_are_expanded_for_paths():
    expanded = resolve_cli_command("~/some/tool")
    assert "~" not in expanded
    assert expanded.endswith(os.path.join("some", "tool")) or expanded.endswith("some/tool")


def test_empty_command_passes_through():
    assert resolve_cli_command("") == ""


# opencode installs under `~/.bun/bin` and is genuinely absent from `PATH` on the
# machine this was written on (`Get-Command opencode` → not found, 2026-08-11),
# which is exactly the case `_KNOWN_LOCATIONS` exists for. The skip is honest
# rather than convenient: on a machine without the binary there is nothing to
# resolve to, and asserting the constant instead of the behaviour would pass
# even if `resolve_cli_command` stopped consulting known locations at all.
_BUN_OPENCODE = Path.home() / ".bun" / "bin" / "opencode.exe"


@pytest.mark.skipif(not _BUN_OPENCODE.exists(), reason="opencode not installed under ~/.bun/bin")
def test_opencode_resolves_from_its_bun_install_when_not_on_path():
    resolved = resolve_cli_command("opencode")
    assert os.path.isabs(resolved), f"stayed a bare name: {resolved!r}"
    assert Path(resolved).exists()
    assert Path(resolved).name.lower().startswith("opencode")
