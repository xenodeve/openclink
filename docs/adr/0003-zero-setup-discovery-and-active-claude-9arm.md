# 0003. Zero-setup CLI discovery + ship `claude-9arm` active, with a user-dir override

- **Status:** Accepted (2026-07-16)
- **Commits:** `d44ae01` (discovery + active claude-9arm), `1e435a6` (user-dir override doc)

## Context

Installing PAL and having `codex` / `antigravity` / `claude-9arm` work should require **no extra
setup**; a CLI that isn't installed should surface a clear "not found", not a load failure. Two
obstacles: (1) editors launch PAL with a minimal `PATH` that omits user-profile install dirs
(winget, `%LOCALAPPDATA%\agy\bin`, npm), so a bundled config's bare command fails to resolve; (2)
`claude-9arm` needs a gateway `--settings` path + model, and there are **multiple separate PAL
installs** on a machine (a `uv tool` install for the editor, a `uvx` env for Codex) — editing one
install's `conf/` is ephemeral (a reinstall wipes it) and doesn't reach the other.

## Decision

Resolve executables at load time and ship `claude-9arm` active; keep a user-level override dir as the
escape hatch.

- `clink/discovery.py` (`resolve_cli_command`, wired into `registry._resolve_executable`) resolves a
  bare command via **PATH first, then per-CLI known install locations**. Unresolved → the bare name
  passes through → the agent's call-time `shutil.which` produces a clear "not found in PATH".
- `clink/registry.py` expands `~` / `%VAR%` in `config_args` (so `--settings ~/.claude-9arm.json` is
  portable).
- `conf/cli_clients/claude-9arm.json` ships **active** (this fork's 9arm Qwen gateway); `.example`
  stays as the generic template.
- Machine-specific overrides live in **`~/.pal/cli_clients/*.json`** (`USER_CONFIG_DIR`,
  `clink/constants.py:14`), read **last** by `registry._iter_config_files` so they override the
  bundled config, survive reinstalls, and are **shared by every PAL install** on the machine.

## Consequences

- A fresh install exposes all clients; each runs if its CLI is present, else reports "not found" —
  the graceful-degradation contract.
- `discovery.py`'s known locations are **Windows-tuned**; on other OSes it degrades to PATH-only until
  per-OS candidates are added (open work).
- Shipping `claude-9arm` active bakes this fork's 9arm gateway convention into the bundled config;
  other gateways use the `.example` or a `~/.pal` override.
- Editing site-packages `conf/` is discouraged (reinstall-wiped, per-install) — prefer `~/.pal`.

Related: [ADR 0002](0002-per-call-model-effort-per-backend.md); memory
[[pal-two-installs-and-config-cache]], [[clink-zero-setup-discovery]].
