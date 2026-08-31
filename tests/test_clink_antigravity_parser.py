"""Tests for the Antigravity (agy) ConPTY text parser.

Written because a mutation survived: removing the no-answer tag from this parser
broke nothing in the suite. The agent-level test for the same behaviour builds
the metadata dict by hand, so it never exercised the parser that produces it —
and this is the client the fork already has a silently-wrong-model scar from.
"""

import pytest

from clink.parsers.antigravity import AntigravityTextParser
from clink.parsers.base import NO_ANSWER_METADATA_KEY, ParserError


def test_a_real_reply_is_returned_clean_and_carries_no_no_answer_tag():
    parser = AntigravityTextParser()

    parsed = parser.parse("\x1b[32mthe answer\x1b[0m\r\n", stderr="")

    assert parsed.content == "the answer"
    assert NO_ANSWER_METADATA_KEY not in parsed.metadata


def test_stderr_returned_as_content_is_tagged_as_no_answer():
    """agy exits 0 with empty stdout when it hits a permission wall.

    The parser reports stderr as the content, so the run arrives looking like a
    reply. The tag is the only thing that distinguishes it from a real one — and
    `finalize_output` is what turns the tag into a failure.
    """
    parser = AntigravityTextParser()

    parsed = parser.parse("", stderr="\x1b[31mtool call denied in headless mode\x1b[0m\r\n")

    assert parsed.content == "tool call denied in headless mode"
    assert parsed.metadata[NO_ANSWER_METADATA_KEY] is True


def test_no_output_at_all_is_a_parser_error():
    parser = AntigravityTextParser()

    with pytest.raises(ParserError):
        parser.parse("", stderr="")
