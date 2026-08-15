"""The live surface carries one product name, and it is OpenClink (#94).

This is the guard that makes a rename checkable instead of "looks done". The
previous rename (zen -> pal) was audited on 2026-08-13 and found to have been
performed correctly — but nothing in the repository would have caught it if it
had not been, and the same is true today.

**Why a guard rather than a test pinning one literal.** `server.py` declares the
advertised name in exactly one place, so asserting that one string equals
"OpenClink" would pass while 400 other occurrences still said PAL. The failure
mode of a rename is not a wrong constant, it is a sweep that missed a shape.

**What is deliberately excluded, and why each one.** These are statements of
history or references to other projects. A sweep that "fixed" them would be
destroying facts, not renaming a product:

- `CHANGELOG.md`, `Documents/`, `docs/reports/` — records of what happened under
  the old names. Rewriting them makes the record lie.
- `docs/name-change.md` — the document whose subject IS the naming history. It
  should gain a paragraph about this rename, not have its existing text replaced.
- URLs — the upstream `zen-mcp-server` issue links in
  `tests/test_path_traversal_security.py` cite where a vulnerability was actually
  reported, and the `LICENSE` and fork-attribution lines name the project this
  one forked from. All must stay literal.
- The legacy-name arrays in `run-server.sh` / `run-server.ps1` — they match old
  names ON PURPOSE, so setup can remove stale registrations. A name belongs there
  only once nothing addresses it: `zen` qualifies, `pal` does not yet, because
  skills still call `mcp__pal__<tool>`. `tests/test_mcp_server_key.py` owns that
  distinction and asserts both halves of it.
- This file — it necessarily contains the names it forbids.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent

# Paths whose whole purpose is to record history or point at another project.
EXCLUDED_PATHS = (
    "CHANGELOG.md",
    "Documents/",
    "docs/reports/",
    "docs/name-change.md",
    "tests/test_product_name.py",
    # Same reason as the line above: this file's entire subject is the old key and
    # when it may be deleted, so it necessarily writes the name it governs.
    "tests/test_mcp_server_key.py",
)

# An ADDRESS. The old name inside one of these must stay literal or the link
# stops resolving — and that argument covers the characters of the address and
# nothing else, so this is matched as a SPAN and exempts only names inside it.
#
# It used to be one of the alternatives in EXEMPT_LINE below, which made it
# line-scoped: any link anywhere on a line exempted the whole line. That is how
# `docs/gemini-setup.md` kept "configure PAL MCP Server" in its opening sentence
# while the guard reported green — the exemption was bought by a link to
# google-gemini/gemini-cli at the far end of the same line.
ADDRESS_SPAN = re.compile(r"(?:git\+)?https?://\S+" r"|\b(?:github|githubusercontent|star-history)\.com/\S*")

# A line is exempt when it belongs to the deliberate legacy-cleanup machinery, or
# when naming the old thing IS the line's job. Checked per line rather than per
# file, so a stale name elsewhere in the same file is still caught.
EXEMPT_LINE = re.compile(
    # `gh --repo xenodeve/pal-mcp-server` addresses the actual repository, which
    # still has that name. Same rule as an address: it is not a product name.
    r"--repo "
    # The upstream project's real, current name, used as the display text of a
    # fork-attribution link (and as a star-history query parameter). It is a
    # different project — renaming it here would credit a repository that does
    # not exist. Previously exempt only because a URL sat on the same line.
    r"|BeehiveInnovations/pal-mcp-server"
    # The kept `pal-mcp-server` console script, named after the `--from <URL>` it
    # is invoked with. The address ends at `openclink.git`; the entry point is the
    # next token, outside it, so it needs its own reason to stay.
    r"|openclink\.git pal-mcp-server"
    # The `pal-mcp-server` console script kept on purpose, and the comment above it.
    r"|pal-mcp-server = \"server:run\"|already pasted into their own client"
    # The Docker migration note in `docker/README.md` must name the literal old
    # volume, or the commands it gives the user do not work on their machine.
    # Exempted per line rather than by excluding the file, so the rest of that
    # README is still checked.
    r"|pal-mcp-config"
    # Declarations that list old names ON PURPOSE, so something can still find
    # them: the setup scripts' stale-registration cleanup, and the env-var
    # fallback that keeps a user's existing `.env` applying.
    r"|LEGACY_MCP_NAMES|LegacyServerNames|_FORCE_OVERRIDE_KEYS"
    # A sentence whose subject IS the previous name. `docs/index.md` says
    # "Formerly known as PAL MCP" for the same reason `README.md` says
    # "เดิมชื่อ Zen MCP" — replacing the name there produces "Formerly known as
    # OpenClink", which states nothing. The sweep agent made exactly that edit
    # and reverted it; encoding the rule means the next one need not rediscover it.
    r"|[Ff]ormerly known as|เดิมชื่อ"
    # The Docker migration note's own heading and opening sentence name the old
    # family so a user can recognise what they have. Same argument as the volume
    # literal above.
    r"|from the `pal-mcp` family|upgrading from the `pal-mcp` Docker names"
)

# Three things that still say the old name for a reason, each with the reason.
# Each is a decision in its own right, and each is tracked on #94.
STILL_DECIDED_ELSEWHERE = re.compile(
    # The key a client files the server under. It is what makes tools appear as
    # `mcp__pal__<tool>`, and `xeno-skills` names that prefix 25 times across 10
    # files. Changing it here alone makes every one of those call a tool that does
    # not exist, so it lands with the other repository, not before it.
    r"servers\['pal'\]|servers\[\"pal\"\]|\['mcpServers'\]\['pal'\]|pal_cfg|get\(\"pal\"\)"
    # The wrapper script the setup scripts generate, named after the console entry
    # point that is deliberately kept for the transition. Renaming the wrapper
    # without renaming that entry point would leave the two disagreeing.
    r"|pal-mcp-server wrapper|pal-mcp-server\.cmd|chmod \+x pal-mcp-server"
    r"|Change to the pal-mcp-server directory|`pal-mcp-server` wrapper script"
    r"|\"args\": \[\"pal-mcp-server\"\]|the kept `pal-mcp-server` alias"
    # `run-server.ps1`'s Cleanup-Docker list, which removes containers left by
    # PREVIOUS install schemes. It names old things on purpose, and adding the
    # current name would make setup tear down the container it is about to start.
    r"|\"pal-mcp-server\",|\"pal-mcp-redis\"|\"pal-mcp-log-monitor\""
    r"|pal-mcp-server:latest\", \"python\"|\$images = @\("
    # The test that exists to prove the old entry point still works.
    r"|the previous entry point was dropped|must keep working through the rename"
    r"|the two names must run the same server|install instruction published so far"
    # The migration note naming the image a user currently has.
    r"|image `pal-mcp-server:latest`"
    # Two comments in `run-server.sh` explaining why the registration freshness
    # check must compare the interpreter: the virtualenv moved and `server.py`
    # did not, so a path-only match leaves the old entry pointing at a directory
    # setup no longer installs into. Both sentences are ABOUT the old name --
    # substitute it and one reads "moved from .openclink_venv to
    # .openclink_venv" and the other stops identifying what is still on disk.
    # Same shape as the Docker migration note above, and as `Formerly known as`.
    r"|from `\.pal_venv` to|\.pal_venv is still on disk"
    # Two tests whose SUBJECT is a legacy name — they exist to prove the old
    # spelling still works, so they must be able to write it. The rename sweep
    # rewrote one of them into `assert scripts["openclink"] == scripts["openclink"]`,
    # which is green and proves nothing; that is the shape this exemption protects.
    r'|OLD = "PAL_MCP_FORCE_ENV_OVERRIDE"|is the exception, and the only one that matters'
    r"|PAL_LEGACY_NAMES`, `PAL_WRAPPER|PAL_CODEX_CONFIG`\) are set and consumed"
    r"|ended in `pal-mcp-server`|`pal-mcp-server` . six copies"
)

# The old product names, in every shape the previous rename had to handle:
# bare, hyphenated, underscored, and the capitalised user-facing form.
STALE_NAME = re.compile(r"pal[-_]mcp[-_]server|pal[-_]mcp\b|PAL[ _]MCP|\bpal_venv\b|PAL_[A-Z]", re.IGNORECASE)


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if p and not any(p.startswith(x) or p == x for x in EXCLUDED_PATHS)]


def _line_carries_a_stale_name(line: str) -> bool:
    """Does this one line still name the old product, after exemptions?

    Extracted so the exemption rules can be tested against a literal line rather
    than only through a whole-repository walk. A rule that is only ever exercised
    by the walk is one nobody can write a regression test for.
    """
    if EXEMPT_LINE.search(line) or STILL_DECIDED_ELSEWHERE.search(line):
        return False
    addresses = [m.span() for m in ADDRESS_SPAN.finditer(line)]
    return any(
        not any(start <= hit.start() and hit.end() <= end for start, end in addresses)
        for hit in STALE_NAME.finditer(line)
    )


def _stale_occurrences() -> list[str]:
    hits: list[str] = []
    for rel in _tracked_files():
        path = REPO / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable — not prose we renamed
        for n, line in enumerate(text.splitlines(), 1):
            if _line_carries_a_stale_name(line):
                hits.append(f"{rel}:{n}: {line.strip()[:110]}")
    return hits


def test_no_live_surface_still_carries_the_old_product_name():
    hits = _stale_occurrences()
    assert not hits, (
        f"{len(hits)} live occurrences of the old product name remain (#94).\n"
        "Each is either a rename the sweep missed, or a historical statement that\n"
        "belongs in EXCLUDED_PATHS/EXEMPT_LINE above — decide which, per line.\n\n"
        + "\n".join(hits[:40])
        + (f"\n… and {len(hits) - 40} more" if len(hits) > 40 else "")
    )


def test_a_url_exempts_only_the_name_inside_it_not_the_whole_line():
    """An unrelated link must not buy the rest of the line an exemption.

    The URL rule exists because `github.com/BeehiveInnovations/pal-mcp-server` is
    an ADDRESS — it must stay literal or it stops resolving. That argument covers
    the characters inside the URL and nothing else.

    Applied per line it covered everything, and `docs/gemini-setup.md` opened with
    "This guide explains how to configure PAL MCP Server to work with [Gemini
    CLI](https://github.com/google-gemini/gemini-cli)" — a live product name in the
    first sentence a reader sees, exempted by a link to somebody else's repository
    at the far end of the line. The guard reported green.

    Both directions are pinned. Narrowing the rule until it exempts nothing would
    also pass a one-sided version of this test, and would then force every genuine
    upstream URL to be rewritten.
    """
    stale_outside = (
        "This guide explains how to configure PAL MCP Server to work with "
        "[Gemini CLI](https://github.com/google-gemini/gemini-cli)."
    )
    assert _line_carries_a_stale_name(stale_outside), (
        "a stale product name outside the URL was exempted by the URL — "
        "the exemption is being applied to the line instead of to the address"
    )

    stale_inside_only = "> **This is a fork** of [upstream](https://github.com/BeehiveInnovations/pal-mcp-server)"
    assert not _line_carries_a_stale_name(stale_inside_only), (
        "the old name inside a repository URL was flagged — that address must stay "
        "literal or the link stops resolving"
    )


def test_the_exclusions_are_not_swallowing_the_whole_repository():
    """A guard whose exclusion list covers everything passes vacuously.

    Without this, adding one broad entry to EXCLUDED_PATHS turns the test above
    into a test of nothing — and it would keep reporting green while the rename
    silently stopped happening.
    """
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    checked = _tracked_files()
    assert len(checked) > 0.8 * len(tracked), (
        f"only {len(checked)} of {len(tracked)} tracked files are checked — "
        "the exclusion list has grown until the guard means nothing"
    )


@pytest.mark.parametrize(
    "script,declaration",
    [
        ("run-server.sh", "LEGACY_MCP_NAMES="),
        ("run-server.ps1", "LegacyServerNames ="),
    ],
)
def test_the_legacy_name_arrays_still_carry_the_previous_names(script: str, declaration: str):
    """The cleanup that removes stale registrations must be extended, not replaced.

    An existing user is on a `zen` install or a `pal` one. Emptying these arrays
    while renaming leaves both stranded, with the old entry still sitting in their
    client config beside the new one — the duplicate-server state this machinery
    exists to prevent.

    Anchored to the declaration line, not the file. The first version searched the
    whole script for a quoted `"pal"` and passed while the array held only the
    `zen` forms — the substring false-positive this repository keeps re-learning.
    """
    line = next(
        (ln for ln in (REPO / script).read_text(encoding="utf-8").splitlines() if declaration in ln),
        None,
    )
    assert line is not None, f"{script} no longer declares {declaration!r} — the legacy-cleanup list is gone"
    assert re.search(
        r'["\']zen["\']', line
    ), f"{script}: {declaration.strip()} does not list 'zen'.\n  found: {line.strip()}"
    # `pal` is deliberately NOT here, and this test used to require it. That was
    # wrong: the list says what to DELETE, and skills still call `mcp__pal__<tool>`,
    # so deleting that entry breaks the callers. The rule is not "every old name"
    # but "every name nothing addresses any more" — `zen` qualifies, `pal` does not
    # yet. `tests/test_mcp_server_key.py` owns that decision and asserts the
    # opposite of what this test originally did.
    assert not re.search(r'["\']pal["\']', line), (
        f"{script} lists 'pal' as a name to delete while skills still address it — "
        f"see tests/test_mcp_server_key.py.\n  found: {line.strip()}"
    )
