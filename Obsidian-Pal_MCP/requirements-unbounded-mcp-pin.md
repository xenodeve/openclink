---
name: requirements-unbounded-mcp-pin
description: "requirements.txt pins mcp>=1.0.0 with no upper bound; mcp 2.0.0 removed Server.list_tools, so a fresh install cannot import server.py"
metadata:
  type: reference
---

**Status as of 2026-08-01:** `pyproject.toml` already pins `mcp>=1.0.0,<2` (`14782f7` on main).
`requirements.txt:1` is still `mcp>=1.0.0` with **no upper bound** — that drift is what remains of #17.
Installers that read `requirements.txt` (common for agents / run-server) still resolve `mcp` 2.0.0.

`mcp` 2.0.0 removed `Server.list_tools`. `server.py:630` decorates with `@server.list_tools()`, so a
**fresh** `pip install -r requirements.txt` produces a tree that dies at import:

```
server.py:630: in <module>
E   AttributeError: 'Server' object has no attribute 'list_tools'
```

Measured 2026-08-01: `uv pip install -r requirements.txt -r requirements-dev.txt` into a clean
`.venv` resolved `mcp 2.0.0`; `hasattr(Server('x'), 'list_tools')` is `False` and no tool-related
attribute remains on the object. Every test module that imports `server.py` therefore fails at
**collection**, so the unit suite cannot run at all.

Why it stays hidden: the PAL that actually answers MCP calls on this machine was installed earlier
against `mcp` 1.x and keeps working, so the breakage is invisible until somebody builds a fresh
environment — a new contributor, CI, or an agent setting up to run tests. There is **no `uv.lock`**,
so nothing pins the resolution.

**How to apply:** before running the suite in a fresh env, check the resolved `mcp` version
(`python -c "import importlib.metadata as m; print(m.version('mcp'))"`). Until the pin is bounded,
install `mcp<2` explicitly. Ledgered under *Other*; related: [[pal-two-installs-and-config-cache]]
(a stale user CLI config produces a *different* collection failure that masks this one).
