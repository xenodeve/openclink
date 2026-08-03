"""Codex-specific CLI agent hooks."""

from __future__ import annotations

from clink.models import ResolvedCLIClient
from clink.parsers.base import ParserError

from .base import AgentOutput, BaseCLIAgent


class CodexAgent(BaseCLIAgent):
    """Codex CLI agent with JSONL recovery support."""

    MODEL_FLAGS = ("-m", "--model")
    # Effort is one `-c key=value` setting among possibly several, so the key —
    # not the flag alone — identifies it.
    EFFORT_FLAG = "-c"
    EFFORT_PREFIX = "model_reasoning_effort="

    # Codex reports these on `turn.completed`. Its wire names happen to match the
    # normalised ones, so this map is an identity — that is a fact about codex,
    # not a rule other adapters can assume.
    USAGE_FIELD_MAP = {
        "input_tokens": "input_tokens",
        "cached_input_tokens": "cached_input_tokens",
        "output_tokens": "output_tokens",
        "reasoning_output_tokens": "reasoning_output_tokens",
    }

    def __init__(self, client: ResolvedCLIClient):
        super().__init__(client)

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

        return self.finalize_output(
            parsed=parsed,
            sanitized_command=sanitized_command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration_seconds,
            output_file_content=output_file_content,
        )
