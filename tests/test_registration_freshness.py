"""An existing registration must be re-checked against the interpreter, not just the script (#94).

The rename moved the virtualenv: `VENV_PATH` went from `.pal_venv` to
`.openclink_venv`. `server.py`'s path did not move.

That combination is what makes a latent bug load-bearing. `run-server.sh`'s
Claude Code path decides whether an existing registration is current with

    local expected_cmd="$python_cmd $server_path"
    if echo "$mcp_list" | grep -F "$server_path" &>/dev/null; then
        return 0

— `expected_cmd` is built and then never read; the comparison is on the server
script alone. On `main` that was harmless, because the interpreter path never
changed. After this rename every existing user's entry reads

    <repo>/.pal_venv/bin/python <repo>/server.py

which still contains `$server_path`, so the check declares it current and returns.
Setup then provisions `.openclink_venv` and installs into that, and the
registration keeps pointing at a virtualenv nothing updates again. Nothing errors:
`.pal_venv` is still on disk, so the server still starts, just from an environment
that stops receiving dependencies.

**Why that is a rename blocker and not a nit.** #94's acceptance criterion is that
"the old MCP server name keeps working until `xeno-skills` is updated", and the
Claude and Codex CLIs are exactly where those skills run. Keeping `mcp__pal__`
registered while silently freezing what it executes satisfies the letter and
loses the point.

The repository already does this correctly elsewhere — the Qwen path compares
`cmd == expected_cmd` before declaring a config current — so this is reusing a
pattern that exists, not inventing one.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "run-server.sh"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _read(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


def test_an_existing_pal_entry_is_refreshed_rather_than_left_on_the_old_interpreter():
    """Not deleting it is only half of keeping it working.

    The config-file clients pop `legacy_keys` (the `zen` forms) and write
    `openclink`. An existing `pal` entry is untouched by both — which is correct,
    because deleting it would break anyone addressing `mcp__pal__` — but it still
    names `.pal_venv`, and setup stops installing into that directory. Nothing
    errors: the directory is still there, so the server starts, from an
    environment that no longer receives dependencies.

    So the entry is refreshed to the same command being written for `openclink`.

    **Refreshed, never created.** The write must be guarded by a membership test,
    or this becomes "register every client under both names" — which is the
    duplicate-server state the cleanup machinery exists to prevent, and would put
    a second copy of every tool in front of users who never had `pal` at all.

    Deleting it from the config-file clients instead would also remove the
    duplication, and is defensible: no skill addresses this server through Claude
    Desktop or Cursor. It is not what shipped, because a missing prefix fails
    silently while a duplicated one is visible, and the duplication ends at
    cutover anyway. If that trade is judged wrong, this is the test to invert.

    Checked in BOTH scripts. Fixing this in `run-server.sh` alone would rebuild
    the cross-platform split that `tests/test_mcp_server_key.py` exists to catch:
    Windows users left on a rotting entry, everyone else refreshed, from one
    release, and invisible from either machine.
    """
    for script, write, guard in (
        ("run-server.sh", r"(?:\['mcpServers'\]|servers)\['pal'\]\s*=", "'pal' in"),
        ("run-server.ps1", r'-Name "pal"', 'PSObject.Properties["pal"]'),
    ):
        text = _read(script)
        writes = [m.start() for m in re.finditer(write, text)]
        assert writes, (
            f"{script} never refreshes an existing `pal` entry, so it keeps naming the "
            "pre-rename virtualenv while setup installs into the new one (#94)"
        )

        for start in writes:
            preceding = text[max(0, start - 300) : start]
            assert guard in preceding, (
                f"{script} writes a `pal` entry without first checking that one already "
                "exists — that registers every client under both names and puts a second "
                "copy of every tool in front of users who never had it"
            )


def test_the_freshness_check_is_not_satisfied_by_the_server_path_alone():
    """The failing shape, pinned directly.

    `grep -F "$server_path"` matches any registration naming server.py, whatever
    interpreter precedes it. Kept as a separate assertion from the one above so
    that reintroducing the path-only grep is caught even if some future rewrite
    keeps `expected_cmd` alive for another purpose.
    """
    lines = _text().splitlines()
    offenders = [
        f"{n}: {line.strip()}"
        for n, line in enumerate(lines, 1)
        if re.search(r'grep -F "\$server_path"', line) and "expected_cmd" not in line
    ]
    assert not offenders, (
        "an existing registration is judged current by matching the server script path "
        "alone. The interpreter moved in this rename; the script did not:\n  " + "\n  ".join(offenders)
    )
