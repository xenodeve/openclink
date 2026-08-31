"""Tests for the Gemini CLI JSON parser."""

import pytest

from clink.agents.base import BaseCLIAgent, CLIAgentError
from clink.models import ResolvedCLIClient
from clink.parsers.base import NO_ANSWER_METADATA_KEY
from clink.parsers.gemini import GeminiJSONParser, ParserError


def _build_rate_limit_stdout() -> str:
    return (
        "{\n"
        '  "response": "",\n'
        '  "stats": {\n'
        '    "models": {\n'
        '      "gemini-2.5-pro": {\n'
        '        "api": {\n'
        '          "totalRequests": 5,\n'
        '          "totalErrors": 5,\n'
        '          "totalLatencyMs": 13319\n'
        "        },\n"
        '        "tokens": {"prompt": 0, "candidates": 0, "total": 0, "cached": 0, "thoughts": 0, "tool": 0}\n'
        "      }\n"
        "    },\n"
        '    "tools": {"totalCalls": 0},\n'
        '    "files": {"totalLinesAdded": 0, "totalLinesRemoved": 0}\n'
        "  }\n"
        "}"
    )


def test_gemini_parser_handles_rate_limit_empty_response():
    parser = GeminiJSONParser()
    stdout = _build_rate_limit_stdout()
    stderr = "Attempt 1 failed with status 429. Retrying with backoff... ApiError: quota exceeded"

    parsed = parser.parse(stdout, stderr)

    assert "429" in parsed.content
    assert parsed.metadata.get("rate_limit_status") == 429
    assert parsed.metadata.get(NO_ANSWER_METADATA_KEY) is True
    assert "Attempt 1 failed" in parsed.metadata.get("stderr", "")


def test_gemini_parser_still_errors_when_no_fallback_available():
    parser = GeminiJSONParser()
    stdout = '{"response": "", "stats": {}}'

    with pytest.raises(ParserError):
        parser.parse(stdout, stderr="")


def test_gemini_no_answer_is_failure_even_on_clean_exit():
    parser = GeminiJSONParser()
    stdout = _build_rate_limit_stdout()
    stderr = "Attempt 1 failed with status 429. Retrying with backoff... ApiError: quota exceeded"
    parsed = parser.parse(stdout, stderr)
    agent = BaseCLIAgent(
        ResolvedCLIClient(
            name="gemini",
            executable=["gemini"],
            working_dir=None,
            timeout_seconds=30,
            parser="gemini_json",
            roles={},
        )
    )

    with pytest.raises(CLIAgentError) as excinfo:
        agent.finalize_output(
            parsed=parsed,
            sanitized_command=["gemini"],
            returncode=0,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=0.1,
        )

    assert excinfo.value.parsed is not None
    assert excinfo.value.parsed.content == parsed.content
