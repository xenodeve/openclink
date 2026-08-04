"""Agent factory for clink CLI integrations."""

from __future__ import annotations

from clink.models import ResolvedCLIClient

from .antigravity import AntigravityAgent
from .base import AgentOutput, BaseCLIAgent, CLIAgentError, TokenUsage
from .claude import ClaudeAgent
from .codex import CodexAgent
from .cursor import CursorAgent
from .gemini import GeminiAgent

_AGENTS: dict[str, type[BaseCLIAgent]] = {
    "gemini": GeminiAgent,
    "codex": CodexAgent,
    "claude": ClaudeAgent,
    "antigravity": AntigravityAgent,
    "cursor": CursorAgent,
}


def create_agent(client: ResolvedCLIClient) -> BaseCLIAgent:
    agent_key = (client.runner or client.name).lower()
    agent_cls = _AGENTS.get(agent_key, BaseCLIAgent)
    return agent_cls(client)


__all__ = [
    "AgentOutput",
    "BaseCLIAgent",
    "CLIAgentError",
    "TokenUsage",
    "create_agent",
]
