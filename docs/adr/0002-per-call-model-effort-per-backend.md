# 0002. Per-call `model` / `reasoning_effort` as an optional, per-backend-mapped clink override

- **Status:** Accepted (2026-07-16)
- **Commits:** `97a7072` (feature), `7e80e42` (Antigravity ordering + fail-closed)

## Context

Upstream `clink` fixes each CLI's model + reasoning at **config time** (`conf/cli_clients/*.json`
args); varying them meant editing config + restarting, or defining a client per variant. We wanted
to dial capability **per call**. But the four back-ends express model/effort differently: Codex has
separate `-m` + `-c model_reasoning_effort=` flags; Antigravity bakes effort into the model *label*
and its `--model` must precede the value-taking `--print`; the `claude` runner (and `claude-9arm`
gateway) take `--model` but have no graded-effort flag.

## Decision

Add two **optional** params to the clink tool (`model`, `reasoning_effort`) and map them **per
back-end** via a small `_model_args()` hook, appended **after** config args so a per-call value wins
and omitting them reproduces the previous command exactly (backward compatible).

- `tools/clink.py` — `CLinkRequest` gains the two fields; `execute()` forwards them to `agent.run()`.
- `clink/agents/base.py` — `_model_args()` default returns `["--model", model]`; `run()` +
  `_build_command()` thread the params through.
- `clink/agents/codex.py` — overrides `_model_args()` to emit `-m <model>` + `-c model_reasoning_effort=<effort>`.
- `clink/agents/antigravity.py` — overrides `_build_command()` to place model options **before**
  `--print` (see the investigation report) and `run()` **fails closed** on a non-zero exit.

## Consequences

- Adding a back-end with a different model/effort contract = one `_model_args()` override, not a
  shared-flag change. The base default (`--model`) covers claude/gemini/antigravity.
- `reasoning_effort` is intentionally a **no-op** where the CLI has no such flag (antigravity: use the
  model label; claude/gateway: none). This asymmetry is by design; the per-back-end support matrix +
  routing guidance live with the delegation skills
  ([xeno-skills `docs/research/`](https://github.com/xenodeve/xeno-skills/tree/main/docs/research)).
- Correctness of the flags reaching the *model* is CLI-specific and not provable from a
  `_build_command` unit test — validate against the real CLI (this is exactly how the Antigravity
  `--print`/`--model` ordering bug hid behind green unit tests).

Related: [ADR 0001](0001-antigravity-via-windows-conpty.md),
[ADR 0003](0003-zero-setup-discovery-and-active-claude-9arm.md).
