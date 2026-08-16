# Open-Work Ledger

Single source of open work for this fork (tracked + untracked). Newest/most-active on top.
🔴 = untracked (MD-only, no GitHub issue). Read this at session start — see the memory
protocol in `docs/agents/` and the entry map (`using-t4`).

> This is a **fork** of [BeehiveInnovations/pal-mcp-server](https://github.com/BeehiveInnovations/pal-mcp-server)
> (unmaintained upstream). Fork-specific changes live in `CHANGES-FORK.md`. This ledger tracks
> the fork's own open work, not upstream's.

## Active

### 🟢 The #96 selection layer — every agent-workable slice is merged (2026-08-16)

`#96` is the PRD, cut into #98–#113. Dependency order, read off the issues rather than assumed:
**#98 and #99 are the roots**; then #101 ← 99, #103 ← 98+99; #104 ← 101; #108/#109/#110 ← 104;
#111 ← 108; #113 ← 111. Plus **#138**, opened by #111 and closed the same day.

**All eleven are merged.** `selectagents` now validates its input, filters on context window before
pricing, ranks on what the whole plan costs, honours an optional budget, returns five priced routes
with a dropped count, derives the agent count, partitions the scope, and persists every plan under an
identity before responding.

**The remainder is blocked on work no agent can do, and the labels now say so.** #102 (and so #105,
#106) waits on **#97**, a `ready-for-human` spike asking whether the vendor API exposes cost-per-task
at all; #107 (and so #112) waits on **#100**, which carries no agent label. All five carried
`ready-for-agent` while being unstartable — **the label removed, with the reason on each issue**,
because `t4-afk` builds its unattended worklist from it and an agent picking one up would either stall
or guess at the answer the spike exists to measure.

**What the tool still does not do, and says so in its own response:** the dataset is a committed
fixture whose prices are CONSTRUCTED (#102 replaces the file wholesale — **do not build on its
numbers**), and every seat names the same model and effort, because nothing in this layer yet decides
that a survey seat should differ from a working one.

**It remains in `DISABLED_TOOLS`.** Take it out of `.env.example` when #102 lands and the numbers are
real.

- 🚧 **#15 supervised session** — carried `ready-for-agent` while its own body says **"do not start"**.
  Label moved to `ready-for-human`: it is blocked on **#12 question 1** (does the master's MCP host
  issue a follow-up tool call?), and #12 closed COMPLETED **without answering it** — its findings
  comment is titled *"Q2 answered, Q1 still blocking"* and its last comment withdraws the transport
  measurement as mis-scoped. Building the handle-plus-poll shape on an unverified premise is the
  expensive direction: not a slow start, a wrong one.
- ✅ **#121 PowerShell quality gate** (PR #143) — the `.ps1` copy auto-fixed for six weeks because the
  #63 guard read only the `.sh`. Both are now parametrized, **and the covered set is itself asserted**,
  because the defect was a file nobody asserted on. Running it surfaced a live `B007`, fixed here.
- ✅ **#103 plan identity** (PR #141) — `tools/plan_record.py`, on #98's store. Written before the
  response exists, and the test **records the order** rather than looking afterwards, because both
  orders leave the same directory behind. Not-found raises; it never resolves to `{}`.
- ✅ **#113 scope partition** (PR #140) — every item exactly one owner, shares sum on both axes, an
  undividable count refused rather than rebalanced. The read follows the items and the boundaries are
  cumulative, so nothing is lost or invented to rounding.
- ✅ **#138 a budget bounds the whole plan** (PR #142) — `plan_cost()` is now the one cost figure the
  layer ranks and budgets on. The read is charged once across the seats, only the answers multiply.
  **Beware:** this issue was auto-closed once by a commit saying *"Filed rather than fixed: #138"* —
  GitHub reads `fixed: #n` as a closing keyword regardless of the surrounding words.
- ✅ **#111 derived agent count** (PR #139) — and it **corrected #108's filter**: the required window is
  one item-share, not the whole read, or no candidate could ever need a second seat. A generalisation
  (identical at `item_count=1`), pinned by test. Three mutations came back 0 red and all three were
  real gaps — including a tool-seam test that held only because the count happened to be 1.
