# clink-brainstorm gap analysis — "what is this project missing?"

**Date:** 2026-07-16
**Repo revision at time of run:** `001746ae2a4309229fe484e412ecae8e7573b676` (`001746a`, branch `chore/bootstrap-t4-operating-layer`)
**Method:** multi-agent brainstorm via PAL `clink` (`clink-brainstorm` skill) — one question, three independent agentic CLIs in parallel, each reading the real repo; findings then verified by hand.
**Status:** Analysis complete. Findings NOT yet ticketed — follow-ups proposed at the end.
**Scope:** whole-repo gap audit, explicitly asked to go *beyond* the six hardening items already in `docs/OPEN-WORK-LEDGER.md`.

---

## 1. Workflow (what was run, exactly)

1. Gathered context myself (orchestrator = Claude Opus 4.8 [1m]): root listing, `git log`, `docs/OPEN-WORK-LEDGER.md`, `DONE.md`, `CHANGES-FORK.md`, `clink/` + `docs/` + `tests/` trees.
2. Wrote **one standalone question** ("produce a prioritized list of what this project is genuinely missing"), tailored per agent to its cognitive lens, listing the six already-known gaps and instructing each agent NOT to restate them. Each prompt pointed the agent at the real repo path and named the files to start from.
3. **Fired three `clink` agents in parallel** (independent calls, one message). No per-call `model` or `reasoning_effort` was passed to any of them → **each used its configured default** (this matters — see §4).
4. Read each response for substance, then **verified the four highest-impact, cheapest-to-check claims myself** with `grep`/`Read` before trusting them (see §3.1).
5. Synthesized into a prioritized recommendation (this file is the durable record of that synthesis).

Rounds run: **1** (single round). No challenge loop and no forced-adversarial round were run — the top findings were concrete and independently verified by hand, so extra rounds would have been low-value. `continuation_id`s were preserved (see §4) if a round 2 is ever wanted.

---

## 2. Models / effort used per agent

I did **not** override model or effort on any call, so every agent ran on its **preset default** (`conf/cli_clients/*.json`). Recorded for reproducibility:

| Agent (`cli_name`) | Backend model | Effort | Command (as launched) | Wall time | Tokens (in / out / reasoning) | Result | `continuation_id` |
|---|---|---|---|---:|---|---|---|
| `antigravity` | `agy` persisted default (Gemini; no `--model` passed) | default (agy bakes effort into the model name; none set) | `agy.exe --print` | 36.3s | n/a (parser text) | **No analysis** — returned only "I will view…" planning narration, `return_code 0`. Effectively empty. | `e8120844-5cc2-4629-8ac2-65ebb369c0ec` |
| `codex` | codex CLI default model (no `-m` passed) | codex default (no `reasoning_effort` passed) | `codex.CMD exec --json --dangerously-bypass-approvals-and-sandbox --enable web_search_request` | 399.5s | 1,619,774 (1,508,352 cached) / 13,389 / 7,104 | **Full analysis**, 13 ranked gaps (code/runtime lens) | `5156a43b-4f1f-4923-b07d-a8a518293173` |
| `claude-9arm` | `qwen3.6-35b-a3b` (via 9arm gateway; `--model qwen3.6-35b-a3b` from config) | n/a (gateway model, no effort knob) | `claude.exe --print --output-format json --settings ~/.claude-9arm.json --model qwen3.6-35b-a3b --append-system-prompt …` | 320.3s | 872,030 / 7,336 / — | **Full analysis**, 14 ranked gaps (logic/coherence lens); `total_cost_usd` 4.54 (internal accounting) | `bdfe76a6-1ac2-4e2b-8bb3-a291f3586844` |

**Orchestrator / synthesis:** Claude Opus 4.8 (1M ctx), effort `high`.

Notes:
- **Antigravity produced no usable output** — it returned its tool-plan narration and stopped without a synthesized answer (`return_code 0`, no error). Consistent with the known antigravity PTY/timeout fragility already in the ledger. So the analysis below rests on **two** agents, not three.
- **claude-9arm hit 2 permission denials** (`Read` on `clink/discovery.py` and `clink/parsers/__init__.py` were blocked by the host classifier), so a few of its file:line citations are inferred rather than read — flagged where relevant.

