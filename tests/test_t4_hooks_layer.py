"""Pin the T4 hooks layer installed by #36 (PR #82).

The layer shipped with manual demonstrations (payloads fed by hand) and no
committed tests, so a future edit could silently break the gate and nothing
would notice. These tests pin the behavior at two seams:

  - the gate's *decision* logic (feed a PreToolUse payload, assert the
    deny/ask/silence verdict), isolated from the repo's real `.claude/t4.json`
    so no test ever runs the 38s verify suite; and
  - the committed *config* files (`.claude/t4.json`, `.claude/settings.json`,
    the hook file set), which is the part the shipping gate actually reads.

The gate is marker-guarded: it exits silently unless `.claude/t4.json` exists
in the *current working directory*. The decision tests therefore run the real
`t4-gate` script from a temp dir that carries a minimal marker, which is also
how the marker-guard itself is exercised (no marker -> silence).

Each verdict test is falsified by mutation: breaking the rule it pins flips
its assertion (see DONE.md 2026-08-05 — a test whose mutation no-ops is
evidence of nothing).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / ".claude" / "hooks"
SETTINGS = REPO / ".claude" / "settings.json"
MARKER = REPO / ".claude" / "t4.json"


def _git_bash() -> str | None:
    """Locate a real Git-bash, mirroring run-hook.cmd's preference order.

    The plain `bash` on Windows resolves to the WSL stub in System32, which
    lacks the gate's perl/grep toolchain — so we accept only the Git-for-Windows
    bash paths, exactly like the launcher the settings.json actually invokes.
    """
    for candidate in (
        Path(r"C:\Program Files\Git\bin\bash.exe"),
        Path(r"C:\Program Files (x86)\Git\bin\bash.exe"),
    ):
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("bash")
    if found and Path(found).resolve().is_file() and "git" in found.lower():
        return found
    return None


BASH = _git_bash()


def _payload(command: str) -> str:
    """A real PreToolUse payload, JSON-escaped as Claude Code would send it."""
    return json.dumps({"tool_name": "Bash", "command": command})


def _run_gate(command: str, marker_config: dict | None) -> str:
    """Run the real t4-gate against `command` from a temp dir.

    marker_config None -> no `.claude/t4.json` in cwd (marker-guard test).
    """
    import tempfile

    tmp = tempfile.mkdtemp(prefix="t4-gate-test-")
    try:
        if marker_config is not None:
            claude = Path(tmp) / ".claude"
            claude.mkdir(parents=True)
            (claude / "t4.json").write_text(json.dumps(marker_config), encoding="utf-8")
        result = subprocess.run(
            [BASH, str(HOOKS / "t4-gate")],
            input=_payload(command),
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.stdout.strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _verdict(output: str) -> str | None:
    """The permissionDecision from a gate verdict line, or None for silence."""
    if not output:
        return None
    try:
        return json.loads(output)["hookSpecificOutput"]["permissionDecision"]
    except (json.JSONDecodeError, KeyError):
        return None


# --- committed config -------------------------------------------------------


def test_marker_is_valid_json_with_an_armed_verify():
    # The shipping marker must exist and carry a non-empty verify: an empty
    # verify silently disarms the ship gate (t4-gate treats "" as "off").
    data = json.loads(MARKER.read_text(encoding="utf-8"))
    assert data.get("t4") is True
    assert isinstance(data.get("verify"), str) and data["verify"].strip()


def test_verify_targets_the_fast_unit_suite_not_the_full_gate():
    # The full code_quality_checks.sh is not the verify: it aborts on this
    # Windows box (.venv vs .openclink_venv), so wiring it would make every merge
    # fail. The verify must stay the fast unit suite.
    verify = json.loads(MARKER.read_text(encoding="utf-8"))["verify"]
    assert "pytest" in verify
    assert "not integration" in verify
    assert "code_quality_checks" not in verify


def test_settings_is_valid_json_and_registers_the_three_hooks():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    hooks = data["hooks"]
    assert hooks["SessionStart"], "no session-start hook"
    assert hooks["UserPromptSubmit"], "no prompt-reminder hook"
    assert hooks["PreToolUse"], "no PreToolUse gate hook"


def test_session_start_matcher_reinjects_after_compact():
    # startup|clear|compact — a compact must re-inject the map, so a permanent
    # per-session lock would silently kill it.
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    matchers = [e.get("matcher", "") for e in data["hooks"]["SessionStart"]]
    assert any("startup" in m and "compact" in m for m in matchers), matchers


def test_settings_preserves_the_permissions_block():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert "permissions" in data
    assert "allow" in data["permissions"] and "deny" in data["permissions"]


def test_the_four_hook_files_and_snapshot_exist():
    for name in ("t4-gate", "t4-session-start", "t4-prompt-reminder", "run-hook.cmd"):
        assert (HOOKS / name).is_file(), f"missing {name}"
    assert (HOOKS / "using-t4.snapshot.md").is_file()


def test_extensionless_hooks_are_pinned_lf_by_gitattributes():
    # core.autocrlf=true would check the extensionless bash hooks out with CRLF
    # and break them (`\r: command not found`). The pin must exist.
    attrs = (REPO / ".gitattributes").read_text(encoding="utf-8")
    assert ".claude/hooks/*" in attrs
    assert "eol=lf" in attrs


# --- gate decisions (behavioral) -------------------------------------------


def test_gate_denies_pr_create_without_issue_ref():
    out = _run_gate("gh pr create --title x", {"t4": True, "verify": ""})
    assert _verdict(out) == "deny"


def test_gate_allows_pr_create_with_issue_ref_in_body():
    out = _run_gate('gh pr create --title x --body "Closes #36"', {"t4": True, "verify": ""})
    assert _verdict(out) is None


def test_gate_allows_pr_create_with_issue_ref_via_body_file():
    import tempfile

    tmp = tempfile.mkdtemp(prefix="t4-gate-body-")
    try:
        body = Path(tmp) / "body.md"
        body.write_text("Closes #36\n", encoding="utf-8")
        # The gate runs in bash; a Windows `C:\...` backslash path can't be
        # stat-ed by `[ -f ]`. Use the forward-slash form the gate can resolve.
        cmd = f"gh pr create --title x --body-file {body.as_posix()}"
        out = _run_gate(cmd, {"t4": True, "verify": ""})
        assert _verdict(out) is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_gate_denies_dangerous_git():
    for command in (
        "git reset --hard HEAD",
        "git clean -f",
        "git push --force",
        "git branch -D feature/x",
    ):
        out = _run_gate(command, {"t4": True, "verify": ""})
        assert _verdict(out) == "deny", command


def test_gate_allows_reset_hard_under_afk():
    # afk:true is the revert-to-green escape for an unattended run; the gate
    # must not deadlock the tool that parks a failing item.
    out = _run_gate("git reset --hard HEAD", {"t4": True, "verify": "", "afk": True})
    assert _verdict(out) is None


def test_gate_asks_before_merge_and_runs_verify():
    # With verify wired to a passing command, merge reaches the review ask —
    # proof the ship gate ran verify rather than trusting a claim.
    out = _run_gate("gh pr merge 99", {"t4": True, "verify": "true"})
    assert _verdict(out) == "ask"


def test_gate_denies_merge_when_verify_fails():
    out = _run_gate("gh pr merge 99", {"t4": True, "verify": "false"})
    assert _verdict(out) == "deny"
    assert "verify failed" in out.lower() or "verify" in out.lower()


def test_gate_is_silent_without_the_marker():
    # Marker-guard: a copy leaking into a non-T4 checkout does nothing.
    assert _run_gate("gh pr create --title x", None) == ""


def test_gate_ignores_the_words_inside_a_commit_message():
    # Command-position anchoring: quoted words are not a command.
    out = _run_gate('git commit -m "prepare gh pr create later"', {"t4": True, "verify": ""})
    assert _verdict(out) is None


def test_session_start_injects_the_snapshot_when_plugin_root_absent():
    # Without CLAUDE_PLUGIN_ROOT the hook falls back to the committed snapshot
    # for full-content injection; the injected text must carry the map marker.
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        claude = Path(td) / ".claude"
        claude.mkdir(parents=True)
        (claude / "t4.json").write_text(json.dumps({"t4": True}), encoding="utf-8")
        # Copy the committed snapshot into the temp repo so the hook finds it
        # on the fallback path, independent of the machine's skills install.
        (claude / "hooks").mkdir()
        snapshot = (HOOKS / "using-t4.snapshot.md").read_bytes()
        (claude / "hooks" / "using-t4.snapshot.md").write_bytes(snapshot)
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = ""
        result = subprocess.run(
            [BASH, str(HOOKS / "t4-session-start")],
            input=_payload("echo hi"),
            cwd=td,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
    assert "hookEventName" in result.stdout
    assert "SessionStart" in result.stdout
    # A marker that exists only in the real snapshot, not in the fallback
    # directive (which also says "using-t4", so asserting that word would pass
    # with the snapshot fallback broken — found by mutation M12). Pure ASCII:
    # unicode dashes/arrows in the map are mojibake'd by cp1252 subprocess decode.
    assert "Re-route at every phase boundary" in result.stdout
