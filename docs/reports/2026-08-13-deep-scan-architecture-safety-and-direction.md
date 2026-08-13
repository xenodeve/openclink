# Deep scan of the fork — architecture, the safety boundary, and where it can go (2026-08-13)

**Method:** three rounds. Rounds 1–2 sent twelve independent readers over twelve subsystems and handed each load-bearing claim to a separate agent instructed to *break* it — 380 claims, of which 27 reached a refuter and **11 were refuted or materially corrected**. Round 3 (§10c) sent eight readers over the ~21,000 lines the first two never opened, with **no refuter stage**: verification was done afterwards in the main loop against named claims, which cost almost nothing and produced the sharpest numbers in this report. **605 claims in total**, read at `2aa6e49`, branch `feat/85-opencode-client`.

**Coverage:** roughly 26,000 of the 30,238 lines of production Python have now been read. What remains is named with line counts in §10b and §11.

**Scope note, because it changes how to read this:** this is a **code scan**. Issue and PR numbers appear only as annotations so that whoever picks a finding up can find its tracker context — no finding here was derived from reading the tracker, and none should be actioned on the strength of an issue number alone.

**Honest limit on the method.** The refutation pass was designed to attack every load-bearing claim and was cut short by a quota exhaustion partway through: **41 of 68 planned refutations never ran.** So the 27 verdicts below are a *sample*, and the 11-refuted-of-27 rate — **41%** — is the most useful single number in this report. It is the rate at which a careful, evidence-citing reader's load-bearing claim did not survive one round of adversarial checking. Apply it to everything here that is not marked as refuter-verified.

---

## 1. The clink call path, and every point where something is dropped

A `clink` tool call runs: MCP request → `reconstruct_thread_context` (if continuing) → `CLinkTool.execute` → agent `_build_command` → `asyncio.create_subprocess_exec` → parse → metadata assembly → `_prune_metadata` → `_apply_output_limit` → turn recorded → response.

Six places lose information, and only two of them tell the caller:

| Where | What is lost | Caller told? |
|---|---|---|
| `_prune_metadata` (`tools/clink.py:690`) | `events`, `raw`, `raw_events` — the worker's whole event stream | yes, as `events_removed_for_normal: true` |
| `_apply_output_limit` (`tools/clink.py:617-651`) | on a `<SUMMARY>` hit, **everything outside the tags** | partly — sizes are reported, the discarded body is not |
| turn recording (`tools/clink.py:343-347, 367`) | the thread stores the **post-limit** text | no |
| history eviction (`utils/conversation_memory.py:964-972`) | oldest turns, when the budget is exhausted | only as a prose line inside the prompt |
| file inclusion (`tools/shared/base_tool.py:812-824`) | a file skipped by history is still filtered out of the tool's own embedding | no |
| the turn ceiling (`MAX_CONVERSATION_TURNS`, default 50) | `add_turn` returns `False` and **every caller ignores it** | no |

**The summarisation path is a selection, not a compression.** When a response exceeds `MAX_RESPONSE_CHARS` (20,000, hardcoded at `tools/clink.py:46`) and carries a `<SUMMARY>` block, what returns is the text inside the first matching tag pair and nothing else — the analysis that produced the summary is discarded and only its character count survives. *(Refuter-verified.)*

**And the truncated copy is what the thread keeps.** Driven against the real `execute`, a 25,000-char answer with a `<SUMMARY>` tag left the thread holding only the summary. A follow-up turn cannot see what the delegate actually said, so any feature that re-reads a delegation — verification, audit, escalation — reads a lossy copy with no marker saying so. *(Refuter-verified.)*

**Correction from the refutation pass:** an earlier reading of this called `MAX_RESPONSE_CHARS` the only cap. There is a second, independent one — `MAX_DRAINED_OUTPUT_CHARS = 10_000` (`clink/agents/base.py:71`), applied to drained output on the timeout path at `:296-297`. Every response cap in the tool surface still lives on the clink path; no other tool bounds what it returns.

**clink never reads file contents.** `_format_file_references` (`tools/clink.py:759-773`) emits `path (last modified …, N bytes)` and nothing else, and the child is told to open the files itself. This is a genuine design decision with a consequence worth naming: a delegation to a sandboxed or remote CLI answers about files it never opened, and no token budget applies because nothing was read.

---

## 2. The safety boundary — the largest single property of this fork, and the least documented

Stated plainly: **a `clink` tool call starts an unsandboxed foreign coding agent, carrying the server's entire environment, in whatever directory the server happens to occupy, and the MCP host is told the tool is read-only.**

Each clause is separately verified:

- **`readOnlyHint: True`** — `tools/clink.py:156-157`. A host that uses the annotation to decide auto-approval will auto-approve arbitrary code execution. No test anywhere asserts any annotation value. *(Known since the 2026-07-16 hardening review; still shipped.)*
- **Full environment inheritance** — `clink/agents/base.py:533-536`, `env = os.environ.copy()` then `env.update(self.client.env)`. Every shipped client declares `"env": {}` and no entry in `INTERNAL_DEFAULTS` supplies one, so **the child's environment is byte-identical to PAL's**, including `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`, `DIAL_API_KEY`, `CUSTOM_API_KEY`. There is no allowlist.
- **`.env` is part of that inheritance** — `utils/env.py:57` calls `reload_env()` at module scope, imported by `server.py:72`, `config.py:11` and `clink/registry.py:27`, so PAL's own `.env` is in `os.environ` on the clink path and is handed to the child. *(Refuter-verified, both by reading the chain and by executing it.)*
- **No working directory is set** — no shipped client sets `working_dir`, so `cwd=None` and the delegate runs against the server's own directory.
- **Every shipped config disarms the target CLI's own safety mechanism.** Privilege is inherited from vendor bypass flags rather than decided. *(Tracker context: this is what #14's per-client trust level exists to replace.)*
- **The error envelope relays the child verbatim** — a failed child's stdout and stderr come back to the MCP caller (bounded at 20,000 chars each), so anything the foreign agent printed, including an environment dump it chose to make, is returned.

**Two further surfaces found by the security reader:**

