# Deep scan of the fork — architecture, the safety boundary, and where it can go (2026-08-13)

## 0. What this is, how it was produced, and what it does not cover

**A code scan.** Issue and PR numbers appear only as annotations so that whoever picks a finding up can find its tracker context. No finding here was derived from reading the tracker, and none should be actioned on the strength of an issue number alone.

**Three rounds, at `2aa6e49` (branch `feat/85-opencode-client`):**

| Round | Shape | Output |
|---|---|---|
| 1–2 | twelve readers over twelve subsystems; each load-bearing claim handed to a separate agent instructed to **break** it | 380 claims; 27 reached a refuter, **11 refuted or materially corrected**, 16 survived |
| 2b | direct scan by the author over the largest gaps the readers named | the Windows path probe, the retry predicate, the real timeout ladder |
| 3 | eight readers over the ~21,000 lines rounds 1–2 never opened; **no refuter stage** — verification done afterwards against named claims | 225 claims, 1.51 M tokens, all eight returned |

**605 claims in total.** Roughly **26,000 of the 30,238 lines** of production Python have been read; §16 names what remains, with line counts.

**Two honest limits on the method.**

The refutation pass in rounds 1–2 was cut short by quota exhaustion: **41 of 68 planned refutations never ran.** The 27 that did produced an **11-refuted rate of 41%** — the rate at which a careful, evidence-citing reader's load-bearing claim did not survive one round of adversarial checking. Apply it to anything here not marked refuter-verified.

Round 3 had no refuter stage at all by design, and the substitute worked better than expected: verifying named claims directly in the main loop cost almost nothing and produced the sharpest numbers in this report (the `ast` count in §7, the path probe in §3, the allowlist reroute in §9). **Targeted verification by the synthesiser beat adversarial fan-out on cost and on precision** — worth carrying into the next round.

**The shape of what was found changed between rounds.** Rounds 1–2 found defects in the **plumbing**. Round 3 found them in the **contract** — what a tool advertises versus what it does, and what a prompt instructs versus what any code consumes. Nothing in that second class can fail a test, because nothing fails.

---

## 1. The clink call path, and every point where something is dropped

A `clink` call runs: MCP request → `reconstruct_thread_context` (if continuing) → `CLinkTool.execute` → agent `_build_command` → `asyncio.create_subprocess_exec` → parse → metadata assembly → `_prune_metadata` → `_apply_output_limit` → turn recorded → response.

Six places lose information; two of them tell the caller:

| Where | What is lost | Caller told? |
|---|---|---|
| `_prune_metadata` (`tools/clink.py:690`) | `events`, `raw`, `raw_events` — the worker's whole event stream | yes, as `events_removed_for_normal: true` |
| `_apply_output_limit` (`tools/clink.py:617-651`) | on a `<SUMMARY>` hit, **everything outside the tags** | partly — sizes reported, discarded body not |
| turn recording (`tools/clink.py:343-347, 367`) | the thread stores the **post-limit** text | no |
| history eviction (`utils/conversation_memory.py:964-972`) | oldest turns when the budget is exhausted | only as prose inside the prompt |
| file inclusion (`tools/shared/base_tool.py:812-824`) | a file skipped by history is filtered out of the tool's own embedding too | no |
| the turn ceiling (`MAX_CONVERSATION_TURNS`, default 50) | `add_turn` returns `False` and **every caller ignores it** | no |

**The summarisation path is a selection, not a compression.** Over `MAX_RESPONSE_CHARS` (20,000, hardcoded at `tools/clink.py:46`) with a `<SUMMARY>` block present, what returns is the text inside the first tag pair and nothing else. *(Refuter-verified.)* A second, independent cap exists — `MAX_DRAINED_OUTPUT_CHARS = 10_000` (`clink/agents/base.py:71`) on the timeout path. Every response cap in the tool surface is on the clink path; **no other tool bounds what it returns.**

**The truncated copy is what the thread keeps.** Driven against the real `execute`, a 25,000-char answer with a `<SUMMARY>` tag left the thread holding only the summary — so verification, audit or escalation on a continuation reads a lossy copy with no marker saying so. *(Refuter-verified.)*

**clink never reads file contents.** `_format_file_references` (`tools/clink.py:759-773`) emits `path (last modified …, N bytes)`; the child is told to open the files itself. A delegation to a sandboxed or remote CLI answers about files it never opened, and no token budget applies because nothing is read.

---

## 2. The safety boundary — the largest property of this fork, and the least documented

**A `clink` tool call starts an unsandboxed foreign coding agent, carrying the server's entire environment, in whatever directory the server occupies, and the MCP host is told the tool is read-only.**

- **`readOnlyHint: True`** — `tools/clink.py:156-157`. A host that auto-approves on the annotation auto-approves arbitrary code execution. No test asserts any annotation value. Known since 2026-07-16.
- **Full environment inheritance** — `clink/agents/base.py:533-536`. Every shipped client declares `"env": {}` and no `INTERNAL_DEFAULTS` entry supplies one, so **the child's environment is byte-identical to PAL's**, including every provider key. No allowlist.
- **`.env` is inside that inheritance** — `utils/env.py:57` calls `reload_env()` at module scope, imported on the clink path. *(Refuter-verified by reading the chain and by executing it.)*
- **No working directory is set** — no shipped client sets `working_dir`, so `cwd=None`.
- **Every shipped config disarms the target CLI's own safety mechanism.** Privilege is inherited from vendor bypass flags, not decided. *(Tracker: #14 exists to replace this.)*
- **None of the four clink role prompts forbids writing.** The words modify, write, edit, commit and delete do not appear, so the prompt layer adds no constraint behind the annotation either.
- **The error envelope relays the child verbatim** — a failed child's stdout and stderr return to the caller (20,000 chars each), including any environment dump it chose to make.

**Argv injection on Windows.** A caller-supplied `model` string can break out of its argument and execute commands, because the resolved executables are `.cmd` shims and Python's `list2cmdline` escaping is not honoured by `cmd.exe`. The guard that could refuse a bad model, `refuse_unservable`, is **inert for every shipped client** because no config declares a `model_catalog`.

**The path sandbox in the docstring does not exist**, and the block list has measured gaps. `utils/file_utils.py:16` claims *"All file access is restricted to PROJECT_ROOT and its subdirectories"*; `resolve_and_validate_path` (`:282-324`) enforces only absoluteness, symlink resolution, a short dangerous-root list, and the home **root**. Driving `is_dangerous_path` and `resolve_and_validate_path` directly:

