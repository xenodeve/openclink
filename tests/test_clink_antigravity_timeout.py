"""agy's own print-mode deadline must not be reported as a model problem (#49).

`agy --print-timeout` defaults to 5m0s — a client-side deadline sitting inside
clink's 1800s child timeout, which OpenClink does not model. Measured 2026-08-05
against the real binary, in the text mode OpenClink actually runs (the config passes no
`--output-format json`):

    EXIT=1   stdout=0 bytes   stderr='Error: timeout waiting for response'

and, because the runner drives agy through a ConPTY, both streams arrive merged
in the captured output. So OpenClink *has* the reason in hand.

It then discards it. Every non-zero exit is reported as
"(a requested model may be unsupported/rejected)", which for a timeout **names
the wrong cause** — the same failure shape as an error that blames a model for
what is really a stale binary on PATH. A wrong cause costs more than a vague one,
because it sends the reader somewhere.

Note what the deadline actually bounds: a 20s bound on a prompt that takes far
longer still SUCCEEDED, because the model began responding inside 20s. It is a
wait-for-first-response bound, not a bound on the whole call.
"""

from __future__ import annotations

import pytest

from clink.agents.antigravity import AntigravityAgent
from clink.agents.base import CLIAgentError
from clink.models import ResolvedCLIClient, ResolvedCLIRole

TIMEOUT_OUTPUT = "\r\nError: timeout waiting for response\r\n"


def _agent() -> tuple[AntigravityAgent, ResolvedCLIRole]:
    from pathlib import Path

    role = ResolvedCLIRole(name="default", prompt_path=Path("systemprompts/clink/default.txt").resolve(), role_args=[])
    client = ResolvedCLIClient(
        name="antigravity",
        executable=["agy"],
        internal_args=["--print"],
        config_args=[],
        env={},
        timeout_seconds=30,
        parser="antigravity_text",
        runner="antigravity",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return AntigravityAgent(client), role


async def _run_with_child(monkeypatch, returncode: int, output: str) -> CLIAgentError:
    agent, role = _agent()
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(AntigravityAgent, "_run_in_pty", lambda *_a, **_k: (returncode, output))

    with pytest.raises(CLIAgentError) as excinfo:
        await agent.run(role=role, prompt="hi", files=[], images=[], model="Gemini 3.1 Pro (High)")
    return excinfo.value


@pytest.mark.asyncio
async def test_a_print_timeout_is_reported_as_a_timeout_not_as_a_model_problem(monkeypatch):
    exc = await _run_with_child(monkeypatch, 1, TIMEOUT_OUTPUT)
    message = str(exc)

    # The cause agy itself gave, carried through rather than replaced by a guess.
    assert "timeout" in message.lower()
    # And the guess is gone: this failure has nothing to do with the model, and
    # saying it might sends the reader to the wrong place.
    assert "unsupported" not in message.lower()
    assert "rejected" not in message.lower()


@pytest.mark.asyncio
async def test_the_flag_that_caused_it_is_named_so_the_reader_can_act(monkeypatch):
    # Actionable, per #27's rule: a timeout the caller cannot locate is not much
    # better than a wrong cause. The deadline is agy's own and is settable.
    exc = await _run_with_child(monkeypatch, 1, TIMEOUT_OUTPUT)
    assert "--print-timeout" in str(exc)


@pytest.mark.asyncio
async def test_a_non_timeout_failure_still_reports_the_model_as_a_possible_cause(monkeypatch):
    # The existing message is correct for the failure it was written for — a
    # rejected model really does exit non-zero with a catalog error. Narrowing
    # the timeout case must not delete that.
    exc = await _run_with_child(monkeypatch, 1, "Error: model 'nope' is not in the catalog\r\n")
    message = str(exc).lower()
    assert "unsupported" in message or "rejected" in message
    assert "timeout" not in message
