# Reports & research (fork)

Investigations, post-mortems, and research records for this fork. Engineer-audience; `file:line`
and commit SHAs welcome. One dated file per topic.

## Index

- [2026-07-16 — clink Antigravity model-override investigation](2026-07-16-clink-antigravity-model-override-investigation.md)
  — root cause + RESOLVED: `agy --print` swallowed `--model`; fixed by ordering + fail-closed (issue #2, `7e80e42`). This is a bug in *this fork's* clink code, so it lives here (referenced by [ADR 0002](../adr/0002-per-call-model-effort-per-backend.md)).
- [2026-07-16 — clink architecture & hardening review](2026-07-16-pal-clink-architecture-hardening-review.md)
  — independent (codex) review of the antigravity / model-selection / discovery / claude-9arm work at `d44ae01`: 7.5/10, model-routing fix sound; hardening follow-ups (readOnlyHint, isolation, PTY timeout, failure-path tests) tracked in `docs/OPEN-WORK-LEDGER.md`.
- [2026-07-16 — clink-brainstorm gap analysis](2026-07-16-clink-brainstorm-gap-analysis.md)
  — multi-agent `clink-brainstorm` (codex + claude-9arm; antigravity returned empty) at `001746a` answering "what is this project missing?". Records the workflow, the per-agent model/effort used (all preset defaults), and a prioritized gap list going beyond the ledger's six — top new items: setup scripts install upstream not the fork, delegated CLIs inherit all of `os.environ`, non-zero exit reported as success, no Windows CI. Follow-ups proposed, not yet ticketed.

_(Delegation-**routing** research — the subagent delegation log, token-economics, and model×effort
capability matrix — lives with the skills that it calibrated, in
[xenodeve/xeno-skills `docs/research/`](https://github.com/xenodeve/xeno-skills/tree/main/docs/research),
not here. This repo's reports cover clink *code*.)_
