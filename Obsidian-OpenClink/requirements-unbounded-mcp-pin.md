---
name: requirements-unbounded-mcp-pin
description: "requirements.txt pins mcp>=1.0.0 with no upper bound; mcp 2.0.0 removed Server.list_tools, so a fresh install cannot import server.py"
metadata:
  type: reference
---

**Status as of 2026-08-01: fixed by #17.** Both `pyproject.toml` and `requirements.txt` now pin
`mcp>=1.0.0,<2`, and `requirements.txt` also carries the `pywinpty` marker it had been missing.
`tests/test_dependency_pins.py` fails if the two manifests ever drift again, so this exact defect
cannot return silently. The **decision** about adopting the 2.x API is deliberately *not* made —
it is tracked as **#18**, and the `<2` bound must not be lifted outside that issue.

The history below is why the bound is load-bearing; keep it when editing.

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

Why it stays hidden: the OpenClink that actually answers MCP calls on this machine was installed earlier
against `mcp` 1.x and keeps working, so the breakage is invisible until somebody builds a fresh
environment — a new contributor, CI, or an agent setting up to run tests. There is **no `uv.lock`**,
so nothing pins the resolution.

**How to apply:** the generalizable lesson is that **this repo carries the same dependency list
twice** — `pyproject.toml` and `requirements.txt` — and installers disagree about which they read,
so a fix applied to one manifest alone ships a tree that still breaks. When you touch either, touch
both; `tests/test_dependency_pins.py` is the guard that enforces it. A fresh env still can't be fully
trusted until there is a `uv.lock` (still absent), so when a fresh install misbehaves, check the
resolved version first: `python -c "import importlib.metadata as m; print(m.version('mcp'))"`.

Related: [[openclink-two-installs-and-config-cache]] (a stale user CLI config produces a *different*
collection failure that masks this one — clear that before concluding the pin is at fault).
