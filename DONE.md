# Ship Log

What shipped in this fork, newest on top, one dated `##` entry per unit. The record a future
agent reads to learn how a change was validated. Fork-specific; upstream history is in git.

## 2026-08-04 — an AFK batch on the clink honesty line, plus the Phase 0 spike (#12, #43, #37, #41, #29)

Five items cleared unattended. The thread joining four of them: **a knob, a default, a payload or a
failure that the caller could not see.** #43 dropped `reasoning_effort` silently; #29 resolved an
omitted model to a config default and reported it like a choice; #37 forwarded a parser's whole
payload beside a field that was capped; #41 reported what a failed run spent but not what ran it.

**Validated** — each red observed before its implementation, each mutation-tested:

- **#43** (PR #45) `agy --effort low|medium|high` is real. Measured against the binary: the two knobs
  are mutually exclusive for every model it serves (`agy models` shows every id either bakes its tier
  in or has no ladder), so the client refuses the pair before spawn. Honoured, not merely accepted —
  same prompt, `--effort low` → 0 thinking tokens, `--effort high` → 446. The refusal probes cost no
  quota: agy validates argv before calling a model (`duration_seconds: 0`).
- **#37** (PR #46) `raw` / `raw_events` dropped in `_prune_metadata`, the one point both paths pass
  through. Dropped rather than capped because a repo-wide grep found **no production reader** — only
  two parser-level test assertions. Mutation: pruning one key, or one path, reddens the other.
- **#41** (PR #47) `CLIAgentError` carries the same field names as `AgentOutput`, so `_call_accounting`
  is one projection for both outcomes. `observed_model` is now omitted when unobserved rather than
  reported as `"unknown"` — which is what the function's own docstring already promised two lines up.
- **#29** (PR #48) **Breaking.** `model` is required. 12 test call sites had to carry one; one test
  asserted `requested_model` absent, a state that no longer exists through the tool, and was rewritten
  rather than patched. `CHANGES-FORK.md` gained a Breaking-changes section because its intro claimed
  every fork change was additive.
- **#12** (PR #44) Phase 0 spike. All four live clients are resumable headlessly; only Claude Code
  demonstrably has a pre-tool hook that can block, so Phase 4 must be proven there first rather than
  shipped uniformly. **The epic's transport premise is now an open question, not a finding** — the
  60–108s figure was not measured on Claude Code, and the fault is intermittent, so five successful
  calls prove nothing about it either way.

**Two corrections landed on the spike report itself**, both from the owner: the premise is host-scoped
(PAL is an MCP server on all four hosts, one was measured), and the fault is random, so a rate is
needed rather than a verdict. Recorded in `docs/reports/2026-08-04-clink-phase0-spike-host-followup-and-cli-capability.md`.

**The owed gates were paid on 2026-08-04, after the batch and before any merge.** `/simplify`,
`/code-review` and `/scrutinize` had run zero times across the batch, against `t4-afk`'s own gate list.
Run afterwards across all ten open PRs (six here, four in `xeno-skills`), they found a real defect in
**seven** of them — so the omission was not harmless, and none of it would have surfaced at merge:

- **#46** `/simplify` — `events` was already pruned with exactly the shape this PR added for
  `raw`/`raw_events`: same marker convention, same debug log, written twice. One loop over three keys.
  Mutation-checked (dropping `events` from the tuple reddens 3 tests).
- **#47** `/code-review` — `_call_accounting` was annotated `result: AgentOutput` while the error path
  passes it a `CLIAgentError`. Nothing type-checks this repo, so the declaration was free to be wrong.
- **#48** `/code-review` — the schema's `model` description said "Required" while `required` stayed
  `["prompt"]`. A validating MCP client would accept the omission and meet the refusal at execution
  time. Red observed first, then `["prompt", "model"]`.
- **#44 · xeno #100** `/scrutinize` — **the same defect in both, and it is the one worth remembering:**
  a correction was appended to the body and never propagated to the summary, so the top of each
  document still asserted the claim its own body withdrew. #44's Status section also pointed at a
  section that does not exist.
- **xeno #103** `/code-review` — a test whose description read "each claim carries the date it was last
  verified" checked only that the *column header* existed. Replaced with a row count; mutation-checked.
- **xeno #101** `/code-review` — an assertion anchored on a 7-character generic substring.
- **#45 · xeno #102** — clean. On #45 a reuse candidate was considered and rejected: `_model_args`
  could delegate its `--model` half to `super()`, but `codex.py`'s override writes the same shape
  explicitly, and matching the sibling won.

Also caught while listing each branch's files: a `git add -A` during the review had swept 19 untracked
`.playwright-mcp/` files and `aa-home-snapshot.md` into #47. Removed.

