# PAL clink architecture and hardening review

**Date:** 2026-07-16  
**Reviewed revision:** `d44ae015feb0ec0b834f39eec94fe5c928d1d58c` (`main`)  
**Status:** Review complete; hardening work remains  
**Scope:** Antigravity (`agy`) integration, per-call model selection, zero-setup CLI discovery, and the `claude-9arm` client

## Executive verdict

The fork solves the original Antigravity model-selection failure well. The root cause was identified correctly: `agy` only honored `--model` when it appeared before its internal `--print` argument. The fix is narrow, isolated to the Antigravity runner, fails closed for rejected models, and has been validated against the real CLI rather than only through mocks.

The current implementation is strong enough for controlled internal use. It is not yet fully hardened for unattended, repository-mutating delegation. The largest remaining risks are an inaccurate MCP read-only annotation, insufficient workspace/session isolation, and a PTY timeout path that may not interrupt a blocking read. These are architectural safety issues rather than failures of the original model-routing fix.

| Area | Assessment | Notes |
|---|---:|---|
| Root-cause diagnosis and fix | 9/10 | Correct, minimal, and proven end to end |
| Architecture and extensibility | 8.5/10 | Provider-specific behavior remains isolated |
| Runtime reliability | 7/10 | PTY timeout, output bounds, and exit-state handling need hardening |
| Automated test coverage | 6/10 | Good command-construction checks; important failure paths remain uncovered |
| Security and tool contract | 5.5/10 | `readOnlyHint` and workspace isolation do not match agentic behavior |
| Overall | 7.5/10 | A good solution with a clear hardening path |

## Evidence reviewed

The review covered the following implementation sequence:

- `9087c81` — add Antigravity CLI agent and `claude-alt-gateway` example
- `97a7072` — add per-call `model` and `reasoning_effort` overrides
- `7e80e42` — place Antigravity `--model` before `--print` and fail closed
- `1e435a6` — document persistent machine-local client activation
- `d44ae01` — add zero-setup CLI discovery and ship `claude-9arm` active

Relevant implementation and tests include:

- `clink/agents/antigravity.py`
- `clink/agents/base.py`
- `clink/discovery.py`
- `clink/registry.py`
- `clink/constants.py`
- `clink/models.py`
- `clink/parsers/antigravity.py`
- `tools/clink.py`
- `conf/cli_clients/antigravity.json`
- `conf/cli_clients/claude-9arm.json`
- `tests/test_clink_model_effort.py`
- `tests/test_clink_discovery.py`
- `tests/test_clink_tool.py`

This report should be read together with [the original Antigravity model-override investigation](./2026-07-16-clink-antigravity-model-override-investigation.md).

## What the implementation does well

### 1. The fix addresses the actual parser behavior

`AntigravityAgent._build_command()` places model arguments before the runner's internal `--print` argument. This differs intentionally from the generic command builder, which appends model arguments later. Keeping that exception inside the Antigravity adapter avoids changing working behavior for other CLI providers.

The change is therefore both causally correct and low in blast radius.

### 2. Invalid models fail closed

The Antigravity runner returns an error when `agy` exits nonzero instead of accepting output that might have been produced by an implicit fallback. A live call using `qwen3.6-35b-a3b`, which is not supported by Antigravity, returned an error and the CLI's model catalog. It did not silently report success under another model.

This is an important improvement over the original failure mode, where a requested model could be ignored while the call still appeared successful.

### 3. Per-call overrides fit the existing client architecture

`CLinkRequest` accepts `model` and `reasoning_effort`, and `tools/clink.py` passes them into the selected agent. Provider-specific mappings remain in the respective agent classes. This is preferable to embedding provider flags in the MCP tool layer.

### 4. Discovery reduces machine-specific setup

The discovery layer checks `PATH`, expands home and environment-based command paths, and supports known installation locations. User-level client definitions under `~/.pal/cli_clients` also avoid repeatedly modifying tracked configuration for machine-local providers.

### 5. Real integrations were exercised

The validation was not limited to command-string assertions. The Antigravity runner selected two distinct supported models successfully, rejected an unsupported model, and the `claude-9arm` route completed a deterministic task through its configured gateway.

## Findings and recommendations