- **Argv injection on Windows.** A caller-supplied `model` string can break out of its argument and execute arbitrary commands, because the resolved executables are `.cmd` batch shims and Python's `list2cmdline` escaping is not honoured by `cmd.exe`. The one guard that could refuse a bad model — `refuse_unservable` — is **inert for every shipped client**, because no config declares a `model_catalog`.
- **The path sandbox in the docstring does not exist.** `utils/file_utils.py:16` claims "All file access is restricted to PROJECT_ROOT and its subdirectories". `resolve_and_validate_path` (`:282-324`) enforces only: absolute path required, symlinks resolved, dangerous system roots blocked, home **root** blocked. Verified allowed against the live functions: `~/.ssh/id_rsa`, `~/.aws/credentials`, `~/.claude.json`, and PAL's own `.env`.

**What is *not* a problem, checked and cleared:** API keys are read via `get_env` and logged **by presence only**; a 12 MB production log contains no secret-shaped material; the OpenAI SDK logs `'security': {'bearer_auth': True}` — a flag, not the credential. Conversation turns live in process memory with a TTL, with no disk or Redis backend to leak from.

**But full prompts do land on disk.** The file handler is attached to the **root** logger at DEBUG, so `openai._base_client`, `httpx` and friends are captured: system prompt, user prompt and any embedded file contents are written verbatim to `logs/mcp_server.log`. The clink runner also writes the full spawned argv on every call — 274 occurrences in the current log — which for the claude client includes the entire `--append-system-prompt` value.

**`SECURITY.md` describes a different system.** It characterises PAL as "middleware between AI clients … and various AI model providers" and never mentions clink, subprocess spawning, foreign CLI agents, bypassed approval flags, or environment inheritance — it names Codex CLI and Cursor as *clients*, which is the opposite of their role here. It also routes vulnerability reports to the **unmaintained upstream's** advisory page.

---

## 3. Concurrency and liveness — three defects that compound

**The timeout does not fire.** `clink/agents/base.py:284-292` wraps `process.communicate()` in `asyncio.wait_for`; on timeout it calls `process.kill()` and then `await process.communicate()` **with no timeout**. If the CLI spawned a grandchild, that grandchild inherits the stdout pipe, so the second `communicate()` never returns. **The `CLIAgentError("timed out after N seconds")` is therefore never raised** — the caller is never told, and the coroutine is pinned until the orphan exits. This is worse than "leaks a process", and it changes the fix: any supervisor must drain with its own deadline and close the parent's pipe. *(Tracker context: #20.)*

**On antigravity the deadline is unreachable by construction.** `clink/agents/antigravity.py:194-207` checks the deadline at the top of the loop and then calls `proc.read()`, which performs a **blocking** `socket.recv` — pywinpty defaults to blocking mode, which also makes two branches of that loop dead code. A live-but-silent `agy` blocks the worker thread indefinitely, and `asyncio.to_thread` cannot cancel it. In practice `agy`'s own `--print-timeout` (5 minutes) usually saves it — but that is the child's discipline, not PAL's. *(Tracker context: #65 owns the print-timeout decision.)*

**A stale doc claim to stop planning against:** `_run_in_pty` *does* call `proc.close(force=True)`, which reaches pywinpty's `terminate(force=True)`. The 2026-07-16 report's "the agy subprocess is never killed" is **wrong for the direct child**; it remains true for descendants, and it is unreachable anyway when the read blocks. Re-planning from that report would fix an already-fixed bug and leave the real one.

**The largest event-loop stall is not in clink at all.** `provider.generate_content(...)` is a plain synchronous HTTP call invoked directly from `async def execute` (`tools/simple/base.py:444`, again at `:501`, `tools/workflow/workflow_mixin.py:1493`, `tools/consensus.py:618`) — no `await`, no `asyncio.to_thread`. One `chat`/`analyze`/`debug`/`consensus` call freezes the whole loop for the entire round-trip, up to the 600 s httpx read timeout, plus up to 17 s of `time.sleep` in the retry loop. **A load test that fires only clink calls will miss this**, and the same process serves both.

**Supporting facts:** there is no concurrency control of any kind — no semaphore, queue, admission cap or per-workspace lease. `DEFAULT_STREAM_LIMIT = 10MB` (`clink/constants.py:9`) is a flow-control watermark, not a cap. Logging defaults to DEBUG and writes synchronously from the event-loop thread, including inline 20 MB rollovers; the log tree is currently 118 MB. On a continuation, every file referenced anywhere in the thread is re-read and line-numbered synchronously before the subprocess is spawned — measured 11 ms at a 64k-token budget, 51 ms at 320k.

**Ten concurrent clink calls, concretely:** ten tasks on one loop, ten subprocesses with no cap, all in PAL's cwd with PAL's full environment; ~110–510 ms of aggregate blocking file I/O if they are continuations; full transcripts accumulating in memory unbounded; and any one that times out never reports.

**One shared mutable structure is unprotected.** `add_turn` is a lock-free read-modify-write: it reads the whole thread, appends, writes it back (`utils/conversation_memory.py:354 … 384`). The storage lock covers each get and each set but not the pair, so two concurrent calls on one `continuation_id` silently lose a turn — which also under-reports the cost accounting that sums surviving turns.

---

## 4. The memory layer

**The highest-value finding in this section, and possibly in the report.** The guard that stops `SimpleTool` from rebuilding history looks for `"=== CONVERSATION HISTORY ==="` (`tools/simple/base.py:335`), but `build_conversation_history` emits `"=== CONVERSATION HISTORY (CONTINUATION) ==="` (`utils/conversation_memory.py:798`). The substring never matches. So on **every** chat continuation through the MCP server, the else-branch runs: a second user turn is added whose content is the already-enhanced prompt — full prior history plus new input plus follow-up instructions — and history is rebuilt on top of it. Two user turns per continuation, one containing the entire prior history, so stored thread size grows super-linearly.

Everything else in this layer is smaller but consistent in shape — *the caller is never told what was lost*:

