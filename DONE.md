# Ship Log

What shipped in this fork, newest on top, one dated `##` entry per unit. The record a future
agent reads to learn how a change was validated. Fork-specific; upstream history is in git.

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
