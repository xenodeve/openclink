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

**The vacuous-red family this belongs to** — **five** variants have now bitten this project:

1. an assertion that passes because the thing under test is *absent* (a missing path echoed by `sh`);
2. a red that is really a **collection/import error**, which proves nothing about behaviour;
3. a red that is real, reproduces, and tests only that a document contains a sentence somebody just
   made up;
4. a **substring false-positive** — `assert "--check" in script`, where the script contains
   `--check-only` for a *different* tool. The assertion passes while the thing it names is absent;
5. **a clean result from a detector nobody probed.** "0 findings" is indistinguishable from "the
   detector stopped working", and the two are read identically — as good news.

**Variant 4 was mine, not a worker's, and mutation is the only reason it was found.** Written on
2026-08-05 for `#63`: the gate had to stop running `black` in write mode, the test asserted the flag,
and it would have passed with `black` still rewriting the tree because `isort`'s `--check-only`
contains the string. Reading it twice did not reveal it; reverting `black` and re-running did.

**The general form: a `has X` assertion is only as strong as X is unambiguous in the file.** Anchor on
the whole invocation or a phrase containing a space — never on a flag, a bare word, or a path
fragment that another line can satisfy. This is the same rule the prose-leaf failure teaches from the
other direction, and `xeno-skills`' `tests/skills/` documents its own version of the trap.

**Variant 5, and the rule it forces: before reporting a clean scan, make it dirty on purpose.**
Written on 2026-08-05 while auditing `xeno-skills`' suites. The detector reported **0 shadowed
anchors**, which reads as good news and is worth nothing on its own. Feeding it a temporary suite
carrying a real defect (`--check` beside `--check-only`, same target) moved the count `0 → 1`, so the
zero was a *measured* zero. **A scan you have not seen find something has not been shown to find
anything** — one probe, then delete it.

**The companion failure, and it is the one that humbles: a detector that flags everything reports
nothing.** The delegated first draft of that audit called 30 of 32 suites defective — it flagged
suites with *no* assertions at all, and flagged every anchor without a space, which condemns `446`,
a measured token count and one of the *best* anchors in that repo. Corrected, the real number was 11.

**Then the same error was reproduced by the person who had just written it down**: the replacement's
shadowing check compared anchors suite-wide rather than per target file, reporting two assertions on
*different files* as shadowing each other. **Over-broad flagging does not respect who is writing.**
False positives are not the safe direction — a critic that cries wolf is switched off, and then its
true findings go with it.

Related: [[absence-must-not-conflate-two-facts]] — found by the same kind of read-the-assertion check,
on our own code rather than a worker's. [[gh-and-shell-traps-on-this-box]] — the other class of
mistake that recurs across sessions here.