- **Thread lifetime** is a sliding TTL that slides only on a successful write. *(Refuted as originally stated: an actively-written thread does **not** live forever — once it hits `MAX_CONVERSATION_TURNS`, `add_turn` returns `False` **before** the `setex` that refreshes the TTL, so the thread stops being refreshed and expires.)*
- **A restart destroys every thread** — `get_storage_backend()` unconditionally returns an in-memory singleton; no Redis, sqlite, pickle or file backend exists in production code. The failure message hardcodes "more than 3 hours ago" regardless of the configured timeout. And because the transport is stdio, the server is a subprocess of the client, so "restart" understates the loss window. *(Refuter-verified.)*
- **Two different token estimators** are used inside one budget calculation — `len//3` in `utils/model_context.py:174` gates inclusion, `len//4` in `utils/token_utils.py:33` produces the number reported and subtracted from the file budget. The remaining-token figure is systematically optimistic by a third of the history's own internal estimate.
- **`model_metadata` is one untyped slot with three incompatible schemas** — clink writes `{"accounting": …}`, SimpleTool writes `{"usage": …, "metadata": …}`, workflow tools write `{"work_history": […]}`. *(Refuter-verified, including a search for a fourth writer.)*
- **Continuation resolves against the originating tool.** `server.py:1098-1099` reads `requires_model()` from the tool that *created* the thread. Continuing a clink thread with `chat` silently resolves a new model instead of inheriting the thread's.
- **The clink history budget is sized against the wrong model** — a fallback provider model chosen by `get_preferred_fallback_model()`, never the CLI model that will receive the prompt. The model-catalog work gave clink a per-call model but not a per-call context window.
- **Documented turn limits contradict the constant** in three places (docstring "20 turns max", config comment "default to 20", `docs/ai-collaboration.md` "up to 10 exchanges"); the constant is 50.

---

## 5. The MCP surface — and the options nobody has costed

PAL advertises exactly **two** capabilities, `tools` and `prompts`, via a hand-written `ServerCapabilities(...)` literal that bypasses the SDK's own `get_capabilities()`. `listChanged` is unset on both. `resources`, `logging`, `completions` and `experimental` are never populated.

**The pinned SDK already exposes every unused capability as a one-call API on the server session** — `create_message` (sampling), `elicit`/`elicit_form`/`elicit_url`, `list_roots`, `send_log_message`, `send_progress_notification`, and the three `send_*_list_changed` notifications. None is reachable from PAL's code today. That makes the following genuine design options rather than speculation:

