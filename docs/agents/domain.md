# Domain — PAL MCP Server (fork)

What the words mean here, so a fresh agent reads code and issues with the right model.

## What this is

A **Model Context Protocol (MCP) server** (Python, `server.py`) that lets one AI CLI orchestrate
many models + other AI CLIs. This is **[xenodeve's fork](https://github.com/xenodeve/pal-mcp-server)**
of [BeehiveInnovations/pal-mcp-server](https://github.com/BeehiveInnovations/pal-mcp-server)
(unmaintained upstream). Everything the fork adds is additive and listed in `CHANGES-FORK.md`.

## Ubiquitous language

- **clink** — the CLI-to-CLI bridge tool (`tools/clink.py`). Spawns an external AI CLI as a
  subagent and returns its result. This fork's changes concentrate here.
- **client / `cli_name`** — a configured external CLI (`codex`, `claude`, `antigravity`, `gemini`,
  `claude-9arm`), defined in `conf/cli_clients/*.json`, loaded by `clink/registry.py`.
- **runner / agent** — the Python class that executes a client (`clink/agents/*.py`); `base` is the
  plain pipe path, `antigravity` drives `agy` through a Windows ConPTY.
- **parser** — normalizes a CLI's stdout into a `ParsedCLIResponse` (`clink/parsers/*.py`).
- **role** — a system-prompt preset per client (`default` / `planner` / `codereviewer`).
- **agy / Antigravity** — Google's post-Gemini-CLI tool; the Gemini CLI is retired.
- **claude-9arm** — the `claude` runner pointed at an alternate OpenAI-compatible gateway (this
  fork's 9arm Qwen gateway) via `--settings`/`--model`.
- **model / reasoning_effort** — per-call overrides this fork adds to clink (see `CHANGES-FORK.md`).
- **discovery** — `clink/discovery.py`: resolve a bare command to an absolute path so bundled
  configs work with zero setup.

## Where things live

`server.py` (MCP entry) · `tools/` (MCP tools incl. `clink.py`) · `clink/` (registry, agents,
parsers, discovery, constants) · `conf/cli_clients/` (client configs) · `systemprompts/clink/`
(role prompts) · `providers/` (model providers) · `tests/` + `simulator_tests/` · `docs/`.

See `docs/agents/workflow.md` for how to ship, `issue-tracker.md` + `triage-labels.md` for the
tracker, `docs/adr/README.md` for load-bearing decisions, `docs/reports/` for research records.
