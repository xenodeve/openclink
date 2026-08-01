# Issue Tracker (fork)

Issues live in **GitHub Issues** on `xenodeve/pal-mcp-server` (use the `gh` CLI). Issues were
disabled by default on the fork; they are now enabled. Issues are the source of truth for *what to
do* and *its state* — reconcile session todos back to issues before the session ends.

## Bilingual rule (tracker-only)

Issue bodies, PRD bodies, and PR descriptions must be **bilingual — English + a full Thai mirror**:

- **Title:** English, conventional-commit style (`feat(clink): …`, `fix(clink): …`).
- **Body:** each section in English, then a mirrored Thai version (an `**EN**` / `**TH**` pair or a
  `## สรุปภาษาไทย` section). **The Thai mirrors the English exactly** — same detail, not a digest.
- Code identifiers, filenames, log excerpts, commit SHAs stay English; the Thai explains around them.
- **Scope: tracker only.** Chat, reports (`docs/reports/`), commit messages, and inline comments are
  not required bilingual (commits/identifiers stay English).

## Lifecycle

- Every code change maps to one issue you're allowed to work.
- Keep the issue **body** current as scope changes (bilingual), not just comments.
- **Close with a stated reason + evidence** — completed-with-evidence (commit SHA / passing test) /
  cancelled / duplicate / wontfix / stale. Never close silently; never leave finished work open.
- New work discovered mid-session → a `docs/OPEN-WORK-LEDGER.md` row and, if non-trivial, an issue.

## `gh` quick reference

```bash
gh issue list --repo xenodeve/pal-mcp-server
gh issue create --repo xenodeve/pal-mcp-server --title "…" --body-file -   # bilingual body
gh issue close <n> --repo xenodeve/pal-mcp-server --reason completed --comment "…evidence…"
gh pr create --repo xenodeve/pal-mcp-server --base main --head <branch> --body-file -  # Closes #<n>
```

Labels: see `triage-labels.md`.
