"""A refused tuple must be refused *before* anything is spawned (#27).

The point of validating at all is that the process never starts. An exception
reaching the caller does not establish that: it is also what you get from a
process that started, ran, and failed. So these tests spy on the spawn itself
and assert it was never reached — the acceptance criterion asks for that
directly rather than inferred from a raise.
"""

import asyncio
import shutil
from pathlib import Path

import pytest

from clink.agents.base import CLIAgentError
from clink.agents.codex import CodexAgent
from clink.models import OutputCaptureConfig, ResolvedCLIClient, ResolvedCLIRole

CATALOG = {"gpt-5.6-sol": ["low", "medium", "high"], "composer-2.5": []}


def _agent(catalog, config_args=None, output_to_file=None):
    prompt_path = Path("systemprompts/clink/codex_default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
    client = ResolvedCLIClient(
        name="codex",
        executable=["codex"],
        internal_args=["exec"],
        config_args=["--json", *(config_args or [])],
        env={},
        timeout_seconds=30,
        parser="codex_jsonl",
        roles={"default": role},
        output_to_file=output_to_file,
        working_dir=None,
        model_catalog=catalog,
    )
    return CodexAgent(client), role


class SpawnSpy:
    """Records whether a subprocess was ever created."""

    def __init__(self):
        self.called = False

    async def __call__(self, *_args, **_kwargs):
        self.called = True
        raise AssertionError("a process was spawned for a request that should have been refused")


@pytest.fixture()
def spawn_spy(monkeypatch):
    spy = SpawnSpy()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    return spy


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model,effort",
    [
        pytest.param("no-such-model", "high", id="unknown-model"),
        pytest.param("gpt-5.6-sol", "max", id="tier-the-model-does-not-serve"),
        pytest.param("composer-2.5", "high", id="tier-on-a-model-with-no-tiers"),
    ],
)
async def test_an_unserviceable_tuple_never_reaches_a_process(spawn_spy, model, effort):
    agent, role = _agent(CATALOG)

    with pytest.raises(CLIAgentError) as excinfo:
        await agent.run(role=role, prompt="hi", files=[], images=[], model=model, reasoning_effort=effort)

    assert spawn_spy.called is False
    # The refusal has to be actionable: it names what was asked for and what the
    # client can serve, so an agent can correct the call without hunting a catalog.
    message = str(excinfo.value)
    assert model in message
    assert "codex" in message


@pytest.mark.asyncio
async def test_a_client_with_no_catalog_still_spawns(spawn_spy):
    """The opt-in property, asserted from the spawn side.

    A client that declared no catalog must reach the process exactly as before —
    otherwise adding validation would silently break every client that has not
    declared one yet.
    """
    agent, role = _agent(None)

    with pytest.raises(AssertionError, match="a process was spawned"):
        await agent.run(role=role, prompt="hi", files=[], images=[], model="anything-at-all")

    assert spawn_spy.called is True


@pytest.mark.asyncio
async def test_a_servable_tuple_still_spawns(spawn_spy):
    agent, role = _agent(CATALOG)

    with pytest.raises(AssertionError, match="a process was spawned"):
        await agent.run(role=role, prompt="hi", files=[], images=[], model="gpt-5.6-sol", reasoning_effort="high")

    assert spawn_spy.called is True


@pytest.mark.asyncio
async def test_codex_config_model_not_in_catalog_is_refused(spawn_spy):
    agent, role = _agent(CATALOG, ["-c", "model=unlisted-model"])

    with pytest.raises(CLIAgentError) as excinfo:
        await agent.run(role=role, prompt="hi", files=[], images=[])

    assert spawn_spy.called is False
    assert "unlisted-model" in str(excinfo.value)


@pytest.mark.asyncio
async def test_codex_two_token_model_wins_over_config_model(spawn_spy):
    # The measured Codex 0.144.4 probe showed -m overrides -c model= even when
    # the -c spelling appears later on the command line.
    agent, role = _agent(CATALOG, ["-m", "gpt-5.6-sol", "-c", "model=unlisted-model"])

    with pytest.raises(AssertionError, match="a process was spawned"):
        await agent.run(role=role, prompt="hi", files=[], images=[])

    assert spawn_spy.called is True


