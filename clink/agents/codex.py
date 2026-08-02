"""Codex-specific CLI agent hooks."""

from __future__ import annotations

from collections.abc import Sequence

from clink.models import ResolvedCLIClient
from clink.parsers.base import ParsedCLIResponse, ParserError

from .base import AgentOutput, BaseCLIAgent, TokenUsage, last_flag_value

# Codex reports each of these on the `turn.completed` event; the names already
# match the normalised account, so the adapter only has to select and type-check.
_USAGE_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")

_EFFORT_SETTING = "model_reasoning_effort="


class CodexAgent(BaseCLIAgent):
    """Codex CLI agent with JSONL recovery support."""

    def __init__(self, client: ResolvedCLIClient):
        super().__init__(client)

    def _extract_token_usage(self, parsed: ParsedCLIResponse) -> TokenUsage | None:
        usage = parsed.metadata.get("usage")
        if not isinstance(usage, dict):
            return None
        reported = {name: usage[name] for name in _USAGE_FIELDS if isinstance(usage.get(name), int)}
        return TokenUsage(**reported) if reported else None

    def _resolve_model_effort(self, command: Sequence[str]) -> tuple[str | None, str | None]:
        # Codex carries effort as one `-c key=value` setting among possibly several,
        # so match on the key rather than taking the last `-c` blindly.
        effort: str | None = None
        for index, token in enumerate(command[:-1]):
            value = command[index + 1]
            if token == "-c" and value.startswith(_EFFORT_SETTING):
                effort = value[len(_EFFORT_SETTING) :]
        return last_flag_value(command, "-m", "--model"), effort

    def _model_args(self, model: str | None, reasoning_effort: str | None) -> list[str]:
        # Codex takes the model and the reasoning effort as separate knobs:
        #   -m <model>   -c model_reasoning_effort=<low|medium|high|xhigh|max>
        args: list[str] = []
        if model:
            args += ["-m", model]
        if reasoning_effort:
            args += ["-c", f"model_reasoning_effort={reasoning_effort}"]
        return args

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

        resolved_model, resolved_effort = self._resolve_model_effort(sanitized_command)

        return AgentOutput(
            parsed=parsed,
            sanitized_command=sanitized_command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration_seconds,
            parser_name=self._parser.name,
            output_file_content=output_file_content,
            resolved_model=resolved_model,
            resolved_effort=resolved_effort,
            token_usage=self._extract_token_usage(parsed),
        )