### Critical — the MCP tool is marked read-only although it can mutate state

**Evidence:** `tools/clink.py:99-100` returns `{"readOnlyHint": True}`. The same tool launches external coding agents with relaxed or bypassed permissions. Those agents may edit files, execute commands, and affect systems accessible from their working directory.

**Impact:** MCP clients and users may approve or route the tool under the false assumption that it cannot modify state. This is a contract and safety failure even when the delegated prompt happens to be analytical.

**Recommendation:** Set `readOnlyHint` to false for the current tool. A stronger long-term design is to expose separate contracts:

- a read-only delegation tool whose runtime permissions enforce analysis-only behavior; and
- an agentic delegation tool explicitly marked as mutating.

Documentation alone is not sufficient because the annotation is machine-readable and may influence client policy.

**Acceptance criteria:** A test asserts the tool annotation, and the annotation agrees with the maximum capability of the launched agent.

### Major — workspace and session isolation are insufficient for mutating delegation

**Evidence:** `clink/models.py` provides a configuration-level working directory but no required per-call absolute workspace. Antigravity can retain project/session state independently of the process current directory. During investigation, an `agy` session reopened a MangaDock context while PAL was invoked from the T4 Fastwork workspace.

**Impact:** A valid agent response can refer to or modify the wrong repository. This is especially dangerous when permission bypass is enabled because the model may act correctly against stale context.

**Recommendation:** Require an explicit `working_directory_absolute_path` for agentic calls and pass it through every runner. For Antigravity, also create or select a fresh project/session tied to that path rather than relying only on process `cwd`. If reliable session isolation is not available, default Antigravity delegation to artifact-only output and require an explicit opt-in for in-place mutation.

**Acceptance criteria:** An integration test starts from a persisted session associated with repository A, requests repository B, and proves that reads and writes are confined to B.

### Major — the PTY timeout may not interrupt a blocking read

**Evidence:** In `clink/agents/antigravity.py:119-156`, the deadline is checked before `proc.read()`. If that read blocks while the process remains alive and produces no output, control may never return to the deadline check. The output is also accumulated into an unbounded `chunks` list.

**Impact:** A hung CLI can outlive the requested timeout, retain a child process, and consume unbounded memory when output is large.

**Recommendation:** Move timeout enforcement outside the blocking read path using a watchdog, cancellable reader, or platform-appropriate polling mechanism. Bound captured output using the same stream limit applied by the generic runner, terminate the complete child process tree on timeout, and wait for cleanup before returning.

**Acceptance criteria:** Tests cover a silent hung child, continuous oversized output, timeout cleanup, and a child process that spawns descendants.

### Major — automated tests prove structure more than runtime behavior

**Evidence:** `tests/test_clink_model_effort.py` verifies Antigravity argument ordering but does not exercise the PTY runner, nonzero fail-closed behavior, silent model fallback with exit code zero, timeout cleanup, or output bounds. `tests/test_clink_discovery.py` covers helper behavior but not PATH precedence, known Antigravity/Claude locations, Winget selection, or registry inclusion. `tests/test_clink_tool.py` does not verify the read-only annotation.

**Impact:** The exact failure classes most likely to cause wrong-model execution, wrong-workspace mutation, or an indefinite process can regress while the suite remains green.

**Recommendation:** Add three layers of tests:

1. deterministic unit tests for command construction, annotation, discovery precedence, redaction, and exit handling;
2. process-level tests using a fake CLI for timeout, output limits, cleanup, and workspace propagation; and
3. opt-in live tests for supported and unsupported Antigravity models.

The live test should verify machine-readable model evidence if the upstream CLI exposes it. Model self-identification in prose is useful evidence but not a robust assertion.

### Minor — Winget discovery does not reliably select the newest installation

**Evidence:** `clink/discovery.py` sorts matched paths and selects `matches[-1]`, described as the newest by name. Lexical ordering is not guaranteed to match semantic version ordering or installation freshness.

**Impact:** Multiple installed versions can cause PAL to launch an older or otherwise unintended binary.

**Recommendation:** Parse semantic versions where possible or select by a documented, deterministic precedence such as resolved package metadata followed by modification time. Add a test with versions whose lexical and semantic ordering differ.

### Minor — duplicate model flags make effective configuration less clear

