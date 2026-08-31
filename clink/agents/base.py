"""Execute configured CLI agents for the clink tool and parse output."""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from clink.agents.process_tree import ProcessGroup, spawn_kwargs
from clink.constants import DEFAULT_STREAM_LIMIT
from clink.models import ResolvedCLIClient, ResolvedCLIRole
from clink.parsers import BaseParser, ParsedCLIResponse, ParserError, get_parser

logger = logging.getLogger("clink.agent")


@dataclass
class AgentOutput:
    """Container returned by CLI agents after successful execution."""

    parsed: ParsedCLIResponse
    sanitized_command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    parser_name: str
    output_file_content: str | None = None


class CLIAgentError(RuntimeError):
    """Raised when a CLI agent fails (non-zero exit, timeout, parse errors)."""

    def __init__(self, message: str, *, returncode: int | None = None, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class BaseCLIAgent:
    """Execute a configured CLI command and parse its output."""

    def __init__(self, client: ResolvedCLIClient):
        self.client = client
        self._parser: BaseParser = get_parser(client.parser)
        self._logger = logging.getLogger(f"clink.runner.{client.name}")

    async def run(
        self,
        *,
        role: ResolvedCLIRole,
        prompt: str,
        system_prompt: str | None = None,
        files: Sequence[str],
        images: Sequence[str],
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> AgentOutput:
        # Files and images are already embedded into the prompt by the tool; they are
        # accepted here only to keep parity with SimpleTool callers.
        _ = (files, images)
        # The runner simply executes the configured CLI command for the selected role.
        command = self._build_command(
            role=role,
            system_prompt=system_prompt,
            model=model,
            reasoning_effort=reasoning_effort,
        )
        env = self._build_environment()

        # Resolve executable path for cross-platform compatibility (especially Windows)
        executable_name = command[0]
        resolved_executable = shutil.which(executable_name)
        if resolved_executable is None:
            raise CLIAgentError(
                f"Executable '{executable_name}' not found in PATH for CLI '{self.client.name}'. "
                f"Ensure the command is installed and accessible."
            )
        command[0] = resolved_executable

        sanitized_command = list(command)

        cwd = str(self.client.working_dir) if self.client.working_dir else None
        limit = DEFAULT_STREAM_LIMIT

        stdout_text = ""
        stderr_text = ""
        output_file_content: str | None = None
        start_time = time.monotonic()

        output_file_path: Path | None = None
        command_with_output_flag = list(command)

        if self.client.output_to_file:
            fd, tmp_path = tempfile.mkstemp(prefix="clink-", suffix=".json")
            os.close(fd)
            output_file_path = Path(tmp_path)
            flag_template = self.client.output_to_file.flag_template
            try:
                rendered_flag = flag_template.format(path=str(output_file_path))
            except KeyError as exc:  # pragma: no cover - defensive
                raise CLIAgentError(f"Invalid output flag template '{flag_template}': missing placeholder {exc}")
            command_with_output_flag.extend(shlex.split(rendered_flag))
            sanitized_command = list(command_with_output_flag)

        self._logger.debug("Executing CLI command: %s", " ".join(sanitized_command))
        if cwd:
            self._logger.debug("Working directory: %s", cwd)

        try:
            process = await asyncio.create_subprocess_exec(
                *command_with_output_flag,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                limit=limit,
                env=env,
                **spawn_kwargs(),
            )
        except FileNotFoundError as exc:
            raise CLIAgentError(f"Executable not found for CLI '{self.client.name}': {exc}") from exc

        # Own the whole tree the subagent spawns, not just this one PID, so
        # cancellation can terminate every descendant (issue #144).
        group = ProcessGroup(process.pid)
        try:
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(prompt.encode("utf-8")),
                    timeout=self.client.timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                # Confirmed by the OS before we proceed -- do not return early.
                await group.terminate()
                await self._reap(process)
                raise CLIAgentError(
                    f"CLI '{self.client.name}' timed out after {self.client.timeout_seconds} seconds",
                    returncode=None,
                ) from exc
            except asyncio.CancelledError:
                await group.terminate()
                await self._reap(process)
                raise

            duration = time.monotonic() - start_time
            return_code = process.returncode
            stdout_text = stdout_bytes.decode("utf-8", errors="replace")
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")

            if output_file_path and output_file_path.exists():
                output_file_content = output_file_path.read_text(encoding="utf-8", errors="replace")
                if self.client.output_to_file and self.client.output_to_file.cleanup:
                    try:
                        output_file_path.unlink()
                    except OSError:  # pragma: no cover - best effort cleanup
                        pass

                if output_file_content and not stdout_text.strip():
                    stdout_text = output_file_content

            if return_code != 0:
                recovered = self._recover_from_error(
                    returncode=return_code,
                    stdout=stdout_text,
                    stderr=stderr_text,
                    sanitized_command=sanitized_command,
                    duration_seconds=duration,
                    output_file_content=output_file_content,
                )
                if recovered is not None:
                    return recovered

            if return_code != 0:
                raise CLIAgentError(
                    f"CLI '{self.client.name}' exited with status {return_code}",
                    returncode=return_code,
                    stdout=stdout_text,
                    stderr=stderr_text,
                )

            try:
                parsed = self._parser.parse(stdout_text, stderr_text)
            except ParserError as exc:
                raise CLIAgentError(
                    f"Failed to parse output from CLI '{self.client.name}': {exc}",
                    returncode=return_code,
                    stdout=stdout_text,
                    stderr=stderr_text,
                ) from exc

            return AgentOutput(
                parsed=parsed,
                sanitized_command=sanitized_command,
                returncode=return_code,
                stdout=stdout_text,
                stderr=stderr_text,
                duration_seconds=duration,
                parser_name=self._parser.name,
                output_file_content=output_file_content,
            )
        finally:
            # Cleanup runs on every exit path -- success, failure, cancellation
            # and server shutdown (#20 story 32). On Windows this also kills
            # any straggler still in the Job Object as a safety net.
            group.close()

    @staticmethod
    async def _reap(process) -> None:
        """Let asyncio's child watcher observe the OS-confirmed exit so the
        transport is cleaned up properly after an out-of-band group kill."""
        wait = getattr(process, "wait", None)
        if wait is None:
            return
        try:
            await wait()
        except Exception:  # pragma: no cover - best effort
            pass

    def _build_command(
        self,
        *,
        role: ResolvedCLIRole,
        system_prompt: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> list[str]:
        base = list(self.client.executable)
        base.extend(self.client.internal_args)
        base.extend(self.client.config_args)
        base.extend(role.role_args)
        # Per-call overrides go LAST so they win over any model set in config.
        base.extend(self._model_args(model, reasoning_effort))

        return base

    def _model_args(self, model: str | None, reasoning_effort: str | None) -> list[str]:
        """Map a per-call model/effort override to this CLI's flags.

        Base default: `--model <model>` (claude/gemini/antigravity). Reasoning effort
        is baked into the model name for those CLIs, so it is ignored here — Codex,
        which takes a separate effort knob, overrides this.
        """
        _ = reasoning_effort
        return ["--model", model] if model else []

    def _build_environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self.client.env)
        return env

    # ------------------------------------------------------------------
    # Error recovery hooks
    # ------------------------------------------------------------------

    def _recover_from_error(
        self,
        *,
        returncode: int,
        stdout: str,
        stderr: str,
        sanitized_command: list[str],
        duration_seconds: float,
        output_file_content: str | None,
    ) -> AgentOutput | None:
        """Hook for subclasses to convert CLI errors into successful outputs.

        Return an AgentOutput to treat the failure as success, or None to signal
        that normal error handling should proceed.
        """

        return None
