# Home — PAL MCP (fork) memory

Map of Content for the durable memory of this fork. **One line per note — hook + link.** Read this
at session start; open only the notes the task touches. Open work → `docs/OPEN-WORK-LEDGER.md`;
what shipped + how it was validated → `DONE.md`; fork-specific changes → `CHANGES-FORK.md`.

## Memories

- [[agy-print-swallows-model]] — `agy --print` is value-taking; `--model` MUST precede `--print` or agy silently uses its default model
- [[clink-per-call-model-effort]] — the fork's per-call `model` / `reasoning_effort`, mapped per back-end (support matrix)
- [[clink-zero-setup-discovery]] — bare commands are discovery-resolved; `~/.pal/cli_clients/` overrides; `claude-9arm` ships active
- [[antigravity-quota-split]] — `agy` quota is split: a Gemini pool vs a non-Google (Claude/GPT-OSS) pool that burns faster
- [[clink-quota-routing-and-harness-equivalence]] — `codex` is nearly out of weekly quota (use `luna`, not `sol`) and `claude` is at its limit; `claude-9arm` is the same harness, so harness-level findings transfer from it for free
- [[pal-two-installs-and-config-cache]] — Claude Code's PAL (uv-tool) vs Codex's PAL (uvx) are separate installs; `~/.pal` is shared; config is cached at start; a reinstall wipes site-packages conf
- [[requirements-unbounded-mcp-pin]] — `mcp>=1.0.0` is unbounded; mcp 2.0.0 dropped `Server.list_tools`, so a fresh install can't import `server.py` and the suite dies at collection
- [[ci-unavailable-billing-blocked]] — GitHub Actions has never run here (billing-blocked account) even though every workflow reads `active`; the PR gate is local evidence, not a green check
- [[absence-must-not-conflate-two-facts]] — in the clink accounting block a marker means a fact about the CLI or the call; a fact about PAL's own config stays silent, or it lands on every response
- [[delegated-red-can-reproduce-and-still-be-worthless]] — a subagent's failing test can reproduce exactly and still test nothing; read what the assertion is anchored to, and treat "verifiable leaf" as *observable behaviour*
- [[gh-and-shell-traps-on-this-box]] — always `gh --body-file` (never `--body`), `gh` is off the Bash PATH, `.venv` has no `pip`, and PowerShell `Set-Content` corrupts source encoding

Unresolved `[[wikilinks]]` are memories worth writing later, not errors.
