# CLI enforcement capability — every clink client can block a tool call (2026-08-13)

**This report overturns the Q2 verdict of [`2026-08-04-clink-phase0-spike-host-followup-and-cli-capability.md`](2026-08-04-clink-phase0-spike-host-followup-and-cli-capability.md).** That spike concluded *"Claude Code is the only client that demonstrably has both [a pre-tool hook and a resumable session] today"*, and issue #16 is gated on it: *"Ship only for the clients where #12 proved both."*

**It was measured from `--help` output.** `--help` was the wrong instrument: on `codex` the hook surface is a subcommand-less file convention, on `agy` and `cursor-agent` it is file-based only and appears in no help text at all. Three probes went to the shipped binaries and the vendors' own documentation instead.

*Read-only throughout. No CLI configuration was written and no plugin was imported.*

## The deciding question, answered per client

> **Can a local process block a specific tool call this CLI is about to make, before it happens?**

| Client | Answer | Mechanism | Strength of evidence |
|---|---|---|---|
| `claude` / `claude-9arm` | **yes** | `PreToolUse` hook, `permissionDecision: deny` | already established (`xeno-skills/hooks/t4-gate`) |
| **`codex`** | **yes** | `PreToolUse` hook, hard block, two independent mechanisms | **embedded draft-07 JSON Schema extracted from the shipped binary** |
| **`agy`** (antigravity) | **yes** | `hooks.json` → `PreToolUse` → stdout `{"decision":"deny"}` | vendor docs + binary symbols + third-party reports of it blocking |
| **`cursor-agent`** | **yes** | `hooks.json` → `beforeShellExecution` / `beforeReadFile` / `beforeMCPExecution` / `preToolUse` → `{"permission":"deny"}` | binary + vendor docs |

**Four of five clients, not one.** The premise that `cursor-agent --help` contains no `hook` is true and was misleading: the surface exists and is simply undocumented in help output.

## codex — the vocabulary, extracted from the binary

`codex-cli 0.144.4`. The binary embeds the complete draft-07 schema for every hook's stdin and stdout, keyed by titles such as `pre-tool-use.command.input`. The `HookEventName` enum, whole:

```
pre_tool_use  permission_request  post_tool_use  pre_compact  post_compact
session_start session_end  user_prompt_submit  subagent_start  subagent_stop  stop
```

**Eleven events, three of them before the action** — `PreToolUse` before the tool executes, `PermissionRequest` before the human is prompted, `UserPromptSubmit` before the prompt reaches the model.

`PreToolUse` stdin carries `session_id`, `turn_id`, `cwd`, `hook_event_name`, `model`, `permission_mode` (`default | acceptEdits | plan | dontAsk | bypassPermissions`), `tool_name`, `tool_input`, `tool_use_id`, `transcript_path` — all required — plus optional `agent_id` and `agent_type`, **which are the seam by which a hook can tell which sub-agent is acting.**

## The stronger lever nobody had looked for: remove the tool rather than refuse the call

A separate probe asked whether enforcement could come from the MCP side instead of the hook side, since PAL is registered as an MCP server on all four hosts. On the Claude Code harness the answer is better than a hook:

```
--tools "Read,Grep,Glob"     # or "" for none — omitted tools are REMOVED FROM CONTEXT
--disallowedTools "mcp__*"   # a deny-list, and the vendor says to prefer --tools
--strict-mcp-config          # ignore every MCP config except the one PAL authors
```

The vendor states the distinction explicitly: *"omitting a tool from `tools` removes it from context so Claude never attempts it; listing it in `disallowedTools` blocks the call but leaves the tool visible."* And MCP tools sit **outside** the `tools` layer, so a PAL-provided edit tool survives while the built-in `Edit` does not.

**That is a boundary rather than a policy.** The worker is not denied permission to edit — it has no edit tool, and the only writing instrument it can reach is one PAL supplied and therefore governs. The recipe is constructible today by editing `conf/cli_clients/claude.json`'s `additional_args`; nothing in PAL needs to change first.

### Tested 2026-08-13 — it holds, and it is stronger than expected

The open question was whether `--tools ""` is accepted alongside a live MCP server, or whether the CLI requires at least one built-in. **It is accepted, and the MCP tool survives.**

A throwaway stdio MCP server exposing exactly one tool (`probe_ping`, returns a fixed token, no arguments) was passed via `--mcp-config` with `--strict-mcp-config` so nothing else could load:

```sh
echo "Call the probe_ping tool and output its result verbatim, nothing else." \
  | claude -p --tools "" --strict-mcp-config --mcp-config ./probe-mcp.json \
           --allowedTools "mcp__probe__probe_ping"
# → PROBE_TOKEN_7F3A
```

