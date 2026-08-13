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
- [2026-08-04 — clink Phase 0 spike: host follow-up calls, and per-CLI hook / resume capability](2026-08-04-clink-phase0-spike-host-followup-and-cli-capability.md)
  — Q2 answered (the per-client pre-tool-hook and resumable-session table; only the Claude Code harness demonstrably has both), Q1 **not** answered. Carries the four-host inventory showing the epic's 60–108 s transport premise was measured on one host of four, and the correction that an intermittent fault has a *rate*, not a verdict. *(Was missing from this index until 2026-08-13.)*
- [2026-08-13 — deep scan: architecture, the safety boundary, and where it can go](2026-08-13-deep-scan-architecture-safety-and-direction.md)
  — twelve-reader code scan with adversarial refutation (380 claims; 27 reached a refuter, 11 refuted or corrected). States the safety boundary plainly — the full `os.environ` reaches every spawned CLI, `readOnlyHint: True`, no `cwd` — records three compounding liveness defects (the clink timeout never reports; the antigravity deadline sits before a blocking read; `provider.generate_content` blocks the event loop), the conversation-history substring mismatch that duplicates a turn on every continuation, and a ranked set of directions grounded in unused MCP capabilities the pinned SDK already exposes.

_(Delegation-**routing** research — the subagent delegation log, token-economics, and model×effort
capability matrix — lives with the skills that it calibrated, in
[xenodeve/xeno-skills `docs/research/`](https://github.com/xenodeve/xeno-skills/tree/main/docs/research),
not here. This repo's reports cover clink *code*.)_
