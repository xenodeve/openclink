---
name: antigravity-quota-split
description: "agy quota is split by vendor: a Gemini pool vs a non-Google (Claude/GPT-OSS) pool that burns noticeably faster"
metadata:
  type: reference
---

Antigravity (`agy`) draws on **two shared subscription pools**, split by vendor:

- **Google pool** — `Gemini 3.5 Flash` + `Gemini 3.1 Pro` share it.
- **non-Google pool** — `GPT-OSS 120B` + `Claude Sonnet 4.6` + `Claude Opus 4.6` share it, and it
  **burns noticeably faster** than the Google side.

(User-reported, 2026-07-16.) So routing `antigravity` to a Claude/GPT model — e.g. via the per-call
`model` override for a non-OpenAI second opinion — is fine *occasionally* but drains the non-Google
allowance fast.

**How to apply:** keep bulk/repeated antigravity work on the cheaper Gemini pool; spend the
Claude/GPT route only when a different vendor's judgment is the actual point. Related:
[[clink-per-call-model-effort]].
