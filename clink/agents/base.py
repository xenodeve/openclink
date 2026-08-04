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

from clink.constants import DEFAULT_STREAM_LIMIT
from clink.models import ResolvedCLIClient, ResolvedCLIRole
from clink.parsers import BaseParser, ParsedCLIResponse, ParserError, get_parser
from clink.parsers.base import NO_ANSWER_METADATA_KEY
from clink.validation import validate_model_request

logger = logging.getLogger("clink.agent")


@dataclass
class TokenUsage:
    """Normalised token account for a single CLI call.

    A field the CLI did not report stays None: an unreported field is not the
    same as a reported zero, and only the former may be filled in later.
    """

    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None


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
    requested_model: str | None = None
    resolved_model: str | None = None
    observed_model: str | None = None
    resolved_effort: str | None = None
    token_usage: TokenUsage | None = None
    # Filled in by the rate-card slice; absent until then.
    cost: float | None = None


# The error path does not run through the tool's output limiter, so whatever is
# captured for a failed call reaches the caller whole. A long run is exactly the
# one that times out, so the transcript is bounded at the point of capture.
MAX_DRAINED_OUTPUT_CHARS = 10_000


def flag_values(command: Sequence[str], flags: Sequence[str], *, prefix: str | None = None) -> list[str]:
    """Return values read for `flags`, in command order.

    A CLI accepts several spellings of one setting, and reading back only one
    of them is how a validated command turns into a spawn of something else.
    This handles `flag value`, `flag=value`, and short attached values such as
    `-fvalue`. With `prefix`, only values carrying the prefix match and the
    prefix is stripped â€” that is the `-c key=value` shape, where the flag alone
    does not identify the setting.
    """
    flag_set = set(flags)
    values: list[str] = []
    for index, token in enumerate(command):
        value: str | None = None
        if token in flag_set and index + 1 < len(command):
            value = command[index + 1]
        else:
            for flag in flags:
                if token.startswith(f"{flag}=") and flag.startswith("--"):
                    value = token[len(flag) + 1 :]
                    break
                if (
                    len(flag) == 2
                    and flag.startswith("-")
                    and not flag.startswith("--")
                    and token.startswith(flag)
                    and token != flag
                ):
                    value = token[len(flag) :]
                    break
        if value is None:
            continue
        if prefix is not None:
            if not value.startswith(prefix):
                continue
            value = value[len(prefix) :]
        values.append(value)
    return values


def _tail(raw: bytes | None) -> str:
    """Decode the last of a drained stream — where the run was when it stopped."""
    if not raw:
        return ""
    return raw[-MAX_DRAINED_OUTPUT_CHARS:].decode("utf-8", errors="replace")


