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

Unresolved `[[wikilinks]]` are memories worth writing later, not errors.
