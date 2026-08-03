# Ship Log

What shipped in this fork, newest on top, one dated `##` entry per unit. The record a future
agent reads to learn how a change was validated. Fork-specific; upstream history is in git.

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