```
DANGEROUS  refused   C:\Windows\System32\config\SAM
DANGEROUS  refused   D:\                       (drive root)
DANGEROUS  refused   C:\Users                  (container itself)
allowed    ACCEPTED  C:\Program Files (x86)\app\x.txt
allowed    ACCEPTED  C:\ProgramData\secrets.txt
allowed    ACCEPTED  D:\Github\pal-mcp-server\.git\config
allowed    ACCEPTED  C:\Users\xenod\.aws\credentials
```

`C:\Program Files (x86)` is a different string from the one on the list. `C:\ProgramData` appears nowhere. **`.git/config` is readable by direct path** — `EXCLUDED_DIRS` contains `.git`, but that set governs *recursive search*, not a path the caller names, and a `.git/config` can carry credentials in a remote URL.

**Two further reach findings from round 3:** `expand_paths` skips dotfiles only while walking a directory — a directly named hidden file is added unconditionally, and because `.env` is a member of `CODE_EXTENSIONS`, any `*.env` file is picked up by an ordinary source scan. And **`ChatTool` writes `pal_generated.code` into any existing directory the caller names and unlinks a pre-existing file there**, resolving the path but never passing it through `is_dangerous_path` or any other check.

**And one class of leak that is not about paths at all:** because workflow tool state survives across runs (§4), **a fresh run's expert prompt embeds the previous unrelated run's findings, file paths and full file contents, and sends them to the external provider.**

**What is *not* a problem, checked and cleared:** API keys are read via `get_env` and logged by presence only; a 12 MB production log contains no secret-shaped material; the OpenAI SDK logs `'security': {'bearer_auth': True}`, a flag rather than the credential. Conversation turns live in process memory with a TTL — no disk or Redis backend to leak from.

**But full prompts do land on disk.** The file handler is attached to the **root** logger at DEBUG, so `openai._base_client`, `httpx` and friends are captured: system prompt, user prompt and embedded file contents are written verbatim to `logs/mcp_server.log`. The clink runner writes the full spawned argv on every call — 274 occurrences in the current log — which for the claude client includes the entire `--append-system-prompt`. On the `/responses` path the whole request payload is logged at INFO, with each message truncated to 100 characters. And `_validate_base_url` checks only scheme, hostname presence and port range, so `https://user:pass@host/v1` passes and the full URL is logged twice before any request.

**`SECURITY.md` describes a different system.** It characterises PAL as *"middleware between AI clients … and various AI model providers"* and never mentions clink, subprocess spawning, foreign CLI agents, bypassed approval flags, or environment inheritance — it names Codex CLI and Cursor as *clients*, the opposite of their role. It routes vulnerability reports to the **unmaintained upstream's** advisory page.

---

## 3. Concurrency and liveness

**The timeout does not fire, and cannot report.** `clink/agents/base.py:284-292` wraps `communicate()` in `asyncio.wait_for`; on timeout it calls `process.kill()` and awaits `communicate()` again **with no timeout**. A grandchild inheriting the stdout pipe makes that second call never return, so `CLIAgentError("timed out after N seconds")` is never raised — the caller is never told and the coroutine is pinned until the orphan exits. Any supervisor built on top must drain with its own deadline and close the parent's pipe. *(Tracker: #20.)*

**On antigravity the deadline is unreachable by construction.** `clink/agents/antigravity.py:194-207` checks the deadline at the top of the loop and then calls `proc.read()`, a **blocking** `socket.recv` — pywinpty defaults to blocking mode, which also makes two branches of that loop dead code. `asyncio.to_thread` cannot cancel it. In practice `agy`'s own `--print-timeout` (5 minutes) usually saves it, but that is the child's discipline, not PAL's. *(Tracker: #65.)*

**A stale doc claim to stop planning against:** `_run_in_pty` *does* call `proc.close(force=True)`, reaching pywinpty's `terminate(force=True)`. The 2026-07-16 report's *"the agy subprocess is never killed"* is **wrong for the direct child**; it remains true for descendants, and is unreachable anyway when the read blocks.

**The largest availability risk in the server is not in clink.** `provider.generate_content(...)` is a plain synchronous HTTP call from an `async def execute` (`tools/simple/base.py:444`, again at `:501`, `tools/workflow/workflow_mixin.py:1493`, `tools/consensus.py:618`) — no `await`, no `asyncio.to_thread`. The httpx read timeout is not one value (`providers/openai_compatible.py:145-200`):

| Endpoint kind | connect | **read** |
|---|---|---|
| standard | 30 s | **600 s** |
| custom remote | 45 s | **900 s** |
| **local** | 60 s | **1800 s** |

So one `chat` against a local model freezes the whole loop — every other tool, every clink child's output drain, the MCP protocol reader — for **half an hour**, plus blocking `time.sleep` from the retry ladder (DIAL ships `RETRY_DELAYS = [1, 3, 5, 8]`). **A load test that fires only clink calls will miss this**, and the same process serves both. `tools/version.py` adds a smaller instance of the same shape: a synchronous `urlopen` to GitHub from inside an async `execute`, blocking the loop for up to 10 seconds, under `readOnlyHint: True`.

**Retryability is a substring vote on the vendor's error prose.** `providers/base.py:217-240` lowercases the message and tests for `timeout`, `connection`, `temporary`, `unavailable`, `retry`, `reset`, `refused`, `broken pipe`, `tls`, `handshake`, `network`, `500`, `502`, `503`, `504`, after excluding `429`/`rate limit`. **`"500" in error_str` matches `"5000"`** — an error about a 5000-token limit is classified as a server error and retried three more times, each attempt failing identically. The base class says *"Subclasses with structured provider errors should override this hook"*; none of the shipped subclasses does.

**Supporting facts.** There is **no concurrency control of any kind** — no semaphore, queue, admission cap or per-workspace lease. `DEFAULT_STREAM_LIMIT = 10MB` (`clink/constants.py:9`) is a flow-control watermark, not a cap. Logging defaults to DEBUG and writes synchronously from the event-loop thread, including inline 20 MB rollovers; the log tree is 118 MB. On a continuation, every file referenced anywhere in the thread is re-read and line-numbered synchronously before the subprocess spawns — 11 ms at a 64k-token budget, 51 ms at 320k.