**`/security-review` did not trigger, and here is the checkable fact:** `git diff --name-only main...`
for all five branches lists `clink/agents/{antigravity,base}.py`, `tools/clink.py`, `CHANGES-FORK.md`,
one report, and test files. No file under an auth, secret, token, entitlement or payment path.

## 2026-08-03 — the clink model is read back from every spelling, and reported three ways (#27 PR #35, #28 PR #40)

Two slices that only make sense together: #27 refuses a model the client cannot serve *before* spawning,
and #28 reports `requested` / `resolved` / `observed` so a backend that ran something else is visible
*after*. Both merged onto a `main` that already had #13.

**The lesson worth keeping is that both were fixed twice.** Each shipped a first version that closed the
case in front of it, and a pre-merge review found the same defect one layer out:

- #27's first fix handled `-c model=X`. Probing the real binary found **five more spellings that all
  reached the API** — `-mX`, `--model=X`, `-cmodel=X`, `--config model=X`, `--config=model=X`. The fix
  covered three of eight while its own commit message argued against enumerating spellings. Parsing is
  now one function, `flag_values`, and *both* the model and effort knobs derive from it; the effort knob
  had the identical hole.
- #28's `model_substituted` compared names with `!=`. The shipped claude config asks for `sonnet` and
  the parser reports `claude-sonnet-4-5-20250929`, so the flag fired on **every ordinary run of that
  client** — worse than absent, because a flag that fires constantly cannot carry the one signal it
  exists for.

**Verified against the real CLI, and that phrase needed care.** Two codex binaries are installed:
`which codex` gives **0.142.4**, while clink spawns `codex.CMD` **0.144.4**, and they disagree — the
older one 400s on a model the newer serves. A shell probe silently tests the wrong one. Precedence was
measured, not assumed: a two-token model flag beats a config-key spelling regardless of token order.

**Stated rather than overstated.** `refuse_unservable` reads the command, and codex also takes a model
from `~/.codex/config.toml` (line 1 here is `model = "gpt-5.6-luna"`) and from `--profile`. The catalog
therefore cannot be enforced from argv at all. Closing that is a public-contract change, so it is #39,
and the docstring now says plainly that the check guards what PAL builds and does not guarantee what the
CLI runs.

**Validated:** `960 passed, 4 skipped` on `main`. Red was genuine throughout — the refusal tests failed
with `a process was spawned for a request that should have been refused`, each logging the command that
actually spawned. Ten mutants across the two slices, all killed. Two survived on first run and both
pointed at real coverage gaps rather than dead code: the antigravity parser had no test at all, and the
punctuation-normalisation step in the name comparison was unexercised.

Follow-ups filed rather than absorbed: #37, #39, #41 · and #36 for the missing enforcement layer.

## 2026-08-03 — a clink run that failed is now reported as failed (#13, `e3c7c5b`)

A non-zero exit used to be re-parsed by the recovery hook and, if the output parsed, returned as a
successful `AgentOutput` with the exit code discarded. A master agent cannot supervise a subagent
whose failures arrive labelled as completions, and no test asserted otherwise — the masking path was
entirely uncovered.

The outcome is now stated rather than inferred from parseability, and decided in exactly one place:
`BaseCLIAgent.finalize_output`. That seam only exists because #23 routed all five construction sites
through it — including `AntigravityAgent`, which overrides `run` wholesale and could never have
inherited a fix applied to the base loop. Recovery keeps its real job: salvaged content and the
normalised token account now travel on `CLIAgentError` (`parsed`, `token_usage`) and are surfaced by
`_build_error_metadata`, so #23's guarantee that a failed call still reports what it consumed holds —
only its address moved from the result to the error.

**The issue's second case was mis-specified and the correction is the durable part.** It described
"exit 0 with empty output"; no parser in the tree can produce that, since all four raise on empty
content. The real mechanism is that `clink/parsers/antigravity.py` returns *stderr as the content*
when stdout is empty, tagging it `empty_stdout` (**renamed later the same day** — the tag is now the
shared `NO_ANSWER_METADATA_KEY`, because the gemini parser spelled the same concept `empty_response`
and `finalize_output` checked only one of them) — so an empty run arrives with non-empty text and
that tag is the only thing separating a diagnostic from a reply. The parser had been labelling it all
along and nothing read the label.

**Validated:** three tests observed failing first (all `DID NOT RAISE CLIAgentError`), then green.
Three existing tests asserted the removed behaviour: two rewritten to the new contract, one removed
outright with a comment in its place explaining that its rewrite would have duplicated a new test
verbatim. `pytest tests/ -m "not integration"` → **906 passed / 0 failed**. Verified end to end
against the **real codex binary** — driving it with a nonexistent model exits 1 with JSONL that
parses cleanly (the exact shape that used to become a success) and is now reported as a failure
carrying the API's own 400 message; `token_usage` correctly absent because the turn never completed.

