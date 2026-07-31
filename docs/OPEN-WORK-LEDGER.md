# Open-Work Ledger

Single source of open work for this fork (tracked + untracked). Newest/most-active on top.
🔴 = untracked (MD-only, no GitHub issue). Read this at session start — see the memory
protocol in `docs/agents/` and the entry map (`using-t4`).

> This is a **fork** of [BeehiveInnovations/pal-mcp-server](https://github.com/BeehiveInnovations/pal-mcp-server)
> (unmaintained upstream). Fork-specific changes live in `CHANGES-FORK.md`. This ledger tracks
> the fork's own open work, not upstream's.

## Active

### Supervised subagent sessions — epic PRD (#11)

`clink` gives a master agent no way to see whether a subagent is running, blocked or dead, so it
re-spawns duplicates; and there is no way for a master to approve/deny a privileged action from a
weaker back-end. Root cause measured: the MCP transport gives up at ~60–108s while clink's child
timeout is 1800s, so the master is told "failed" while the child runs on — and no in-flight registry
exists to refuse the duplicate.

Split into one issue per deliverable. **Start order: #13 → #14, and #12 in parallel.**

| # | Deliverable | State |
|---|---|---|
| #12 | Phase 0 — spike: does the host issue a follow-up call? which CLIs have a pre-tool hook + resumable session? | ready-for-agent (no production code) |
| #13 | Phase 1 — honest outcome semantics (non-zero exit ≠ success) | ready-for-agent · lands red first |
| #14 | Phase 2 — per-client trust level applied at spawn | ready-for-agent · needs live per-client verification |
| #15 | Phase 3 — supervised session: non-blocking call, registry, evidence-based status | 🚧 gated on #12 Q1 + #13 |
| #16 | Phase 4 — interrupt-and-resume per-action approval | 🚧 gated on #12 (both Qs) + #15 |

Records this epic owes: an **ADR** for the blocking→handle call-shape change (#15), and a
**report** in `docs/reports/` for the transport-timeout diagnosis. Neither is written yet — the
call-shape decision is itself gated on #12, and the timeout finding is diagnosed but not fixed,
so it is not a post-mortem yet.

### Hardening follow-ups (from the 2026-07-16 architecture review, 7.5/10)

Source: `docs/reports/2026-07-16-pal-clink-architecture-hardening-review.md`. The model-routing fix
is sound; these are safety/reliability items for unattended, repo-mutating delegation.

- 🔴 **`readOnlyHint` is inaccurate.** `CLinkTool.get_annotations()` returns `readOnlyHint: True`
  (`tools/clink.py`), but clink launches agents with bypass-approvals/sandbox flags that mutate the
  repo. Fix the annotation to match agentic behavior.
- 🔴 **Workspace/session isolation** — delegated agents run against the live working dir; add
  isolation (a scratch/worktree or explicit cwd) before trusting unattended repo-mutating runs.
- 🔴 **PTY timeout may not interrupt a blocking read** (`clink/agents/antigravity.py` `_run_in_pty`) —
  the timeout check sits between reads; a read that blocks past the deadline isn't interrupted. Harden
  the teardown.
- 🔴 **Test coverage of failure paths** — good command-construction tests exist; the non-zero-exit /
  timeout / parse-error paths (esp. the Antigravity runner) are uncovered.

### New gaps from the 2026-07-16 clink-brainstorm (not yet ticketed)

Source: `docs/reports/2026-07-16-clink-brainstorm-gap-analysis.md` (codex + claude-9arm brainstorm at
`001746a`; 4 of the top 6 hand-verified). Candidates — confirm before ticketing. Ordered impact÷effort:

- 🔴 **Setup scripts + docs install `upstream`, not the fork** — `run-server.sh:1872,1897,2449` +
  `docs/getting-started.md` generate `uvx --from git+…/BeehiveInnovations/…`; a doc-following user runs
  upstream with none of the fork's work. Also check `run-server.ps1`. **(S, do first — verified.)**
- 🔴 **`pywinpty` missing from `requirements.txt`** (present in `pyproject.toml`); run scripts install
  from `requirements.txt` → install OK, first `agy` call fails. No `uv.lock`. **(S — verified.)**
- 🔴 **Delegated CLIs inherit all of `os.environ`** (`clink/agents/base.py:228`) — secret exposure;
  needs minimal env + per-client allowlist. **(M — verified.)**
- 🔴 **All CLIs told "You are operating through the Gemini CLI agent"** (`tools/clink.py:472–474`) —
  parameterize by `client.name`. **(S — verified.)**
- ✅ **Non-zero CLI exit reported as `success`** — now tracked as **#13** (Phase 1 of the epic above).
  (`clink/agents/{claude,codex}.py` `_recover_from_error`; no test asserts otherwise.) **(M.)**
- 🔴 **No Windows CI** (`.github/workflows/test.yml` = ubuntu-only) — the fork's Windows-first core is
  untested in CI. **(M.)** Plus lower-tier: `shlex` Windows-path corruption, unbounded output/metadata,
  unsanitized command metadata, Claude `--print` ordering untested, antigravity timeout orphans child.

### Other

- 🔴 **Cross-platform CLI discovery** — `clink/discovery.py` known-install-locations are
  Windows-focused (winget / `%LOCALAPPDATA%` / npm). macOS/Linux paths not yet added; on those
  OSes it degrades to PATH-only. Add per-OS candidates when the fork runs there.
- 🔴 **Antigravity live model-selection integration test** — unit tests assert the `_build_command`
  ordering (`tests/test_clink_model_effort.py::test_antigravity_places_model_before_print`), but
  there's no opt-in live test that drives `agy` and asserts the selected model reaches the backend.
  See `docs/reports/2026-07-16-clink-antigravity-model-override-investigation.md` (acceptance criteria).
- 🔴 **Config activation persistence, revisited** — zero-setup discovery + the bundled active
  `claude-9arm.json` cover the common case; the `~/.pal/cli_clients/` user-dir override is the
  escape hatch for custom gateways/paths. No open code item; documented in `CHANGES-FORK.md`.

## Shipped & closed

Feature/fix history for the fork is in `DONE.md` (newest on top) and the closed GitHub issues
(#1 per-call model/effort · #2 antigravity `--model` order fix · #3 zero-setup discovery +
claude-9arm), each closed-with-evidence citing its commit SHA.
