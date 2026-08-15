"""Parser for OpenCode CLI JSONL output."""

from __future__ import annotations

import json
from typing import Any

from .base import NO_ANSWER_METADATA_KEY, BaseParser, ParsedCLIResponse, ParserError


def _accumulate(into: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Add every numeric leaf of `new` into `into`, recursing through nested dicts.

    Recursive because the token block nests (`cache: {write, read}`), and a
    shallow merge would replace the cache sub-account rather than add to it.
    Booleans are excluded deliberately: `bool` is a subclass of `int` in Python,
    so a flag would otherwise be summed into a count.
    """
    for key, value in new.items():
        if isinstance(value, dict):
            existing = into.get(key)
            into[key] = _accumulate(existing if isinstance(existing, dict) else {}, value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            into[key] = into.get(key, 0) + value
    return into


class OpenCodeJSONLParser(BaseParser):
    """Parse stdout emitted by `opencode run --format json`.

    Shape recorded from opencode 1.18.15 (see tests/test_clink_opencode_parser.py):
    one JSON event per line, each with a `type` and a `part` payload. The reply is
    `part.text` on `type:"text"`; the account and the CLI's own price ride on
    `part.tokens` / `part.cost` of `type:"step_finish"`.

    Close to codex_jsonl but not the same shape, which is why this is its own
    parser rather than a reused one: codex nests the reply under `item`, keys usage
    at the event root, and reports no cost at all.
    """

    name = "opencode_jsonl"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
        events: list[dict[str, Any]] = []
        texts: list[str] = []
        errors: list[str] = []
        tokens: dict[str, Any] | None = None
        cost: float | None = None

        for line in lines:
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            events.append(event)
            event_type = event.get("type")
            part = event.get("part") or {}

            if event_type == "text":
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
            elif event_type == "step_finish":
                # An agentic run closes a step per tool round-trip, and each one
                # reports only its OWN spend. Keeping the last would report the
                # cheap closing step and discard the expensive one that did the
                # work — measured at 1,053 input tokens against 102,535 actually
                # spent, which reads as a plausible small number rather than as
                # an error. So accumulate; a single-step run sums a set of one.
                step_tokens = part.get("tokens")
                if isinstance(step_tokens, dict):
                    tokens = _accumulate(tokens if tokens is not None else {}, step_tokens)
                step_cost = part.get("cost")
                if isinstance(step_cost, (int, float)):
                    cost = (cost or 0.0) + float(step_cost)
            elif event_type == "error":
                message = ((event.get("error") or {}).get("data") or {}).get("message")
                if isinstance(message, str) and message.strip():
                    errors.append(message.strip())

        # An error-only run still carries something the caller needs, but it is a
        # diagnosis rather than a reply. Say which, or a clean exit that only
        # errored reads as a successful answer — the same rule codex_jsonl follows.
        answered = bool(texts)
        if not texts and errors:
            texts.extend(errors)

        if not texts:
            raise ParserError("OpenCode CLI JSONL output did not include a text part")

        metadata: dict[str, Any] = {"events": events}
        if not answered:
            metadata[NO_ANSWER_METADATA_KEY] = True
        if errors:
            metadata["errors"] = errors
        if tokens:
            metadata["tokens"] = tokens
        if cost is not None:
            metadata["cost"] = cost
        if stderr and stderr.strip():
            metadata["stderr"] = stderr.strip()

        return ParsedCLIResponse(content="\n\n".join(texts).strip(), metadata=metadata)