**Evidence:** The live `claude-9arm` invocation included a configured `--model` and a per-call `--model` override. Both values were the same in the validated call, and the downstream CLI accepted them.

**Impact:** When values differ, behavior depends on undocumented last-flag-wins semantics. Logs are also harder to interpret.

**Recommendation:** Normalize model flags before execution so the command contains exactly one effective model selection. Preserve the final value in structured metadata.

### Minor — command sanitization may expose secrets stored in arguments

**Evidence:** Successful clink responses include `sanitized_command` metadata. Prompt content is removed, but generic secret-bearing flags in user-defined client arguments are not comprehensively redacted.

**Impact:** A client definition containing a token or API key as a command-line argument could expose that value through MCP output or logs.

**Recommendation:** Redact values following common secret flags such as `--api-key`, `--token`, `--secret`, and provider-defined equivalents. Prefer environment variables over command-line secrets and test both `--key value` and `--key=value` forms.

### Minor — unknown PTY exit state can be reported as success

**Evidence:** `clink/agents/antigravity.py:156` returns `(exit_status or 0)`. A missing exit status (`None`) is therefore converted to success.

**Impact:** An abnormal PTY shutdown can be indistinguishable from a clean exit.

**Recommendation:** Treat `None` as an explicit runner error and reserve zero for a confirmed successful process exit.

### Clarification needed — gateway cost metadata and documentation

The live `claude-9arm` response reported `costUSD: 0.208735`, while related documentation describes the route as local/free or unlimited. This report does not establish whether that number represents actual billing, an upstream synthetic estimate, or compatibility metadata.

The documentation should avoid a billing claim until the value's provenance is verified. If it is synthetic, label it as such or omit it from user-facing cost totals.

## Validation record

The following calls were executed against the real integrations during the investigation:

| Route | Requested model | Result | Evidence |
|---|---|---|---|
| `clink -> antigravity` | `Gemini 3.1 Pro (High)` | Passed | Exact marker `AGY_GEMINI31_HIGH_OK`; command placed model before `--print`; exit 0 |
| `clink -> antigravity` | `Claude Sonnet 4.6 (Thinking)` | Passed | Exact marker `AGY_CLAUDE46_THINKING_OK`; command placed model before `--print`; exit 0 |
| `clink -> antigravity` | `qwen3.6-35b-a3b` | Failed as intended | Exit 1 with supported-model catalog; no silent successful fallback |
| `clink -> claude-9arm` | `qwen3.6-35b-a3b` | Passed | Exact deterministic result `CLAUDE_9ARM_OK 703`; provider and model metadata matched; exit 0 |

The `claude-9arm` validation used the deterministic calculation `37 * 19 = 703`. Its parser was `claude_json`, and the recorded duration was approximately 14.1 seconds.

### Automated test limitation

The focused pytest subset could not be independently rerun from either the current Python environment or the repository's `.venv` because neither environment contained `pytest`. No dependency was installed because changing a shared or project environment was outside the review scope and would violate the repository's small, verified-change policy.

Therefore:

- the live integration results above are directly observed;
- the test files were reviewed statically; and
- test-pass counts appearing in commit history were not treated as independently verified evidence.

## Recommended implementation order

1. Correct the MCP mutability annotation.
2. Add required per-call workspace propagation and Antigravity session isolation.
3. Make PTY timeout, process-tree cleanup, and output bounds reliable.
4. Add process-level regression tests for those safety properties.
5. Harden discovery selection, argument redaction, duplicate flag handling, and unknown exit-state behavior.
6. Add an opt-in live Antigravity model-selection test and clarify gateway cost semantics.

The first three items should be complete before treating clink as safe for unattended in-place edits across multiple repositories.

## Final assessment

PAL's Antigravity integration is not a superficial adapter. It handles a real CLI parsing quirk, preserves provider isolation, supports per-call routing, rejects unsupported models, and has demonstrated successful execution through both Antigravity and `claude-9arm`. That is a solid engineering result.

The remaining work is concentrated in operational safety boundaries: accurately declaring mutability, proving the target workspace, and guaranteeing process cancellation. Addressing those boundaries would move the implementation from a capable internal integration to a dependable multi-agent execution layer.