---

## 3. Analysis (synthesized findings)

Ranked. "✅ verified" = I confirmed it myself in this repo at `001746a`; "⚠️ plausible" = reported by an agent, not independently re-checked.

### 3.1 Top tier — both agents converged AND I verified by hand

| # | Gap | Evidence (hand-verified) | Why it matters | Effort |
|---|---|---|---|---|
| 1 | **Setup scripts + docs install `upstream`, not the fork** | ✅ `run-server.sh:1872,1897,2449,2569` and `docs/getting-started.md:84,105,126,143,171,235` generate MCP config running `uvx --from git+https://github.com/BeehiveInnovations/pal-mcp-server.git` | A user following the README/scripts silently runs **upstream without any of the fork's clink/T4 work**. Highest impact, lowest effort. | S |
| 2 | **Delegated CLIs inherit the entire `os.environ`** | ✅ `clink/agents/base.py:228` `env = os.environ.copy()` then `env.update(self.client.env)` | A delegated (or prompt-injected) CLI can read every unrelated API key / GH token. Workspace isolation alone does not fix this. Needs a minimal env + per-client allowlist. | M |
| 3 | **`readOnlyHint=True` is inaccurate** (already in ledger, re-confirmed) | `tools/clink.py` annotations; every CLI runs with bypass-approvals | Host treats a repo-mutating tool as read-only. | S |
| 4 | **All CLIs are told "You are operating through the Gemini CLI agent"** | ✅ `tools/clink.py:472–474` `_agent_capabilities_guidance()` hardcodes the Gemini string, returned verbatim for codex/claude/antigravity too | Gives every delegated agent a false identity/capability set. | S |
| 5 | **Non-zero CLI exit is reported as `success`** | `clink/agents/claude.py` + `clink/agents/codex.py` `_recover_from_error` accept any parsable output despite non-zero exit; `tests/*` lock this contract in | An orchestrator continues after an edit failed / timed out / was partial. Dangerous in unattended mode. Needs explicit `partial`/`failed` status. | M |
| 6 | **No Windows CI** | `.github/workflows/test.yml` runs `ubuntu-latest` only | The fork's core (ConPTY, `pywinpty`, discovery, Windows path handling) is Windows-first and **never exercised in CI** — green while Windows can be broken. | M |

### 3.2 Codex lens (code / runtime) — agent-reported

