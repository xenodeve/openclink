"""Gemini-specific CLI agent hooks."""

from __future__ import annotations

import json
from typing import Any

from clink.models import ResolvedCLIClient
from clink.parsers.base import ParsedCLIResponse

from .base import AgentOutput, BaseCLIAgent


class GeminiAgent(BaseCLIAgent):
    """Gemini-specific behaviour."""

    # The gemini parser files the token block under `token_usage`, never `usage`,
    # and spells every class differently from the normalised account. `total` and
    # `tool` are deliberately unmapped: neither has a counterpart, and `total` is
    # the dangerous one because it would look plausible in `input_tokens`.
    USAGE_METADATA_KEY = "token_usage"
    USAGE_FIELD_MAP = {
        "prompt": "input_tokens",
        "cached": "cached_input_tokens",
        "candidates": "output_tokens",
        "thoughts": "reasoning_output_tokens",
    }

    def __init__(self, client: ResolvedCLIClient):
        super().__init__(client)

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
        combined = "\n".join(part for part in (stderr, stdout) if part)
        if not combined:
            return None

        brace_index = combined.find("{")
        if brace_index == -1:
            return None

        json_candidate = combined[brace_index:]
        try:
            payload: dict[str, Any] = json.loads(json_candidate)
        except json.JSONDecodeError:
            return None

        error_block = payload.get("error")
        if not isinstance(error_block, dict):
            return None

        code = error_block.get("code")
        err_type = error_block.get("type")
        detail_message = error_block.get("message")

        prologue = combined[:brace_index].strip()
        lines: list[str] = []
        if prologue and (not detail_message or prologue not in detail_message):
            lines.append(prologue)
        if detail_message:
            lines.append(detail_message)

        header = "Gemini CLI reported a tool failure"
        if code:
            header = f"{header} ({code})"
        elif err_type:
            header = f"{header} ({err_type})"

        content_lines = [header.rstrip(".") + "."]
        content_lines.extend(lines)
        message = "\n".join(content_lines).strip()

        metadata = {
            "cli_error_recovered": True,
            "cli_error_code": code,
            "cli_error_type": err_type,
            "cli_error_payload": payload,
        }

        parsed = ParsedCLIResponse(content=message or header, metadata=metadata)
        return self.finalize_output(
            parsed=parsed,
            sanitized_command=sanitized_command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration_seconds,
            output_file_content=output_file_content,
        )