@pytest.mark.asyncio
async def test_codex_config_model_in_catalog_is_allowed(spawn_spy):
    agent, role = _agent(CATALOG, ["-c", "model=gpt-5.6-sol"])

    with pytest.raises(AssertionError, match="a process was spawned"):
        await agent.run(role=role, prompt="hi", files=[], images=[])

    assert spawn_spy.called is True


@pytest.mark.asyncio
async def test_codex_attached_short_model_is_refused(spawn_spy):
    model = "definitely-not-a-real-model-zk79"
    agent, role = _agent(CATALOG, [f"-m{model}"])

    with pytest.raises(CLIAgentError) as excinfo:
        await agent.run(role=role, prompt="hi", files=[], images=[])

    assert spawn_spy.called is False
    assert model in str(excinfo.value)


@pytest.mark.asyncio
async def test_codex_attached_long_model_is_refused(spawn_spy):
    model = "definitely-not-a-real-model-zk79"
    agent, role = _agent(CATALOG, [f"--model={model}"])

    with pytest.raises(CLIAgentError) as excinfo:
        await agent.run(role=role, prompt="hi", files=[], images=[])

    assert spawn_spy.called is False
    assert model in str(excinfo.value)


@pytest.mark.asyncio
async def test_codex_attached_short_config_model_is_refused(spawn_spy):
    model = "definitely-not-a-real-model-zk79"
    agent, role = _agent(CATALOG, [f"-cmodel={model}"])

    with pytest.raises(CLIAgentError) as excinfo:
        await agent.run(role=role, prompt="hi", files=[], images=[])

    assert spawn_spy.called is False
    assert model in str(excinfo.value)


@pytest.mark.asyncio
async def test_codex_two_token_long_config_model_is_refused(spawn_spy):
    model = "definitely-not-a-real-model-zk79"
    agent, role = _agent(CATALOG, ["--config", f"model={model}"])

    with pytest.raises(CLIAgentError) as excinfo:
        await agent.run(role=role, prompt="hi", files=[], images=[])

    assert spawn_spy.called is False
    assert model in str(excinfo.value)


@pytest.mark.asyncio
async def test_codex_attached_long_config_model_is_refused(spawn_spy):
    model = "definitely-not-a-real-model-zk79"
    agent, role = _agent(CATALOG, [f"--config=model={model}"])

    with pytest.raises(CLIAgentError) as excinfo:
        await agent.run(role=role, prompt="hi", files=[], images=[])

    assert spawn_spy.called is False
    assert model in str(excinfo.value)


def test_config_attached_to_long_flag_does_not_match_short_config_flag():
    from clink.agents.base import flag_values

    assert flag_values(["codex", "--config=model=X"], ("-c", "--config"), prefix="model=") == ["X"]
    assert flag_values(["codex", "--config=model=X"], ("-c",), prefix="model=") == []


@pytest.mark.parametrize(
    "config_args",
    [
        pytest.param(["--config", "model_reasoning_effort=high"], id="two-token-long-config"),
        pytest.param(["-cmodel_reasoning_effort=high"], id="attached-short-config"),
    ],
)
def test_codex_config_effort_spellings_resolve(config_args):
    agent, role = _agent(CATALOG, config_args)
    command = agent._build_command(role=role)

    assert agent._resolve_model_effort(command) == (None, "high")


def test_model_prefix_does_not_match_model_reasoning_effort():
    from clink.agents.base import flag_values

    assert flag_values(["codex", "-c", "model_reasoning_effort=high"], ("-c",), prefix="model=") == []


@pytest.mark.asyncio
async def test_model_injected_by_output_flag_template_is_refused(spawn_spy):
    model = "definitely-not-a-real-model-zk79"
    output_to_file = OutputCaptureConfig(flag_template=f"--model={model} {{path}}")
    agent, role = _agent(CATALOG, output_to_file=output_to_file)

    with pytest.raises(CLIAgentError) as excinfo:
        await agent.run(role=role, prompt="hi", files=[], images=[])

    assert spawn_spy.called is False
    assert model in str(excinfo.value)


def test_codex_config_model_and_effort_resolve_independently():
    agent, role = _agent(CATALOG, ["-c", "model=gpt-5.6-sol", "-c", "model_reasoning_effort=high"])
    command = agent._build_command(role=role)

    assert agent._resolve_model_effort(command) == ("gpt-5.6-sol", "high")
