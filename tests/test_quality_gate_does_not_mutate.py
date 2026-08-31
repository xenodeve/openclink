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

**And there are two scripts, which this file did not know (#121).** #63 was fixed
on `code_quality_checks.sh`; `code_quality_checks.ps1` kept running all three
formatters in write mode for six weeks, and these tests were anchored to a single
path so they never looked. The guard passed on the platform that did not need it
and was silent on the one this repository is primarily developed on.

Every check below is now parametrized over both copies. The invocations differ by
shell, so the expected text is per-script rather than shared — a single pattern
loose enough to match both would be loose enough to match neither properly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Both copies of one contract. Listed here rather than globbed, so a THIRD gate
# script added tomorrow fails this file's own consistency check below instead of
# being silently skipped the way the PowerShell copy was for six weeks.
GATES = {
    "code_quality_checks.sh": ("$BLACK . --check", "$ISORT . --check-only"),
    "code_quality_checks.ps1": ("& $blackCmd . --check", "& $isortCmd . --check-only"),
}

# The exclusions the gate itself uses; the check must cover the same tree.
EXCLUDES = ["--exclude", "test_simulation_files/", "--exclude", r"\.openclink_venv/", "--exclude", r"\.venv/"]


def _script(name: str) -> str:
    path = REPO / name
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def _code(name: str) -> str:
    """The script with its full-line comments removed.

    A flag search over the whole file cannot tell a command from a note about
    one. Both scripts now carry comments explaining *why* `--fix` is absent, and
    those comments made the `--fix` assertion red — the guard correctly reporting
    a string it found and wrongly calling it an invocation.

    Full-line comments only. Both shells use `#`, and stripping from the first
    `#` anywhere on a line would cut into quoted arguments the moment one
    contains a hash.
    """
    return "\n".join(line for line in _script(name).splitlines() if not line.lstrip().startswith("#"))


def test_every_gate_script_in_the_repo_is_covered_here():
    # The failure #121 is about was not a wrong assertion — it was a file nobody
    # asserted on. So the list of files is itself checked, and a new gate script
    # reddens this rather than joining the one that drifted.
    found = {p.name for p in REPO.glob("code_quality_checks.*")}

    assert found == set(GATES), f"a gate script is not covered by these tests: {found ^ set(GATES)}"


@pytest.mark.parametrize("script", sorted(GATES))
def test_the_gate_does_not_ask_ruff_to_fix(script):
    # `ruff check --fix` silently rewrites and exits 0, so the verify pass that
    # follows it can never fail. That is why #54 looked like a clean tree — and
    # why the PowerShell copy carried a pointless "verify all linting passes"
    # re-run until #121 removed it along with the --fix that made it meaningless.
    assert "--fix" not in _code(script)


@pytest.mark.parametrize(
    ("script", "index"),
    [(script, index) for script in sorted(GATES) for index in (0, 1)],
)
def test_the_gate_asks_the_formatters_to_report(script, index):
    # Anchored on the whole invocation, not on the bare flag. `"--check" in
    # "--check-only"` is True, so asserting the flag alone would let black run
    # in write mode as long as isort carried its own flag -- a substring
    # false-positive that passes while the defect stands. Caught by mutation,
    # not by reading.
    invocation = GATES[script][index]
    assert invocation in _code(script), f"{script}: {invocation}"


@pytest.mark.parametrize("script", sorted(GATES))
def test_the_gate_still_runs_the_unit_suite(script):
    # Control: passes before and after. Turning the formatters into reporters
    # must not quietly drop the half of the gate that catches real defects.
    text = _code(script)
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
