# 0001. Drive Antigravity (`agy`) through a Windows ConPTY

- **Status:** Accepted (2026-06-28)
- **Commit:** `9087c81` (fork addition)

## Context

Google retired the Gemini CLI in mid-2026 in favor of **Antigravity** (`agy`, a closed-source Go
binary). `agy` only emits output when it believes it's attached to a real terminal: under a plain
piped subprocess — the way every MCP server, including PAL's `BaseCLIAgent`
(`clink/agents/base.py`, `asyncio.create_subprocess_exec`), spawns a child CLI — it exits 0 with
**empty stdout**. So the upstream plain-pipe path cannot capture any `agy` output.

## Decision

Run `agy` inside a real Windows pseudo-console (**ConPTY**) via `pywinpty`, in an Antigravity-specific
runner, instead of the base plain-pipe path.

- `clink/agents/antigravity.py` — `AntigravityAgent` spawns `agy` with `winpty.PtyProcess.spawn`
  (in `_run_in_pty`, off the event loop) and passes the prompt as a positional argument.
- `clink/parsers/antigravity.py` — strips the ANSI/CR-LF noise a real terminal introduces
  (`parser="antigravity_text"`).
- `conf/cli_clients/antigravity.json` + `clink/constants.py` (`runner="antigravity"`) wire it in.
- **`clink/agents/base.py` is left untouched** — the ConPTY path lives entirely in the subclass, so
  the other CLIs' plain-pipe path is unaffected.

## Consequences

- **Windows-only** (`pywinpty` is Windows-specific). On macOS/Linux `agy` may work over a plain pipe;
  if it needs a PTY there too, that requires `pty.fork()`/`pexpect`, not `pywinpty`. Tracked as open
  work if the fork ever runs there.
- Adds a real dependency (`pywinpty`) and a distinct execution path for one CLI — do **not** copy the
  ConPTY pattern for other CLIs unless they have the same "silent under a pipe" symptom.
- Because output flows through a terminal, the parser must keep stripping escape codes; a new `agy`
  output format is a parser change, not a runner change.

See `CHANGES-FORK.md` for the narrative. Related: [ADR 0002](0002-per-call-model-effort-per-backend.md)
(the Antigravity runner also carries the per-call `--model` ordering fix).
