---
name: delegated-red-can-reproduce-and-still-be-worthless
description: "A subagent's failing test can reproduce exactly on your machine and still be worthless — check what the assertion is anchored to, not just that it failed"
metadata:
  type: feedback
---

**Re-running a delegated red is not the check. Reading what it asserts is.**

Measured 2026-08-05, and the controlled comparison is what makes it worth keeping: the *same* model
(`gpt-5.6-luna`, `high`), the *same* prompt shape, two leaves dispatched **at the same moment**.

- **`pal#26` — a code leaf.** Returned a good test: it asserted on the dict `_call_accounting`
  returns, so its failures were behavioural (`KeyError` on a missing key); it hand-computed five
  figures, all five of which recomputed correctly; and it included a real control asserting the new
  keys are *absent* on the untouched path.
- **`xeno-skills#81` — a prose leaf.** Returned 11 assertions, every one a `grep -qiF` for **an exact
  sentence the worker had invented**. It ran, exited 1, reported 11 failed — and reproduced here
  exactly as reported. **The result was real and the test was worthless**, because the fix it demanded
  was *"paste these 11 strings into the file"*. It would go green on a change that added the sentences
  and nothing else.

**Why the difference is not the model.** A code change has an output you can assert against. A
document's "behaviour" *is* its prose, so a worker with nothing to observe falls back to inventing the
prose and asserting on its own invention. `clink-subagents` says the cheap tier suits *verifiable*
leaves — and a prose assertion looks verifiable while being circular.

**So `verifiable leaf` must be read as _observable behaviour_, not _checkable-looking_.** If you
cannot name the observation the test makes before you delegate, you are not delegating a leaf.

**Two tells worth checking in any returned test, delegated or your own:**

- **A "control" that is trivially true forever.** `[ -f "$FILE" ]` on a file that has been in the repo
  for months cannot catch an over-broad fix. A real control asserts a *behaviour* that must hold both
  before and after.
- **Positive assertions only.** With no negative check, a partial edit that adds the new wording
  *beside* the old, wrong wording passes. `tests/skills/` has `hasnt()` for exactly this; the returned
  file defined it and never called it.

**The vacuous-red family this belongs to** — three variants have now bitten this project:

1. an assertion that passes because the thing under test is *absent* (a missing path echoed by `sh`);
2. a red that is really a **collection/import error**, which proves nothing about behaviour;
3. this one — a red that is real, reproduces, and tests only that a document contains a sentence
   somebody just made up.

Related: [[absence-must-not-conflate-two-facts]] — found by the same kind of read-the-assertion check,
on our own code rather than a worker's.
