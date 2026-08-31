---
name: ci-unavailable-billing-blocked
description: "GitHub Actions never runs on this fork — the account is billing-blocked — so the PR gate is workflow discipline at open-time, not a green check"
metadata:
  type: project
---

**Do not spend a session trying to get CI green, enable Actions, or wait for checks on a PR here.
It cannot run.** The account is billing-blocked (developer, 2026-08-01), and that is not something
the repo can fix from its side.

Measured 2026-08-01:

```
gh workflow list --all   -> Tests, PR Docker Build, Docker Release, Semantic PR, Semantic Release: all "active"
gh run list --limit 20   -> 1 run in the repo's entire history (a Copilot review, failed, 12s)
gh pr checks 19          -> no checks reported
```

`.github/workflows/test.yml` triggers on `pull_request: branches: [main]`, so the config is correct
and the workflows *look* enabled — which is exactly the trap. Nothing has ever executed. PR #5 was
merged and PR #19 opened with **zero** checks.

**Why:** the reasoning that "workflows are listed as active, therefore CI is wired up" is wrong here,
and an agent that checks only `gh workflow list` will conclude the opposite of the truth. Check
`gh run list` — an empty run history is the tell.

**How to apply:** the merge gate in this repo is **workflow discipline at PR-open time, not a green
check**. There is no machine backstop, so the `t4-dev-workflow` evidence rules are the *only* thing
between a red change and `main`: run the suite locally and quote the real output, run
ruff/black/isort locally, state exemptions with a checkable fact, and never write "tests pass"
without having run them. Treat `mergeStateStatus: CLEAN` as "no conflicts", never as "verified".

Related: [[requirements-unbounded-mcp-pin]] (the defect that a working CI would have caught on a
fresh install, and which instead surfaced only when a human built a clean venv).
