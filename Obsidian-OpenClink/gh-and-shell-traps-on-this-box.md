---
name: gh-and-shell-traps-on-this-box
description: "Recurring tooling traps on this machine — always use gh --body-file, gh is not on the Bash PATH, .venv has no pip, and heredocs with apostrophes break the Bash tool"
metadata:
  type: feedback
---

**These are not one-off accidents. Each has cost time in more than one session, and one of them was
re-hit on 2026-08-05 by the same agent that had written it down hours earlier.** That is the reason
this note exists: knowing a trap in a handoff document is not the same as not falling into it, so it
belongs somewhere a session actually loads.

### Always pass a GitHub body with `--body-file`, never `--body`

Write the body to a file and point `gh` at it. **Do not** inline it.

Passing prose to `--body` breaks in at least two ways, both of which look like a `gh` usage error and
send you to the wrong place:

- **PowerShell expands `$NAME` inside a double-quoted argument.** A body containing `$BLACK` or
  `$RUFF` — which any PR about a shell script will — gets mangled, and the remaining text is then
  parsed as flags. Observed 2026-08-05: `unknown flag: --check\ in script`.
- **An escaped `\"` inside a PowerShell `--body` makes `gh` see two arguments**, so the body is
  truncated at the quote and the rest becomes garbage flags.

Backticks and `#` in the body are safe inside a file and hostile on a command line. **There is no
body short enough to be worth inlining** — the failure mode is silent truncation, not a clean error.

### `gh` is not on the Bash tool's PATH

Use PowerShell with the absolute path: `'C:\Program Files\GitHub CLI\gh.exe'`. This is one instance of
the wider fact that **the Bash tool and the PowerShell tool resolve different binaries** — the same
divergence that makes a stale `codex` answer a valid model with an HTTP 400 blaming the model. See
[[openclink-two-installs-and-config-cache]].

### `.venv` has no `pip`

Use `uv pip install --python .venv/Scripts/python.exe <pkg>`. Note the repo also documents `.openclink_venv`
(what `run-server.sh` creates) while this checkout carries `.venv`, so a doc-following agent finds no
venv and a `.venv`-finding agent gets an under-provisioned one. Neither is wrong, which is what makes
it cost a session.

### Heredocs with apostrophes break the Bash tool

Write the content with the file-writing tool instead. Related: a `PreToolUse` guard rejects whole
commands whose *text* contains certain path-like strings, so prose mentioning paths also belongs in a
file rather than on a command line.

### Do not use PowerShell `Get-Content`/`Set-Content` to edit source files

It re-encodes. Observed 2026-08-05: round-tripping `clink/agents/base.py` through
`Set-Content -NoNewline` turned an em-dash into mojibake across the file. Use the editing tool, which
preserves encoding — and note that `git checkout -- <file>` to undo it will also discard any
uncommitted work in that file.

Related: [[delegated-red-can-reproduce-and-still-be-worthless]] — the other class of mistake that
survives being written down, and needs a mechanical check rather than a reminder.
