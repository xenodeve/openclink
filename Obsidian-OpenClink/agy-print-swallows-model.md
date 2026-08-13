---
name: agy-print-swallows-model
description: "agy --print is value-taking; --model must precede --print or agy silently uses its default model (Gemini 3.5 Flash)"
metadata:
  type: reference
---

Antigravity (`agy`)'s **`--print` is a value-taking flag** — it consumes the *next token* as the
prompt. So `agy --print --model "X" "<prompt>"` makes `--print` swallow `--model` as its value:
`agy` runs with an empty model and **silently falls back to its persisted default**
(`~/.gemini/antigravity-cli/settings.json`, e.g. *Gemini 3.5 Flash*), exit 0 — no error.

Correct order: **`agy --model "X" --print "<prompt>"`** (model options BEFORE `--print`). Verified
live: wrong order → Gemini 3.5 Flash regardless of request; right order → the requested model
reaches the backend. `AntigravityAgent._build_command` (`clink/agents/antigravity.py`) now emits
this order, and `run()` fails closed on a non-zero exit (an unsupported model exits 1 + a catalog).

**How to apply:** any hand-built `agy` invocation (or a new runner) must put model/session options
before `--print`, and must not trust exit-0 as proof the model took effect — check the model in the
response or the `~/.gemini/antigravity-cli/log/` line. Full trace:
`docs/reports/2026-07-16-clink-antigravity-model-override-investigation.md`. Related:
[[clink-per-call-model-effort]].
