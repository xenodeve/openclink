# Architecture Decision Records (fork)

Load-bearing, hard-to-reverse decisions for this fork. **Write a new ADR — never edit-to-reverse.**
An ADR supersedes; the old one stays as history. Read the relevant ADR before touching its area.
See `t4-engineering-records` for the format/discipline.

Write an ADR when a decision is costly to undo: a seam/interface, a data/format contract, a
platform dependency, a security boundary. A reversible implementation detail does not need one.

## Index

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-antigravity-via-windows-conpty.md) | Drive Antigravity (`agy`) through a Windows ConPTY | Accepted |
| [0002](0002-per-call-model-effort-per-backend.md) | Per-call `model`/`reasoning_effort` as an optional, per-backend-mapped clink override | Accepted |
| [0003](0003-zero-setup-discovery-and-active-claude-9arm.md) | Zero-setup CLI discovery + ship `claude-9arm` active, with a `~/.pal` override | Accepted |

The Antigravity `--print`/`--model` ordering bug is a **fix**, recorded as a post-mortem
(`docs/reports/2026-07-16-clink-antigravity-model-override-investigation.md`, RESOLVED section), not
an ADR; ADR 0002 references the fail-closed behavior it introduced.
