"""Claude-specific CLI agent hooks."""

from __future__ import annotations

from clink.models import ResolvedCLIRole
from clink.parsers.base import ParserError

from .base import AgentOutput, BaseCLIAgent


class ClaudeAgent(BaseCLIAgent):
    """Claude CLI agent with system-prompt injection support."""

    # claude publishes usage twice: a flat `usage` block and a per-model
    # `modelUsage` breakdown. This reads the flat one — it needs no summation
    # across models, and re-deriving a total the CLI already computed is a way
    # for the two to disagree. Recorded 2026-08-05 from a real
    # `--output-format json` run: on a single-model call the two agree exactly.
    #
    # `cache_creation_input_tokens` is deliberately unmapped. It is billed, and
    # in that recorded run it was 24477 against 2 input tokens — but the
    # normalised account has no field for it, and `cached_input_tokens` means
    # cache *reads* for every other client. Folding it in would make the account
    # wrong rather than incomplete.
    USAGE_FIELD_MAP = {
        "input_tokens": "input_tokens",
        "cache_read_input_tokens": "cached_input_tokens",
        "output_tokens": "output_tokens",
    }

    def _build_command(
        self,
        *,
        role: ResolvedCLIRole,
        system_prompt: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> list[str]:
        command = list(self.client.executable)
        command.extend(self.client.internal_args)
        command.extend(self.client.config_args)

        if system_prompt and "--append-system-prompt" not in self.client.config_args:
            command.extend(["--append-system-prompt", system_prompt])

        command.extend(role.role_args)
        # Per-call model override (claude CLI takes `--model`); last wins over config.
        command.extend(self._model_args(model, reasoning_effort))
        return command

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
        try:
            parsed = self._parser.parse(stdout, stderr)
        except ParserError:
            return None

        return self.finalize_output(
            parsed=parsed,
            sanitized_command=sanitized_command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration_seconds,
            output_file_content=output_file_content,
        )
