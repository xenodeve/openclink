"""The key clients file this server under, and why the old one must survive it (#94).

The setup scripts write an entry into each client's config. That entry's KEY is
what makes tools reachable as `mcp__<key>__<tool>` — so it is not an internal
name, it is the address every caller uses.

**Why this could not simply be renamed with everything else.** `xeno-skills`
names `mcp__pal__` 25 times across 10 files, including all four clink skills.
Flipping the key alone would leave every one of those calling a tool that does
not exist, and the breakage appears at the caller, not here.

**Why it also could not simply be deferred.** `LEGACY_MCP_NAMES` exists to delete
stale registrations. Had this rename added the `pal` forms to it — as #94's own
suggested order said to — the next `run-server.sh` run would delete the entry the
skills still call and write one they do not: the two halves of the break, in a
single command the user runs for an unrelated reason. So `pal` is deliberately
absent from that list, and the spec step is the thing that was wrong.

What actually shipped is a split by client, not one key:

1. the config-file clients (Claude Desktop, VS Code, VS Code Insiders, Cursor,
   Windsurf, Trae, Gemini, Qwen) register under `openclink` now — no skill
   addresses this server through them;
2. the Claude and Codex CLIs keep `pal`, because that is where the skills run;
3. an existing `pal` entry is never deleted, by any mechanism;
4. `zen` stays in the cleanup list — that one really is stale.

Points 2 and 3 flip together once `xeno-skills#206` lands AND users have pulled
it. Neither may flip alone, and the tests below are what say so.
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


def test_no_embedded_python_block_deletes_a_registration_by_a_literal_name():
    """There is ONE list of names to delete, and `pal` is not on it.

    #94 said it in the spec: "`run-server.sh:1413` already carries
    `LEGACY_MCP_NAMES` … Reuse it; do not invent a second one." Three of the four
    deletion sites obey — they iterate `legacy_keys` / `legacy`, piped in from
    that array. The fourth hardcoded its own tuple:

        for key in ('openclink', 'pal'):
            del servers[key]

    so the two mechanisms disagreed about `pal`, and the hardcoded one won on the
    path it sits on. `test_an_existing_pal_entry_is_not_deleted_by_the_cleanup_list`
    could not see it: that test reads the DECLARATION line, and this deletion
    never consults the declaration.

    Anchored to the deletion statement rather than to the name, so a new site that
    invents a third list is caught by shape, not by remembering to look.
    """
    deletion = re.compile(r"(?:del\s+servers\[|servers\.pop\(|\.pop\()\s*['\"]([a-z0-9_-]+)['\"]")
    literal_key_loop = re.compile(r"for\s+key\s+in\s+\((?P<keys>[^)]*)\)")

    offenders: list[str] = []
    for script in SCRIPTS:
        for n, line in enumerate(_text(script).splitlines(), 1):
            for match in deletion.finditer(line):
                offenders.append(f"{script}:{n}: deletes {match.group(1)!r} by literal name — {line.strip()[:80]}")
            loop = literal_key_loop.search(line)
            if loop and "'" in loop.group("keys"):
                named = re.findall(r"['\"]([a-z0-9_-]+)['\"]", loop.group("keys"))
                if named:
                    offenders.append(f"{script}:{n}: iterates a hardcoded key list {named} — {line.strip()[:80]}")

    assert not offenders, (
        "a registration is deleted by a name written at the deletion site instead of "
        "coming from LEGACY_MCP_NAMES. That is the second mechanism #94 forbade, and "
        "it is how `pal` gets deleted while the shared list deliberately spares it:\n  " + "\n  ".join(offenders)
    )


def test_no_config_file_client_is_still_registered_under_pal():
    """The GUI clients moved to the new key, on both platforms.

    Windows and Unix must not hand out different tool prefixes. `run-server.ps1`
    drives Claude Desktop, VS Code, VS Code Insiders, Cursor, Windsurf and Trae
    from a `ConfigJsonPath` table; `run-server.sh` writes the same entries
    directly. They are two implementations of one contract, and nothing made them
    agree -- a Windows user got `mcp__pal__<tool>` while everyone else got
    `mcp__openclink__<tool>`, from the same release. Six of six entries.

    The failure is invisible on either machine alone, because each script is
    self-consistent, so only a test that reads both catches it.
    """
    paths = [
        ln.split("=", 1)[1].strip().strip('"')
        for ln in _text("run-server.ps1").splitlines()
        if "ConfigJsonPath" in ln and "=" in ln and '"' in ln
    ]
    assert paths, "run-server.ps1 no longer declares any ConfigJsonPath entries"
    stale = [p for p in paths if p.endswith(".pal")]
    assert not stale, (
        f"{len(stale)} of {len(paths)} client entries in run-server.ps1 still register under "
        f"`pal` while run-server.sh writes `openclink`: {stale}"
    )

    writes_pal = re.findall(
        r"""\[["']mcpServers["']\]\[["']pal["']\]|servers\[["']pal["']\]\s*=""", _text("run-server.sh")
    )
    assert not writes_pal, (
        f"run-server.sh writes {len(writes_pal)} config-file entries under `pal` while "
        "run-server.ps1 writes `openclink` — the same split, the other way round"
    )


@pytest.mark.parametrize("script", SCRIPTS)
def test_the_two_cli_clients_are_still_registered_under_pal(script: str):
    """Claude Code and Codex are the deliberate exception, and both scripts agree.

    This is the half of the cutover that cannot move yet. `xeno-skills` calls
    `mcp__pal__<tool>`, and those skills run inside the Claude and Codex CLIs --
    not inside Claude Desktop, VS Code or Cursor. So the config-file clients moved
    to `openclink` immediately (the test above), and these two keep answering to
    the old name until `xeno-skills#206` lands and users pull it.

    Two keys from one release is a real cost, and it is written down here rather
    than left to be rediscovered as a bug: without this test the split looks
    exactly like the ps1/sh mismatch that WAS a bug, and someone "fixes" it.

    Expected to INVERT with `test_an_existing_pal_entry_is_not_deleted_by_the_cleanup_list`
    -- at cutover both flip together, and neither may flip alone.
    """
    text = _text(script)
    registrations = re.findall(r"claude mcp add[^\n\"]*", text) + re.findall(r"\[mcp_servers\.[a-z_]+\]", text)
    assert registrations, f"{script} no longer shows how to register with either CLI"

    moved_early = [r for r in registrations if "openclink" in r]
    assert not moved_early, (
        f"{script} registers a CLI client under `openclink` before xeno-skills#206 has landed:\n  "
        + "\n  ".join(moved_early)
        + "\nEvery skill calling mcp__pal__<tool> breaks the moment a user runs setup."
    )
