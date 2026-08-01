---
name: clink-zero-setup-discovery
description: "bare clink commands are discovery-resolved to absolute paths; ~/.pal/cli_clients overrides; claude-9arm ships active"
metadata:
  type: reference
---

Bundled client configs use a **bare** `command` (`agy`/`claude`/`codex`/`gemini`). `clink/discovery.py`
(`resolve_cli_command`, wired into `registry._resolve_executable`) resolves it: **PATH first, then
per-CLI known install locations** (winget, `%LOCALAPPDATA%\agy\bin`, `%APPDATA%\npm`). This is why a
CLI installed under a user-profile dir still works when the editor launches PAL with a minimal PATH.
Unresolved → the bare name passes through → a clear call-time "not found in PATH" (a missing CLI is
a graceful per-client error, not a registry-load failure). The registry also expands `~`/`%VAR%` in
`config_args`.

`conf/cli_clients/claude-9arm.json` **ships active** (this fork's 9arm Qwen gateway: bare `claude`
+ `--settings ~/.claude-9arm.json --model qwen3.6-35b-a3b`); `.example` stays as the generic
template. For a custom path/gateway, drop an override in **`~/.pal/cli_clients/*.json`** — the
registry reads it last (overrides the bundled config), it survives reinstalls, and it's shared by
every PAL install on the machine (see [[pal-two-installs-and-config-cache]]).

**How to apply:** to add a machine-specific client/path, prefer `~/.pal/cli_clients/` over editing
site-packages (which a reinstall wipes). Discovery is Windows-tuned; add per-OS candidates in
`discovery.py` for macOS/Linux. Related: [[clink-per-call-model-effort]].
