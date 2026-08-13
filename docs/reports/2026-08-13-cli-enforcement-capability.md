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

**Untested, and it is the test that decides the shape:** whether `--tools ""` is accepted alongside a live MCP server, or whether the CLI requires at least one built-in.

## Two capabilities that close part of the native-subagent gap with no PAL work at all

- **`agy --json-schema`** — *"JSON schema string or path to a schema file to enforce structured output"*. Also present on Claude Code as `--json-schema`. So structured output with vendor-side validation exists per-client; PAL's own `schema` parameter would add retry-on-content, not validity.
- **`agy --effort low|medium|high` and `--model`** — the per-agent effort and model override, native.

## What this changes

- **#16 (Phase 4, interrupt-and-resume per-action approval) is gated on a premise that no longer holds.** Its header says to ship only where #12 proved both capabilities; on this evidence that is four clients, not one. The gate should be re-scoped rather than left as written.
- **#11 story 24's per-client capability probe is still right and now cheap** — the probe has an answer to encode instead of a question to ask.
- **The `docs/reports/2026-08-04` Q2 table should be read together with this file.** It is not withdrawn: its resume column stands, its host inventory stands, and its Q1 remains unanswered. Only the pre-tool-hook column is superseded.

## Evidence register

**VERIFIED-BINARY** — the codex `HookEventName` enum and the `PreToolUse` stdin schema, extracted from `codex.exe` with the bundled ripgrep; `agy.exe` permission strings; `cursor-agent`'s hook event names from its JS bundles.

**VERIFIED-LOCAL** — `codex --version` (0.144.4); `agy` 1.1.12 at `%LOCALAPPDATA%\agy\bin\agy.exe`, **not on PATH**; `cursor-agent` 2026.08.11-e8db854, **not on PATH**; `claude --help`'s `--tools`, `--disallowedTools`, `--strict-mcp-config`, `--json-schema`; a live `agy -p` turn whose refusal message names the allowlist file, its key, its rule grammar, and that headless mode is deny-by-default.

**VERIFIED-WEB** — the OpenAI hooks documentation; `code.claude.com/docs/en/cli-reference` for the tools/MCP layer separation.

**UNKNOWN** — whether `--tools ""` is accepted with a live MCP server; whether an imported hook fires under `agy` (nothing was imported, by instruction); whether the same file-based hook conventions hold on non-Windows installs.