A second run asked the worker to enumerate its own tools and then read a file that existed in its working directory. Its answer, verbatim:

> `mcp__probe__probe_ping`
> That is the complete list — one tool. I can't read `probe-target.txt`. I have no file-reading, shell, or search tool available.

So the two layers are genuinely separate: **every built-in is gone from the worker's context while the MCP tool remains callable.**

**The consequence changes the recipe, and it enlarges [#89](https://github.com/xenodeve/pal-mcp-server/issues/89)'s deliverable 2.** `--tools ""` removes far more than `Edit` — the same worker lost `Read`, `Grep` and `Bash`, and reported that it could not invoke a skill either, because the harness's `Skill` tool is a built-in like any other. A worker with no built-ins at all cannot do the work. The usable configuration is therefore **an allowlist of the read-only built-ins plus PAL's own writing instrument**, not an empty list:

```
--tools "Read,Grep,Glob"     # keep the worker able to look
                             # Edit / Write / Bash / Skill are absent by omission
```

Two follow-ons fall out of that. **PAL must supply whatever it removes** — an epic that constrains a worker at spawn owns the tools the worker now lacks. And **[#88](https://github.com/xenodeve/pal-mcp-server/issues/88)'s skill floor cannot be delivered by telling the worker to load a skill** when `Skill` is one of the omitted built-ins; the floor has to arrive as prompt text.

*The probe server and its config are not committed — they are twenty lines of JSON-RPC over stdio and are cheaper to rewrite than to maintain. The commands above are the whole recipe.*

## Two capabilities that close part of the native-subagent gap with no PAL work at all

- **`agy --json-schema`** — *"JSON schema string or path to a schema file to enforce structured output"*. Also present on Claude Code as `--json-schema`. So structured output with vendor-side validation exists per-client; PAL's own `schema` parameter would add retry-on-content, not validity.
- **`agy --effort low|medium|high` and `--model`** — the per-agent effort and model override, native.

## What this changes

- **#16 (Phase 4, interrupt-and-resume per-action approval) is gated on a premise that no longer holds.** Its header says to ship only where #12 proved both capabilities; on this evidence that is four clients, not one. The gate should be re-scoped rather than left as written.
- **#11 story 24's per-client capability probe is still right and now cheap** — the probe has an answer to encode instead of a question to ask.
- **The `docs/reports/2026-08-04` Q2 table should be read together with this file.** It is not withdrawn: its resume column stands, its host inventory stands, and its Q1 remains unanswered. Only the pre-tool-hook column is superseded.
- **#89's tier 1 is no longer a hypothesis and its scope is larger than written.** The spawn-time constraint is verified end to end, and with it the finding that removing built-ins removes the worker's ability to read, search, run and load a skill — so tier 1 owns replacing them. **#88 inherits the skill half of that.**

## Evidence register

**VERIFIED-BINARY** — the codex `HookEventName` enum and the `PreToolUse` stdin schema, extracted from `codex.exe` with the bundled ripgrep; `agy.exe` permission strings; `cursor-agent`'s hook event names from its JS bundles.

**VERIFIED-LOCAL** — `codex --version` (0.144.4); `agy` 1.1.12 at `%LOCALAPPDATA%\agy\bin\agy.exe`, **not on PATH**; `cursor-agent` 2026.08.11-e8db854, **not on PATH**; `claude --help`'s `--tools`, `--disallowedTools`, `--strict-mcp-config`, `--json-schema`; a live `agy -p` turn whose refusal message names the allowlist file, its key, its rule grammar, and that headless mode is deny-by-default.

**VERIFIED-LOCAL (2026-08-13, the `--tools` probe)** — `claude -p --tools ""` accepted with a prompt on stdin; the same invocation with `--strict-mcp-config --mcp-config` against a one-tool stdio MCP server returned that tool's token; the worker enumerated its own tools as that MCP tool alone and stated it had no file-reading, shell or search tool, and no `Skill` tool. *Note the arity trap: `--tools` is variadic, so a positional prompt after it is parsed as a tool name — pass the prompt on stdin.*

**VERIFIED-WEB** — the OpenAI hooks documentation; `code.claude.com/docs/en/cli-reference` for the tools/MCP layer separation.

**UNKNOWN** — whether an imported hook fires under `agy` (nothing was imported, by instruction); whether the same file-based hook conventions hold on non-Windows installs; **whether a `PreToolUse` hook actually denies inside a child that PAL itself spawned** — the surface is verified, a firing is not, and PAL passes a `cwd` only when the client config sets `working_dir` (`clink/agents/base.py:242,276`), so a repository-scoped `hooks.json` would not be found where a user-level one would.