class CLIAgentError(RuntimeError):
    """Raised when a CLI agent fails (non-zero exit, timeout, parse errors)."""

    def __init__(
        self,
        message: str,
        *,
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
        parsed: ParsedCLIResponse | None = None,
        token_usage: TokenUsage | None = None,
        requested_model: str | None = None,
        resolved_model: str | None = None,
        observed_model: str | None = None,
        resolved_effort: str | None = None,
        cost: float | None = None,
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        # Whatever the failed run still managed to say. Reporting the outcome
        # honestly must not cost the caller its diagnosis.
        self.parsed = parsed
        # A run that failed still spent the tokens it spent. Making the outcome
        # honest must not make the call unaccountable.
        self.token_usage = token_usage
        # The same argument, one field over: a failed run still ran *some* model,
        # and a wrong-model run is a plausible reason for it to have failed at all
        # — so the accounting is most valuable exactly where it used to be absent
        # (#41). These names deliberately match `AgentOutput`'s, so the tool can
        # project the accounting block from either with one function instead of
        # two that drift.
        self.requested_model = requested_model
        self.resolved_model = resolved_model
        self.observed_model = observed_model
        self.resolved_effort = resolved_effort
        self.cost = cost


class BaseCLIAgent:
    """Execute a configured CLI command and parse its output."""

    # How this CLI spells the model and effort knobs. Declared once so the code
    # that *writes* them (`_model_args`) and the code that *reads them back*
    # (`_resolve_model_effort`) cannot drift apart — this fork already has a scar
    # from a CLI silently ignoring a correctly-constructed `--model`.
    MODEL_FLAGS: tuple[str, ...] = ("--model",)
    # Flags whose value is a `key=value` config setting; the model is the one keyed below.
    MODEL_CONFIG_FLAGS: tuple[str, ...] = ()
    MODEL_CONFIG_PREFIX: str = "model="
    EFFORT_FLAGS: tuple[str, ...] = ()
    EFFORT_PREFIX: str | None = None

    # Which metadata key this CLI publishes its usage payload under. Per-client
    # because the parsers already differ: codex and claude write `usage`, gemini
    # writes `token_usage`. A field map describes the fields *inside* the payload
    # and so cannot reach one filed under a different name.
    USAGE_METADATA_KEY: str = "usage"

    # CLI usage key -> normalised TokenUsage field. Empty means this client has no
    # adapter yet, so it reports no usage rather than a wrong one.
    USAGE_FIELD_MAP: dict[str, str] = {}

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
        self.refuse_unservable(command)
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

        self.refuse_unservable(command_with_output_flag)
        try:
            process = await asyncio.create_subprocess_exec(
                *command_with_output_flag,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                limit=limit,
                env=env,
            )
        except FileNotFoundError as exc:
            raise CLIAgentError(f"Executable not found for CLI '{self.client.name}': {exc}") from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(prompt.encode("utf-8")),
                timeout=self.client.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            # Keep the partial transcript: it is the only record of what the run
            # got through before the deadline.
            drained_stdout, drained_stderr = await process.communicate()
            raise CLIAgentError(
                f"CLI '{self.client.name}' timed out after {self.client.timeout_seconds} seconds",
                returncode=None,
                stdout=_tail(drained_stdout),
                stderr=_tail(drained_stderr),
            ) from exc

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

        return self.finalize_output(
            parsed=parsed,
            sanitized_command=sanitized_command,
            returncode=return_code,
            stdout=stdout_text,
            stderr=stderr_text,
            duration_seconds=duration,
            output_file_content=output_file_content,
            requested_model=model,
        )

    def finalize_output(
        self,
        *,
        parsed: ParsedCLIResponse,
        sanitized_command: list[str],
        returncode: int,
        stdout: str,
        stderr: str,
        duration_seconds: float,
        output_file_content: str | None = None,
        requested_model: str | None = None,
    ) -> AgentOutput:
        """Build the result, or raise if the run did not actually succeed.

        Every construction site goes through here — including the error-recovery
        hooks and the runners that override `run` — so this is the one place the
        outcome is decided, and no path can return a result the run did not earn.

        Two rules, both stated rather than inferred from whether output parsed:

        - A child that exited non-zero **failed**. Parseable output is a
          diagnosis, not a success; recovery salvages the content and it travels
          on the error instead of relabelling the run.
        - A run that produced **no answer** failed even on a clean exit. The
          parsers flag this with the shared `NO_ANSWER_METADATA_KEY`, declared
          here because two parsers independently restating one vocabulary was
          the defect. They fall back to reporting stderr as content, which is
          how an empty run acquires non-empty text.
        """
        resolved_model, resolved_effort = self._resolve_model_effort(sanitized_command)
        token_usage = self._extract_token_usage(parsed)

        failure: str | None = None
        if returncode != 0:
            failure = f"CLI '{self.client.name}' exited with status {returncode}"
        elif parsed.metadata.get(NO_ANSWER_METADATA_KEY):
            failure = (
                f"CLI '{self.client.name}' exited cleanly without producing an answer; "
                "the content below is its diagnostic output, not a reply"
            )

        if failure is not None:
            raise CLIAgentError(
                failure,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                parsed=parsed,
                token_usage=token_usage,
                requested_model=requested_model,
                resolved_model=resolved_model,
                observed_model=parsed.metadata.get("model_used"),
                resolved_effort=resolved_effort,
            )

        return AgentOutput(
            parsed=parsed,
            sanitized_command=sanitized_command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration_seconds,
            parser_name=self._parser.name,
            output_file_content=output_file_content,
            requested_model=requested_model,
            resolved_model=resolved_model,
            observed_model=parsed.metadata.get("model_used"),
            resolved_effort=resolved_effort,
            token_usage=token_usage,
        )

    def refuse_unservable(self, command: Sequence[str]) -> None:
        """Raise if this client cannot serve the tuple the command asks for.

        Called before anything is spawned — earlier even than resolving the
        executable, because refusing a model the client cannot serve should not
        depend on whether the CLI happens to be installed.

        This reads the command, so it can only refuse a model the command names. A CLI that also takes a
        model from its own config file or a profile can still spawn one the catalog excludes, with nothing
        on the argv to see. The check is a guard over what PAL builds, not a guarantee about what the CLI
        ultimately runs.

        Every runner has to call this, including one that overrides `run`.
        `_build_command` would have been the tidier single choke point, but
        `AntigravityAgent` overrides that too, so putting it there would silently
        exempt exactly the client this fork already has a wrong-model scar from.
        """
        if not self.client.model_catalog:
            return
        model, effort = self._resolve_model_effort(command)
        refusal = validate_model_request(
            client_name=self.client.name,
            model=model,
            effort=effort,
            catalog=self.client.model_catalog,
        )
        if refusal is not None:
            raise CLIAgentError(refusal, returncode=None)

    def _extract_token_usage(self, parsed: ParsedCLIResponse) -> TokenUsage | None:
        """Map this CLI's raw usage report onto the normalised account.

        Two per-client declarations, because they answer different questions:
        `USAGE_METADATA_KEY` is *where* the payload is, `USAGE_FIELD_MAP` is what
        the fields inside it are called. The map is empty in the base — a client
        whose adapter is not written yet reports no usage rather than a wrong one.
        """
        if not self.USAGE_FIELD_MAP:
            return None
        usage = parsed.metadata.get(self.USAGE_METADATA_KEY)
        if not isinstance(usage, dict):
            return None
        reported = {field: usage[key] for key, field in self.USAGE_FIELD_MAP.items() if isinstance(usage.get(key), int)}
        return TokenUsage(**reported) if reported else None

    def _resolve_model_effort(self, command: Sequence[str]) -> tuple[str | None, str | None]:
        """What the built command asks for, once per-call overrides, config args
        and role args have been merged.

        Read back from the command rather than from the request, because a model
        can arrive via `config_args` or `role_args` that never pass through
        `_model_args`. This is the *resolved* request, not proof the backend
        complied — that is the observed value, which most CLIs do not report.
        """
        model_values = flag_values(command, self.MODEL_FLAGS)
        model = model_values[-1] if model_values else None
        if model is None:
            config_model_values = flag_values(
                command,
                self.MODEL_CONFIG_FLAGS,
                prefix=self.MODEL_CONFIG_PREFIX,
            )
            model = config_model_values[-1] if config_model_values else None

        effort_values = flag_values(command, self.EFFORT_FLAGS, prefix=self.EFFORT_PREFIX)
        effort = effort_values[-1] if effort_values else None
        return model, effort

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
