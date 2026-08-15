# Triage Labels (fork)

Default label vocabulary for `xenodeve/openclink` issues. Keep it small; a label earns its
place by changing what an agent does next.

## Triage roles (one per issue)

- `needs-triage` — new, not yet assessed.
- `needs-info` — blocked on a question / missing repro.
- `ready-for-agent` — scoped enough for the coding agent to pick up.
- `ready-for-human` — needs a human decision or an external/dashboard action.
- `wontfix` — decided not to do; close with the reason.

## Optional groups (add as the tracker grows)

- **Type** — `Feature` / `bug` / `tech-debt` / `security` / `documentation`.
- **Component** (one per issue) — `clink` / `agent:<name>` / `registry` / `discovery` / `providers`
  / `server` / `conf`.
- **Severity** — `critical` / `Major` / `Minor`. A `security` issue must be `critical` or `Major`.

## Notes

- A missing/unavailable CLI at runtime is expected behavior (a clear "not found"), **not** a bug —
  don't file it as one.
- Fork-vs-upstream: label fork-only work so it's distinguishable if this ever syncs with upstream.

## Creating them

**Create the labels with `gh label create <name> --repo xenodeve/openclink`, then report the
reconciliation: which were created, which already existed, and which this document names but you
skipped.**

The previous wording here said to create them *lazily* and to *proceed silently* if the vocabulary was
thinner than documented. Those two compose into **never created and never mentioned** — measured on
2026-08-05, this repo carried 16 labels against the 19 named here, with the whole Type and Severity
groups missing and `needs-triage` among them. A documented vocabulary with no labels behind it **reads
as configured and is not**, and `t4-afk` builds its worklist from labels.

`agent:<name>` is a **pattern, not a label**: it cannot be pre-created, so a reconciliation report
should name it as deliberately absent rather than leave a future audit counting it as missing forever.

Same defect, same fix: `xeno-skills#96` and its PR #108.
