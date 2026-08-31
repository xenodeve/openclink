"""The accounting block identifies the executable selected for a CLI call."""

from pathlib import Path

from clink.agents.codex import CodexAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole
from clink.parsers.base import ParsedCLIResponse
from tools.clink import CLinkTool


def _codex() -> CodexAgent:
    role = ResolvedCLIRole(
        name="default",
        prompt_path=Path("systemprompts/clink/default.txt").resolve(),
        role_args=[],
    )
    client = ResolvedCLIClient(
        name="codex",
        executable=["codex"],
        internal_args=["exec"],
        config_args=[],
        env={},
        timeout_seconds=30,
        parser="codex_jsonl",
        runner="codex",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return CodexAgent(client)


def _accounting(command: list[str], metadata: dict | None = None) -> dict:
    output = _codex().finalize_output(
        parsed=ParsedCLIResponse(content="OK", metadata=metadata or {}),
        sanitized_command=command,
        returncode=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
    )
    return CLinkTool()._call_accounting(output)


def test_accounting_reports_the_absolute_resolved_executable_path(tmp_path):
    resolved_path = str(tmp_path / "older" / "codex.EXE")

    accounting = _accounting([resolved_path, "-m", "gpt-5.6-luna"])

    assert accounting["resolved_executable"] == resolved_path
    assert Path(accounting["resolved_executable"]).is_absolute()


def test_different_executable_resolutions_produce_different_accounting_paths(tmp_path):
    older_path = str(tmp_path / "older" / "codex.EXE")
    newer_path = str(tmp_path / "newer" / "codex.EXE")

    older_accounting = _accounting([older_path, "-m", "gpt-5.6-luna"])
    newer_accounting = _accounting([newer_path, "-m", "gpt-5.6-luna"])

    assert older_accounting["resolved_executable"] == older_path
    assert newer_accounting["resolved_executable"] == newer_path
    assert older_accounting["resolved_executable"] != newer_accounting["resolved_executable"]


def test_unresolved_executable_is_omitted_from_accounting():
    accounting = _accounting(["codex-not-on-process-path", "-m", "gpt-5.6-luna"])

    assert "resolved_executable" not in accounting


def test_a_failed_run_reports_the_executable_too():
    """The case the issue is actually about, and the one the ACs did not name.

    The PATH divergence did not surface as a successful call - it surfaced as
    an HTTP 400 saying the MODEL required a newer Codex, from a stale binary.
    So the failure path is where this field earns its keep: a caller staring at
    a wrong-cause error needs to know which binary produced it.

    `_call_accounting` takes either outcome by design (#41), so the error has to
    carry the command under the same name or the projection silently reports
    nothing exactly when it matters most.
    """
    from clink.agents.base import CLIAgentError

    resolved = str(Path(__file__).parent.resolve() / "stale" / "codex.EXE")
    error = CLIAgentError(
        "CLI 'codex' exited with status 1",
        returncode=1,
        sanitized_command=[resolved, "-m", "gpt-5.6-luna"],
    )

    accounting = CLinkTool()._call_accounting(error)

    assert accounting["resolved_executable"] == resolved


def test_control_existing_normalized_usage_reporting_is_unchanged():
    usage = {
        "input_tokens": 100_000,
        "cached_input_tokens": 900_000,
        "output_tokens": 20_000,
        "reasoning_output_tokens": 10_000,
    }

    accounting = _accounting(["codex", "-m", "gpt-5.6-luna"], {"usage": usage})

    assert accounting["normalized_usage"] == usage
