# Name Changes

This project has shipped under three names. This page is the record of both
changes, and of what each one asked of an existing user.

## Zen MCP → PAL MCP

Renamed to avoid confusion with another similarly named product, and to reflect
its role as a Provider Abstraction Layer. The software and workflows were the
same.

Existing users had to run `run-server.sh` again to set up the new connection, and
to revisit any `ZEN` name used within `.env` and change it to `PAL`.

## PAL MCP → OpenClink

Renamed 2026-08-13. `pal-mcp-server` on PyPI is taken at version 10.4.3 by
something that is not this project, so publishing under that name was never
available — and the name is the deliverable for anyone installing without
cloning. `openclink` was free on PyPI, npm and GitHub. The software and workflows
are, again, the same.

**Most of this one needs nothing from you.** Unlike the previous rename, three
things were deliberately kept working rather than moved:

| What you have | What happens |
|---|---|
| `~/.pal/cli_clients/*.json` — your own clink client overrides | Still read. The new location is `~/.openclink/cli_clients/`, and the server now logs a warning naming both, so you are told rather than left to discover it. A file in the new directory wins if both define the same client. |
| `PAL_MCP_FORCE_ENV_OVERRIDE` in your `.env` | Still honoured. `OPENCLINK_MCP_FORCE_ENV_OVERRIDE` is the current spelling and takes precedence if both are set. |
| The `pal-mcp-server` console command | Still installed, alongside `openclink`. Both run the same server, so an `mcpServers` block you already pasted into a client keeps working. |
| A `zen` registration in a client config | Removed by setup, as before. That name really is stale. |

**The one thing that has not moved yet is the tool prefix.** Tools still appear
to the Claude and Codex CLIs as `mcp__pal__<tool>`, because the skills in
[`xeno-skills`](https://github.com/xenodeve/xeno-skills) call them by that name
and those skills run inside those two CLIs. Renaming the entry before the skills
are updated would break every one of them, at the caller rather than here.

Everything else — Claude Desktop, VS Code, VS Code Insiders, Cursor, Windsurf,
Trae, Gemini CLI, Qwen — registers as `openclink` from this release, because no
skill addresses this server through them.

So for a short period one machine can legitimately answer to both prefixes. That
is the cutover, not a bug. The CLIs move once `xeno-skills` has shipped the
change **and** users have pulled it; only then does `pal` join `zen` in the list
of registrations setup removes.
