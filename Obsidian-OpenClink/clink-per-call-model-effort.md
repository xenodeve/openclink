---
name: clink-per-call-model-effort
description: "the fork's per-call clink model/reasoning_effort params, mapped per back-end (codex full, agy model-only, claude-9arm model-only)"
metadata:
  type: reference
---

This fork adds optional per-call `model` + `reasoning_effort` params to the `clink` tool (both
optional, appended after config args → backward compatible), via a `_model_args()` hook on the base
agent that `CodexAgent` overrides. Support differs by back-end (all live-verified 2026-07-16):

- **codex** — `model` → `-m` (validated: an invalid model errors 400, not a silent fallback);
  `reasoning_effort` → `-c model_reasoning_effort=<low|medium|high|xhigh|max>` (reasoning tokens
  scale with it). Full support. Account exposes `gpt-5.6-sol`, `gpt-5.6-luna`, `gpt-5.5`.
- **antigravity** — `model` → `--model` (fail-closed; but the flag must precede `--print` — see
  [[agy-print-swallows-model]]); effort is baked into the model *label* (`(High)`, `(Thinking)`),
  so `reasoning_effort` is ignored.
- **claude-9arm** (Claude Code → a gateway model) — `model` → `--model` (last-wins), limited to what
  the gateway serves; `reasoning_effort` is a no-op (Qwen gateway has only thinking on/off).
- **claude / gemini** — base `--model`; effort ignored.

**How to apply:** dial codex effort up for the hardest leaf / down for cheap mechanical work; for
antigravity, pick effort via the model label; don't expect graded effort on claude/gateway. The
per-back-end capability + routing matrix lives with the delegation skills (xeno-skills
`docs/research/2026-07-16-model-effort-capability-matrix.md`). Related:
[[clink-zero-setup-discovery]], [[antigravity-quota-split]].
