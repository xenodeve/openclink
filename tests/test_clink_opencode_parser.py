"""Behaviour of the OpenCode JSONL parser.

Every fixture below is REAL output, recorded 2026-08-11 from
`opencode.exe 1.18.15` on this machine, not a shape invented from the docs.
The success fixture is the verbatim three-line reply to

    opencode run --format json -m opencode-go/deepseek-v4-flash \
      "Reply with exactly the word PONG and nothing else."

and the error fixture is the verbatim reply from the same binary against the
out-of-credit `opencode/*` (Zen) provider. Issue #85 records both, and its
acceptance criteria require the parser to be pinned by recorded output —
because a parser tested against a guessed shape passes while disagreeing with
the CLI, which is the failure this file exists to prevent.
"""

import pytest

from clink.parsers.base import NO_ANSWER_METADATA_KEY, ParserError
from clink.parsers.opencode import OpenCodeJSONLParser

# Recorded verbatim; session/message ids shortened, nothing else altered.
RECORDED_SUCCESS = """
{"type":"step_start","timestamp":1786438373380,"sessionID":"ses_00ffa44f","part":{"id":"prt_ff006500","messageID":"msg_ff005c2f","sessionID":"ses_00ffa44f","type":"step-start"}}
{"type":"text","timestamp":1786438377682,"sessionID":"ses_00ffa44f","part":{"id":"prt_ff00660c","messageID":"msg_ff005c2f","sessionID":"ses_00ffa44f","type":"text","text":"PONG","time":{"start":1786438377674,"end":1786438377680}}}
{"type":"step_finish","timestamp":1786438377789,"sessionID":"ses_00ffa44f","part":{"id":"prt_ff006613","reason":"stop","messageID":"msg_ff005c2f","sessionID":"ses_00ffa44f","type":"step-finish","tokens":{"total":121705,"input":121702,"output":3,"reasoning":0,"cache":{"write":0,"read":0}},"cost":0.00851956}}
"""

RECORDED_ERROR = (
    '{"type":"error","timestamp":1786438130396,"sessionID":"ses_00ffdf70",'
    '"error":{"name":"APIError","data":{"message":"Insufficient balance. Manage your billing here: '
    'https://opencode.ai/workspace/wrk_01KZ/billing","statusCode":401,"isRetryable":false}}}'
)


def test_the_reply_is_the_text_part_not_the_whole_transcript():
    """`part.text` on the `type:"text"` line is the answer.

    The other two lines carry no reply at all, so a parser that concatenated
    events would return telemetry as if it were the model's response.
    """
    parsed = OpenCodeJSONLParser().parse(stdout=RECORDED_SUCCESS, stderr="")
    assert parsed.content == "PONG"


def test_step_finish_tokens_are_published_for_the_usage_adapter():
    """The token account rides on `step_finish`, keyed `tokens`.

    `BaseCLIAgent` reads usage out of parser metadata by a per-client key, so a
    parser that dropped this leaves the client reporting no usage at all while
    the CLI was reporting it all along.
    """
    parsed = OpenCodeJSONLParser().parse(stdout=RECORDED_SUCCESS, stderr="")
    assert parsed.metadata["tokens"] == {
        "total": 121705,
        "input": 121702,
        "output": 3,
        "reasoning": 0,
        "cache": {"write": 0, "read": 0},
    }


def test_the_cli_prices_its_own_call_and_the_number_survives():
    """OpenCode reports `cost` per call, so OpenClink needs no rate card for it.

    Issue #77 is open precisely because OpenClink's pricing layer is unreachable
    without one. Dropping this field would discard the only client that
    sidesteps that problem.
    """
    parsed = OpenCodeJSONLParser().parse(stdout=RECORDED_SUCCESS, stderr="")
    assert parsed.metadata["cli_cost"] == pytest.approx(0.00851956)


def test_the_cost_is_published_with_its_unit_or_the_tool_will_not_report_it():
    """The unit is a precondition, not decoration — so it needs its own assertion.

    `tools/clink.py` emits `cli_reported_cost` only when BOTH keys are present,
    because a bare figure invites summing credits with currency (#25). Every test
    of that projection hand-feeds the metadata, so without this one, deleting the
    `cli_cost_unit` line here would revert #126 end to end with a green suite —
    the parser would keep reporting a cost and the tool would silently stop
    projecting it.

    That gap was real and a review found it, not this file.
    """
    parsed = OpenCodeJSONLParser().parse(stdout=RECORDED_SUCCESS, stderr="")
    assert parsed.metadata["cli_cost_unit"] == "USD"


