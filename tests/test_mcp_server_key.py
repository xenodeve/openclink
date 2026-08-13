"""The key clients file this server under, and why the old one must survive it (#94).

The setup scripts write an entry into each client's config. That entry's KEY is
what makes tools reachable as `mcp__<key>__<tool>` — so it is not an internal
name, it is the address every caller uses.

**Why this could not simply be renamed with everything else.** `xeno-skills`
names `mcp__pal__` 25 times across 10 files, including all four clink skills.
Flipping the key alone would leave every one of those calling a tool that does
not exist, and the breakage appears at the caller, not here.

**Why it also could not simply be deferred.** `LEGACY_MCP_NAMES` exists to delete
stale registrations, and this rename added the `pal` forms to it. Renaming the
written key while `pal` sits in that list means the next `run-server.sh` run
deletes the entry the skills still call and writes one they do not — the two
halves of the break, in a single command the user runs for an unrelated reason.

So this is a sequenced cutover, and these tests pin the sequence:

1. new installs register under `openclink`;
2. an existing `pal` entry is left alone, because it is still addressed;
3. `zen` stays in the cleanup list — that one really is stale.

Step three of the cutover happens in `xeno-skills`, and `pal` returns to the
cleanup list only after it lands.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SCRIPTS = ("run-server.sh", "run-server.ps1")


def _text(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("script", SCRIPTS)
def test_new_installs_are_registered_under_openclink(script: str):
    """The written key is the new name.

    Asserting the absence of `'pal'` instead would pass on a script that wrote no
    entry at all, so this checks for the thing that must be present.
    """
    text = _text(script)
    assert re.search(r"""["']openclink["']\s*\]?\s*=|\[["']openclink["']\]""", text), (
        f"{script} does not register the server under 'openclink' — "
        "new installs would still be addressed as mcp__pal__<tool>"
    )


@pytest.mark.parametrize("script", SCRIPTS)
def test_an_existing_pal_entry_is_not_deleted_by_the_cleanup_list(script: str):
    """`pal` is not stale yet, so it must not be in the list of things to remove.

    This is the assertion that keeps the cutover safe. It is expected to be
    INVERTED once `xeno-skills` stops calling `mcp__pal__` — at which point `pal`
    joins `zen` in the list and this test becomes the one that says so.
    """
    declaration = next(
        (ln for ln in _text(script).splitlines() if "LEGACY_MCP_NAMES=" in ln or "LegacyServerNames =" in ln),
        None,
    )
    assert declaration is not None, f"{script} no longer declares its legacy-name list"
    assert not re.search(r"""["']pal["']|["']pal-mcp["']|["']pal-mcp-server["']""", declaration), (
        f"{script} lists 'pal' as a legacy name to delete, but skills still call "
        f"mcp__pal__<tool>. Running setup would remove the entry they address.\n"
        f"  found: {declaration.strip()}"
    )


@pytest.mark.parametrize("script", SCRIPTS)
def test_zen_is_still_cleaned_up_because_that_one_really_is_stale(script: str):
    """Removing `pal` from the list must not empty it.

    Nothing addresses `mcp__zen__` any more, and a duplicate entry from that era
    is exactly the mess the cleanup exists to prevent.
    """
    declaration = next(
        (ln for ln in _text(script).splitlines() if "LEGACY_MCP_NAMES=" in ln or "LegacyServerNames =" in ln),
        None,
    )
    assert declaration is not None
    assert re.search(
        r"""["']zen["']""", declaration
    ), f"{script}: the legacy-name list no longer removes 'zen' registrations.\n  found: {declaration.strip()}"