**Ten concurrent clink calls, concretely:** ten tasks on one loop, ten subprocesses with no cap, all in PAL's cwd with PAL's full environment; ~110–510 ms of aggregate blocking file I/O if they are continuations; full transcripts accumulating unbounded; and any one that times out never reports.

**One shared structure is unprotected.** `add_turn` is a lock-free read-modify-write (`utils/conversation_memory.py:354 … 384`); the storage lock covers each get and each set but not the pair, so two concurrent calls on one `continuation_id` silently lose a turn — which also under-reports the accounting that sums surviving turns.

---

## 4. State that outlives its request

Two independent leaks, both consequences of one design statement that is false.

**`server.py:260` says *"Tools are instantiated once and reused across requests (stateless design)"*. They are not stateless.** Round 3 enumerated **eleven instance fields that survive across two unrelated runs**; only `_embedded_file_content`, `_file_reference_note` and `_actually_processed_files` are cleared per call. Surviving: `work_history`, `consolidated_findings`, `analysis_config`, `review_config`, `git_config`, `security_config`, `trace_config`, `branches`, `initial_request`, and per-request scratch on `SimpleTool` (`_current_arguments`, `_current_model_name`, `_model_context`).

Three consequences, in ascending severity:

1. Every counter, summary and file list the host reads back is wrong after the first run.
2. `consolidated_findings` is the sole input to `prepare_expert_analysis_context`, so **the previous run's file contents are sent to the external provider inside this run's call** (§2).
3. **The leak becomes durable.** State restore only fires when the thread contains an assistant turn from the same tool carrying `work_history`; otherwise the run proceeds on stale singleton state and then **persists it into the new thread**, where it is later restored as legitimate-looking history.

`ConsensusTool` is the only tool that resets both fields, in its own `execute_workflow` override rather than in the shared mixin. The fix is one named lifecycle reset, not a defensive read in twelve places.

**The conversation doubles every turn.** `server.py:1088` adds the user turn and `tools/simple/base.py:353` adds a **second** user turn whose content is the entire embedded conversation history — because the guard at `:335` looks for `"=== CONVERSATION HISTORY ==="` while `utils/conversation_memory.py:798` emits `"=== CONVERSATION HISTORY (CONTINUATION) ==="`. The substring never matches. Measured on a 15-character user message, the prompt sent to the model grows:

```
3,069 → 6,480 → 13,307 → 26,965 → 54,280 characters
```

Three turns per exchange, so the 50-turn cap is consumed in about sixteen. **Any measurement of token cost, budget behaviour or thread capacity taken before this is fixed is measuring the bug.** The advertised capacity compounds it: `remaining_turns` counts turns while the note calls them "exchanges", so a fresh thread advertises 49 exchanges against a real capacity nearer sixteen — and the cap's `False` return is ignored, so the failure is a silently dropped turn rather than an error.

**Everything else in the memory layer is the same shape — the caller is never told what was lost:**

- **Thread lifetime** is a sliding TTL that slides only on a successful write. *(Refuted as first stated: an actively-written thread does **not** live forever — at `MAX_CONVERSATION_TURNS`, `add_turn` returns `False` **before** the `setex`, so the TTL stops sliding.)*
- **A restart destroys every thread** — `get_storage_backend()` unconditionally returns an in-memory singleton; no Redis, sqlite, pickle or file backend exists in production code. The failure message hardcodes "more than 3 hours ago" regardless of configuration. Because the transport is stdio, the server is a subprocess of the client, so "restart" understates the loss window. *(Refuter-verified.)*
- **Three different token estimators** are in one pipeline: `len//3` in `utils/model_context.py:174` gates history inclusion, `len//4` in `utils/token_utils.py:33` produces the number reported and subtracted from the file budget, and the MCP-boundary file gate uses `bytes ÷ ratio` (2.5–4.5). A `.json` file is scored 60% higher by the gate than by the consumer.
- **`model_metadata` is one untyped slot with three incompatible schemas** — clink writes `{"accounting": …}`, SimpleTool `{"usage": …}`, workflow tools `{"work_history": […]}`. *(Refuter-verified, including a search for a fourth writer.)*
- **`work_history` is persisted quadratically** — every turn stores the whole growing list, though restore reads only the latest.
- **Continuation resolves against the originating tool** (`server.py:1098-1099`), so continuing a clink thread with `chat` silently resolves a new model instead of inheriting the thread's; and the clink history budget is sized against a fallback provider model, never the CLI model that will receive the prompt.
- **Documented turn limits contradict the constant** in three places (docstring "20 turns max", config comment "default to 20", `docs/ai-collaboration.md` "up to 10 exchanges"); the constant is 50.

---

## 5. The prompt layer — nobody had read it, and a quarter of it is never sent

`systemprompts/` is 2,355 lines whose content reaches a model on every call, and round 3 was the first time any of it was read.

**`PLANNER_PROMPT`, `TRACER_PROMPT` and `DOCGEN_PROMPT` reach no model.** Each is returned only by `get_system_prompt()`, read on a `WorkflowTool` only inside `_call_expert_analysis`, gated on `requires_expert_analysis()`. Reproduced by instantiating all three and calling both methods:

```
planner  requires_expert_analysis() = False   system prompt bytes =  6,394
tracer   requires_expert_analysis() = False   system prompt bytes =  6,788
docgen   requires_expert_analysis() = False   system prompt bytes = 16,697
                                                          total    29,879
```

**29,879 bytes of assembled system prompt, about a quarter of the corpus, delivered to nothing.** `DOCGEN_PROMPT` is the second-largest prompt in the repo and the only place the Objective-C/Swift `///` rule and the Big-O requirement are written down. **Editing any of the three changes nothing** — those tools' behaviour lives entirely in the `next_steps` strings inside the tool bodies.

**Six statuses the prompts declare MANDATORY have no consumer.** `full_codereview_required`, `focused_review_required`, `test_sample_needed`, `more_tests_required`, `no_bug_found`, `more_refactor_required` — the workflow layer promotes exactly three statuses and none is these. A model correctly signalling *"this diff is too large to review honestly"* or *"there is no bug here"* has that signal buried inside the analysis blob, so **a codereview of an oversized diff returns a confident partial review presented as complete.** `SPECIAL_STATUS_MODELS`, the registry built to validate these, is imported by `base_tool.py` and never referenced again. Symmetrically, the two statuses the layer *does* handle — `investigation_paused`, `refactoring_paused` — are requested by no prompt.

