"""The one user-facing environment variable survives the rename (#94).

Twelve `PAL_*` variable names exist in the tree. Eleven of them
(`PAL_LEGACY_NAMES`, `PAL_WRAPPER`, `PAL_QWEN_*`, `PAL_GEMINI_CONFIG`,
`PAL_CODEX_CONFIG`) are set and consumed inside a single `run-server.sh`
invocation — an inline prefix on a `python3 -c` call — so renaming them is
invisible outside that script and needs no compatibility.

**`PAL_MCP_FORCE_ENV_OVERRIDE` is the exception, and the only one that matters.**
It is something a user writes into their own `.env`, which lives outside the
repository and is not touched by any sweep. Renaming it without a fallback does
not raise: the new name is simply absent, `_compute_force_override` falls back to
its `"false"` default, and the user's setting stops taking effect silently. A
setting that quietly stops applying is worse than one that errors, because
nothing points at the cause.

So both names are read, and the new one wins when both are present — an explicit
new setting should beat a stale old one rather than the other way round.
"""

from __future__ import annotations

import pytest

from utils.env import _compute_force_override

NEW = "OPENCLINK_MCP_FORCE_ENV_OVERRIDE"
OLD = "PAL_MCP_FORCE_ENV_OVERRIDE"


def test_the_new_name_is_honoured():
    assert _compute_force_override({NEW: "true"}) is True


def test_the_old_name_still_works_so_existing_dotenv_files_keep_applying():
    """A user's `.env` is outside the repository. No sweep can reach it."""
    assert _compute_force_override({OLD: "true"}) is True


@pytest.mark.parametrize(
    "values,expected",
    [
        ({NEW: "true", OLD: "false"}, True),
        ({NEW: "false", OLD: "true"}, False),
    ],
    ids=["new-true-wins", "new-false-wins"],
)
def test_the_new_name_wins_when_both_are_set(values, expected):
    """Precedence in both directions, so the test cannot pass by accident.

    Checking only the true-beats-false case would also pass an implementation
    that ORs the two names together and ignores precedence entirely.
    """
    assert _compute_force_override(values) is expected


def test_neither_name_present_is_still_false():
    assert _compute_force_override({}) is False
