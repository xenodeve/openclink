"""The quality gate must report, not rewrite the tree (#63).

`code_quality_checks.sh` is the script `CLAUDE.md` tells every agent to run
before and after any change, and it ran all three formatters in **write** mode.
It therefore never failed — it edited tracked files and exited 0.

That is worse than a noisy gate, because there is nothing to notice. It is the
mechanism behind two contaminated commits on 2026-08-04: run the gate as
instructed, get unrelated modified files, then `git add -A` sweeps them into a
behaviour commit. One of those carried a settings change the developer had
explicitly rejected.

Two halves, and both are needed. Making the gate report while the tree is
unformatted just moves the failure from silent to permanent, so the debt is paid
first and pinned here so it stays paid.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "code_quality_checks.sh"

# The exclusions the gate itself uses; the check must cover the same tree.
EXCLUDES = ["--exclude", "test_simulation_files/", "--exclude", r"\.pal_venv/", "--exclude", r"\.venv/"]


def _script() -> str:
    assert SCRIPT.is_file(), f"{SCRIPT} is missing"
    return SCRIPT.read_text(encoding="utf-8")


def test_the_gate_does_not_ask_ruff_to_fix():
    # `ruff check --fix` silently rewrites and exits 0, so the verify pass that
    # follows it can never fail. That is why #54 looked like a clean tree.
    assert "--fix" not in _script()


@pytest.mark.parametrize(
    "invocation",
    [
        "$BLACK . --check",
        "$ISORT . --check-only",
    ],
)
def test_the_gate_asks_the_formatters_to_report(invocation):
    # Anchored on the whole invocation, not on the bare flag. `"--check" in
    # "--check-only"` is True, so asserting the flag alone would let black run
    # in write mode as long as isort carried its own flag -- a substring
    # false-positive that passes while the defect stands. Caught by mutation,
    # not by reading.
    assert invocation in _script(), invocation


def test_the_gate_still_runs_the_unit_suite():
    # Control: passes before and after. Turning the formatters into reporters
    # must not quietly drop the half of the gate that catches real defects.
    text = _script()
    assert "pytest" in text
    assert "not integration" in text


def test_the_repo_is_already_formatted_so_the_gate_has_nothing_to_rewrite():
    # The debt half. Measured 2026-08-05: black would have rewritten 10 files
    # under tests/ and simulator_tests/. With the gate in check mode and this
    # red standing, an agent would land on a failing gate through no fault of
    # its own -- so the reformat lands in the same change, in its own commit.
    result = subprocess.run(
        [sys.executable, "-m", "black", "--check", ".", *EXCLUDES],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"black would reformat:\n{result.stderr}"