def test_the_cost_is_not_published_under_the_rate_card_key():
    """`cost` belongs to `price_call`'s output, and this is not that.

    The tool merges parser metadata and then the accounting block into one dict.
    `accounting["cost"]` is a dict; this is a float. Publishing under the same
    name is harmless only until a client gets a rate card, at which point the
    later update wins and two different claims have quietly changed places.
    """
    parsed = OpenCodeJSONLParser().parse(stdout=RECORDED_SUCCESS, stderr="")
    assert "cost" not in parsed.metadata


# Recorded verbatim 2026-08-11 from a REAL agentic call through OpenClink's own path —
# `agent.run(...)` against opencode 1.18.15, asking it to read a file with its own
# tool. The tool call makes the run take two steps, and each step closes with its
# own `step_finish`.
#
# This fixture exists because the single-step one above cannot fail the way real
# work does: every delegation that touches a file, a test or a build is
# multi-step, so a parser that keeps only the last account under-reports every
# call that matters. Measured here: 1,053 reported against 102,535 actually spent.
RECORDED_MULTISTEP = """
{"type":"step_start","sessionID":"ses_multi","part":{"type":"step-start"}}
{"type":"tool_use","sessionID":"ses_multi","part":{"type":"tool","tool":"read"}}
{"type":"step_finish","sessionID":"ses_multi","part":{"type":"step-finish","reason":"tool_use","tokens":{"total":122935,"input":101482,"output":61,"reasoning":16,"cache":{"write":0,"read":21376}},"cost":0.0071444464}}
{"type":"step_start","sessionID":"ses_multi","part":{"type":"step-start"}}
{"type":"text","sessionID":"ses_multi","part":{"type":"text","text":"\\"\\"\\"Parser for OpenCode CLI JSONL output.\\"\\"\\""}}
{"type":"step_finish","sessionID":"ses_multi","part":{"type":"step-finish","reason":"stop","tokens":{"total":123947,"input":1053,"output":14,"reasoning":0,"cache":{"write":0,"read":122880}},"cost":0.000247702}}
"""


def test_tokens_are_summed_across_every_step_not_taken_from_the_last():
    """A multi-step run spends tokens per step; the account is the sum.

    Keeping the last `step_finish` reports the cheap closing step and discards
    the expensive one that did the work — here 1,053 input instead of 102,535,
    a 99% under-report that looks like a plausible small number.
    """
    parsed = OpenCodeJSONLParser().parse(stdout=RECORDED_MULTISTEP, stderr="")
    assert parsed.metadata["tokens"]["input"] == 101482 + 1053
    assert parsed.metadata["tokens"]["output"] == 61 + 14
    assert parsed.metadata["tokens"]["reasoning"] == 16 + 0
    assert parsed.metadata["tokens"]["cache"]["read"] == 21376 + 122880


def test_cost_is_summed_across_every_step():
    """Same argument, and the field OpenClink cannot currently derive itself.

    The last step cost 0.000248 of a call that cost 0.007392 — reporting it
    alone under-states the call by 96.6%.
    """
    parsed = OpenCodeJSONLParser().parse(stdout=RECORDED_MULTISTEP, stderr="")
    assert parsed.metadata["cli_cost"] == pytest.approx(0.0071444464 + 0.000247702)


def test_the_reply_is_still_only_the_text_part_on_a_multi_step_run():
    # The tool_use step carries no reply; only the text part does.
    parsed = OpenCodeJSONLParser().parse(stdout=RECORDED_MULTISTEP, stderr="")
    assert parsed.content == '"""Parser for OpenCode CLI JSONL output."""'


def test_an_error_only_run_is_content_but_is_not_an_answer():
    """A 401 is worth returning, and must not read as a successful reply.

    Same rule the codex parser follows: keep the diagnosis, flag that no answer
    was produced, or a clean exit that only errored looks like a reply.
    """
    parsed = OpenCodeJSONLParser().parse(stdout=RECORDED_ERROR, stderr="")
    assert "Insufficient balance" in parsed.content
    assert parsed.metadata[NO_ANSWER_METADATA_KEY] is True


def test_output_with_no_text_part_and_no_error_is_a_parse_failure():
    """Silence is not an empty answer.

    Returning `content=""` would hand the caller a successful-looking empty
    reply; the caller cannot tell that apart from a model that said nothing.
    """
    with pytest.raises(ParserError):
        OpenCodeJSONLParser().parse(stdout='{"type":"step_start","part":{}}', stderr="")
