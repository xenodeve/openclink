"""A formatting nit must not hide the test results (#79).

Found by running `/scrutinize` on #63 — the gate that turned the formatters from
rewriters into reporters. It fixed the silent-rewrite defect and introduced a
new one: the script runs under `set -e`, so the first non-zero check **aborts**,
and the formatting checks sit in Step 1 while the unit suite is Step 2.

Measured 2026-08-05: adding one badly-formatted file makes the script exit 1 at
the black check, and **the 1045-test suite never runs.** An agent that writes a
working fix with a misplaced space learns nothing about whether its code works.

That inverts the signal. Formatting is the cheapest, least informative check in
the file; the tests are the expensive, most informative one. Letting the first
block the second means the gate is most useless exactly when there is real work
to check.

The fix is not to reorder — a formatting failure still has to fail the gate.
It is to run everything and report everything, then exit non-zero if anything
failed.
"""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "code_quality_checks.sh"


def _script() -> str:
    assert SCRIPT.is_file(), f"{SCRIPT} is missing"
    return SCRIPT.read_text(encoding="utf-8")


def test_a_failing_check_does_not_abort_the_run():
    # `set -e` plus a bare check command is what makes the first failure the
    # last thing that runs. The script must collect outcomes instead.
    # Anchored on the newline-prefixed directive, not on `set -e\n`: the real
    # line is `set -e  # Exit on any error`, so the trailing comment made the
    # first version of this assertion pass while the directive was still there.
    # A substring false-positive, caught by reading the red rather than the code.
    text = _script()
    assert "\nset -e" not in text, "set -e aborts on the first failing check, hiding every later one"


def test_every_check_records_its_outcome_rather_than_exiting():
    text = _script()
    assert "record " in text, "there is no helper collecting per-check outcomes"
    assert "FAILED_CHECKS" in text, "nothing accumulates which checks failed"


def test_the_unit_suite_runs_even_when_formatting_fails():
    # The whole point: the expensive, informative check must not be gated behind
    # the cheap, uninformative one.
    # Anchored on the actual invocations, not on `text.find("$BLACK")` /
    # `find("pytest")`: both strings appear earlier in the tool-resolution block
    # and the dev-dependency loop, so the first version compared the wrong two
    # positions and produced an empty slice. Positional assertions need anchors
    # that occur once.
    text = _script()
    black_call = text.find("$BLACK . --check")
    pytest_call = text.find("-m pytest tests/")
    assert black_call > 0 and pytest_call > black_call, "black must be checked before the suite runs"
    assert (
        'record "Formatting (black)"' in text[black_call:pytest_call]
    ), "the black check must record its outcome rather than abort before pytest"


def test_the_gate_still_fails_when_something_failed():
    # Control on the other direction: reporting everything must not turn a red
    # gate green. A gate that always exits 0 is the silent-rewrite defect wearing
    # a different hat.
    # `assert "exit 1" in text` was the first version and it SURVIVED the
    # mutation that deleted the exit from the failure branch — the script also
    # exits 1 in the no-virtualenv guard, which satisfied the assertion while
    # the gate had gone green-on-failure. Anchored inside the branch instead.
    text = _script()
    branch = text.find("${#FAILED_CHECKS[@]} -gt 0")
    assert branch > 0, "the failure branch is gone"
    tail = text[branch:]
    assert "exit 1" in tail[: tail.find("\nfi")], "the failure branch must exit non-zero"


def test_the_gate_still_runs_all_four_checks():
    # Control: passes before and after. Collecting outcomes must not drop a check.
    text = _script()
    for tool in ("$RUFF", "$BLACK", "$ISORT", "pytest"):
        assert tool in text, tool
