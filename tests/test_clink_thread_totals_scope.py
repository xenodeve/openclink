"""What the cumulative figures cover, and what happens when recording fails (#77).

Three findings from `/scrutinize` on the merged #21 cost line, all traced rather
than inferred:

2. `cumulative_usage` reads as "this thread" but covers only the turns carrying
   a clink account. Cross-tool continuation is a documented first-class feature
   (`utils/conversation_memory.py:30`), so a thread with 5 `chat` turns and 2
   `clink` turns reported a total over two turns under a name that implies
   fifteen. It was correct only by accident of key naming.
3. `_record_assistant_turn` and the totals update shared one `try/except` logged
   at `debug`, so a recording failure removed the feature silently AND left the
   next call totalling a thread quietly missing a turn.
4. The override passed `model_info["provider"]` straight through, narrowing the
   base's contract, which normalises a provider *object*.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from clink.agents.codex import CodexAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole
from clink.parsers.base import ParsedCLIResponse
from tools.clink import CLinkTool


def _request(thread_id: str) -> SimpleNamespace:
    return SimpleNamespace(absolute_file_paths=[], images=[], prompt="x", continuation_id=thread_id)


def _account() -> dict:
    role = ResolvedCLIRole(name="default", prompt_path=Path("systemprompts/clink/default.txt").resolve(), role_args=[])
    client = ResolvedCLIClient(
        name="codex",
        executable=["codex"],
        internal_args=[],
        config_args=[],
        env={},
        timeout_seconds=30,
        parser="codex_jsonl",
        runner="codex",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    output = CodexAgent(client).finalize_output(
        parsed=ParsedCLIResponse(content="OK", metadata={"usage": {"input_tokens": 100, "output_tokens": 20}}),
        sanitized_command=["codex"],
        returncode=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
    )
    return CLinkTool()._call_accounting(output)


def test_the_totals_say_how_many_turns_they_cover():
    """Finding 2. The count is what makes the figure self-describing.

    A caller can compare it against the thread's own length and see that the
    total is partial. Without it, "cumulative" is a claim about the thread that
    the number does not support.
    """
    from utils.conversation_memory import add_turn, create_thread

    thread_id = create_thread("clink", {"prompt": "x"})
    # Two turns from another tool, carrying no clink account — the cross-tool case.
    add_turn(thread_id, "assistant", "chat reply", tool_name="chat", model_metadata={"usage": {"x": 1}})
    add_turn(thread_id, "assistant", "chat reply 2", tool_name="chat")
    CLinkTool()._record_assistant_turn(
        thread_id, "OK", _request(thread_id), {"provider": "codex", "model_name": "m", "accounting": _account()}
    )

    totals = CLinkTool()._thread_totals(thread_id)

    assert totals["cumulative_usage"] == {"input_tokens": 100, "output_tokens": 20}
    assert totals["cumulative_turns"] == 1, "the total covers one clink turn out of three on the thread"


def test_a_recording_failure_does_not_silently_remove_the_totals(monkeypatch, caplog):
    """Finding 3. Two operations, two outcomes — and the failure is visible.

    Sharing one `except` meant a storage error deleted the feature from the
    response with a `debug`-level trace nobody sees at default level.
    """
    import logging

    import tools.clink as tc

    def _boom(*_a, **_k):
        raise RuntimeError("storage down")

    monkeypatch.setattr(CLinkTool, "_record_assistant_turn", _boom)
    with caplog.at_level(logging.WARNING, logger=tc.logger.name):
        result = CLinkTool()._record_turn_and_total("t-does-not-exist", "OK", _request("t"), {})

    assert result == {}, "no totals are invented when the turn could not be stored"
    assert any(
        "storage down" in r.message or "record" in r.message.lower() for r in caplog.records
    ), "a recording failure must be visible at WARNING, not buried at debug"


def test_the_provider_contract_matches_the_base():
    """Finding 4. The base normalises a provider object; the override must too."""

    class FakeProvider:
        def get_provider_type(self):
            return SimpleNamespace(value="codex-object")

    from utils.conversation_memory import create_thread, get_thread

    thread_id = create_thread("clink", {"prompt": "x"})
    CLinkTool()._record_assistant_turn(
        thread_id,
        "OK",
        _request(thread_id),
        {"provider": FakeProvider(), "model_name": "m", "accounting": _account()},
    )

    assert get_thread(thread_id).turns[-1].model_provider == "codex-object"


def test_a_string_provider_still_passes_through_unchanged():
    """Control: passes before and after. The normal path must not regress."""
    from utils.conversation_memory import create_thread, get_thread

    thread_id = create_thread("clink", {"prompt": "x"})
    CLinkTool()._record_assistant_turn(
        thread_id, "OK", _request(thread_id), {"provider": "codex", "model_name": "m", "accounting": _account()}
    )

    assert get_thread(thread_id).turns[-1].model_provider == "codex"