- **`pywinpty` is in `pyproject.toml` but NOT `requirements.txt`** ✅ (confirmed in codex's own file dump: `requirements.txt` lacks it; `pyproject.toml` has `pywinpty>=2.0.0; sys_platform=='win32'`). Run scripts install from `requirements.txt` → install succeeds, first `agy` call fails. No `uv.lock`; open-ended `>=` pins. — S/M
- **`shlex.split(command, posix=True)` corrupts Windows paths** ⚠️ `clink/registry.py` `_resolve_executable` — `C:\Tools\agy.exe` → `C:Toolsagy.exe`; spaces split into bad tokens. Prefer list-valued command / platform-correct parse. — S/M
- **Output not actually bounded** ⚠️ `base.py:run()` uses `communicate()` (accumulates full stdout); the 20k cap (`tools/clink.py` `_apply_output_limit`) trims only `content`, while `raw`/`raw_events` and error stdout/stderr stay unbounded → memory + oversized MCP responses. — M/L
- **Command metadata not sanitized** ⚠️ `claude.py` embeds the full system prompt in `--append-system-prompt`; `base.py:run()` logs the command and `tools/clink.py` returns it to the caller → prompt/secret leak via logs + response. — M
- **Cancellation/timeout cleanup has no encompassing `finally`** ⚠️ temp files (`base.py`) and child process trees can leak on timeout/parse-error/spawn-failure. — L
- **Parser type/framing gaps** ⚠️ `parsers/gemini.py` assumes dict from `json.loads` (valid `[]` → uncaught `AttributeError` bypassing `ParserError`); `parsers/codex.py` silently drops malformed lines; `parsers/antigravity.py` doesn't model cursor overwrites/backspaces. — M
- **Invalid `cwd` reported as "executable not found"** ⚠️ `registry.py` `_resolve_optional_path` doesn't require the dir to exist; `base.py` mislabels the spawn error. — S

### 3.3 claude-9arm lens (logic / coherence) — agent-reported

- **Claude agent `--print` ordering is unverified** ⚠️ (high-value) `clink/agents/claude.py` appends model args after `--print` and does NOT override `_build_command` like antigravity had to; **no unit test** in `tests/test_clink_model_effort.py` for the Claude agent. Same bug class as the antigravity `--model` bug (ADR 0002). — S
- **Antigravity timeout orphans the child** ⚠️ `clink/agents/antigravity.py` `_run_in_pty` breaks the read loop and `proc.close()` closes only the Python handle — the `agy` subprocess is never killed (contrast `base.py` which does `process.kill()`). Extends known ledger item #3 from "may not interrupt" to "leaks a process." Also: reads `exitstatus` before close and returns `exit or 0`, so `None` → success. — S/M
- **Registry singleton, no reachable reload** ⚠️ `clink/registry.py` `get_registry()` caches; `reload()` exists but nothing in the tool layer can call it → config change needs a full server restart. — M
- **No health-check / CLI-availability tool** ⚠️ nothing lets an orchestrator verify a CLI is present before delegating. — S
- **No input-length validation on `prompt`** ⚠️ output capped at 20k, input uncapped → arg-length/memory risk. — S
- **ConPTY dimensions hardcoded `50×200`** ⚠️ `antigravity.py` — wide output truncates. — S
- **Governance:** `conf/cli_clients/claude-9arm.json` ships active with a real gateway path; no CODEOWNERS / clink issue template; no `CHANGELOG.md` / architecture diagram (only `DONE.md` + ADRs). — S/M

### 3.4 Orchestrator's read (full-session context the agents lacked)

- The **six top-tier items dominate**; four of them I verified by hand, so they are not hallucinations.
- **#1 (upstream URL) is the single most important** despite being effort S — it silently erases the fork's entire value for anyone following the docs.
- The current ledger focuses on isolation/PTY/discovery but **misses three whole categories** the agents surfaced: (a) **distribution** still points upstream, (b) **secret hygiene** (`os.environ.copy()` + unsanitized command metadata), (c) **failure semantics** (non-zero→success, locked in by tests).
- Antigravity failing to answer *this* review is itself weak evidence for the antigravity-reliability items.

---

## 4. Proposed follow-ups (not yet ticketed)

Suggested order (impact ÷ effort):

1. Fix `upstream` → `xenodeve/pal-mcp-server` in `run-server.sh` + `docs/getting-started.md` (+ `run-server.ps1` — check it too). **[S, do first]**
2. Add `pywinpty` to `requirements.txt`; generate `uv.lock`. **[S]**
3. Parameterize `_agent_capabilities_guidance()` by `client.name`; fix `readOnlyHint`. **[S]**
4. Failure semantics: introduce `partial`/`failed` status instead of inferring success from parsable output. **[M]**
5. Minimal-env allowlist for delegated CLIs (`base.py:_build_environment`). **[M]**
6. Add a `windows-latest` CI job. **[M]**
7. Add a Claude-agent `_build_command` test (guard the `--print` ordering); harden antigravity timeout to kill the child. **[S each]**

Each should become a bilingual (TH+EN) GitHub issue per the fork's issue→PR gate before any code lands. These are **candidates**, not yet on the ledger.

---

## 5. Reproducing / continuing this brainstorm

- Re-run: `clink-brainstorm` skill → three `clink` calls (`antigravity`, `codex`, `claude-9arm`) with the same standalone question.
- To push a round 2 at any agent without re-explaining, reuse its `continuation_id` from §2.
- If antigravity keeps returning empty, that is the known PTY/timeout symptom — treat as a 2-agent brainstorm or swap in `claude`/`gemini`.
