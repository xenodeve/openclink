"""Tests for the Codex CLI JSONL parser.

Added because the no-answer rule was applied to two of the four parsers. Codex
has the same diagnostic-as-content fallback the other two do — it promotes error
events to the answer when the run produced no `agent_message` — and nothing said
so, which is what makes such a run look like a success.
"""

import json

import pytest

from clink.parsers.base import NO_ANSWER_METADATA_KEY, ParserError
from clink.parsers.codex import CodexJSONLParser


def _events(*events: dict) -> str:
    return "\n".join(json.dumps(event) for event in events)


def test_an_answer_is_not_tagged_as_no_answer():
    parser = CodexJSONLParser()
    stdout = _events(
        {"type": "item.completed", "item": {"type": "agent_message", "text": "42"}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}},
    )

    parsed = parser.parse(stdout, stderr="")

    assert parsed.content == "42"
    assert NO_ANSWER_METADATA_KEY not in parsed.metadata


def test_content_built_only_from_error_events_is_tagged_as_no_answer():
    """Codex really does emit these — e.g. `Model metadata for ... not found`.

    When no agent_message arrived, the parser falls back to the error text so a
    caller can still diagnose the run. That text is a diagnosis, not a reply, and
    the tag is the only thing that says so.
    """
    parser = CodexJSONLParser()
    stdout = _events(
        {"type": "error", "message": "Model metadata for `zk79` not found."},
        {"type": "error", "message": "Exceeded skills context budget of 2%."},
    )

    parsed = parser.parse(stdout, stderr="")

    assert parsed.metadata[NO_ANSWER_METADATA_KEY] is True
    assert "zk79" in parsed.content
    assert parsed.metadata["errors"] == [
        "Model metadata for `zk79` not found.",
        "Exceeded skills context budget of 2%.",
    ]


def test_an_answer_alongside_errors_is_still_an_answer():
    """A run can emit a diagnostic and still answer. Only the errors-only case is no-answer."""
    parser = CodexJSONLParser()
    stdout = _events(
        {"type": "error", "message": "Exceeded skills context budget of 2%."},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "OK"}},
    )

    parsed = parser.parse(stdout, stderr="")

    assert parsed.content == "OK"
    assert NO_ANSWER_METADATA_KEY not in parsed.metadata
    assert parsed.metadata["errors"] == ["Exceeded skills context budget of 2%."]


def test_no_events_at_all_is_a_parser_error():
    parser = CodexJSONLParser()

    with pytest.raises(ParserError):
        parser.parse("", stderr="")