**`GENERATE_CODE_PROMPT` and its own consumer contradict each other.** The prompt spends ~1,763 tokens per capable-model chat call demanding complete, immediately-applicable code; `tools/chat.py` then tells the coding agent the blocks are partial excerpts that will corrupt the codebase if applied. Its `<NEWFILE:>`/`<UPDATED_EXISTING_FILE:>` tag structure is parsed by nothing — the whole block is written verbatim to one file named `pal_generated.code`.

**Smaller, same class:** twelve of fourteen prompts tell the model code arrives with markers written literally as `LINE│ code` while the formatter emits a right-aligned number and a bar; `CONSENSUS_PROMPT` caps every consulted model at 850 tokens *"to ensure transport compatibility"*, a number appearing nowhere in the code, while demanding a verdict plus seven evaluation dimensions plus 3–5 takeaways; `systemprompts/clink/codex_codereviewer.txt` begins with the literal token `/review `, concatenated as the first characters of the prompt piped to `codex exec`; and when `LOCALE` is set, `Always respond in {locale}.` is prepended ahead of prompt bodies that mandate strict JSON with English keys.

**Nothing tests any of this.** Five clink role prompt files were deleted in `c42e9e9` and eight test fixtures still name two of them — the tests pass because they hand `agent.run()` a literal string and never read a file. **No test in the repo loads a real `systemprompts/clink/*.txt` through the production path**, which is why the "you are the Gemini CLI" injection and the `/review` prefix could sit in place unnoticed.

---

## 6. The contract layer — what a tool advertises versus what it does

The largest class round 3 found, and the one no test can catch. Each verified.

**The paid-call opt-out does not work.** `confidence='certain'` is the documented way to decline an expert model call. `debug`, `thinkdeep`, `secaudit` and `testgen` advertise a seven-value enum but type the field as plain `str`, so `'Certain'`, `'CERTAIN'` or any typo is accepted and silently fails the exact-equality check — **and the caller is billed for the call they declined.** `refactor` is the only one that enforces its enum with a `Literal`. `analyze` advertises the same enum and ignores it entirely, pinning confidence to `"medium"`.

**`use_assistant_model` is inert on five tools.** `planner`, `consensus`, `docgen` and `tracer` advertise it while hard-coding `requires_expert_analysis() == False`. On `thinkdeep` it is worse — advertised, and the override never reads it, so disabling expert analysis on the most expensive tool does nothing. The central gate that would have enforced this once, `BaseWorkflowMixin.should_call_expert_analysis`, is **shadowed by an `@abstractmethod` of the same name on `WorkflowTool`**, forcing twelve hand-written re-implementations of one policy — which is how one of them lost it.

**`exclude=True` does not remove a field from a schema.** `codereview`, `debug` and `precommit` each carry the comment *"Override inherited fields to exclude them from schema"* over `temperature`/`thinking_mode` declared with pydantic `exclude=True`, which affects serialisation only. Three authors independently wrote the same wrong idiom, which points at the real cause: the schema is generated from static dicts and never consults the pydantic model.

**Parameters that change nothing.** `precommit` never runs git — no subprocess, no git library anywhere — so `compare_to`, `include_staged` and `include_unstaged` are inert while the required-actions text instructs the caller to run the commands. `testgen` says it *"generates framework-specific tests"* and writes nothing. `secaudit`'s `audit_focus`, `threat_level` and `compliance_requirements` do not change the investigation. `refactor`'s `style_guide_examples` paths are validated and never opened, and `refactor_type` does not narrow the work. `codereview`'s `severity_filter`, `standards` and `focus_on` filter and enforce nothing. `analyze`'s `output_format` changes nothing. `thinkdeep`'s `problem_context` and `focus_areas` never reach the expert model, and `thinkdeep` never sends file content to it at all.

**Schemas that disagree with their own server.** `planner` and `tracer` mark `model` as required while `requires_model()` is `False`, so every call must invent a value the server discards — and a strict host rejects calls that omit it. `docgen` marks six server-defaulted fields as required. `tracer` marks two step-1-only fields as globally required. `cli_name` is in clink's `required` array while the tool defaults it. `clink` advertises `images` and then refuses every call that uses it. `consensus` declares `minItems: 2` while its validator checks only truthiness, so a one-model "consensus" is accepted end to end.

**A total panel failure reports success.** When every model in a `consensus` panel fails, the tool still emits `consensus_workflow_complete`, `consensus_complete: true`, and a **hardcoded `consensus_confidence: "high"`**, listing the failed models under `models_consulted`. An orchestrator cannot detect a dead panel from the envelope. Reproduced: the literal is hardcoded at **two** sites, `tools/consensus.py:399` and `:512`, so a fix must change both.

**And there is no response contract to program against.** Seven sites hand-build a wire response; `apilookup` and `challenge` emit statuses absent from `ToolOutput`'s `Literal` with different field names; `tools/models.py` is **86% dead** (26 of 28 public names have zero production references), so anyone extending the envelope reads a contract that nothing consumes.

**Dead hooks that look live.** `planner`'s and `tracer`'s five completion hooks are never called; `docgen`'s 13-line MANDATORY FINAL VERIFICATION message is unreachable; `thinkdeep`'s tailored expert instruction is dead because the method is named `…instructions` against a base hook named `…instruction`; `BaseWorkflowMixin.execute` is shadowed in the MRO. Editing any of them produces no behaviour change.

---

## 7. The literal-backslash-n corruption, measured

Several tools build their expert-analysis prompt **and** their caller-facing guidance with `"\\n"` — a literal backslash followed by `n` — instead of a newline. Evaluating every string literal in each file with `ast`:

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

**In four tools the corrupted form outnumbers the correct one, and `debug` and `secaudit` are clean** — which is what proves it a mistake rather than a convention. The expert model receives the investigation context as one unbroken line with `\n` litter where the section delimiters should be, and the **caller** receives the numbered required-actions list the same way. These tools exist to steer a calling agent through forced pauses; the steering instructions are the product.

**Any measured quality difference between `debug`/`secaudit` and `analyze`/`codereview` may be this bug rather than the prompts** — which makes fixing it a precondition for evaluating anything else in the tool layer.

---

## 8. The provider layer