- ✅ **#110 five priced routes** (PR #137) — winner-first, signed deltas to the predecessor, dropped
  count reported. **The routes follow the rule that picked the winner**, which #109 made non-obvious:
  under a budget that is descending capability, not ascending cost. `Choice.ranked` exists for this.
- ✅ **#109 optional budget** (PR #136) — no budget takes the cheapest; a budget takes the best that
  fits, which is the only reading satisfying both of the issue's criteria. Also fixed the INCOMPLETE
  disclosure, which had gone a slice stale in three places at once, and added the test that fails when
  the unbuilt list is too LONG. **Keep that list pruned in every slice from here.**
- ✅ **#108 context-window filter** (PR #135) — a hard filter ahead of pricing, with both exclusion
  reasons named rather than counted. `rank()` returns a `Ranking`, not a list, and
  `output_ceiling_tokens` is **required** — it defaulted to 0, which is fail-open on a safety filter.
  Unblocks #111.
- ✅ **#98 on-disk record store** (PR #131) — first persistence in the repo. See `DONE.md` for the
  finding: the test for its hardest criterion passed 3/3 against a fully non-atomic implementation.
- ✅ **#104 cost-per-task ranking** (PR #134) — the arithmetic core, pure and fixture-backed.
  `conf/selectagents_dataset.json` is a committed fixture whose prices are CONSTRUCTED; #102 replaces
  it. Unblocks #108, #109, #110.
- ✅ **#101 input contract** (PR #133) — seven required fields, a closed kind-of-work list, one
  free-text description that reaches nothing computed. Three published-but-unenforced constraints
  found and closed; see `DONE.md`.
- ✅ **#99 `selectagents` skeleton** (PR #132) — registered, advertised, dispatched, returns a stub.
  **Disabled by default** until #104: an advertised tool spends context window in every client, and
  this one computes nothing. Remove it from `DISABLED_TOOLS` in `.env.example` when the first real
  ranking lands.

### ✅ opencode is fully supported (2026-08-16, #125 #126 #127, PR #128)

Three gaps in the client that shipped in #86, each verified end to end against the real binary rather
than through `_build_command`: `reasoning_effort` was discarded instead of becoming `--variant`; the
cost opencode measures itself never reached the accounting block; and `cache.read` — the largest token
class on a real run, 144,256 against 102,535 input — had the right field and no way to reach it.

**Two follow-ups this deliberately did not take**, so they do not get lost:

