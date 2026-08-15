"""Best-effort discovery of CLI executables so bundled configs work with zero setup.

Bundled client configs use a bare command name (`agy`, `claude`, `codex`, `gemini`). When
the editor launches OpenClink with a minimal `PATH`, a CLI installed under a user-profile location
(winget / `%LOCALAPPDATA%` / `npm`) isn't on that `PATH`, so a bare command fails to resolve.
`resolve_cli_command()` looks the command up on `PATH` first, then against per-CLI known
install locations. If nothing is found it returns the input unchanged, so the agent's
call-time check produces a clear "not found in PATH" error rather than guessing.

Locations are Windows-focused (this fork's primary platform); on other OSes the `%VAR%`
paths simply don't resolve and it degrades to `PATH`-only lookup.
"""

from __future__ import annotations

import os
import shutil
from glob import glob
from pathlib import Path

# Exact candidate paths, checked after PATH (first existing one wins).
_KNOWN_LOCATIONS: dict[str, list[str]] = {
    "agy": [r"%LOCALAPPDATA%\agy\bin\agy.exe"],
    "claude": [r"%APPDATA%\npm\claude.cmd", r"~\.local\bin\claude.exe"],
    "codex": [r"%APPDATA%\npm\codex.cmd"],
    "gemini": [r"%APPDATA%\npm\gemini.cmd"],
    # Installed by bun, which does not put its bin dir on PATH — verified absent
    # from PATH on this machine 2026-08-11 while the binary was present.
    "opencode": [r"~\.bun\bin\opencode.exe"],
}

# Glob candidates (e.g. winget package dirs carry a version/hash suffix).
_GLOB_LOCATIONS: dict[str, list[str]] = {
    "claude": [r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Anthropic.ClaudeCode_*\claude.exe"],
}


def _expand(p: str) -> str:
    return os.path.expandvars(os.path.expanduser(p))


def resolve_cli_command(command: str) -> str:
    """Resolve a bare CLI command to an absolute path (PATH → known locations).

    Returns the input unchanged if it's already a path or nothing is found.
    """
    if not command:
        return command
    # Already a path (has a separator) → leave it to the caller / call-time check.
    if os.sep in command or (os.altsep and os.altsep in command):
        return _expand(command)

    on_path = shutil.which(command)
    if on_path:
        return on_path

    key = command.lower()
    for cand in _KNOWN_LOCATIONS.get(key, []):
        expanded = _expand(cand)
        if Path(expanded).exists():
            return expanded
    for pattern in _GLOB_LOCATIONS.get(key, []):
        matches = sorted(glob(_expand(pattern)))
        if matches:
            return matches[-1]  # newest by name (version-suffixed)

    return command
