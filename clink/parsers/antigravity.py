"""Parser for Antigravity (agy) ConPTY output.

`agy --print` is driven through a pseudo-console (see clink/agents/antigravity.py), so its
plain-text reply arrives wrapped in the terminal's ANSI escape codes and CR/LF line endings.
This parser strips those and returns the clean text as the response content.
"""

from __future__ import annotations

import re
from typing import Any

from .base import NO_ANSWER_METADATA_KEY, BaseParser, ParsedCLIResponse, ParserError

# CSI/SGR sequences (colours, cursor moves) + OSC sequences (e.g. hyperlinks) a TTY emits.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[\]P][^\x07\x1b]*(?:\x07|\x1b\\)?")


def _clean(text: str) -> str:
    text = _ANSI.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


class AntigravityTextParser(BaseParser):
    """Strip ANSI/CR noise from `agy`'s ConPTY output and return the plain reply."""

    name = "antigravity_text"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        content = _clean(stdout)
        metadata: dict[str, Any] = {}
        stderr_text = _clean(stderr) if stderr else ""
        if stderr_text:
            metadata["stderr"] = stderr_text

        if content:
            return ParsedCLIResponse(content=content, metadata=metadata)

        if stderr_text:
            metadata[NO_ANSWER_METADATA_KEY] = True
            return ParsedCLIResponse(content=stderr_text, metadata=metadata)

        raise ParserError("Antigravity CLI returned empty output")
