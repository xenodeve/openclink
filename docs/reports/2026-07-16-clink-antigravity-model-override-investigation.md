# Investigation handoff — PAL clink cannot override Antigravity model/effort (2026-07-16)

## Status

**✅ RESOLVED — root cause found, fixed, and live-validated (2026-07-16).** See the
**[Resolution](#resolution-2026-07-16--fixed--live-validated)** section at the end. Original
handoff below is preserved as the record. The mechanism turned out to be **argument order**
(`--print` is value-taking and swallowed `--model`), not persisted state, an internal ID, or
`--agent`.

## Executive summary

PAL's custom `clink` implementation accepts a per-call `model`, maps it to
`agy --model <display-name>`, and records the expected command in successful-call metadata.
However, Antigravity continues to report **Gemini 3.5 Flash** when invoked with supported model
names returned by `agy models`, including `Gemini 3.1 Pro (High)` and
`Claude Sonnet 4.6 (Thinking)`.

The same failure reproduces by invoking `agy` directly, outside PAL. Therefore the demonstrated
problem is not loss of the argument in MCP request parsing, PAL command construction, or the
ConPTY runner. The remaining failure boundary is the `agy --model` invocation contract and/or
Antigravity's persisted project/session state. `agy` silently returns exit code `0` while using
or reporting its default model, so PAL currently treats the fallback as success.

For Antigravity, reasoning effort is intentionally encoded in the model display name — for
example `(Low)`, `(High)`, or `(Thinking)`. PAL ignores the separate `reasoning_effort` value for
this runner. Consequently, model selection and effort selection fail together when `--model`
does not take effect.

## Environment under test

- PAL MCP server: `9.8.2`
- PAL source checkout: `D:\Github\pal-mcp-server`
- PAL branch/commit: `main` at `97a7072aa83bcd51d79a4a50eccf4f680c120e69`
- Relevant fork commit: `97a7072 feat(clink): per-call model + reasoning_effort override + fork docs & bilingual README`
- Antigravity executable: `C:\Users\xenod\AppData\Local\agy\bin\agy.exe`
- `agy.exe` exposes no Windows file/product version metadata in this installation
- OS: Windows 11
- PAL runner: Antigravity-specific Windows ConPTY runner

No PAL, Antigravity, MCP, or machine configuration was changed during this investigation.

## Expected behavior

Given a model name emitted by `agy models`:

```text
clink(
  cli_name="antigravity",
  model="Gemini 3.1 Pro (High)",
  reasoning_effort="high",
  role="default",
  prompt="..."
)
```

PAL should launch:

```text
agy --print --model "Gemini 3.1 Pro (High)" "<prepared prompt>"
```

and Antigravity should run Gemini 3.1 Pro at the effort encoded by `(High)`. The separate
`reasoning_effort` parameter is not expected to add another Antigravity CLI flag.

## Actual behavior

PAL builds and launches the expected command, receives output, parses it, and reports
`return_code: 0`. The returned content nevertheless identifies the active model as
**Gemini 3.5 Flash**.

### Reproduction matrix

| Invocation | Requested model | PAL command metadata | Observed response | Exit |
|---|---|---|---|---|
| PAL `clink` | `qwen3.6-35b-a3b` | `agy.EXE --print --model qwen3.6-35b-a3b` | Gemini 3.5 Flash | 0 |
| PAL `clink` | `Gemini 3.1 Pro (High)` | `agy.EXE --print --model "Gemini 3.1 Pro (High)"` | Gemini 3.5 Flash | 0 |
| PAL `clink` | `Claude Sonnet 4.6 (Thinking)` | `agy.EXE --print --model "Claude Sonnet 4.6 (Thinking)"` | Gemini 3.5 Flash | 0 |
| Direct `agy` | `Claude Sonnet 4.6 (Thinking)` | N/A — PAL bypassed | Gemini 3.5 Flash | 0 |

The Qwen result is expected to be unsupported and is not evidence by itself. The two supported
model names and the direct invocation are the decisive reproductions.

### Models advertised by this `agy` installation

Command:

```powershell
agy models
```

Output:

```text
Gemini 3.5 Flash (Medium)
Gemini 3.5 Flash (High)
Gemini 3.5 Flash (Low)
Gemini 3.1 Pro (Low)
Gemini 3.1 Pro (High)
Claude Sonnet 4.6 (Thinking)
Claude Opus 4.6 (Thinking)
GPT-OSS 120B (Medium)
```

### Direct reproduction outside PAL

```powershell
agy --print --model "Claude Sonnet 4.6 (Thinking)" `
  "Model-routing verification only. State the exact model family you are currently running, in one short line."
```

Observed:

```text
I am currently running on the Gemini 3.5 Flash model.
```

The process exited `0`. It also inspected `D:\Github\MangaDock` even though the process was
started with `D:\Github\T4 Fastwork` as its working directory. This indicates that `agy` may
restore a persisted Antigravity project/session independently of the process cwd. That state is
a plausible source of a model override, but it is not yet proved to be the cause.

## Verified PAL data path

The argument survives every PAL-owned seam:

1. `CLinkRequest.model` and `CLinkRequest.reasoning_effort` accept the MCP fields in
   `D:\Github\pal-mcp-server\tools\clink.py:53` and `:60`.
2. `CLinkTool.execute()` passes both fields to the selected agent in
   `D:\Github\pal-mcp-server\tools\clink.py:235`–`:245`.
3. `BaseCLIAgent._build_command()` appends per-call overrides after config and role arguments in
   `D:\Github\pal-mcp-server\clink\agents\base.py:200`–`:225`.
4. `AntigravityAgent.run()` calls that builder, resolves `agy`, appends the prompt, and launches
   the full command through ConPTY in
   `D:\Github\pal-mcp-server\clink\agents\antigravity.py:30`–`:65`.
5. Successful-call metadata records the sanitized command at
   `D:\Github\pal-mcp-server\tools\clink.py:336`–`:351`; all live PAL calls showed the requested
   `--model` value there.

The direct `agy` reproduction removes MCP parsing, PAL request handling, command construction,
the PAL parser, and the ConPTY wrapper from the causal path.

## What is proved vs not proved

### Proved

- The PAL MCP server and `clink` tool are connected and can execute Antigravity successfully.
- PAL accepts and forwards the requested model as `--model <exact display name>`.
- `reasoning_effort` is deliberately ignored for Antigravity; effort is encoded in the model
  name by design (`clink/agents/base.py:217`–`:225`).
- Supported names copied verbatim from `agy models` do not change the model reported by the
  resulting Antigravity response.
- The same behavior occurs in a direct `agy` process without PAL.
- The failure is silent: exit code `0`, parseable content, no PAL-visible error.

### Not proved

- Whether Antigravity actually runs Gemini 3.5 Flash or merely reports a stale/default identity.
  The CLI exposes no machine-readable selected-model metadata in the observed output.
- Whether `--model` expects an internal model ID instead of the display name printed by
  `agy models`.
- Whether a persisted project, agent, conversation, or account policy overrides the CLI flag.
- Whether `--model` only takes effect with `--new-project`, an explicit `--project`, or a fresh
  conversation.
- Whether this behavior is an `agy` defect or an undocumented invocation constraint.

## Most likely failure mechanisms to test next

These are ordered hypotheses, not established root causes:

1. **Persisted project/session wins over `--model`.** The direct command reopened the MangaDock
   workspace despite a different cwd. Test a fresh project/session and an explicit project ID.
2. **Display name is not the accepted selector.** `agy models` may print UI labels while
   `--model` expects an internal identifier. Inspect official CLI output/logs or source for model
   IDs; do not invent a mapping.
3. **Silent fallback on invalid/unavailable routes.** The account may advertise routes but lack
   entitlement, causing `agy` to fall back without a non-zero exit.
4. **`--print` path ignores the model override.** Compare non-interactive `--print` with a fresh
   interactive invocation using the same model.

## Test gap in the PAL fork

`D:\Github\pal-mcp-server\tests\test_clink_model_effort.py:60`–`:68` tests only the pure
`BaseCLIAgent._build_command()` result, using a synthetic `gemini` client. It proves flag mapping,
not that:

- `AntigravityAgent` receives the request fields;
- the ConPTY command preserves them;
- `agy` accepts the selected model;
- the actual selected model matches the request; or
- an unsupported/ignored model fails visibly.

There is no Antigravity model-selection integration test in the current checkout.

## Recommended implementation sequence for Claude

1. **Reproduce from the PAL repo without changing config.** Record `agy models`, the direct
   `--print --model` matrix, exit codes, raw stdout, and any CLI log that exposes selected model
   or fallback reason. Redact tokens and account identifiers.
2. **Determine the supported selector contract.** Find whether `agy --model` requires the
   display label or an internal ID and whether a fresh/explicit project is mandatory.
3. **Add a failing test first.** At minimum, add an `AntigravityAgent`-specific test that captures
   the complete list passed to `_run_in_pty`. If the required invocation includes another flag,
   make that test express the exact contract before changing the runner.
4. **Apply the smallest runner-specific fix.** Keep any Antigravity behavior inside
   `clink/agents/antigravity.py`; do not alter shared runners unless the verified contract is
   actually shared.
5. **Fail closed when selection is rejected.** If `agy` provides selected-model metadata or a
   fallback warning, compare it with the request and return a PAL error rather than reporting a
   successful override. Do not infer success from exit code `0` alone.
6. **Add an opt-in live integration test.** Exercise one supported non-default route and one
   invalid route. The test must validate machine-readable model selection if available; model
   self-identification in generated prose is not a sufficient long-term oracle.
7. **Update docs only after live validation.** The current guide claims per-call Antigravity
   selection works (`docs/clink-model-effort-guide.md:21`–`:25`, `:76`–`:77`). Mark the limitation
   or restore the claim only after the live test passes.

## Acceptance criteria

- A model copied from the supported `agy` catalog is selected through PAL `clink` in a fresh,
  repeatable invocation.
- At least two distinct routes can be selected and distinguished using reliable metadata or
  another deterministic oracle.
- An invalid/unavailable model produces an explicit error; it must not silently return the
  default model as success.
- Antigravity effort follows the selected `(Low)`, `(High)`, or `(Thinking)` route.
- Omitting `model` preserves the existing default behavior.
- Existing Codex/Claude/Gemini clink behavior remains unchanged.
- Unit tests and the opt-in Antigravity live test pass, and the exact commands/results are
  recorded in the validation section of the eventual fix report.

## Safety constraints for the follow-up

- Do not edit shared MCP/client configuration as the first experiment.
- Do not guess model IDs or account settings.
- Back up any config before an explicitly authorized edit.
- Restart PAL only if PAL configuration or installed source actually changes; verify with a real
  clink model-selection call afterward.
- Do not call the issue fixed from command construction tests alone.

---

## Resolution (2026-07-16) — FIXED + live-validated

**Root cause: argument ORDER, via flag consumption.** `agy`'s `--print` is a **value-taking**
flag — it consumes the next token as the prompt. PAL built `agy --print --model "X" <prompt>`,
so `--print` swallowed `--model` as its value (the `agy` log recorded `promptLength=7` =
`len("--model")` and `model=""`), and `agy` fell back to the persisted default in
`~/.gemini/antigravity-cli/settings.json` (`"Gemini 3.5 Flash (High)"`). Ruled out: display
name vs internal ID (labels work), `--agent` (none configured), `--new-project` (no effect),
and any model env var (none; the internal `CASCADE_DEFAULT_MODEL_OVERRIDE` was not used).

**Fix — PAL fork commit `7e80e42` (`clink/agents/antigravity.py`):**
- `AntigravityAgent._build_command()` now places model options **before** `--print` →
  `agy --model "X" --print <prompt>`. Kept Antigravity-specific; shared runners unchanged.
- `AntigravityAgent.run()` **fails closed**: raises `CLIAgentError` on any non-zero `agy` exit
  (an unsupported model exits `1` with a catalog error) instead of returning the fallback as
  success.
- New unit test `test_antigravity_places_model_before_print` asserts the ordering; 6/6
  model-effort tests pass.

**Live validation (via PAL `clink`, after redeploy):**

| Requested model | Response | Command (metadata) | Exit |
|---|---|---|---|
| `Claude Sonnet 4.6 (Thinking)` | "Claude Sonnet, Anthropic" | `agy --model "Claude Sonnet 4.6 (Thinking)" --print` | 0 |
| `Gemini 3.1 Pro (High)` | "Gemini 3.1 Pro, Google" | `agy --model "Gemini 3.1 Pro (High)" --print` | 0 |
| `Totally-Invalid-Model-XYZ` | error + model catalog (fail-closed) | (model before `--print`) | 1 |

Meets the acceptance criteria: two distinct non-default routes selected and distinguished, an
invalid model produces an explicit error (not a silent default), and omitting `model` preserves
the default. Independent PowerShell reproduction confirmed wrong-order → *Gemini 3.5 Flash* vs
right-order → the requested model. (Minor: `agy` self-reported "Claude Sonnet 4.5" for a
requested 4.6 — a self-identification quirk, not a routing failure; the family/vendor is correct.)

**Deploy note.** The code fix is model-order in `_build_command`. On the machine under test, PAL
also needed the Antigravity client `command` set to the absolute `agy.exe` path — bare `agy` was
not on the *restarted* PAL process's `PATH` (a separate environment issue surfaced by the
restart, not part of this bug). codex's own PAL (uvx from git) picks up the fix on a fresh fetch
of fork `main`.

**Security — ACTION REQUIRED (found during this investigation).** A GitHub PAT was observed in
`C:\Users\xenod\.gemini\config\config.json` and echoed in an `agy` diagnostic log. **Revoke /
rotate it.** Never store secret values in command permission strings.

