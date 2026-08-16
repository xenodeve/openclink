"""Compute a delegation plan from measured data rather than from judgement (#96).

**This is the skeleton (#99) and it computes nothing yet.** Registered, advertised,
dispatched by name, returns a constant that says so. The ranking arrives in #104,
the input contract in #101, the dataset in #102.

Built as a tracer bullet on purpose: the whole path is proven before anything
worth computing runs through it. A tool that passes its own unit tests has been
shown to work, not to be *reachable* — and this repository has the scar for that
distinction. `tools/clink.py` accepted an `images` parameter no runner ever
consumed, so calls returned exit 0 with a plausible answer while nothing reached
the CLI.

Follows `docs/adding_tools.md` rather than inventing: a `BaseTool` subclass with
`requires_model()` False, exported from `tools/__init__.py`, and an entry in
`server.py`'s `TOOLS`. `listmodels` is the closest existing shape — a tool that
answers from local computation instead of asking a model.
"""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent

from tools.models import ToolOutput
from tools.shared.base_models import ToolRequest
from tools.shared.base_tool import BaseTool

# Said in the payload, not only in this docstring. A placeholder that reads like
# a real answer is worse than an error: #96 exists because a delegation resting
# on something nobody measured is the failure, and a confident-looking plan from
# a tool that ranks nothing is exactly that failure wearing the fix's clothes.
_STUB_CONTENT = (
    "selectagents is not implemented yet.\n\n"
    "The tool is registered and reachable (#99), which is all this response proves. "
    "It does not rank models, read a dataset, or compute a plan — do not treat "
    "anything here as a delegation decision. The input contract lands in #101, the "
    "model dataset in #102, and the first real ranking in #104."
)


class SelectAgentsTool(BaseTool):
    """The selection layer's entry point."""

    def get_name(self) -> str:
        return "selectagents"

    def get_description(self) -> str:
        return (
            "Compute a delegation plan — whether to delegate, to how many agents, and on which "
            "model and effort each — from a measured model dataset rather than from recollection. "
            "Returns the planned agents, the criteria the choice rested on, ranked alternatives "
            "with their cost deltas, and an identity for the plan. NOT IMPLEMENTED YET (#99): "
            "currently returns a stub."
        )

    def get_input_schema(self) -> dict[str, Any]:
        # Deliberately empty of required fields. The real contract — fixed fields
        # plus a closed kind-of-work enumeration — is #101's deliverable, and
        # declaring a guessed version here would give callers a shape to write
        # against that #101 then has to break.
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }

    def get_system_prompt(self) -> str:
        """No model is asked anything; the plan is computed."""
        return ""

    def get_request_model(self):
        return ToolRequest

    def requires_model(self) -> bool:
        """False, and it is the point rather than an optimisation.

        A tool that reports True is routed through model resolution before
        dispatch. The selection layer exists so a delegation stops depending on
        an agent's judgement — resolving a model to decide which model to use
        would put the judgement back one level down.
        """
        return False

    async def prepare_prompt(self, request: ToolRequest) -> str:
        return ""

    def format_response(self, response: str, request: ToolRequest, model_info: dict | None = None) -> str:
        return response

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        output = ToolOutput(
            status="success",
            content=_STUB_CONTENT,
            content_type="text",
            metadata={"tool_name": self.name, "stub": True},
        )
        return [TextContent(type="text", text=output.model_dump_json())]