| Unused | What it would buy | The seam it attaches to |
|---|---|---|
| **Progress notifications** | Long work is currently **completely silent**: a child may run 1800 s and PAL reports nothing until it exits; a 672 s call has been measured. The data already exists and is thrown away — codex `--json`, opencode `--format json` and claude JSONL are line-oriented event streams that PAL consumes only after `communicate()` returns the whole buffer at exit. | the parser layer, plus streaming reads instead of `communicate()` |
| **Elicitation** | The epic that most needs an ask-the-caller channel is designing a bespoke one (#16 specifies "a new local control endpoint" whose "shape [is] deliberately undefined"). Elicitation is that channel, already in the protocol and already in the SDK. | the approval flow |
| **Resources** | Several things PAL holds are natively resource-shaped: conversation threads addressed by `continuation_id`, the CLI-client registry, the model catalog that `listmodels` renders as prose, the rotating logs. | `utils/conversation_memory`, `clink/registry` |
| **`structuredContent` / `outputSchema`** | Every tool already returns a Pydantic-modelled envelope serialised to a text blob; the pinned SDK will populate `structuredContent` automatically for a handler returning a dict, validating against a declared `outputSchema`. PAL declares none. | `ToolOutput` |
| **Sampling** | PAL requires the operator's own API keys for every model-backed tool; sampling would let it borrow the host's model. | the provider stack |
| **Roots** | PAL solves the same problem by demanding absolute paths and validating them itself. | `utils/file_utils` |
| **`logging` capability** | PAL logs richly to stderr and files, and its own comments note stderr is unreliable under stdio. | the logging setup |

**Schema defects on the live wire, not in a markdown file:**

- **`model` has no `enum`** although the function building it has already computed the concrete model list — it renders them into the *description* prose instead, with a "+N more via `listmodels`" truncation that exists precisely because prose has no room. With an enum, the SDK's own validation would reject a bad model at the boundary for free.
- **`clink` advertises `images` and then refuses every call that uses it** (`tools/clink.py:216` advertises; `:292-299` raises). The fork correctly turned a silent drop into a loud error and stopped one step short of removing the key.
- **`cli_name` is in the schema's `required` array while the tool defaults it when absent** — and a test asserts the defaulting. A compliant host will reject a call the server would have served.
- **`reasoning_effort`'s shipped description is false.** It tells callers the field is "Ignored by CLIs that bake effort into the model name (e.g. antigravity)". Since #43, `AntigravityAgent._model_args` emits a real `--effort`, and `refuse_unservable` **refuses model+effort together**. The description actively causes the error it should prevent, and it is the one copy no sweep of `docs/` would catch.
- **Schema strictness is inconsistent and load-bearing**, because `@server.call_tool()` defaults to `validate_input=True`: most tools emit `additionalProperties: False` plus a draft-07 `$schema`; `challenge` emits neither, so it silently accepts junk arguments every other tool rejects.
- **An unknown tool name returns success** — `[TextContent(text=f"Unknown tool: {name}")]` with `isError` false (`server.py:876-878`), and a test locks it in. An agent branching on `isError` feeds the string "Unknown tool: x" into its reasoning.
- **Half the prompt feature is dead on the wire.** Prompts are advertised with `arguments=[]` while `handle_get_prompt` reads `arguments.get("model")` and `arguments.get("thinking_mode")`, so every template renders with fallbacks. The documented structured name `chat:gpt5` is not implemented — there is no `:` parsing anywhere in the handler, so it falls through to `Unknown prompt`.

---

## 6. What the tests actually pin

The unit suite is healthy in size — 1085 collected, 1081 pass, 4 skip, ~36–40 s — and its clink refusal tests are genuinely good: they assert **from the spawn side**, using a spy that fails if any process is created, rather than inferring "refused" from an exception, and they cover six argv spellings of the model flag. The opencode parser tests are the one place pinned against **verbatim recorded real-CLI output**, including a multi-step fixture that catches a 99% under-report the single-step fixture cannot.

Against that:

- **Outside two integration tests, every clink agent test fakes `asyncio.create_subprocess_exec` and `shutil.which`.** No unit test observes a real process, real argv handling, real PATH resolution, or real stream draining. *(Corrected by the refutation pass: end-to-end clink coverage **does** exist — `tests/test_clink_integration.py` drives the real `CLinkTool().execute()`. The accurate statement is that clink has no test in the `simulator_tests/` harness, which is excluded from CI entirely.)*
- **The antigravity `--model`-before-`--print` fix — the fork's canonical example of a CLI silently ignoring a correctly-built command — is asserted only against the built Python list**, never against `agy`'s behaviour. The same is true of the `--effort` mutual-exclusivity rule, which was measured by hand once and is re-measured by nothing.
- **Roughly 40 assertions pin tool prose** — `get_description()` substrings and schema description text — across `test_challenge.py`, `test_debug.py`, `test_refactor.py`, `test_planner.py`, `test_consensus*.py` and others. Rewording a description breaks the suite; changing what the tool does does not. This is the exact failure `CLAUDE.md` warns about.
- **Both quality-gate test files assert on the *source text* of `code_quality_checks.sh` and never execute it** — eleven of twelve are string containment checks.
- **The documented gate does not run on this checkout.** `./code_quality_checks.sh` exits 1 immediately because it probes only `.pal_venv` or an activated `$VIRTUAL_ENV`, and the repo carries `.venv`. The T4 hook layer worked around it by wiring raw pytest, which means **the linting half is not enforced at merge either.**
- **`code_quality_checks.ps1` still runs all three formatters in write mode** — the exact defect removed from the `.sh` — aborts on first failure, passes `-x` to pytest, and with `-SkipTests -SkipLinting` prints "All Code Quality Checks Passed!" and exits 0 having run nothing. No test covers it.
- **`.coveragerc` measures a package that does not exist** (`source = gemini_server`), and `pytest-cov` is neither declared nor installed. **Nobody has measured coverage on this repo.**
- **The simulator harness cannot find this repo's virtualenv on Windows** — both `_get_python_path()` implementations probe only POSIX layouts and fall through to bare `python`. *(Refuter-verified by execution.)*

---

## 7. Windows, packaging, and the install path

The fork's primary platform is Windows, and several defects sit exactly there.

- **`shlex.split()` in POSIX mode destroys Windows absolute paths** in a client config's `command` field (`clink/registry.py:189`) — the field the fork's own override mechanism tells users to fill with an absolute path. `C:\Tools\agy.exe` becomes `C:Toolsagy.exe`. The asymmetry is the trap: `additional_args` **are** handled correctly via expanduser/expandvars, so the same path works as an argument and breaks as a command.
- **`return (exit_status or 0), …`** (`clink/agents/antigravity.py:218`) maps an indeterminate exit status to success, contradicting the "fail closed" intent stated 80 lines above it.
- **The ConPTY is spawned at a hardcoded `dimensions=(50, 200)`**, and the parser strips ANSI and normalises line endings but does not undo terminal line-breaking — so the long code blocks this client is mostly used for do not survive intact.
- **The Linux error message is wrong on both counts** — it says antigravity "requires the pywinpty package — add it to PAL's dependencies", but pywinpty *is* declared and *cannot* be installed on Linux. The accurate sentence already exists in `CHANGES-FORK.md`.
- **The prompt goes in argv for antigravity only** — every other client writes it to stdin — putting the full prompt, including embedded file contents, into the OS process table.
- **The two-venv problem is a three-name problem.** Scripts, the entry wrapper and the sample client config hardcode `.pal_venv` with a POSIX `bin/` layout; the checkout has `.venv` with `Scripts/`; `CLAUDE.md` names a third, `venv`. Both venv names are gitignored, so nothing detects the mismatch.
- **`run-server.sh` — the command the README tells you to run — emits MCP client configs pointing at upstream** (`:1872, :1897, :2449`), as does `docs/getting-started.md`. The READMEs were fixed; the script was not. **The failure is silent: PAL starts and works, just without any of the fork.**
- **Docker cannot run clink at all.** The runtime image installs `ca-certificates` and `procps`; none of `codex`, `agy`, `claude`, `cursor` or `opencode` is present, nor node/npm/bun to install them. Image labels still say `version="1.0.0"` against a project at 9.8.2 and point `image.source` at upstream.
- **Logs follow the installed package**, not the project — `Path(__file__).parent / "logs"` — so under the README's own uvx install path they land in a uv cache directory while `docs/logging.md` says they are in your project folder.
- **The test suite writes into the same log files the server uses.** Everything currently in `logs/` is pytest output. A single run can push 20 MB of fixture noise through the rotation and evict the window an incident needed.
- **CLI executable paths are frozen at registry load** for the process lifetime, and one resolution strategy is a version-globbed winget directory — so a CLI upgrade that changes its install directory is invisible until restart.
- **There is no `uv.lock`**, and the README's Option B installs straight from git, so every install re-resolves from open-ended `>=` constraints. Only `mcp` carries an upper bound, and it exists because an unbounded resolve already broke the server once.

---

## 8. Documentation drift, measured as a blast radius

The useful finding here is not that docs are stale — it is **how far one code change propagates**.

A single change (`#43`/`#45`, giving antigravity a real `--effort`) invalidated **at least five** documents, and none was updated: ADR 0002, `CHANGES-FORK.md:151`, `docs/tools/clink.md`, `docs/clink-model-effort-guide.md`, and the Obsidian note `clink-per-call-model-effort.md` — plus, most importantly, **the live tool schema description in `tools/clink.py:117-122`**, which is the copy that reaches every MCP client at runtime.

Two structural findings behind that:

- **The fork's only breaking public-contract change has no ADR.** `model` became required and schema-enforced; ADR 0002 still records it as optional with "omitting them reproduces the previous command exactly". The directory whose stated job is hard-to-reverse decisions does not contain the fork's most consequential one.
- **`CHANGES-FORK.md`'s framing sentence is false.** *(Refuter-verified.)* It says "Everything from upstream is unchanged except for the clink changes described below", and the fork makes several further behavioural changes beyond that list. Related: the "unmaintained since ~mid-2026" claim is **contradicted** rather than merely unsupported by this clone — the newest upstream commit in the object database is 2025-12-15.
- **`docs/index.md` is the untouched upstream list of ten documents** and links to none of the fork's own surface: no `adr/`, no `reports/`, no `agents/`, no ledger, no `tools/` pages. `docs/reports/README.md` likewise omits the 2026-08-04 Phase 0 report from its index — the one carrying the host inventory and per-client capability table.

**Also worth recording as a method observation:** staleness here is **not** one-directional. `AGENTS.md` and `CLAUDE.md` correctly state the quality gate reports rather than rewrites; the ledger still asserts the opposite. Reconciling docs *against* the ledger would move a correct statement to an incorrect one. Each has to be checked against code independently.

---

## 9. Directions — ranked, each grounded in a seam that already exists

**Tier 1 — cheap, unblocked, and each removes a live failure.**

1. **Set `readOnlyHint` to `false`** (`tools/clink.py:157`) and add the test that asserts it. One line. It moves the decision back to the host's approval flow instead of silently bypassing it. Known since 2026-07-16.
2. **Build the child environment from an allowlist** instead of `os.environ.copy()` (`clink/agents/base.py:533-536`). The seam is a single function and every client already declares an `env` dict nobody fills.
3. **Drain with a deadline and own the process tree** on timeout (`base.py:284-292`) — the current code cannot report a timeout at all. *(#20 names this as one of three items not gated on anything.)*
4. **Stop using a blocking PTY read** (`antigravity.py:194-207`) — set `PYWINPTY_BLOCK=0` or read on a deadline. No teardown fix reaches an unreachable branch.
5. **Fix the four contract mismatches on the live wire**: drop `images` from the schema, add the `model` enum, reconcile `cli_name`'s required flag, and correct the `reasoning_effort` description.
6. **Point `run-server.sh` and `docs/getting-started.md` at the fork.** The one defect that silently erases the whole fork for anyone following the documented setup.

**Tier 2 — small changes with disproportionate reach.**

7. **Fix the `=== CONVERSATION HISTORY ===` substring mismatch.** One string. It stops every chat continuation from storing a duplicate turn containing the entire prior history.
8. **Report what was dropped.** History eviction, the ignored `add_turn` return, and the discarded summary body all lose information silently. Returning `(dropped_turns, dropped_files)` and surfacing it in metadata is the same "absence must be reported, never guessed" discipline the fork already applied to accounting.
9. **Move `provider.generate_content` off the event loop** (`asyncio.to_thread`), removing a stop-the-world of up to 600 s from a process that also serves clink.
10. **Point tests at a temporary log directory** and default `LOG_LEVEL` to INFO, restoring `logs/` as an incident-response tool and removing a variable-latency term from every measurement.

**Tier 3 — the design moves, in dependency order.**

11. **Stream instead of buffer.** Replace `communicate()` with bounded concurrent draining, and emit **progress notifications** from the events the parsers already receive. This is the single change that unlocks the most: real timeouts, bounded memory, live status, and the evidence base for supervision. *(#15, #20.)*
12. **Adopt elicitation for the approval flow** instead of designing a bespoke control endpoint. *(#16.)*
13. **Declare `outputSchema` and return dicts** so hosts receive `structuredContent` for free.
14. **Expose threads, the client registry and the model catalog as resources.**
15. **Decide the `mcp` 2.x question** (`#18`) — the only measured fact about 2.x in this repo is an import-time crash on `Server.list_tools`; nothing else has been established.

**Tier 4 — the reliability floor this all sits on.** No coverage has ever been measured; the simulator harness cannot run on the fork's primary platform; the documented quality gate does not execute on a correct checkout; and its PowerShell twin still rewrites the tree. Until those four are fixed, every claim about regression safety in this repository is unfalsifiable.

---

## 10. What was refuted, and why it is recorded rather than deleted

A research record that shows only surviving claims is a failure-selected sample. **11 of the 27 claims that reached a refuter did not survive intact.** The instructive ones:

- *"clink has zero end-to-end tests"* — **false.** `tests/test_clink_integration.py` drives the real `execute()`. The true statement is narrower: no clink test is registered in the `simulator_tests/` harness, and that harness is excluded from CI.
- *"An actively-written thread never expires"* — **false.** At the turn ceiling `add_turn` returns before the `setex`, so the TTL stops sliding.
- *"clink's 20,000-char cap is the only response cap"* — **false.** `MAX_DRAINED_OUTPUT_CHARS = 10_000` is a second, independent cap on the timeout path.
- *"The pricing layer is entirely unreachable"* — **partly false.** The rate-card computation is dormant because no config declares one, but a real per-call cost still reaches the caller for the opencode client, via its parser.
- *"`_recover_from_error`'s contract is inverted"* — **overstated.** The framework behaviour is byte-identical to upstream; only the docstring's first line is stale relative to how the fork's own subclasses now use the hook.
- *"The xAI output limits are a fork defect"* — **misattributed.** The equal `max_output_tokens`/`context_window` values are inherited verbatim from upstream and the same shape appears in `conf/openrouter_models.json` for non-xAI models.

The pattern is worth stating: **every one of these was a negative or a universal claim** — "zero", "never", "the only", "entirely". The positives largely survived. A future scan should spend its refutation budget on exactly those words.

---

## 10b. Second pass — the surfaces the readers left, scanned directly

The twelve-reader pass covered roughly a third of the 30,238 lines of production Python, deeply on `clink/`, `utils/conversation_memory.py`, the MCP boundary in `server.py`, logging and packaging. This section is a follow-up pass over the largest gaps it named. Every finding here was produced by reading or by executing the repo's own code in this checkout.

### The Windows path policy has gaps, verified by execution

`utils/security_config.py` blocks two Windows directories — `C:\Windows` and `C:\Program Files` — plus filesystem roots and the bare `C:\Users` container. Driving `is_dangerous_path` and `resolve_and_validate_path` directly:

```
DANGEROUS  refused   C:\Windows\System32\config\SAM
DANGEROUS  refused   D:\                       (drive root)
DANGEROUS  refused   C:\Users                  (container itself)
allowed    ACCEPTED  C:\Program Files (x86)\app\x.txt
allowed    ACCEPTED  C:\ProgramData\secrets.txt
allowed    ACCEPTED  D:\Github\pal-mcp-server\.git\config
allowed    ACCEPTED  C:\Users\xenod\.aws\credentials
```

Three of those matter. **`C:\Program Files (x86)` is a different string** from the one on the list, so the 32-bit half of the same directory is unprotected. **`C:\ProgramData`** is where machine-wide application state, certificates and credentials live and appears nowhere. And **`.git/config` is readable by direct path** — `EXCLUDED_DIRS` does contain `.git`, but that set governs *recursive search*, not a path the caller names, and a `.git/config` can carry credentials inside a remote URL.

This is the same defect shape as the docstring finding in §2: the block list reads as a policy and is a short literal set. On a Windows-primary fork it covers two directories on one drive.

### Retryability is decided by substring matching on the error text

`providers/base.py:217-240` classifies an error as retryable by lowercasing its message and testing for `timeout`, `connection`, `temporary`, `unavailable`, `retry`, `reset`, `refused`, `broken pipe`, `tls`, `handshake`, `network`, `500`, `502`, `503`, `504` — after excluding anything containing `429` or `rate limit`.

**`"500" in error_str` matches `"5000"`.** A provider error saying a request exceeded a 5000-token limit is classified as a server error and retried, with sleeps, three more times — each retry deterministically failing the same way. The rate-limit exclusion is right and is the only structured part of the decision; everything else is a substring vote on prose the vendor controls.

The base class says as much: *"Subclasses with structured provider errors should override this hook."* None of the shipped subclasses does.

### The event-loop stall is up to thirty minutes, not ten

§3 recorded that `provider.generate_content(...)` is a synchronous HTTP call on an async path, bounded by the httpx read timeout. The timeout is not one value (`providers/openai_compatible.py:145-200`):

| Endpoint kind | connect | **read** |
|---|---|---|
| standard | 30 s | **600 s** |
| custom remote | 45 s | **900 s** |
| **local** | 60 s | **1800 s** |

So one `chat` against a local model can freeze the whole server — every other tool, every clink child's output drain, and the MCP protocol reader — for **half an hour**, and the retry loop adds `time.sleep` on top: DIAL ships `RETRY_DELAYS = [1, 3, 5, 8]`, seventeen seconds of blocking sleep on the only thread there is.

This changes the priority of moving that call off the loop from "worth doing" to "the largest availability risk in the server", and it is entirely independent of clink.

### Coverage after this pass

Deeply read: `clink/` (2,385), `utils/conversation_memory.py` (1,108), `utils/security_config.py` (163), the MCP boundary and logging in `server.py` (1,526 total, ~800 read), the provider retry and timeout paths, `tools/clink.py`, and the base-class surface of `tools/shared/`, `tools/simple/`, `tools/workflow/`.

**Still unread, with line counts, so the next pass can be scoped rather than guessed:** `systemprompts/` (2,355 — the prompts every tool actually sends, entirely unread); the per-tool bodies under `tools/` outside the shared machinery (roughly 10,000 of 15,709); `providers/` outside the retry/timeout paths (roughly 3,800 of 4,560, including the whole of `gemini.py`, `dial.py`, `azure_openai.py`, `openrouter.py`); `utils/file_utils.py` above line 421, `utils/model_restrictions.py`, `utils/client_info.py`, `utils/file_types.py` (roughly 1,300); and the test bodies.

**The highest-value of those is `systemprompts/`**, because it is the only unread area whose content reaches a model on every single call and is therefore load-bearing for output quality rather than for correctness of the plumbing.

---

## 10c. Round 3 — the ~21,000 lines the first two rounds never opened

**Method:** eight readers, one per unread surface, no refuter stage — verification was done afterwards in the main loop against specific claims, which costs almost nothing and is where the sharpest numbers below came from. All eight returned; **225 claims, 1.51 M tokens.** Surfaces: `systemprompts/` (2,355), `tools/shared/` (1,606+), `tools/simple/base.py` (1,011), `tools/workflow/` (2,225), `providers/` core and per-vendor (4,560), and the nineteen tool bodies (~10,000).

The first two rounds found defects in the *plumbing*. This round found them in the **contract** — what a tool advertises versus what it does, and what a prompt instructs versus what any code consumes. That class is invisible to every test in the repository, because nothing fails.

### The prompt layer: a quarter of it is never sent to anything

`PLANNER_PROMPT`, `TRACER_PROMPT` and `DOCGEN_PROMPT` — **30,104 bytes, roughly 24% of the prompt corpus** — reach no model. Each is returned only by `get_system_prompt()`, which on a `WorkflowTool` is read only inside `_call_expert_analysis`, which is gated on `requires_expert_analysis()`. Verified directly: all three tools return `False`. `DOCGEN_PROMPT` is the second-largest prompt in the repo and the only place the Objective-C/Swift `///` rule and the Big-O requirement are written down. Editing any of the three changes nothing; those tools' behaviour lives entirely in the `next_steps` strings inside the tool bodies.

Two more prompt-layer findings of the same kind:

- **Six statuses the prompts declare MANDATORY have no consumer.** `full_codereview_required`, `focused_review_required`, `test_sample_needed`, `more_tests_required`, `no_bug_found`, `more_refactor_required` — the workflow layer promotes exactly three statuses and none of them is these. So a model correctly signalling *"this diff is too large to review honestly"* or *"there is no bug here"* has that signal buried inside the analysis blob, and a codereview of an oversized diff returns a confident partial review presented as complete. `SPECIAL_STATUS_MODELS`, the registry built to validate these, is imported by `base_tool.py` and never referenced.
- **`GENERATE_CODE_PROMPT` and its own consumer contradict each other.** The prompt spends ~1,763 tokens per capable-model chat call demanding complete, immediately-applicable code; `tools/chat.py` then tells the coding agent the blocks are partial excerpts that will corrupt the codebase if applied. And its `<NEWFILE:>`/`<UPDATED_EXISTING_FILE:>` tag structure is parsed by nothing — the whole block is written verbatim to one file named `pal_generated.code`.

### The literal-backslash-n corruption, measured precisely

Several tools build their expert-analysis prompt and their caller-facing guidance with `"\\n"` — a literal backslash followed by `n` — instead of a newline. Evaluating every string literal in each file with `ast`:

```
tools/analyze.py       literal-backslash-n:  54   real newlines:  48   <-- corrupted
tools/codereview.py    literal-backslash-n:  74   real newlines:  52   <-- corrupted
tools/precommit.py     literal-backslash-n:  74   real newlines:  58   <-- corrupted
tools/refactor.py      literal-backslash-n:  61   real newlines:  52   <-- corrupted
tools/testgen.py       literal-backslash-n:  19   real newlines:  65
tools/tracer.py        literal-backslash-n:  26   real newlines: 226
tools/debug.py         literal-backslash-n:   0   real newlines: 123
tools/secaudit.py      literal-backslash-n:   0   real newlines: 132
```

**In four tools the corrupted form outnumbers the correct one**, and `debug` and `secaudit` are clean — which is what proves it is a mistake rather than a convention. The consequence runs both ways: the expert model receives the investigation context as one unbroken line with `\n` litter where the section delimiters should be, and the **caller** receives the numbered required-actions list the same way. These tools exist to steer a calling agent through forced pauses; the steering instructions are the product.

**Any measured quality difference between `debug`/`secaudit` and `analyze`/`codereview` may be this bug rather than the prompts** — which makes it a precondition for evaluating anything else in the tool layer.

### The conversation doubles every turn

`server.py:1088` adds the user turn, and `tools/simple/base.py:353` adds a **second** user turn whose content is the entire embedded conversation history — because the guard at `:335` looks for a header string that is never emitted (§4). Measured on a 15-character user message: the prompt sent to the model goes **3,069 → 6,480 → 13,307 → 26,965 → 54,280 characters** across five exchanges. The thread grows three turns per exchange, so the 50-turn cap is consumed in about sixteen.

**Any measurement of token cost, budget behaviour or thread capacity taken before this is fixed is measuring the bug.** And the advertised capacity compounds it: `remaining_turns` counts turns while the note calls them "exchanges", so a fresh thread advertises 49 exchanges against a real capacity nearer sixteen.

### The tool singletons leak, and the leak reaches a third-party model

`server.py:260` states *"Tools are instantiated once and reused across requests (stateless design)"*. They are not stateless. **Eleven instance fields survive across two unrelated runs**; only three are cleared per call. `work_history`, `consolidated_findings`, `analysis_config`, `review_config`, `git_config`, `security_config`, `trace_config`, `branches` and `initial_request` all persist.

`consolidated_findings` is the sole input to `prepare_expert_analysis_context`, so **a fresh run's expert prompt embeds the previous unrelated run's findings, file paths and full file contents, and sends them to the external provider.** Worse, the state-restore path only matches assistant turns from the same tool, so a contaminated singleton gets written into the new thread and then restored later as legitimate-looking history — an in-memory leak becoming durable.

`ConsensusTool` is the only tool that resets both fields, and it does so in its own override rather than in the shared mixin. The fix is a named lifecycle reset in one place, not a defensive read in twelve.

### Contract defects — what a tool advertises versus what it does

This is the round's largest class. A representative set, each verified:

- **`confidence='certain'` is the documented way to decline a paid expert call.** `debug`, `thinkdeep`, `secaudit` and `testgen` advertise a seven-value enum but type the field as plain `str`, so `'Certain'`, `'CERTAIN'` or any typo is accepted and silently fails the exact-equality check — and the caller is billed for the call they declined. `refactor` is the only one that enforces its enum with a `Literal`.
- **`analyze` advertises the same enum and ignores it entirely**, pinning confidence to `"medium"` and never skipping expert analysis; its own attempt to exclude the field from the schema is defeated by the schema builder's ordering.
- **`use_assistant_model` is inert on four tools** — `planner`, `consensus`, `docgen`, `tracer` advertise it while hard-coding `requires_expert_analysis() == False`. On `thinkdeep` it is worse: advertised, and the override never reads it, so disabling expert analysis on the most expensive tool does nothing.
- **`exclude=True` does not remove a field from a schema.** `codereview`, `debug` and `precommit` each carry the comment *"Override inherited fields to exclude them from schema"* over `temperature`/`thinking_mode` declared with pydantic `exclude=True` — which affects serialisation only. Three authors independently wrote the same wrong idiom, which points at the schema builder never consulting the pydantic model.
- **`precommit` never runs git.** No subprocess, no git library, anywhere. `compare_to`, `include_staged` and `include_unstaged` change no behaviour; the required-actions text instructs the caller to run the git commands.
- **`testgen` says it "generates framework-specific tests"** and writes nothing — it has no framework parameter and returns guidance plus an expert opinion, like the other seven.
- **`secaudit`'s `audit_focus`, `threat_level` and `compliance_requirements` do not change the investigation** — `get_required_actions` branches only on step number and emits a fixed six-step plan.
- **`refactor`'s `style_guide_examples` paths are validated and never opened**; `refactor_type` does not narrow the work; `codereview`'s `severity_filter`, `standards` and `focus_on` filter and enforce nothing; `analyze`'s `output_format` changes nothing.
- **`planner` and `tracer` mark `model` as required in their JSON Schema while `requires_model()` is `False`**, so every call must invent a value the server discards — and a host doing strict validation rejects calls that omit it. `docgen` marks six server-defaulted fields as required.
- **A total consensus panel failure reports success.** When every model fails, `consensus` still emits `consensus_workflow_complete`, `consensus_complete: true`, and a **hardcoded `consensus_confidence: "high"`**, listing the failed models under `models_consulted`. An orchestrator cannot detect a dead panel from the envelope. Its schema also declares `minItems: 2` while the validator only checks truthiness, so a one-model "consensus" is accepted end to end.

### The provider layer

- **An allowlist reroutes rather than denies.** Verified by execution: with `OPENAI_ALLOWED_MODELS=gpt-5.2`, the name `o3` is silently served by **DIAL** as `o3-2025-04-16`. An operator setting an allowlist for cost or compliance gets a different vendor, a different data-processing agreement and a different bill instead of a refusal.
- **Usage reads zero on the most expensive models.** `_extract_usage` reads `prompt_tokens`/`completion_tokens`, which do not exist on the Responses API usage object, so every `/responses` call — `gpt-5.2-pro`, `gpt-5.1-codex`, `gpt-5-codex`, `o3-pro` — records `input_tokens=0` and `output_tokens=0` while `total_tokens` is real. The account is internally inconsistent, and input and output bill at several-fold different rates.
- **Gemini drops the thinking budget from its usage**: `thoughts_token_count` and `cached_content_token_count` are never read and the total is recomputed as input+output, so PAL reports 1,200 tokens where the vendor reported 6,200. The correct figure (`total_token_count`) is already on the object.
- **Gemini's canonical rate-limit error is never retried.** The predicate enters its 429 branch on `resource_exhausted` and then lists `resource_exhausted` among the **non**-retryable indicators, so `429 RESOURCE_EXHAUSTED` — the SDK's own spelling — fails on the first attempt.
- **`thinking_mode` reaches only Gemini.** Every tool call site passes it; the OpenAI-compatible base forwards a six-item kwargs whitelist that does not include it. `max_output_tokens` is declared on every model in every manifest and **sent to no vendor at all** — no caller passes it.
- **`/responses` demotes every system message to a user message**, a workaround for an o3-pro-era quirk, so four flagship models receive a structurally different prompt from every other model. The `instructions` field the Responses API provides for exactly this is never set.
- **The response reservation ignores `max_output_tokens`**: `gemini-2.5-pro` reserves 209,715 tokens of its window for a response that can be at most 65,536 — 144,179 tokens of usable input budget discarded.
- **Auto-mode is alphabetical for four providers of seven.** `get_preferred_model()` is implemented only by Gemini, OpenAI and X.AI; elsewhere the fallback is `sorted(allowed_models)[0]`, so `ToolModelCategory` is inert and the FAST_RESPONSE category can get the most expensive model in the catalogue. If nothing is available at all, the ultimate fallback is the hardcoded literal `gemini-2.5-flash`, reported to the operator as the suggested model on installs that never intended to use Google.
- **`capability_rank` saturates at 100** and the frontier models exceed it, so three OpenAI and two Gemini models tie and fall through to an alphabetical tie-break — listing `gemini-2.5-pro` ahead of `gemini-3-pro-preview`. `intelligence_score` is documented as the primary ordering signal and has no effect at the top of the range.
- **A restriction set mutates itself at runtime**: `is_allowed()` writes resolved canonical names back into the set it is checking, so a policy declared by alias grows during a session.
- **`AZURE` and `CUSTOM` are absent from `ModelRestrictionService.ENV_VARS` entirely**, so `is_allowed()` returns `True` unconditionally for them; and a restricted Custom model is still **advertised** by `list_models` and then fails on use — a menu listing unusable models.

### Silent failure is the house style, and that is the finding

Counted across this round, the same shape recurs: **images dropped with a warning when the model cannot see them, so the user gets a confident answer about an image that was never sent** · temperature corrected twice with no user-visible signal · a `relevant_files` value passed as a string silently replaced with an empty list, so the tool analyses nothing and reports success · oversize direct `code` dropped from `read_files` with no entry in `files_skipped` · `_create_continuation_offer` swallowing every exception with no log, making a storage failure indistinguishable from the legitimate turn-limit `None` · a memory-write failure converting an already-billed model response into a tool error.

**None of these can fail a test, because none of them fails.** That is the argument for the structured-output work in §5: an envelope that can carry *"this was dropped"* turns a whole class of silent degradation into something a caller can act on.

### Three things that are simply dead

`tools/models.py` is **86% dead** — 26 of 28 public names have zero production references. `chat`'s web-search instruction is built and then discarded by a string split before the model sees it, so chat has no web-search prompting at all despite three methods existing to configure it. `DEFAULT_THINKING_MODE_THINKDEEP` has no effect on the workflow expert path, which uses a hardcoded `"high"` — and startup logging actively confirms the wrong value to the operator.

### What this round changes about the priorities in §9

Three items join Tier 1, all cheap and all currently corrupting output rather than breaking a path:

1. **Fix the literal-backslash-n in four tools** — `debug` and `secaudit` show the correct form in the same codebase.
2. **Fix the duplicate user turn** — one string comparison, and it is a precondition for every token or cost measurement.
3. **Reset workflow singleton state on a new run** — eleven fields, one named lifecycle hook, and it currently leaks one user's file contents into another's provider call.

And one joins Tier 2: **make `confidence` a `Literal` in the four tools that type it as `str`**, because that field is the only mechanism a caller has to decline a paid expert call.

---

## 11. What nobody read

Named honestly by the readers themselves, because an unstated boundary reads as coverage:

- **No real delegation was executed.** Every claim about what a child CLI does with a stdin prompt, a `--model` flag or its own deadline is code-and-help-text reasoning, not observed behaviour. Only `opencode run --help` and `cursor-agent --help` were run.
- **~5,000 lines of per-tool prompt-building** across `analyze`, `codereview`, `precommit`, `refactor`, `secaudit`, `testgen`, `planner`, `docgen`, `tracer`, `consensus` — read only via targeted greps.
- **`providers/` internals** — the HTTP client construction, the `/responses`-vs-`/chat-completions` branch, retry wiring, and `_extract_usage` for the OpenAI-compatible, Gemini, DIAL and Azure providers.
- **The test bodies.** No suite was executed as part of this scan; the 1085/1081 figures come from a reader's own run, not from a verification pass.
- **Rotated logs** `mcp_server.log.1` through `.5` (~21 MB each) were not scanned for secret-shaped patterns; only the current 12 MB file was.
- **The Docker threat model** beyond confirming no ports are published.
- **`mcp` 2.x itself** — no 2.x package is installed and its migration path was not fetched.
- **Three of the four clink role prompts** (`default_planner.txt`, `default_codereviewer.txt`, `codex_codereviewer.txt`).

---

## 12. Evidence register

**VERIFIED** — read in code at `2aa6e49`, or produced by a command whose output was read: every `file:line` citation above; the environment-inheritance chain (read **and** executed); the storage backend's unconditional in-memory singleton; the TTL and sweeper intervals (executed); the `readOnlyHint` literal; the hardcoded Gemini identity string; the `shlex` path corruption (demonstrated with the repo's own interpreter); the `.env` import-time load; the log contents (12 MB current file); the unit-suite counts; the venv layout; the absence of `uv.lock`, of a `rate_card` in any config, and of an `upstream` remote in any config scope.

**REFUTER-VERIFIED** — survived an independent agent instructed to break them: `workflow-state-leaks-across-requests` (confirmed at runtime), `clink-stores-the-truncated-answer` (confirmed at runtime), `summarisation-path-discards-the-body`, `threads-in-process-memory-only`, `MEM-03`, `MEM-04`, `MEM-09`, `ENV-2`, `two-response-envelopes`, `simulator-windows-broken` (confirmed by execution), `simulator-dead-file`, `unmaintained-date-claim-unverified`.

**CORRECTED BY A REFUTER** — the corrected form is what appears above: the response-cap universal, the simulator/end-to-end claim, `MEM-02`, the pricing-layer headline, the `_recover_from_error` contract, the xAI manifest attribution, and the `CHANGES-FORK.md` framing sentence.

**UNVERIFIED / UNKNOWN** — the behaviour of any foreign CLI under a real delegation; whether the `docker-compose` stdio mismatch actually produces a restart loop (reasoned, not run); what `mcp` 2.x replaces the decorators with; coverage of any subsystem, since none has ever been measured; and **every claim in this report that did not reach a refuter — 41 of the 68 planned refutations did not run, and the observed refutation rate among those that did was 41%.**
