# Dev Workflow (fork)

The T4 operating pipeline, adapted to this Python/MCP fork. See `t4-dev-workflow` for the full
discipline; this is the repo-specific instance.

## Pipeline

Idea → (grill the concept) → PRD for an epic → GitHub issues (one per deliverable) → **TDD**
(red → green → refactor) → PR referencing the issue.

**Hard gate: issue → PR.** Never open a PR without a referenced issue; issues are the source of
truth. Every code change maps to an issue you're allowed to work (authored by us or
`ready-for-agent`). Close issues with a stated reason + evidence (commit SHA / test).

## Commands (Python / uv — NOT Bun)

- Quality gate before a PR: `./code_quality_checks.sh` (ruff lint+format, tests).
- Tests: `python -m pytest tests/` (unit) · `simulator_tests/` for end-to-end harness runs.
- Env: `source .pal_venv/bin/activate` (managed venv) or `uv` per the README.
- Non-standard: `agy` (Antigravity) needs a real ConPTY on Windows — see `CHANGES-FORK.md` before
  touching `clink/agents/antigravity.py`.

## Non-negotiables

- **TDD mandatory** for features + bugfixes. Verify behavior, not just that it returns 0.
- **Verify clink changes against a real CLI** — a `_build_command` unit test proves flag order, not
  that the CLI honored it (see the antigravity `--model` bug: unit-green, runtime-wrong). Drive the
  actual CLI for anything model/behavior-affecting.
- **Bilingual (TH + EN), tracker-only** — issue/PRD/PR bodies mirror EN + TH exactly (see
  `issue-tracker.md`). Chat/reports/commits stay as-is (commits English).
- **Records** — a hard-to-reverse decision → an ADR (`docs/adr/`); a fixed+validated bug worth the
  lesson → a post-mortem/investigation in `docs/reports/`. Append `DONE.md` per shipped unit; keep
  `docs/OPEN-WORK-LEDGER.md` current.
- **Don't leak secrets** into configs/prompts (gateway keys live in the user's settings file, not
  the repo).

## Auto-triggered disciplines

Bug/stack trace → `/debug-mantra`. After a fix → `/post-mortem`. After writing code → `/simplify`.
Before merge → `/code-review` + `/scrutinize`. Touching a security boundary (a token/gateway
setting) → `/security-review`. Delegating a mechanical leaf → `clink-subagents` (verify everything).
