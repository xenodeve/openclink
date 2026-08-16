"""Per-call model + reasoning_effort override → CLI-specific flags.

Tests the pure command-building seam (`_build_command`): a clink call may pass
`model` / `reasoning_effort` and each agent maps them to its CLI's flags
(codex: `-m` + `-c model_reasoning_effort=`; antigravity: `--model` + `--effort`,
mutually exclusive; opencode: `--model` + `--variant`, independent; the rest:
`--model` only). Omitting them must leave the command untouched (backward
compatible).

Three of the five clients now need their own `_model_args`, and each was added
only after the effort was found to be going nowhere — codex (#27), antigravity
(#43), opencode (#125). The base's "effort is baked into the model name" default
is right for claude and gemini and wrong for everyone else, so a new client
should be assumed to need an override until its `--help` says otherwise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clink.agents.base import BaseCLIAgent
from clink.agents.codex import CodexAgent
from clink.agents.opencode import OpenCodeAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole


def _client(name: str, parser: str, runner: str | None = None) -> tuple[ResolvedCLIClient, ResolvedCLIRole]:
    prompt_path = Path("systemprompts/clink/default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
    client = ResolvedCLIClient(
        name=name,
        executable=[name],
        internal_args=[],
        config_args=[],
        env={},
        timeout_seconds=30,
        parser=parser,
        runner=runner,
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return client, role


def test_codex_maps_model_and_reasoning_effort():
    client, role = _client("codex", "codex_jsonl")
    agent = CodexAgent(client)
    cmd = agent._build_command(role=role, system_prompt=None, model="gpt-5.6-sol", reasoning_effort="high")
    assert cmd == ["codex", "-m", "gpt-5.6-sol", "-c", "model_reasoning_effort=high"]


def test_codex_model_only_without_effort():
    client, role = _client("codex", "codex_jsonl")
    agent = CodexAgent(client)
    cmd = agent._build_command(role=role, system_prompt=None, model="gpt-5.6-luna")
    assert cmd == ["codex", "-m", "gpt-5.6-luna"]


def test_codex_effort_only_without_model():
    client, role = _client("codex", "codex_jsonl")
    agent = CodexAgent(client)
    cmd = agent._build_command(role=role, system_prompt=None, reasoning_effort="max")
    assert cmd == ["codex", "-c", "model_reasoning_effort=max"]


def test_base_agent_uses_model_flag_and_ignores_effort():
    # claude/gemini take `--model`; effort is baked into the model name, so a base
    # agent ignores reasoning_effort. (antigravity no longer inherits this — it has
    # a real `--effort` flag and overrides `_model_args`; see below.)
    client, role = _client("gemini", "gemini_json")
    agent = BaseCLIAgent(client)
    cmd = agent._build_command(role=role, system_prompt=None, model="Gemini 3.5 Flash (High)", reasoning_effort="high")
    assert cmd == ["gemini", "--model", "Gemini 3.5 Flash (High)"]


def test_opencode_maps_reasoning_effort_to_variant():
    """`opencode run --variant <v>` is a real flag, and nothing was writing it (#125).

    Measured 2026-08-16 against the installed binary, `opencode run --help`:

        --variant   model variant (provider-specific reasoning effort,
                    e.g., high, max, minimal)   [string]

    `OpenCodeAgent` inherited the base `_model_args`, which discards the effort
    because claude and gemini bake the tier into the model name. For opencode that
    is false, so a caller's `reasoning_effort` reached the CLI as nothing at all.

    Third instance of this defect class in this fork — #27 closed it for codex,
    #43 for antigravity.
    """
    client, role = _client("opencode", "opencode_jsonl")
    agent = OpenCodeAgent(client)
    cmd = agent._build_command(
        role=role, system_prompt=None, model="opencode/deepseek-v4-flash", reasoning_effort="high"
    )
    assert cmd == ["opencode", "--model", "opencode/deepseek-v4-flash", "--variant", "high"]


def test_opencode_effort_only_without_model():
    """The knobs are independent here, unlike antigravity's.

    `agy` refuses `--model` and `--effort` together for every model it serves, so
    its agent has `refuse_unservable`. opencode's `--variant` is documented as
    provider-specific rather than mutually exclusive, so effort alone must build.

    **Measured 2026-08-16 against the real binary, and the results are not all
    comfortable.** Recorded here because the next reader will otherwise assume
    this fix was verified end to end:

    1. Valid variant names are per model and enumerable —
       `opencode models opencode --verbose` publishes a `variants` object;
       `deepseek-v4-flash` has `low` / `high` / `max`, each mapping to a
       `reasoningEffort`, and `claude-opus-5` has five tiers under `effort`.
    2. **An invalid variant is accepted and silently ignored.**
       `--variant definitely-not-a-real-variant` exited 0 and answered normally.
       So the CLI will not reject a typo on OpenClink's behalf, and nothing here
       validates against the per-model list — that would cost a ~30s
       `opencode models` call on every clink call.
    3. **No observable effect could be demonstrated on the one model the quota
       constraint permits.** Same prompt on `deepseek-v4-flash-free`, three runs:
       no variant -> `reasoning=0 output=75`; `--variant low` -> `0 / 59`;
       `--variant max` -> `0 / 49`. An earlier single `low` run reported
       `reasoning=67`, which the repeats did not reproduce — that was variance,
       not signal.

    So what this fix establishes is that OpenClink *writes* the flag and can read
    it back. Whether the provider acts on it is **unverified for deepseek**, and
    saying otherwise would repeat the antigravity `--model` mistake this
    repository already has a scar from. It is still strictly better than the
    previous behaviour, which was to discard the caller's value in silence.
    """
    client, role = _client("opencode", "opencode_jsonl")
    agent = OpenCodeAgent(client)
    assert agent._build_command(role=role, system_prompt=None, reasoning_effort="minimal") == [
        "opencode",
        "--variant",
        "minimal",
    ]


def test_opencode_declares_the_variant_flag_so_the_effort_can_be_read_back():
    """Writing the flag without declaring it is the silent half of this bug.

    `_resolve_model_effort` reads the effort back OFF the built command, and that
    value is what `tools/clink.py` reports as `resolved_effort`. Declare the flag
    in `EFFORT_FLAGS` or the CLI honours the variant while the caller is told
    `resolved_effort: None` — indistinguishable from it having been dropped, which
    is the very thing being fixed. #27 closed exactly this hole for codex.

    Asserted through `_resolve_model_effort` rather than by reading the constant,
    so it fails on the behaviour rather than on the spelling.
    """
    client, role = _client("opencode", "opencode_jsonl")
    agent = OpenCodeAgent(client)
    cmd = agent._build_command(
        role=role, system_prompt=None, model="opencode/deepseek-v4-flash", reasoning_effort="max"
    )

    model, effort = agent._resolve_model_effort(cmd)

    assert model == "opencode/deepseek-v4-flash"
    assert effort == "max", (
        "the variant was written to the command but cannot be read back, so the "
        "caller is told resolved_effort=None while the CLI honours it (#125)"
    )


def test_no_overrides_leaves_command_unchanged():
    client, role = _client("codex", "codex_jsonl")
    agent = CodexAgent(client)
    assert agent._build_command(role=role, system_prompt=None) == ["codex"]


def test_antigravity_places_model_before_print():
    # agy's `--print` is VALUE-TAKING (it consumes the next token as the prompt), so
    # `--model` MUST precede `--print` or agy swallows it as the prompt and silently
    # falls back to the persisted default model. AntigravityAgent reorders so model
    # options come before `--print` (verified live: wrong order -> Gemini default,
    # right order -> the requested model reaches the backend).
    from clink.agents.antigravity import AntigravityAgent

    prompt_path = Path("systemprompts/clink/default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
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
    agent = AntigravityAgent(client)
    cmd = agent._build_command(role=role, system_prompt=None, model="Claude Sonnet 4.6 (Thinking)")
    assert cmd == ["agy", "--model", "Claude Sonnet 4.6 (Thinking)", "--print"]
    assert cmd.index("--model") < cmd.index("--print")


def _antigravity_agent():
    from clink.agents.antigravity import AntigravityAgent

    prompt_path = Path("systemprompts/clink/default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
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


def test_antigravity_maps_reasoning_effort_to_its_own_flag():
    # `agy --effort low|medium|high` is a real flag, and with no `--model` it is
    # accepted and honoured (measured 2026-08-04 against the real binary:
    # `agy --effort low --output-format json --print "Reply OK."` -> status SUCCESS).
    # Before this, AntigravityAgent inherited the base `_model_args`, which drops
    # reasoning_effort silently.
    agent, role = _antigravity_agent()
    cmd = agent._build_command(role=role, system_prompt=None, model=None, reasoning_effort="low")
    assert cmd == ["agy", "--effort", "low", "--print"]


def test_antigravity_effort_reads_back_from_the_built_command():
    # Emitting the flag is half the contract: `_resolve_model_effort` reads the
    # effort back OFF the command so `resolved_effort` can be reported to the
    # caller. Without EFFORT_FLAGS declared, that read-back returns None while the
    # CLI honours the flag — the same silent hole #27 closed for codex, and
    # invisible unless pinned here.
    agent, role = _antigravity_agent()
    cmd = agent._build_command(role=role, system_prompt=None, model=None, reasoning_effort="medium")
    assert agent._resolve_model_effort(cmd) == (None, "medium")


def test_antigravity_refuses_model_and_effort_together():
    # Measured 2026-08-04 against the real `agy`: the two knobs are mutually
    # exclusive for EVERY model the CLI serves, and it fails closed itself —
    #   --model "Gemini 3.1 Pro (High)" --effort low
    #     -> "--effort is not supported for model ..."
    #   --model gemini-3.1-pro-high     --effort low
    #     -> "--model gemini-3.1-pro-high conflicts with --effort=low"
    #   --model claude-sonnet-4-6       --effort low
    #     -> "--effort is not supported for model ..."
    # Every id in `agy models` either bakes its tier in or has no ladder at all,
    # so there is no tuple where both are servable. Refuse before spawn (#27's
    # rule) rather than building a command that is guaranteed to error.
    from clink.agents.base import CLIAgentError

    agent, role = _antigravity_agent()
    # Deliberately NOT the id the refusal message uses as its example — with
    # 'gemini-3.1-pro-high' both here and in the boilerplate, the model assertion
    # passes by matching the example rather than the value under test. Caught by
    # mutation: stripping {model!r} from the message left this test green.
    cmd = agent._build_command(
        role=role,
        system_prompt=None,
        model="gemini-3.5-flash-low",
        reasoning_effort="medium",
    )
    with pytest.raises(CLIAgentError) as excinfo:
        agent.refuse_unservable(cmd)
    message = str(excinfo.value)
    # Actionable: it has to name both values, or the caller cannot tell which to drop.
    assert "gemini-3.5-flash-low" in message
    assert "medium" in message
