"""The triage vocabulary must not instruct its own drift (#66).

`docs/agents/triage-labels.md` documented 19 label names while the repo carried
16 labels, none of the Type or Severity groups among them. The cause is not that
somebody forgot: the document *ends by telling the agent to skip the step and
say nothing*, which is the combination `xeno-skills#96` measured and PR #108
replaced with create-then-report.

So the thing under test is the **instruction**, not the label count. Creating the
labels while that sentence stands fixes today and guarantees the recurrence.

`gh label list` needs the network and is not asserted here; the reconciliation is
evidence for the PR. What is testable offline is the half that causes the drift.

Every check has a **negative** counterpart, per `xeno-skills#115`: a positive-only
test goes green on a document carrying the corrected sentence *and* the withdrawn
one beside it — the defect found twice on 2026-08-04 (`#44`, `xeno#100`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parent.parent / "docs" / "agents"
TRIAGE = DOCS / "triage-labels.md"
WORKFLOW = DOCS / "workflow.md"


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} is missing — this test asserts about its content, not its absence"
    return path.read_text(encoding="utf-8")


def test_the_vocabulary_doc_no_longer_tells_the_agent_to_proceed_silently():
    # The root cause, stated as a negative. "Lazily" plus "silently" compose into
    # never created and never mentioned.
    text = _read(TRIAGE).lower()
    assert "proceed silently if" not in text
    assert "it's guidance, not a gate" not in text


def test_the_vocabulary_doc_requires_the_reconciliation_to_be_reported():
    # The replacement has to demand the report, not merely drop the excuse —
    # otherwise the step is silent by omission instead of by instruction.
    text = _read(TRIAGE).lower()
    assert "already existed" in text
    assert "skipped" in text


@pytest.mark.parametrize(
    "twin,real",
    [
        # `Bug` and GitHub's default `bug` would differ only by case.
        ("`Bug`", "`bug`"),
        # `docs` and GitHub's default `documentation` are the same concept under
        # two names. Same decision, same reason: an existing default beats a twin.
        ("`docs`", "`documentation`"),
    ],
)
def test_the_type_group_names_the_label_that_actually_exists(twin, real):
    # Creating a near-duplicate is worse than fixing the doc: two labels for one
    # concept split the triage signal and neither is wrong enough to delete.
    text = _read(TRIAGE)
    assert twin not in text
    assert real in text


def test_the_workflow_note_no_longer_claims_this_repo_has_the_t4_labels():
    # A doc stating current behaviour is a change site. Both halves of this note
    # were false: this repo lacked the labels, and xeno-skills is no longer
    # unlabelled — its open issues carry ready-for-agent, t4, multi-agent,
    # hooks, security, ci, research, blocked, Major, Feature, bug.
    text = _read(WORKFLOW)
    assert "this repo has the T4 triage labels" not in text
    assert "so its issues are unlabelled" not in text


def test_every_documented_triage_role_is_still_listed():
    # Control: passes before and after. The fix must correct the instruction
    # without quietly shrinking the vocabulary it governs.
    text = _read(TRIAGE)
    for role in ("needs-triage", "needs-info", "ready-for-agent", "ready-for-human", "wontfix"):
        assert f"`{role}`" in text, role


@pytest.mark.parametrize("name", ["tech-debt", "critical", "Minor", "registry", "discovery", "providers", "server"])
def test_the_optional_groups_still_name_their_members(name):
    # Control: the Type / Component / Severity members must survive the edit.
    # Shrinking the doc to match a thin label set would "fix" the mismatch
    # backwards, and this issue is about the labels catching up to the doc.
    assert f"`{name}`" in _read(TRIAGE), name