## 2026-08-01 — T4 operating layer (Seed) + clink research relocated (#4)

The fork now runs agent-primary: a fresh session recovers state from `Obsidian-Pal_MCP/Home.md`
(MoC + 7 durable notes), `docs/OPEN-WORK-LEDGER.md`, and this log, with the conventions in
`docs/agents/{domain,workflow,issue-tracker,triage-labels}.md`, decisions in `docs/adr/` (0001–0003),
and the clink-*code* research reports that belong here (delegation-routing research was moved onward
to `xeno-skills` — see `docs/reports/README.md`). `CLAUDE.md` gained an "Operating standard (T4,
fork)" section; the upstream guide is preserved. Adapted to Python/uv/pytest/ruff, not Bun.
**Validated:** docs-only — `git diff --name-only origin/main...HEAD` is 23 `.md` + `.gitignore`, no
`.py`; unit suite on this machine after `mcp<2` local pin + merge of main: **851 passed, 25 failed,
4 skipped** — same 25 failures on clean `origin/main` (Windows POSIX-path test portability, not
this diff). The layer's real test is that the epic filed on top of it (#11 → #12–#16) was written
from these files.

## 2026-08-01 — Bound the `mcp` pin in `requirements.txt` + add `pywinpty` (#17)

`requirements.txt` carried an unbounded `mcp>=1.0.0` and no `pywinpty`, while `pyproject.toml` had
both right — so any installer reading `requirements.txt` (run-server, agents) built an unimportable
tree, because `mcp` 2.0.0 removed `Server.list_tools` which `server.py` decorates with at import.
Fixed by making the two manifests agree, guarded by a new `tests/test_dependency_pins.py` that fails
on any drift between them. **Validated red→green:** the guard test failed first, naming both defects
(`drift: 'mcp>=1.0.0,<2' (pyproject) vs 'mcp>=1.0.0' (requirements)` + `absent from requirements.txt:
"pywinpty>=2.0.0; sys_platform=='win32'"`), then passed. **Validated end-to-end in a clean venv**
(`python -m venv` + `pip install -r requirements.txt -r requirements-dev.txt`): resolved
`mcp==1.29.0` and `pywinpty==3.0.5`, `hasattr(Server('x'),'list_tools')` → `True`, `import server`
→ OK, and `pytest tests/ -q -m "not integration"` → **25 failed, 852 passed, 4 skipped, 16
deselected** — i.e. it *collects and runs* (it previously produced 7 collection errors and 0 tests
run), with the 25 failures matching the pre-existing Windows POSIX-path baseline on clean `main`.
ruff/black/isort clean. Adoption of the `mcp` 2.x API is deliberately **not** decided here — split
to **#18**.

## 2026-07-16 — Zero-setup CLI discovery + active `claude-9arm` (#3, `d44ae01`)

Installing PAL normally exposes `codex` / `antigravity` / `claude-9arm` with no extra setup; an
absent CLI reports "not found". `clink/discovery.py` resolves a bare command via PATH → per-CLI
known install locations (winget, `%LOCALAPPDATA%\agy\bin`, npm); the registry expands `~`/`%VAR%`
in `config_args`; `conf/cli_clients/claude-9arm.json` ships active. **Validated:** loaded the
registry from bundled config alone (no `~/.pal` overrides) → antigravity → `…\agy.exe`,
claude-9arm → winget `claude.exe` with `~` expanded, codex via PATH; `tests/test_clink_discovery.py`
(4) + `tests/test_clink_model_effort.py` (6) green; live clink calls confirmed.

## 2026-07-16 — Antigravity `--model` order fix + fail-closed (#2, `7e80e42`)

`agy --print` is value-taking; the old order let it swallow `--model` → silent default. Fixed by
placing model options before `--print` in the Antigravity runner + raising on a non-zero exit.
**Validated:** independent PowerShell repro (wrong order → *Gemini 3.5 Flash*, right order →
requested model); live via PAL clink: `Claude Sonnet 4.6 (Thinking)` → Claude Sonnet, `Gemini 3.1
Pro (High)` → Gemini 3.1 Pro, invalid model → exit 1 + catalog (fail-closed).

## 2026-07-16 — Per-call `model` + `reasoning_effort` for clink (#1, `97a7072`)

Optional per-call params mapped per back-end (codex `-m`/`-c`, others `--model`), appended after
config args (backward compatible), via a `_model_args()` hook `CodexAgent` overrides. **Validated:**
`tests/test_clink_model_effort.py` (red→green); live — codex effort scales reasoning tokens
(low=0 vs high=45+), invalid model → hard 400, `gpt-5.6-luna` accessible.