- **An allowlist reroutes rather than denies.** Verified by execution: with `OPENAI_API_KEY` and `DIAL_API_KEY` set and `OPENAI_ALLOWED_MODELS=gpt-5.2`, the name `o3` is silently served by **DIAL** as `o3-2025-04-16`. An operator setting an allowlist for cost or compliance gets a different vendor, a different data-processing agreement and a different bill instead of a refusal. Enforcement has to move above the per-provider loop.
- **Usage reads zero on the most expensive models.** `_extract_usage` reads `prompt_tokens`/`completion_tokens`, absent from the Responses API usage object, so every `/responses` call — `gpt-5.2-pro`, `gpt-5.1-codex`, `gpt-5-codex`, `o3-pro` — records `input_tokens=0` and `output_tokens=0` while `total_tokens` is real. Input and output bill at several-fold different rates.
- **Gemini drops the thinking budget from its account** — `thoughts_token_count` and `cached_content_token_count` are never read and the total is recomputed as input+output, so PAL reports 1,200 tokens where the vendor reported 6,200. The correct figure is already on the object.
- **Gemini's canonical rate-limit error is never retried.** The predicate enters its 429 branch on `resource_exhausted` and then lists `resource_exhausted` among the **non**-retryable indicators, so `429 RESOURCE_EXHAUSTED` — the SDK's own spelling — fails on the first attempt.
- **`thinking_mode` reaches only Gemini**; the OpenAI-compatible base forwards a six-item kwargs whitelist that excludes it. **`max_output_tokens` reaches no vendor at all** — declared on every model in every manifest, passed by no caller.
- **`/responses` demotes every system message to a user message**, a workaround for an o3-pro-era quirk, so four flagship models receive a structurally different prompt from every other model. The `instructions` field the API provides for exactly this is never set. The same branch names `o3-pro` in its INFO log and in three raised error strings regardless of the model in use.
- **The response reservation ignores `max_output_tokens`** — `gemini-2.5-pro` reserves 209,715 tokens of its window for a response that can be at most 65,536, discarding 144,179 tokens of usable input budget.
- **Auto-mode is alphabetical for four providers of seven.** `get_preferred_model()` is implemented only by Gemini, OpenAI and X.AI; elsewhere the fallback is `sorted(allowed_models)[0]`, so `ToolModelCategory` is inert and FAST_RESPONSE can draw the most expensive model in the catalogue. With nothing available at all, the ultimate fallback is the literal `gemini-2.5-flash`, reported to the operator as the suggested model on installs that never intended to use Google.
- **`capability_rank` saturates at 100** and the frontier models exceed it, so several tie and fall through to an alphabetical tie-break — listing `gemini-2.5-pro` ahead of `gemini-3-pro-preview`. `intelligence_score` is documented as the primary ordering signal and has no effect at the top of the range.
- **A restriction set mutates itself at runtime** — `is_allowed()` writes resolved canonical names back into the set it is checking, so a policy declared by alias grows during a session. **`AZURE` and `CUSTOM` are absent from `ModelRestrictionService.ENV_VARS` entirely**, so `is_allowed()` returns `True` unconditionally for them; and a restricted Custom model is still **advertised** by `list_models` and then fails on use.
- **OpenRouter accepts any slash-containing name absent from the manifest** and fabricates capabilities at 32,768/32,768. Thirty-eight names or aliases appear in more than one manifest, several resolving to materially different canonical models depending only on which keys are present.
- **Client-construction failure is downgraded and cached.** If building the custom httpx client raises, the fallback is `OpenAI(api_key, base_url)` only — discarding the timeout config, `DEFAULT_HEADERS` and organization — logged once and then cached for the process lifetime. For DIAL that drops the only authentication header. And `_configure_timeouts` reads `CUSTOM_*_TIMEOUT` for **every** provider, so values set for a local Ollama endpoint reconfigure OpenAI, Azure, X.AI, DIAL and OpenRouter.
- **Azure's endpoint is never validated** — `super().__init__` runs before `AZURE_OPENAI_ENDPOINT` is resolved, so the SSRF check never sees the endpoint actually used, and the client gets standard rather than custom-endpoint timeouts.

---

## 9. Silent failure is the house style, and that is the finding

The same shape recurs across every subsystem: **the operation degrades, the caller is told nothing, and the answer looks normal.**

Images dropped with a warning when the model cannot see them, so the user gets a confident answer about an image never sent · temperature corrected twice with no user-visible signal · a `relevant_files` value passed as a string silently replaced with an empty list, so the tool analyses nothing and reports success · oversize direct `code` dropped from `read_files` with no entry in `files_skipped` · history eviction announced only inside the prompt · `_create_continuation_offer` swallowing every exception with no log, making a storage failure indistinguishable from the legitimate turn-limit `None` · a memory-write failure converting an already-billed model response into a tool error · `add_turn`'s `False` return ignored everywhere · an unknown tool name answered with `isError: false` and the text `Unknown tool: x`.

**None of these can fail a test, because none of them fails.** That is the argument for the structured-output work in §10: an envelope that can carry *"this was dropped"* converts a whole class of silent degradation into something a caller can act on. It is also why the round-3 findings are systematically absent from the tracker while the round-1 plumbing findings are on it — the tracker records what broke.

---

## 10. The MCP surface, and the options nobody has costed

PAL advertises exactly **two** capabilities, `tools` and `prompts`, via a hand-written `ServerCapabilities(...)` literal that bypasses the SDK's own `get_capabilities()`. `listChanged` is unset on both. `resources`, `logging`, `completions` and `experimental` are never populated.

**The pinned SDK already exposes every unused capability as a one-call API on the server session** — `create_message` (sampling), `elicit`/`elicit_form`/`elicit_url`, `list_roots`, `send_log_message`, `send_progress_notification`, and the three `send_*_list_changed` notifications. None is reachable from PAL's code today, which makes the following design options rather than speculation:

| Unused | What it would buy | The seam it attaches to |
|---|---|---|
| **Progress notifications** | Long work is **completely silent**: a child may run 1800 s and PAL reports nothing until it exits; a 672 s call has been measured. The data already exists and is discarded — codex `--json`, opencode `--format json` and claude JSONL are line-oriented event streams consumed only after `communicate()` returns at exit. | the parser layer, plus streaming reads |
| **Elicitation** | The epic that most needs an ask-the-caller channel is designing a bespoke one (#16 specifies "a new local control endpoint" whose "shape [is] deliberately undefined"). Elicitation is that channel, already in the protocol and the SDK. | the approval flow |
| **`structuredContent` / `outputSchema`** | Every tool already returns a Pydantic-modelled envelope serialised to a text blob; the SDK populates `structuredContent` automatically for a handler returning a dict, validating against a declared `outputSchema`. PAL declares none — and §9 is the reason it should. | `ToolOutput` |
| **Resources** | Conversation threads by `continuation_id`, the CLI-client registry, the model catalog `listmodels` renders as prose, the rotating logs. | `conversation_memory`, `clink/registry` |
| **Sampling** | PAL requires the operator's own API keys for every model-backed tool; sampling would borrow the host's model. | the provider stack |
| **Roots** / **`logging`** | PAL solves both problems itself — absolute paths it validates, and files under `logs/` its own comments call unreliable under stdio. | `file_utils`, the logging setup |

**Schema defects on the live wire:** `model` has no `enum` although the function building it has already computed the model list — it renders them into the *description* prose with a "+N more via `listmodels`" truncation, when an enum would let the SDK's own validation reject a bad name for free. Schema strictness is inconsistent and load-bearing, because `@server.call_tool()` defaults to `validate_input=True`: `challenge` emits neither `additionalProperties: False` nor a `$schema`, so it silently accepts junk arguments every other tool rejects. **Half the prompt feature is dead on the wire** — prompts are advertised with `arguments=[]` while `handle_get_prompt` reads `arguments.get("model")` and `arguments.get("thinking_mode")`, and the documented structured name `chat:gpt5` has no `:` parsing anywhere in the handler.

---

## 11. What the tests actually pin

The unit suite is healthy in size — 1085 collected, 1081 pass, 4 skip, ~36–40 s — and its clink refusal tests are genuinely good: they assert **from the spawn side**, using a spy that fails if any process is created, and cover six argv spellings of the model flag. The opencode parser tests are the one place pinned against **verbatim recorded real-CLI output**, with a multi-step fixture that catches a 99% under-report the single-step fixture cannot.

Against that:

- **Outside two integration tests, every clink agent test fakes `asyncio.create_subprocess_exec` and `shutil.which`.** *(Corrected by a refuter: end-to-end clink coverage **does** exist in `tests/test_clink_integration.py`. The accurate statement is that clink has no test in the `simulator_tests/` harness, which is excluded from CI.)*
- **The antigravity `--model`-before-`--print` fix — the fork's canonical example of a CLI silently ignoring a correctly-built command — is asserted only against the built Python list**, never against `agy`. Same for the `--effort` mutual-exclusivity rule.
- **Roughly 40 assertions pin tool prose** rather than behaviour. Rewording a description breaks the suite; changing what the tool does does not.
- **Nothing drives `execute_workflow`**, and no test anywhere runs two workflows on one tool instance — which is why §4's leak survived.
- **Both quality-gate test files assert on the source text of `code_quality_checks.sh` and never execute it.**
- **The documented gate does not run on this checkout** — it probes `.pal_venv` or an activated `$VIRTUAL_ENV` and the repo carries `.venv`. The T4 hook layer worked around it by wiring raw pytest, so **the linting half is not enforced at merge either.**
- **`code_quality_checks.ps1` still runs all three formatters in write mode**, aborts on first failure, passes `-x` to pytest, and with `-SkipTests -SkipLinting` prints "All Code Quality Checks Passed!" and exits 0 having run nothing. No test covers it.
- **`.coveragerc` measures a package that does not exist** (`source = gemini_server`) and `pytest-cov` is neither declared nor installed. **Nobody has measured coverage on this repo.**
- **The simulator harness cannot find this repo's virtualenv on Windows** — both `_get_python_path()` implementations probe only POSIX layouts. *(Refuter-verified by execution.)*

### The coverage the report could not otherwise supply

Nobody has ever measured coverage here (`.coveragerc` points at a package that does not exist and `pytest-cov` is not installed), so this is a **proxy**: for each of 28 anchors a finding in this report rests on, does **any** of the 172 files under `tests/` or `simulator_tests/` so much as mention the symbol? Executed against the repo:

```
anchors mentioned by any test: 18 / 28
```

**Read it as an upper bound, not a measure** — a mention may be a mock, a name in a docstring, or an assertion on wording. The true figure is at most 18/28 and probably well below it.

**The pattern is the finding.** Every anchor with *no* mention at all clusters in one place:

```
clink.py::get_annotations                 readOnlyHint True on a mutating tool   -- NONE --
clink.py::_agent_capabilities_guidance    every CLI told it is Gemini            -- NONE --
clink.py::_apply_output_limit             summary discards the body              -- NONE --
clink/agents/base.py::_build_environment  full os.environ to the child           -- NONE --
consensus.py::consensus_confidence        dead panel reports high confidence     -- NONE --
chat.py::_persist_generated_code_block    writes into a caller-named directory   -- NONE --
simple/base.py::prepare_chat_style_prompt websearch instruction discarded        -- NONE --
simple/base.py::set_request_files         catches the wrong exception            -- NONE --
thinkdeep.py::get_expert_analysis_instr…  misnamed override, dead                -- NONE --
openai_compatible.py::_configure_timeouts CUSTOM_* applies to every provider     -- NONE --
```

Meanwhile every upstream-inherited area a finding touches — path traversal, conversation memory, model restrictions, auto-mode selection, retry classification, token usage — **is** mentioned by tests, several of them by four or more files.

**So the coverage gap maps almost exactly onto the fork's own additions.** The four most consequential clink anchors in this report — the annotation, the environment, the identity string and the output limiter — are named by no test at all. That is not an accident of sampling: it is what a feature built under time pressure on top of a well-tested upstream looks like, and it is why §14's Tier 4 is a tier rather than a footnote.

---

## 12. Windows, packaging, and the install path

- **`shlex.split()` in POSIX mode destroys Windows absolute paths** in a client config's `command` field (`clink/registry.py:189`) — the field the fork's own override mechanism tells users to fill with an absolute path. `C:\Tools\agy.exe` becomes `C:Toolsagy.exe`. The asymmetry is the trap: `additional_args` **are** handled correctly, so the same path works as an argument and breaks as a command.
- **`return (exit_status or 0), …`** (`antigravity.py:218`) maps an indeterminate exit status to success, contradicting the "fail closed" intent stated 80 lines above.
- **The ConPTY is hardcoded to `dimensions=(50, 200)`** and the parser does not undo terminal line-breaking, so the long code blocks this client is mostly used for do not survive intact.
- **The Linux error message is wrong on both counts** — pywinpty *is* declared and *cannot* be installed on Linux. The accurate sentence already exists in `CHANGES-FORK.md`.
- **The prompt goes in argv for antigravity only**, putting it — including embedded file contents — into the OS process table.
- **The two-venv problem is a three-name problem**: scripts and the sample config hardcode `.pal_venv` with a POSIX layout; the checkout has `.venv` with `Scripts/`; `CLAUDE.md` names a third, `venv`. Both venv names are gitignored, so nothing detects the mismatch.
- **`run-server.sh` — the command the README tells you to run — emits MCP client configs pointing at upstream** (`:1872, :1897, :2449`), as does `docs/getting-started.md`. The READMEs were fixed; the script was not. **PAL starts and works, just without any of the fork.**
- **Docker cannot run clink at all** — the runtime image has `ca-certificates` and `procps`; none of the CLIs, nor node/npm/bun to install them. Image labels say `version="1.0.0"` against a project at 9.8.2 and point `image.source` at upstream.
- **Logs follow the installed package**, not the project, so under the README's uvx path they land in a uv cache directory while `docs/logging.md` says otherwise. **The test suite writes into the same log files the server uses** — everything currently in `logs/` is pytest output.
- **CLI executable paths are frozen at registry load**, and one resolution strategy is a version-globbed winget directory, so a CLI upgrade is invisible until restart.
- **There is no `uv.lock`**, and Option B installs straight from git, so every install re-resolves from open-ended `>=` constraints. Only `mcp` carries an upper bound, and it exists because an unbounded resolve already broke the server once.

---

## 13. Documentation drift, measured as a blast radius

The useful finding is not that docs are stale — it is **how far one code change propagates**.

A single change (`#43`/`#45`, giving antigravity a real `--effort`) invalidated **at least five** documents, none updated: ADR 0002, `CHANGES-FORK.md:151`, `docs/tools/clink.md`, `docs/clink-model-effort-guide.md`, and the Obsidian note — plus **the live tool schema description in `tools/clink.py:117-122`**, the copy that reaches every MCP client at runtime and which no sweep of `docs/` would catch.

- **The fork's only breaking public-contract change has no ADR.** `model` became required and schema-enforced; ADR 0002 still records it as optional.
- **`CHANGES-FORK.md`'s framing sentence is false** *(refuter-verified)* — it claims everything from upstream is unchanged except the listed clink changes. And the "unmaintained since ~mid-2026" claim is **contradicted** rather than merely unsupported: the newest upstream commit in the object database is 2025-12-15.
- **`docs/index.md` is the untouched upstream list of ten documents** and links to none of the fork's own surface. `docs/reports/README.md` omitted the 2026-08-04 Phase 0 report until this report was filed.
- **Staleness is not one-directional.** `AGENTS.md` and `CLAUDE.md` correctly state the quality gate reports rather than rewrites; the ledger asserts the opposite. Reconciling docs *against* the ledger would move a correct statement to an incorrect one — each must be checked against code independently.

---

## 14. Directions — one ranked list

**Tier 1 — cheap, unblocked, each removes a live failure.**

1. **Set `readOnlyHint` to `false`** (`tools/clink.py:157`) and add the test that asserts it. One line; it returns the decision to the host's approval flow.
2. **Build the child environment from an allowlist** instead of `os.environ.copy()`. One function; every client already declares an `env` dict nobody fills.
3. **Fix the literal-backslash-n in the four corrupted tools** (§7). `debug` and `secaudit` show the correct form in the same codebase, and this is a precondition for evaluating anything else in the tool layer.
4. **Fix the duplicate user turn** (§4) — one string comparison, and a precondition for every token or cost measurement.
5. **Reset workflow singleton state on a new run** (§4) — eleven fields, one named lifecycle hook; it currently sends one run's file contents to a third-party provider inside another run's call.
6. **Drain with a deadline and own the process tree** on timeout (§3) — the current code cannot report a timeout at all.
7. **Stop using a blocking PTY read** (§3) — no teardown fix reaches an unreachable branch.
8. **Fix the contract mismatches on the live wire**: drop `images` from clink's schema, add the `model` enum, reconcile `cli_name`, `planner`/`tracer`'s required `model`, and correct the `reasoning_effort` description.
9. **Point `run-server.sh` and `docs/getting-started.md` at the fork** — the one defect that silently erases the whole fork for anyone following the documented setup.

**Tier 2 — small changes with disproportionate reach.**

10. **Make `confidence` a `Literal` in the four tools that type it as `str`** — it is the only mechanism a caller has to decline a paid expert call.
11. **Remove the `@abstractmethod` shadow on `should_call_expert_analysis`** so one central opt-out gate applies instead of twelve copies.
12. **Report what was dropped** (§9). Returning `(dropped_turns, dropped_files)` and surfacing it in metadata is the same discipline the fork already applied to accounting.
13. **Move `provider.generate_content` off the event loop** — up to a 30-minute stop-the-world in a process that also serves clink.
14. **Fix the usage extractors**: `input_tokens`/`output_tokens` on the Responses path, `total_token_count` for Gemini. Anything that bills or budgets per direction is reading zeros on the most expensive models today.
15. **Point tests at a temporary log directory and default `LOG_LEVEL` to INFO** — restores `logs/` as an incident-response tool and removes a variable-latency term from every measurement.

**Tier 3 — the design moves, in dependency order.**

16. **Stream instead of buffer.** Replace `communicate()` with bounded concurrent draining and emit **progress notifications** from the events the parsers already receive. The single change that unlocks the most: real timeouts, bounded memory, live status, and the evidence base for supervision. *(#15, #20.)*
17. **Adopt elicitation for the approval flow** instead of a bespoke control endpoint. *(#16.)*
18. **Declare `outputSchema` and return dicts** so hosts receive `structuredContent` — the mechanism §9 needs.
19. **Expose threads, the client registry and the model catalog as resources.**
20. **Decide the `mcp` 2.x question** (`#18`) — the only measured fact about 2.x here is an import-time crash on `Server.list_tools`.

**Tier 4 — the reliability floor all of this sits on.** No coverage has ever been measured; the simulator harness cannot run on the fork's primary platform; the documented quality gate does not execute on a correct checkout; its PowerShell twin still rewrites the tree; and nothing drives `execute_workflow`. Until those are fixed, every claim about regression safety in this repository is unfalsifiable.

---

## 15. What was refuted, and why it is recorded rather than deleted

A research record showing only surviving claims is a failure-selected sample. **11 of the 27 claims that reached a refuter did not survive intact.** The instructive ones:

- *"clink has zero end-to-end tests"* — **false.** `tests/test_clink_integration.py` drives the real `execute()`. The true statement is narrower: no clink test is registered in `simulator_tests/`, and that harness is excluded from CI.
- *"An actively-written thread never expires"* — **false.** At the turn ceiling `add_turn` returns before the `setex`, so the TTL stops sliding.
- *"clink's 20,000-char cap is the only response cap"* — **false.** `MAX_DRAINED_OUTPUT_CHARS = 10_000` is a second cap on the timeout path.
- *"The pricing layer is entirely unreachable"* — **partly false.** The rate-card computation is dormant, but a real per-call cost reaches the caller for the opencode client via its parser.
- *"`_recover_from_error`'s contract is inverted"* — **overstated.** The framework behaviour is byte-identical to upstream; only the docstring's first line is stale.
- *"The xAI output limits are a fork defect"* — **misattributed.** Inherited verbatim from upstream, and the same shape appears in `conf/openrouter_models.json` for non-xAI models.

**The pattern is worth stating: every one of these was a negative or a universal** — "zero", "never", "the only", "entirely". The positives largely survived. A future round should spend its verification budget on exactly those words.

---

## 16. What nobody read

Named honestly, because an unstated boundary reads as coverage. Roughly **4,000 of 30,238 production lines remain unread**, plus the test bodies.

- **No real delegation was executed.** Every claim about what a child CLI does with a stdin prompt, a `--model` flag or its own deadline is code-and-help-text reasoning, not observed behaviour. Only `opencode run --help` and `cursor-agent --help` were run.
- **`providers/` outside the paths named in §8** — parts of `gemini.py`, `dial.py`, `azure_openai.py`, `openrouter.py`; roughly 1,500 lines.
- **`utils/client_info.py` (293) and `file_types.py` (271)** beyond their consumer counts, and `file_utils.py` between lines 421 and 523.
- **The test bodies** — ~30,600 lines of `tests/` and ~15,900 of `simulator_tests/`. No suite was executed as part of this scan; the 1085/1081 figures come from a reader's own run.
- **Rotated logs** `mcp_server.log.1`–`.5` (~21 MB each) were not scanned for secret-shaped patterns; only the current 12 MB file was.
- **The Docker threat model** beyond confirming no ports are published.
- **`mcp` 2.x itself** — no 2.x package is installed and its migration path was not fetched.

**The highest-value remaining target is no longer the test bodies** — §11's proxy answers the shape of that question (18 of 28 anchors mentioned by any test, and every clink anchor mentioned by none). **It is executing a real delegation.** By this repository's own standard — *"verify clink changes against a real CLI; a `_build_command` unit test doesn't prove the CLI honored the flags"* — every clink finding here is unverified at the level that matters, and that standard exists because a CLI silently ignoring a correctly-built command is exactly the bug that produced ADR 0002.

---

## 17. Evidence register

**AUTHOR-REPRODUCED** — the five highest-consequence round-3 claims were re-run directly rather than trusted from a subagent, because a subagent's report is a hypothesis until checked. All five held, and two produced corrections now folded in above: (1) the conversation-history guard — the emitted header does **not** contain the looked-for substring, so the guard never matches; (2) `execute_workflow` contains no `self.work_history = []` reset and `server.TOOLS["debug"]` is a module-level singleton; (3) `debug` accepts `confidence="CERTAIN"` with annotation `Optional[str]` while `refactor` raises `ValidationError` — the enum is enforced in exactly one of them; (4) `consensus_confidence: "high"` is hardcoded at **two** sites, not one; (5) the three unreachable system prompts total **29,879** assembled bytes. The coverage proxy in §11 (18 of 28 anchors mentioned by any test) was likewise executed by the author.

**VERIFIED** — read in code at `2aa6e49`, or produced by a command whose output was read: every `file:line` citation; the environment-inheritance chain (read **and** executed); the storage backend's in-memory singleton; the TTL and sweeper intervals (executed); the `readOnlyHint` literal; the hardcoded Gemini identity string; the `shlex` path corruption (demonstrated with the repo's own interpreter); the Windows path probe (executed); the `ast` newline census (executed); the allowlist reroute to DIAL (executed); the conversation-doubling character counts (executed); the `.env` import-time load; the log contents; the unit-suite counts; the venv layout; the absence of `uv.lock`, of a `rate_card` in any config, and of an `upstream` remote in any config scope.

**REFUTER-VERIFIED** — survived an independent agent instructed to break them: `workflow-state-leaks-across-requests` (confirmed at runtime), `clink-stores-the-truncated-answer` (confirmed at runtime), `summarisation-path-discards-the-body`, `threads-in-process-memory-only`, `MEM-03`, `MEM-04`, `MEM-09`, `ENV-2`, `two-response-envelopes`, `simulator-windows-broken` (confirmed by execution), `simulator-dead-file`, `unmaintained-date-claim-unverified`.

**CORRECTED BY A REFUTER** — the corrected form is what appears above: the response-cap universal, the simulator/end-to-end claim, the thread-expiry consequence, the pricing-layer headline, the `_recover_from_error` contract, the xAI manifest attribution, and the `CHANGES-FORK.md` framing sentence.

**UNVERIFIED / UNKNOWN** — the behaviour of any foreign CLI under a real delegation; whether the `docker-compose` stdio mismatch produces a restart loop (reasoned, not run); what `mcp` 2.x replaces the decorators with; the vendor facts behind the `gemini-2.0-flash` manifest values (marked `inferred` by its reader); coverage of any subsystem, since none has ever been measured; and **every round-1/2 claim that did not reach a refuter — 41 of 68 planned refutations did not run, and the observed refutation rate among those that did was 41%.** Round-3 claims carry no refuter pass at all; the ones cited above were re-verified directly by the author, and the rest carry their reader's register.
