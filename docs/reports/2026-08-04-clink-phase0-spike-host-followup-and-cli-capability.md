# Phase 0 spike — host follow-up calls, and per-CLI hook / resume capability (2026-08-04)

Deliverable **Phase 0** of epic PRD [#11](https://github.com/xenodeve/pal-mcp-server/issues/11),
tracked by [#12](https://github.com/xenodeve/pal-mcp-server/issues/12). **Spike only — no production
code shipped.**

## Status

| Question | Answer |
|---|---|
| **Q1 — does the master's MCP host issue a follow-up tool call after a non-terminal result?** | ❌ **NOT ANSWERED.** The stub probe was not run — see *Why Q1 is still open*. Adjacent evidence was gathered that **changes why the question matters**. |
| **Q2 — which clients expose a pre-tool hook and a resumable session?** | ✅ **ANSWERED** for resume on all four live clients; **partially answered** for the pre-tool hook, with the unresolved cells named rather than guessed. |

**The most consequential outcome is not either question.** It is that **the epic's transport premise
is now an open question rather than something this report either confirmed or refuted** — see
*⚠️ Correction*. It was measured on one of four hosts, and the fault it describes is intermittent, so
what is recorded below is a five-sample observation on a single host and nothing more. Phases 3 and 4
should not be re-planned until the premise is measured as a **rate, per host**.

---

## ⚠️ Correction — this section was mis-scoped when first written

**The first version of this report claimed the epic's transport premise "did not reproduce". That
framing was wrong, and the owner corrected it: the 60–108 s figure was not measured on Claude Code.**

`#11` says *"the MCP transport between **the master** and PAL"*. **The master is whichever host is
driving PAL — and it is not one host.** Enumerated 2026-08-04, PAL is configured as an MCP server on
**all four**:

| Host | Where PAL is registered |
|---|---|
| **Claude Code** | `~/.claude.json` → `mcpServers.pal` |
| **codex** | `~/.codex/config.toml` → `[mcp_servers.pal]` |
| **cursor** | `~/.cursor/mcp.json` → `mcpServers.pal` |
| **antigravity** | `~/.gemini/config/mcp_config.json` → `mcpServers.pal`, and `~/.gemini/antigravity-cli/mcp/pal` |

**I measured one of four and wrote the result as a statement about PAL.** The transport deadline is a
property of the *host's MCP client*, not of PAL, so a measurement on one host transfers to no other —
the same rule `#12` already applies to CLI harnesses, applied to the host side, where this report
failed to apply it.

**Direct evidence that the hosts differ, from this session's own logs.** The `codex` run's stderr
carried, six times:

```
ERROR rmcp::transport::worker: worker quit with fatal: Transport channel closed, when Auth(AuthorizationRequired)
```

That is **codex's own MCP client transport dying mid-run** — a failure mode Claude Code did not
exhibit once across the same five calls. Whatever the 60–108 s figure came from, it plausibly came
from a host that behaves like this one.

**The finding, restated correctly and now sharper than the wrong version:**

> **Phase 3's value is host-dependent, and neither `#11` nor `#12` says which host it is for.**
> On a host that backgrounds a long call and delivers the terminal payload later, stories 1 and 2 are
> already satisfied and Phase 3's remaining scope is small. On a host whose transport simply gives up,
> they are not satisfied at all and Phase 3 is load-bearing. **`#12` asks for Q1 "yes/no per host
> tested" but contains no host inventory** — the table above is that inventory, and it is four rows,
> not one.

### And the failure is intermittent, which changes what any measurement can show

**Second correction from the owner: the transport give-up does not happen every time — it occurs
randomly.** That is not a detail; it invalidates the shape of the evidence below.

**A run of successes cannot disprove an intermittent fault.** Five successful calls against an unknown
failure rate *p* is a sample of five. If *p* were as high as 20 %, the probability of seeing five
straight successes is still about **1 in 3** — an entirely unremarkable outcome. The observation below
is therefore **not evidence that the premise is wrong even on Claude Code**; it is evidence only that
this host *can* carry a 672 s call to completion, which was never in doubt.

**Consequences, and they apply to `#12`'s acceptance criteria as written:**

- **Q1 cannot be answered "yes/no per host".** An intermittent fault has a *rate*, not a verdict.
  The acceptance criterion should be **a failure rate over N repeated trials per host**, with N stated,
  plus the observation that supports it. A single probe per host will produce a confident wrong answer
  roughly *p* of the time.
- **The same applies to the stub probe.** If the host's follow-up behaviour is itself flaky, one stub
  run answers nothing. Repeat it.
- **A candidate mechanism is already in hand and is worth chasing before more sampling.** The codex
  stderr above fails with `Auth(AuthorizationRequired)` — an *authorisation* fault on the MCP channel,
  which is exactly the shape of a failure that appears random from the outside (token refresh, session
  expiry, a race on re-auth). **If the intermittency is auth-driven rather than time-driven, then
  "gives up after 60–108 s" is a symptom description, not a cause**, and Phase 3's entire design is
  aimed at the wrong thing. That is worth one hour of root-cause work before any further measurement.

**Recorded as an open question, not a finding.** `#11`'s premise is neither confirmed nor refuted by
this report.

The measurement below stands as what it is: **one host, one day, five samples, reported as such.**

---

## Measured: Claude Code as master

`#11` states:

> The MCP transport between the master and PAL gives up after roughly **60–108 seconds** (measured: a
> subagent returning at 59s succeeded; clients whose typical runtime is ~108s and 400–530s timed out).
> […] For the ~1700 seconds in between, the master has been told "failed" and the child is still
> working.

**Five `clink` calls were made from a live Claude Code session on 2026-08-04. Four exceeded 120 s.
All five returned complete results.**

| Client / model | `duration_seconds` | Outcome |
|---|---|---|
| `codex` / `gpt-5.6-sol` @ `high` | **672.15** | success, full content, usage reported |
| `cursor` / `cursor-grok-4.5-high` | 147.10 | success |
| `antigravity` / `Gemini 3.1 Pro (High)` | 145.04 | success |
| `cursor` / `cursor-grok-4.5-high` (round 2) | 131.86 | success |
| `antigravity` / `Gemini 3.1 Pro (High)` (round 2) | 103.69 | success, returned inline |

**672 s is roughly 6× the ceiling the epic records**, and it is inside `clink`'s own 1800 s child
timeout with room to spare.

**The mechanism is not a follow-up tool call.** At 120 s the host emitted:

> *MCP tool "pal/clink" is still running after 120s. It was moved to the background as task
> `<id>` and keeps running; you'll receive a notification with the result when it completes.*

— and the terminal result arrived later as a **task notification**, carrying the full payload
including `metadata.duration_seconds` and `continuation_offer`.

**What this does and does not establish.**

- **Established (VERIFIED, this session):** on this host, a `clink` call exceeding the 120 s
  foreground window is **not reported to the master as failed**. It is backgrounded and its terminal
  result is delivered intact. The master is not driven to re-spawn a duplicate by a false failure.
- **Not established (INFERRED / UNKNOWN):** whether the host would issue a *follow-up tool call* if
  the tool itself returned a non-terminal payload. That is a different mechanism and is exactly what
  Q1's stub probe exists to measure. Backgrounding is the **host** handling its own transport
  deadline; it is not the host polling a handle.

**Consequence — for this host only.** Two of Phase 3's user stories — *"I am never told a call failed
while its subagent is still working"* and *"so that I can decide to wait instead of re-spawning a
duplicate"* — are **already satisfied by Claude Code** for the 120 s–1800 s band. **On the other three
hosts this is unmeasured**, and the codex transport errors above suggest at least one of them behaves
differently.

Four stories are **not** satisfied by backgrounding on *any* host, because backgrounding does not
address them at all. These are Phase 3's host-independent core:

- cancelling a running subagent by handle (#11 story 11)
- listing in-flight sessions to discover a duplicate before starting one (#11 story 12)
- distinguishing *slow* from *genuinely blocked* (#11 story 4)
- reattaching after losing the response (#11 story 10)

**This is not a refutation of the epic and the first draft of this report was wrong to read like one.**
It is one host out of four, measured on one day. What it establishes is that **the premise is
host-scoped and the epic does not currently say which host it holds for** — so the deliverable is a
per-host row, not a verdict.

---

## Why Q1 is still open

The probe `#12` specifies — *"stub the tool to return a non-terminal status plus a token, spawn no
child at all, and observe whether a second call arrives"* — requires editing the running PAL server
and restarting it. A restart drops the live MCP connection for the session doing the observing, and
clink's client config is cached at process start, so the restart is not free.

That is a disruptive action on a shared, live component, so it was not taken unilaterally. **It
remains the single blocking item for `#12`**, and it is cheap once scheduled: no child spawned, no
subscription quota, one restart.

**The question should be re-scoped before it is run**, given the finding above. As written it asks
whether handle-plus-poll is viable. The more useful form is now:

> Given the host already delivers a late terminal result via backgrounding, does a handle-plus-poll
> shape buy anything the background mechanism does not — and if so, is *that* remainder worth the
> call-shape change Phase 3 proposes?

---

## Q2 — per-client capability table

Every cell below was probed **directly on the command line, not through clink**, as `#12` requires.
Evidence is the CLI's own output.

| Client | Harness | Pre-tool hook | Resumable session |
|---|---|---|---|
| **`claude`** · **`claude-9arm`** | Claude Code | ✅ **YES, and it can block.** Claude Code's `PreToolUse` hook returns `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny\|ask","permissionDecisionReason":"…"}}` — verified in a working hook at `xeno-skills/hooks/t4-gate:32`, which uses both `deny` and `ask`. `claude --help` also advertises `--include-hook-events` — *"Include all hook lifecycle events in the [output] … only works with --print"* — so hook events are observable from a **headless** run. | ✅ **YES.** `-r, --resume [value]` — *"Resume a conversation by session ID"* — plus `-c, --continue`. `ClaudeJSONParser` already extracts `session_id`, and the session lives on disk, so it outlives a PAL restart. |
| **`codex`** | Codex CLI | ⚠️ **A hook system exists; its event vocabulary is UNVERIFIED.** `codex exec --help` carries `--dangerously-bypass-hook-trust` — *"Run enabled hooks without requiring persisted hook trust for this invocation"* — which proves hooks exist **and** that they carry a trust model. Whether any of them fire *before* a tool call, and whether such a hook can block, is **not** discoverable from the local install: the shipped `README.md` is a 2,814-byte npm shim with zero hook documentation. | ✅ **YES, headless.** `codex exec resume [SESSION_ID] [PROMPT]` — *"Conversation/session id (UUID) or thread name. UUIDs take precedence"* — with `--last` for the most recent. `codex` also ships `fork`, `archive`, `unarchive`, `delete` by id or name, so sessions are first-class and persisted. |
| **`cursor`** | cursor-agent | ❌ **None advertised.** `--help` has no `hook` anywhere. The nearest surface is `--auto-review` — *"a server classifier auto-runs safe tool calls and **prompts for the rest**"* — but that is a **server-side** classifier, not a local hook, and its behaviour under `-p` (headless) is **UNVERIFIED**. `plugin` exists but exposes only `marketplace`. | ✅ **YES.** `--resume [chatId]`, `--continue`, and the `ls` / `resume` subcommands. Notably `create-chat` — *"Create a new empty chat and return its ID"* — **mints an identifier before the run**, which is the cleanest handle source of any client here. |
| **`antigravity`** (`agy`) | Antigravity CLI | ⚠️ **UNVERIFIED, with a plausible route.** `--dangerously-skip-permissions` — *"Auto-approve all tool permission requests without prompting"* — proves a permission-request mechanism exists. `agy plugin import [source]` — *"Import plugins from **gemini or claude**"* — suggests Claude-plugin hooks may be importable, but **whether an imported `PreToolUse` hook actually fires and blocks was not tested.** | ✅ **YES.** `--conversation` — *"Resume a previous conversation by ID"* — plus `-c, --continue`. |
| `gemini` | — | n/a — binary retired; preset fails with `Executable 'gemini' not found in PATH` | n/a |

### Harness sharing — stated explicitly, per `#12`

- **`claude-9arm` and `claude` share the Claude Code harness.** Both cells above are harness-level
  properties (`PreToolUse` contract, `--resume`), so the result **transfers**. It was measured on the
  harness, not on a model, and costs nothing to confirm on `claude-9arm`.
- **`agy` is its own harness**, despite being able to *import* Claude plugins. An import path is not
  shared execution; no result transfers from `claude` to `agy` on that basis.
- **`cursor` and `codex` are each their own harness.** Nothing transfers.

### The verdict Phase 4 needs

Phase 4 requires **both** a pre-tool hook and a resumable session, per client.

- **Claude Code (`claude`, `claude-9arm`) is the only client that demonstrably has both today**, and
  it has them with a documented blocking contract and a headless event stream. **Phase 4 should be
  built and proven on this harness first.**
- **`codex` has resume and probably hooks**; the gap is one documentation or one probe away.
- **`cursor` has the best handle story and the weakest hook story.** Its approval surface is
  server-side, which is the wrong side of the boundary for a master-approval design.
- **`agy` has resume; its hook route is speculative.**

This directly supports `#11`'s own requirement — *"I want the approval mechanism gated behind a
per-client capability probe, so that we never ship a feature that silently no-ops on a back-end
lacking the hook"* (story 24). **On this evidence, shipping Phase 4 uniformly across all four clients
would silently no-op on at least two of them.**

---

## Incidental findings

Found while probing; each belongs to a different issue and none is acted on here.

1. **`agy` has a real `--effort` flag** — `--effort  Reasoning effort for the current CLI session
   (low|medium|high)`. This confirms **[#43](https://github.com/xenodeve/pal-mcp-server/issues/43)**
   (*"antigravity silently drops reasoning_effort — agy has a real --effort flag"*) **at source**. Note
   the ladder is three rungs, and `clink-brainstorm` currently documents antigravity's effort as
   *"baked into the model label"* — which is now incomplete rather than wrong.
2. **`agy --print-timeout` defaults to `5m0s`.** A client-side print-mode deadline of 300 s sits
   *inside* clink's 1800 s child timeout and is not currently modelled anywhere in PAL. Any
   `antigravity` run longer than five minutes may be cut by the CLI itself, not by clink.
3. **`cursor create-chat` returns a chat ID without running anything.** If Phase 3 does adopt a
   handle, this is a client that can supply a real, CLI-owned identifier *before* the child starts —
   which is strictly better than a PAL-minted in-memory handle that dies with the process (`#11`
   story 22).
4. **`codex` sessions are first-class on disk** (`resume` / `fork` / `archive` / `delete` by id or
   name), so the same durability argument applies there.

---

## What remains to close `#12`

- [ ] **Run the Q1 stub probe** — re-scoped per *Why Q1 is still open*. Requires one PAL restart.
- [ ] **Resolve the `codex` hook cell** — find the event vocabulary (upstream docs, not the npm shim)
      or probe a hook directly.
- [ ] **Resolve the `agy` hook cell** — import a Claude `PreToolUse` hook via `agy plugin import` and
      observe whether it fires and blocks.
- [ ] **Resolve the `cursor` cell** — determine what `--auto-review` does under `-p`, or record that
      the client has no local pre-tool block point.
- [ ] **Re-measure the transport premise** on the hosts this fork is driven from, and update `#11`'s
      problem statement with the result either way.

Completed by this report: the per-client resume column, the harness-sharing statement, the Phase 4
capability verdict, and the host inventory that shows the timeout premise was measured on one host of
four. The premise itself is left **open** — this report neither confirms nor refutes it.

---

## Evidence register

**VERIFIED** (command run, output read, 2026-08-04): every `--help` quotation above, from
`codex --help` · `codex exec --help` · `codex exec resume --help` · `codex plugin --help` ·
`cursor-agent --help` · `cursor-agent plugin --help` · `agy --help` · `agy plugin --help` ·
`claude --help`; the `PreToolUse` JSON contract from a working hook at `xeno-skills/hooks/t4-gate:32`;
the five `clink` durations, read from `metadata.duration_seconds` in each tool result; the codex npm
README size.

**UNVERIFIED / UNKNOWN**: codex's hook event names and whether any is pre-tool · whether an imported
Claude hook fires under `agy` · `cursor --auto-review` behaviour under `-p` · whether the host issues
a follow-up tool call on a non-terminal payload (Q1) · whether the epic's original 60–108 s
measurement is reproducible on any host.
