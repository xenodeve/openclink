---
name: pal-two-installs-and-config-cache
description: "Claude Code's OpenClink (uv-tool) vs Codex's OpenClink (uvx) are separate installs; ~/.pal is shared; config cached at start; reinstall wipes site-packages conf"
metadata:
  type: reference
---

On this machine there is **more than one OpenClink install**, and they don't share code:

- **Claude Code's OpenClink** runs from a **`uv tool install`** (`~/AppData/Roaming/uv/tools/pal-mcp-server/`).
- **Codex's OpenClink** runs from **`uvx --from git+…`** (per `~/.codex/config.toml`) — a separate cached env.
- A third source-tree clone (`~/pal-mcp-server/.openclink_venv`) may also exist.

Consequences learned the hard way:

- **Config is cached at process start.** Editing a `conf/cli_clients/*.json` needs a full OpenClink
  **restart** (kill the process + reconnect / restart the editor) — a `/mcp` *reconnect* alone
  attaches to the still-running old process.
- **A `uv tool install --force` / uvx refresh wipes the site-packages `conf/` and code** back to the
  fetched commit — any manual edit there is lost. Put machine-specific configs in `~/.pal/cli_clients/`
  instead (read last, survives reinstalls, **shared by all installs** → one activation covers both
  Claude Code's and Codex's OpenClink). See [[clink-zero-setup-discovery]].
- On Windows a running OpenClink **locks** its install dir → kill the OpenClink process before reinstalling.
- `uv cache clean pal-mcp-server` has hung repeatedly here; copying updated files straight into the
  install (then restart) is a reliable fallback.
- **The shared `~/.pal/cli_clients/` is loaded by every checkout, so a config for a CLI your working
  tree doesn't support takes the whole registry down — not just that client.** `_resolve_config`
  (`clink/registry.py:137`) raises `RegistryLoadError: CLI '<name>' is not supported by clink` when
  the name is absent from `INTERNAL_DEFAULTS` (`clink/constants.py`), and because `server.py` builds
  the registry at import, **`pytest` fails at collection** — every suite that imports the server,
  not only the clink tests. Measured 2026-08-01 on `chore/bootstrap-t4-operating-layer`:
  `~/.pal/cli_clients/cursor.json` + a branch predating `main`'s `cursor` entry → 7 collection
  errors, 16 deselected, 0 tests run. Rebasing (or moving the override aside) clears **this** error;
  it did not make the suite green, because a second, unrelated blocker sat behind it — see
  [[requirements-unbounded-mcp-pin]]. The symptom looks like a broken checkout and is easy to
  misdiagnose, and one cause hides the next: falsify before declaring the root cause.

**How to apply:** to ship a code/config change to the *running* OpenClink, update the right install (or all
of them), restart OpenClink, and verify with a real `clink` call — don't assume a push or a reconnect took.
