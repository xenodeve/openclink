---
name: absence-must-not-conflate-two-facts
description: "In the clink accounting block, a marker means a fact about the CLI or the call; a fact about OpenClink's own configuration stays silent — three fields already follow this and a fourth must too"
metadata:
  type: project
---

**Before adding any field to the clink accounting block, decide which of these two it is.** The
convention is now load-bearing across three fields, and it was arrived at twice — the second time by
catching a violation in review, hours after the first.

| The fact is about… | What the caller sees | Why |
|---|---|---|
| **the CLI, or this call** | an explicit marker | the caller must be able to act on it |
| **OpenClink's own configuration** | **nothing at all** | it would be present on every response until someone configures it, and a marker present on everything marks nothing |

Worked examples, all on `main`:

- `usage_unavailable: true` — **emitted.** The CLI genuinely reports no usage (`cursor`, `antigravity`
  declare `USAGE_UNAVAILABLE`). A fact about the CLI.
- **an adapter nobody has written yet — silent.** `USAGE_FIELD_MAP` empty and no declaration means
  OpenClink has not done the work. Marking it would make an unfinished adapter look like a finished one.
- `cost_unavailable: "model_not_priced" | "model_unresolved" | "no_usage_reported"` — **emitted.**
  Each is a fact about this call, and each can only arise once a rate card exists.
- `cost_unavailable: "no_rate_card"` — **suppressed** in `tools/clink.py`, and this is the one that
  had to be caught in review. `finalize_output` prices every call, and no bundled client ships a rate
  card, so it would have appeared on *every response of every client*. The constant `NO_RATE_CARD`
  exists in `clink/pricing.py` precisely so the tool can compare against it without a second copy of
  the string.

**The deeper rule this serves:** absence already means something in this block — the docstring of
`_call_accounting` promises *"a key is absent when the client reported nothing for it, so a caller can
tell 'not reported' from a reported zero."* Every new field has to fit that promise rather than add a
second, contradictory way of saying nothing. Reporting zeros is always wrong here: a call whose
consumption is unknown is not a call that consumed nothing.

Known incomplete, deliberately: `cache_creation_input_tokens` has no field in the normalised account
and so cannot be reported at all — not even as unavailable, because pricing cannot see what the
account cannot represent. See `#56`; it was 24477 tokens against 2 input tokens in a recorded run.

Related: [[delegated-red-can-reproduce-and-still-be-worthless]] — the review that caught the
`no_rate_card` violation is the same class of check.
