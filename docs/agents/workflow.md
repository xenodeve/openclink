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

## Paired repository — `xenodeve/xeno-skills`

This fork is the **tools layer**. [`xenodeve/xeno-skills`](https://github.com/xenodeve/xeno-skills) is
the **agent-enforcement layer**: the skills that decide how a master agent uses these tools. Most
`clink` work has a counterpart there, and **a change to one side is usually incomplete on its own**.

| here (tools — what `clink` *can do*) | xeno-skills (agent — how a master *must behave*) |
|---|---|
| **#11** supervised subagent sessions (epic; phases #12–#16) | **#71** enforcement layer for supervised delegation |
| **#20** subagent lifetime — no fixed deadline, process-tree ownership, cancel/reap | **#74** master-agent pre-delegation checklist — acceptance, feasibility, containment, failure semantics, verification |
| **#21** report the cost of every call — usage, resolved model/effort, credits | **#73** route on measured cost — refresh the figures, name every scale, contract-test them |
| — | **#72** research: the capability matrix that sources #73's figures |
| **#88** a `skills` parameter — PAL guarantees the skill floor the master is supposed to hand over | **#163** split the handoff: the floor becomes PAL's, the task-specific skill stays the master's, and `skills_added_by_default` is the master's own omission rate reported back to it |
| **#89** the ultracode environment (epic) — `clink_phase`, structured returns, an on-disk journal, per-lane caps, and the three enforcement tiers | **#164** `clink-ultracode` — the phase shape, the economics, and the stopping rule; the skill that drives #89 |

**The rule: when you change one side, check the other in the same session.** Specifically —

- **A tool capability lands here** → the skill that told agents to compensate for its absence is now
  wrong. `xeno-skills#74` labels every checklist item `discipline` or `tool` **and names the issue**
  that delivers it, so the items to revisit are mechanically findable.
- **A number changes here** (a price, a rate card, a default model/effort) → skill figures sourced
  from it go stale. `xeno-skills#73` adds a contract test so this breaks a test rather than silently
  misleading an agent.
- **A skill starts requiring something the tool cannot do** → that is a tool gap; file it here.

Four requirements currently belong to **no issue in either repository**: argument allowlisting,
defences against prompt injection carried in repository content, resource admission, and
conflict-aware promotion. They are recorded in `xeno-skills#74`.

> The tracker asymmetry this note used to describe is gone, and **both halves of it were false by
> 2026-08-05**. This repo did *not* carry the full T4 vocabulary — 16 labels against the 19 in
> `triage-labels.md`, with the Type and Severity groups missing (#66). And xeno-skills is no longer
> unlabelled: its open issues carry `ready-for-agent`, `ready-for-human`, `t4`, `multi-agent`,
> `hooks`, `security`, `ci`, `research`, `blocked`, `Major`, `Feature` and `bug`.
> Read the labels in either repo as real triage, and treat a missing one as a defect to file rather
> than a convention to work around.

## Auto-triggered disciplines

Bug/stack trace → `/debug-mantra`. After a fix → `/post-mortem`. After writing code → `/simplify`.
Before merge → `/code-review` + `/scrutinize`. Touching a security boundary (a token/gateway
setting) → `/security-review`. Delegating a mechanical leaf → `clink-subagents` (verify everything).

## Convening a panel — `clink-brainstorm` needs no permission

**Standing authorization: invoke `clink-brainstorm` whenever you judge it useful. Don't ask first.**
It is the one discipline here you may spend freely, because the cases it covers are the ones where
being wrong is expensive and being slow is not.

Reach for it when:

- **The plan is complex** — several interacting parts, or an approach you cannot fully specify yet.
- **The decision is hard to reverse** — an architectural seam, a schema, a public interface, a
  dependency adoption, anything heading for an ADR. If `t4-engineering-records` would want an ADR
  for it, that is a reason to convene a panel *before* deciding, not after.
- **The stakes are high** — a trust boundary, a change that lands across many call sites, a
  migration.
- **You are confident and alone.** A single agent's confident answer is the failure mode a panel
  exists to catch — measured in this repo's own research, one seat got 9 of 10 absence claims wrong
  while formatting them authoritatively, and only disagreement with the other seats surfaced it.

**What it is, and is not.** `clink-brainstorm` convenes several independent agents on the *same*
question and returns **judgment** — what is wrong, what to build, which approach wins. That is not
what `clink-subagents` does (it returns **finished work**), and the two must not share model or
effort settings. Don't route a panel through the small model; the deliverable is reasoning.

**It is not free, and that is not a reason to skip it here.** A round is several agents and minutes
of wall-clock. Weigh it against the cost of the decision, not against the cost of a single call —
for a reversible one-liner it is overkill, for a seam you will live with it is cheap.

**Synthesize, don't paste.** The panel's answers are input to your judgment, not a vote to average.
Say where they converged, where they split, and which side you think is right — you hold the session
context they do not. And verify their claims: convergence is evidence, not proof.
