# Triage Labels (fork)

Default label vocabulary for `xenodeve/pal-mcp-server` issues. Keep it small; a label earns its
place by changing what an agent does next.

## Triage roles (one per issue)

- `needs-triage` — new, not yet assessed.
- `needs-info` — blocked on a question / missing repro.
- `ready-for-agent` — scoped enough for the coding agent to pick up.
- `ready-for-human` — needs a human decision or an external/dashboard action.
- `wontfix` — decided not to do; close with the reason.

## Optional groups (add as the tracker grows)

- **Type** — `Feature` / `Bug` / `tech-debt` / `security` / `docs`.
- **Component** (one per issue) — `clink` / `agent:<name>` / `registry` / `discovery` / `providers`
  / `server` / `conf`.
- **Severity** — `critical` / `Major` / `Minor`. A `security` issue must be `critical` or `Major`.

## Notes

- A missing/unavailable CLI at runtime is expected behavior (a clear "not found"), **not** a bug —
  don't file it as one.
- Fork-vs-upstream: label fork-only work so it's distinguishable if this ever syncs with upstream.

Create labels lazily (`gh label create <name> --repo xenodeve/pal-mcp-server`); proceed silently if
the vocabulary is thinner than this — it's guidance, not a gate.