- **An unsupported `--variant` is accepted and silently ignored by the CLI**, and OpenClink does not
  validate against the per-model `variants` list because reading it costs a ~30s `opencode models`
  call. Caching that list would close it (#125).
- **`--variant` has no demonstrated effect on `deepseek-v4-flash`.** Three controlled runs at no
  variant, `low` and `max` gave indistinguishable token profiles. OpenClink writes the flag and reads
  it back; the provider side is unverified, and the quota constraint permits no other model for
  testing. Worth re-probing on a tiered model if one becomes cheap to call.

`cache.write` stays unmapped — a schema question, still **#56**.

**Gate debt paid late, and it found something (#129, PR #130).** PR #128 merged with
`scrutinize=not-run`; running it afterwards showed `cli_reported_cost` never reached
`sum_thread_accounts`, so a thread of opencode calls reported usage and nothing at all about cost while
every turn carried a measured figure. Fixed with two totals that are never merged. Reviewing that fix
found a second thing — the extraction walks `accounts` three times, so the helper takes a `Sequence`;
an `Iterable` would let a one-shot iterator silently zero both totals.

Whether `cost` should exist at all, and whether a real rate card ships, is still **#77** — untouched.

### 🟡 The rename shipped; the tool prefix is the one piece left (2026-08-16, #94 → #122)

**OpenClink is live on `main` at `7effad8`** (PR #114, 22 commits, 176 files; PR #86 / OpenCode client rode
along as an ancestor and merged with it). `pal-mcp-server` is taken on PyPI at 10.4.3 by an unrelated project,
which is what made the name the blocker under #93.

**What is NOT done, and must not be rushed: `mcp__pal__<tool>`.** The Claude and Codex CLIs are still registered
as `pal`, because `xeno-skills` names that prefix 25 times and its skills run inside those two. Every other
client moved to `openclink` already. `pal` is deliberately absent from `LEGACY_MCP_NAMES` (the list setup
*deletes*), and an existing `pal` entry is refreshed to the current command rather than left to rot.

Order: **`xeno-skills#206` merges → users actually pull → only then** move the CLIs, add `pal` to the cleanup
list, delete the two refresh blocks, and invert the two tests. Doing it at merge time breaks anyone mid-upgrade.
Full criteria in **#122**. The signal is `tests/test_mcp_server_key.py` and `tests/test_registration_freshness.py`,
which carry the inversion in their docstrings — not anyone's memory.

**Both review gates were paid before merge and found four defects**, the sharpest being a latent bug the rename
activated: the registration freshness check compared `server.py`'s path and never the interpreter, so moving
`VENV_PATH` from `.pal_venv` to `.openclink_venv` left every existing registration pointing at a virtualenv
setup no longer installs into — silently, because the old directory is still on disk. Detail in `DONE.md`.

Also filed: **#121** — the #63 fix ("the quality gate reports, it does not rewrite") landed on
`code_quality_checks.sh` only, and its guard reads only that file, so on Windows the gate still rewrites
tracked files.

### ✅ The #36 hooks layer is now pinned by tests (2026-08-09, #83)

The #36 layer shipped with manual demonstrations and **zero committed tests**. Retroactive TDD landed as PR #84
(merged, `d08fca1`, issue #83 closed): `tests/test_t4_hooks_layer.py` — 17 tests at the config seam
(marker/verify/settings/permissions/gitattributes) and the gate-decision seam (real `t4-gate` run against
PreToolUse payloads in a temp sandbox). **Every test falsified by mutation** (M1–M12, each confirmed red then
reverted) — M12 caught a weak assertion (the word `using-t4` is in the fallback directive too), fixed to a
snapshot-only ASCII marker. Suite 1050 → 1067. The known-unguarded forms (quoted absolute-path `gh`,
`mcp__github__*`) are deliberately unpinned pending `xeno-skills#83/#84`.

### ✅ The T4 enforcement layer is real as of 2026-08-09 (#36)

Slice 2 shipped as PR #82 (merged, `4aef920`). `.claude/t4.json` (verify = fast unit suite, timed 38s), the
byte-identical hook scripts + `run-hook.cmd`, `hooks` merged into `.claude/settings.json` (permissions block
preserved), `using-t4.snapshot.md`, and a `.gitattributes` eol=lf pin for the extensionless hooks. Gate
demonstrated firing: bare `gh pr create` no-issue → deny; dangerous git → deny; `gh pr merge` → ask after
running verify itself. **Two forms remain known-unguarded** (quoted absolute-path `gh` and
`mcp__github__*`), recorded rather than claimed — the fix is upstream (`xeno-skills#83/#84`), not a fork edit.
The `"verify"` value is `.venv`-specific because that is what this checkout carries; the two-venv ledger item
below is why the full `code_quality_checks.sh` is not wired.

### The #21 cost line is built end to end (2026-08-05) — one decision blocks the last slice

`#23 → #24 → #25` have all landed. Every configured client now either maps its CLI's usage onto the
normalised account or **declares that its CLI reports none** — the two were previously the same value,
so an unwritten adapter was indistinguishable from a finished one. Cost is computed from that account
against a per-client rate card and **carries its unit**, because a subscription backend prices in
credits and a token-billed one in currency and the two are never summed.

**Nothing blocks #26 mechanically** — its `blocked-by` (#25) is discharged, and it is additive
accounting across a continuation thread rather than anything needing real prices. **But #56 should
land first**, and the reason is not a dependency: the account has **no field for cache-creation
tokens**, which in a recorded 2026-08-05 claude run was **24477 tokens against 2 input tokens**.
Pricing cannot see what the account cannot represent, so **no marker anywhere can report the
shortfall** — #26 would put a confident, wrong number in front of a caller. `ready-for-human`: adding
a field changes the account #23 shipped.

**No real vendor rate ships anywhere.** The schema and the arithmetic are in; `conf/cli_clients/*.json`
carries no prices, because none was fetched and verified. A client without a card loads and runs, and
says nothing about it. Populating the cards is #26's input.

🔴 **`code_quality_checks.sh` silently rewrites tracked files on every run.** `ruff`, `black` and
`isort` all run in **write** mode, so the script the docs tell every agent to run leaves unrelated
modifications in the tree — the mechanism behind two contaminated commits on 2026-08-04. `ruff` is now
clean on `main` (#54), but **`black` would still rewrite 10 files** under `tests/` and
`simulator_tests/`. Inventoried in PR #55, not fixed: a 10-file reformat inside a lint PR is the
muddied diff #54 was opened to avoid. **No issue yet.**

✅ **The T4 label vocabulary is real as of 2026-08-05** (#66). 16 → **25 labels**; the nine missing
were created and `#54`/`#63` re-triaged onto `tech-debt`. **The fix that mattered was not the labels:**
`triage-labels.md` ended by telling the agent to create them *lazily* and *proceed silently* if the
vocabulary was thin, which composes into never created and never mentioned — the same wording
`xeno-skills#96` measured and PR #108 replaced. Creating labels without that edit would have
guaranteed the recurrence. Two near-duplicates were avoided by reconciling the doc to GitHub's
existing defaults rather than creating twins (`Bug`→`bug`, `docs`→`documentation`), and
`agent:<name>` is recorded as a pattern that cannot be pre-created.

### AFK batch 2026-08-04 — five PRs merged; the owed gates are paid

| PR | Issue | State |
|---|---|---|
| #44 | #12 | Phase 0 spike. **Q1 unanswered** — the stub probe needs a OpenClink restart, which drops the observing session's MCP connection |
| #45 | #43 | agy `--effort`, measured against the real binary |
| #46 | #37 | parser `raw` payload dropped in `_prune_metadata` |
| #47 | #41 | model accounting on the error path |
| #48 | #29 | **Breaking** — `model` required. **Must merge last**: #46 and #47 add tests that omit it |

✅ **The owed gates are paid** (2026-08-04, before any merge). `/simplify`, `/code-review` and
`/scrutinize` had run zero times during the batch, against `t4-afk`'s gate list. Run afterwards over all
ten open PRs they found a real defect in **seven**, each fixed on its own branch — see `DONE.md` for the
list. `/security-review` did not trigger; the exemption's checkable fact is recorded there too.

**The one to carry forward:** on both documentation PRs (#44 and xeno #100) the defect was identical —
a correction written into the body while the summary above it kept the withdrawn claim. Correcting a
document means correcting what a reader skims, not only what the correction section says.

✅ **#49 shipped 2026-08-05** (PR #53). `agy --print-timeout` bounds the wait for the **first
response**, not the whole call — a 20s bound on a much longer prompt succeeded. Forced at 3s: exit 1,
stdout 0 bytes, stderr `Error: timeout waiting for response`. **Still open on #49:** whether OpenClink should
raise `--print-timeout` to match its own 1800s child timeout. That is a larger call and was not taken.

**The #21 cost line has moved on** — see the 2026-08-05 section at the top. #24 and #25 shipped;
#26 is the only slice left.

**#22 is likely closeable** — its three slices (#27, #28, #29) are merged. Confirm.

**Masteragent (#11) — nothing AFK-able.** #14 and #16 are security-boundary; #15 and #20 are
architecture/seam; #12's remainder needs a OpenClink restart and three other hosts. All park by the boundary
test, not by preference.

### Validate the (client, model, effort) tuple + report requested/resolved/observed — PRD (#22)

`clink` accepts any model string or none at all, and reports nothing about what actually ran.
Verified 2026-08-02: the request field is optional and free-form and its own description says
*"Omit to use the CLI's configured default"* (`tools/clink.py`), a supplied value is forwarded
unchecked, and `CLIClientConfig` (`clink/models.py`) carries no catalog. Only the Antigravity runner
fails closed today, and only because `agy` itself exits non-zero on an unknown model
(`clink/agents/antigravity.py:89`) — so the same mistake is caught on one client and tolerated on
the others.

Worse, a correct *request* is not proof the backend honoured it: this fork already shipped a fix for
`agy` silently substituting its default while the constructed command was correct, with the flag-order
unit test green throughout (see `DONE.md`, 2026-07-16). Nothing records requested vs resolved vs
observed, so a recurrence is undetectable.

**Seam: same as #21** — validation in the runner (not a host hook, so it binds every agent), three
model values on `AgentOutput`. Either issue can land first. Catalogs are per-client config and their
absence stays permissive, so this lands incrementally. **The guarantee is deliberately narrow and is
stated in the response**: passing proves catalog membership, not that the routing was good
(→ `xeno-skills#74`) and not that the backend complied (→ the observed value).
Tracked as **#22** (`ready-for-agent`).

### Report the cost of every clink call — PRD (#21)

A master agent cannot see what a delegation cost it. Usage is reported under a different key per CLI
(`usage` / `model_usage` / `token_usage`) and **not at all** for `cursor` and `antigravity`;
`AgentOutput` never records which model or effort actually ran, so attribution means re-parsing
`sanitized_command`; and no cost concept exists anywhere in `clink/` or `tools/`.

Measured 2026-08-02: choosing `gpt-5.6-luna` over `gpt-5.6-sol` cost **13–24× fewer subscription
credits for the same correct answer**, established only by copying token counts out of six responses
by hand against a rate card fetched from OpenAI's site. **Seam agreed with the developer:
`AgentOutput`** — one seam covering all six clients and the failure paths (note it has **5**
construction sites, so new fields must default to absent). Reporting only; budget enforcement is
deliberately out of scope and left to a later issue. Tracked as **#21** (`ready-for-agent`).

### Decide: adopt the mcp 2.x server API, or stay bounded (#18)

#17 bounded `mcp` at `<2` in both manifests, which unblocks the suite but is a **stop-gap, not a
decision**. `mcp` 2.0.0 removed `Server.list_tools`, which `server.py` decorates with at import, so
adopting 2.x means rewriting the registration path in the file every tool routes through. Tracked as
**#18** (`needs-info`) — the investigation is not started. **Do not lift the `<2` bound outside that
issue.** See [[requirements-unbounded-mcp-pin]].

### Supervised subagent sessions — epic PRD (#11)

`clink` gives a master agent no way to see whether a subagent is running, blocked or dead, so it
re-spawns duplicates; and there is no way for a master to approve/deny a privileged action from a
weaker back-end. Root cause measured: the MCP transport gives up at ~60–108s while clink's child
timeout is 1800s, so the master is told "failed" while the child runs on — and no in-flight registry
exists to refuse the duplicate.

Split into one issue per deliverable. **#17 has landed, so the suite runs and red-first TDD is
possible again. Start order: #13 → #14, with #12 runnable in parallel throughout.**

| # | Deliverable | State |
|---|---|---|
| #12 | Phase 0 — spike: does the host issue a follow-up call? which CLIs have a pre-tool hook + resumable session? | ready-for-agent (no production code) |
| #13 | Phase 1 — honest outcome semantics (non-zero exit ≠ success) | ✅ shipped 2026-08-03 (PR #34, `2823072`) |
| #14 | Phase 2 — per-client trust level applied at spawn | ready-for-agent · needs live per-client verification |
| #15 | Phase 3 — supervised session: non-blocking call, registry, evidence-based status | 🚧 gated on #12 Q1 + #13 |
| #16 | Phase 4 — interrupt-and-resume per-action approval | 🚧 gated on #12 (both Qs) + #15 |

**Accounting/routing slices shipped 2026-08-03**, all on `main` and all mutation-verified:

| # | Deliverable | State |
|---|---|---|
| #23 | normalised token account + one output factory + declared flag vocabulary | ✅ PR #32 |
| #27 | refuse a model the client cannot serve, before spawn | ✅ PR #35 (`d4862b1`) |
| #28 | report requested / resolved / observed model, flag a substitution | ✅ PR #40 (`8de2023`) |
| #30 | unit suite green on Windows | ✅ PR #31 |

**The suite baseline changed with #30: it is now 0 failed, not "25 failed is normal".** On `main` at
`3ed29be` (2026-08-05) it is **1008 passed, 4 skipped, 16 deselected**, and `ruff check .` is clean.
Any red is yours.

Opened by this batch, none of it started:

| # | What | Why it is not a commit |
|---|---|---|
| #36 | retrofit the T4 enforcement layer — this repo has the docs but **no `.claude/hooks/`, no `t4.json`, no `hooks` key** | ✅ shipped 2026-08-09 (PR #82, `4aef920`) — see the top of this ledger |
| #37 | parser `raw` / `raw_events` metadata reaches the caller uncapped on both paths | predates #13, outside its finding |
| #39 | **the model catalog cannot be enforced from argv** — codex takes a model from `~/.codex/config.toml` and `--profile` | closing it is a public-contract change; `ready-for-human` |
| #41 | a failed run reports no model accounting; `"unknown"` is truthy and unlike its neighbour's absence convention | two small contract questions |

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
- ✅ **`pywinpty` missing from `requirements.txt`** — shipped with **#17**; both manifests now agree and
  `tests/test_dependency_pins.py` fails if they drift again. **`uv.lock` is still absent** — nothing
  pins the resolution, so this class of drift can still arrive from a transitive dependency. **(S.)**
- 🔴 **Delegated CLIs inherit all of `os.environ`** (`clink/agents/base.py:228`) — secret exposure;
  needs minimal env + per-client allowlist. **(M — verified.)**
- 🔴 **All CLIs told "You are operating through the Gemini CLI agent"** (`tools/clink.py:487`) —
  parameterize by `client.name`. **(S — verified; line shifted after the cursor merge.)**
- ✅ **Non-zero CLI exit reported as `success`** — **fixed 2026-08-03 (#13, `e3c7c5b`)**. The outcome
  is now decided in one place, `BaseCLIAgent.finalize_output`, which every construction site reaches
  including the antigravity runner that overrides `run` wholesale. Salvaged content and normalised
  usage travel on `CLIAgentError` so honesty costs the caller neither the diagnosis nor the
  accounting. Verified against the real codex binary, not only in unit tests. **The issue's second
  case was mis-specified:** "exit 0 with empty output" cannot occur — all four parsers raise on empty
  content. The real mechanism is `clink/parsers/antigravity.py` returning *stderr as content* when
  stdout is empty and tagging it — the tag existed and nothing read it. It is now the shared
  `NO_ANSWER_METADATA_KEY` set by **all four** parsers, not the per-parser spelling this line
  originally cited (`empty_stdout` / `empty_response`). See `DONE.md`.
- 🔴 **No CI runs at all — and it cannot be switched on.** Superseding the "no *Windows* CI" framing:
  `gh workflow list --all` shows every workflow `active`, but `gh run list` returns **one run in the
  repo's entire history** (a Copilot review), so `test.yml` has **never executed** — PR #5 merged and
  PR #19 opened with zero checks. **The account is billing-blocked, so enabling Actions is not an
  available fix** (developer, 2026-08-01). **Consequence: the PR gate is workflow discipline at
  open-time, not a green check** — there is no machine backstop, so the evidence rules in
  `t4-dev-workflow` are the only thing standing between a red change and `main`. See
  [[ci-unavailable-billing-blocked]]. The Windows-portability defects below still matter (they are
  what a local run trips over), but they are no longer gated on "before CI can be switched on".
  **(M.)** **Measured 2026-08-01 on clean `origin/main` (`4eff266`): 25 failed, 851
  passed, 4 skipped** on Windows. ✅ **Fixed 2026-08-03 — the suite is now 0 failed / 886 passed**
  (**#30**, branch `fix/30-suite-green-on-windows`, `3bcd1e0`). **The diagnosis recorded here was
  wrong, and the way it was wrong is the lesson:** it sampled one failure, found a hard-coded POSIX
  path, and generalised that to all 25. There were **three unrelated causes**, and the largest was
  not a path problem at all —
  **(a) locale encoding, 12 of 25:** google-genai's vendored replay client opens cassettes with
  `open(path, 'r')` and no encoding, so Windows decodes UTF-8 gemini cassettes as cp1252 and the
  exact-equality request comparison fails on the mojibake. This also accounted for the 10
  `test_conversation_*` failures that **passed in isolation** and looked like test pollution — they
  were downstream of the chat tests failing, and needed no fix of their own.
  **(b) bash resolution, 3 of 25:** `subprocess` with a bare `"bash"` hits System32's WSL stub,
  because CreateProcess searches System32 before PATH. Note `shutil.which("bash")` disagrees and
  reports Git-for-Windows, so any PATH-based reasoning about this is misleading.
  **(c) POSIX path semantics, 10 of 25:** the originally-sampled cause, and genuinely a test defect —
  Windows' own dangerous paths (`C:\Windows`, `C:\Program Files`, `C:\Users`) are enforced correctly,
  and a POSIX path on Windows resolves to an ordinary user location where blocking would be a false
  positive. Fixed by parametrising the security tests per platform rather than skipping, so Windows
  gains real path-traversal coverage it never had; reintroducing the original CWE-22 is caught by 8
  tests.
  **Windows CI is no longer gated on this** — it would now land green, though Actions still cannot be
  switched on while the account is billing-blocked. See [[ci-unavailable-billing-blocked]].
  Plus lower-tier, still open: `shlex` Windows-path corruption, unbounded output/metadata,
  unsanitized command metadata, Claude `--print` ordering untested, antigravity timeout orphans child.

### Other

- 🔴 **An unknown CLI in `~/.openclink/cli_clients/` (or the pre-rename `~/.pal/cli_clients/`, still read too) fails the whole registry, not just that client.**
  `_resolve_config` (`clink/registry.py:137`) raises when a config's name is absent from
  `INTERNAL_DEFAULTS`; `server.py` builds the registry at import, so `pytest` dies at collection
  across every suite that imports the server. Reproduced 2026-08-01 (7 collection errors, 0 tests
  run) from a stale `cursor.json` override against a branch predating `main`'s cursor support.
  Fail-closed is defensible, but the blast radius should be one client — consider warn-and-skip for
  a *user-dir* config, keeping the hard error for a bundled one. See
  [[openclink-two-installs-and-config-cache]].
- 🔴 **Two venv names coexist on a dev box.** `run-server.sh` / `run-server.ps1` (and therefore
  `CLAUDE.md` / `AGENTS.md`) use `.openclink_venv`, but this checkout carries a `.venv` that those scripts
  never created — and it had no `pytest` until 2026-08-01. An agent that follows the docs finds no
  venv; one that finds `.venv` gets an under-provisioned environment. Neither is wrong, which is what
  makes it cost a session. Decide on one name, or have the docs detect either.
- 🔴 **Cross-platform CLI discovery** — `clink/discovery.py` known-install-locations are
  Windows-focused (winget / `%LOCALAPPDATA%` / npm). macOS/Linux paths not yet added; on those
  OSes it degrades to PATH-only. Add per-OS candidates when the fork runs there.
- 🔴 **Antigravity live model-selection integration test** — unit tests assert the `_build_command`
  ordering (`tests/test_clink_model_effort.py::test_antigravity_places_model_before_print`), but
  there's no opt-in live test that drives `agy` and asserts the selected model reaches the backend.
  See `docs/reports/2026-07-16-clink-antigravity-model-override-investigation.md` (acceptance criteria).
- 🔴 **Config activation persistence, revisited** — zero-setup discovery + the bundled active
  `claude-9arm.json` cover the common case; the `~/.openclink/cli_clients/` user-dir override (the
  pre-rename `~/.pal/cli_clients/` is still read too) is the
  escape hatch for custom gateways/paths. No open code item; documented in `CHANGES-FORK.md`.

## Shipped & closed

Feature/fix history for the fork is in `DONE.md` (newest on top) and the closed GitHub issues
(#1 per-call model/effort · #2 antigravity `--model` order fix · #3 zero-setup discovery +
claude-9arm), each closed-with-evidence citing its commit SHA.
