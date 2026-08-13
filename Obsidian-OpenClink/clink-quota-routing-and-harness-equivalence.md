---
name: clink-quota-routing-and-harness-equivalence
description: "codex is nearly out of weekly quota and claude is at its limit; claude-9arm runs the same Claude Code harness, so harness-level findings transfer from it to claude for free"
metadata:
  type: reference
---

Current allowance state (user-reported, 2026-08-01) and the routing rules that follow from it.

## Pools

- **`codex` — ~2% of the weekly allowance left.** Do not spend it on exploratory or test calls. When a
  codex-lane probe is genuinely needed, use **`gpt-5.6-luna`**, not `gpt-5.6-sol`. Reserve `sol` for a
  call whose deliverable is judgment and that will actually be acted on.
- **`claude` — at its limit.** Route to **`claude-9arm`** instead.

## Harness equivalence — the part worth remembering

`claude-9arm` is the **real Claude Code CLI**, pointed at a local/gateway LLM via `--settings` /
`--model`. Only the model behind it differs; the harness is identical (same flags, same hooks, same
session/resume mechanics, same `--output-format` shapes).

So a question splits in two, and only one half needs `claude`:

| Question is about… | Test on | Transfers to `claude`? |
| --- | --- | --- |
| **the harness** — CLI flags, hook events, `--resume`, `--permission-prompt-tool`, output framing, exit-code behaviour | `claude-9arm` | **Yes** — same binary |
| **the model** — answer quality, reasoning depth, instruction-following | `claude` | No — different model |

**How to apply:** any capability spike against the Claude family (does this flag exist, does this hook
fire, does the session resume) runs on `claude-9arm` at zero Anthropic cost, and the result is valid
for `claude`. Only escalate to `claude` when the *model's* output is the thing under test — and right
now, not even then.

Related: [[antigravity-quota-split]] (the same vendor-pool logic for `agy`),
[[clink-per-call-model-effort]] (how to set the per-call model/effort).
