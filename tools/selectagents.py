"""Compute a delegation plan from measured data rather than from judgement (#96).

**It validates its input (#101) and computes nothing yet (#99).** Registered,
advertised, dispatched by name; a complete scope is accepted and echoed back, and
anything else is refused. The dataset arrives in #102, the first real ranking in
#104.

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
from pydantic import ConfigDict, Field, ValidationError, field_validator

from tools.models import ToolOutput
from tools.shared.base_models import ToolRequest
from tools.shared.base_tool import BaseTool

# The closed list, and closing it is the substance of #101. A caller able to
# invent a category moves the mapping from work to capability axis out of tested
# code and into an agent's head, which is what #96 exists to stop.
#
# Grounded rather than invented: these are the shapes `clink-subagents` already
# names as delegable leaves — "a well-specified function/module, a mechanical
# refactor across a known site, a bulk format/transform, a first-draft you'll
# review, focused external-doc research/summarization" — plus the two judgment
# shapes that skill routes elsewhere, because a caller will ask for them and the
# tool must be able to say what it is looking at.
#
# Each member exists because it loads a DIFFERENT axis. Two entries that would
# rank identically are one entry with two names, and the list gets longer without
# the answer getting better.
KIND_OF_WORK: tuple[str, ...] = (
    "implementation",  # write new code against a specification
    "refactor",  # change existing code without changing its behaviour
    "bulk_transform",  # mechanical, repetitive edits across known sites
    "research",  # gather and summarise information from outside the repo
    "review",  # judge work that already exists
    "analysis",  # reason about a system without editing it
)

# How the caller will know the result is right. Closed for the same reason and a
# second one: it is what decides whether a cheap seat is enough. Work checked by
# a test suite tolerates a weaker model than work nobody will check.
VERIFICATION: tuple[str, ...] = (
    "automated_tests",  # a suite decides, and the agent can run it
    "diff_review",  # a human or a stronger agent reads the change
    "spot_check",  # sampled, not exhaustive
    "unverifiable",  # nothing will confirm it — say so rather than imply a check
)


_SCOPE_FIELDS: tuple[str, ...] = (
    "kind_of_work",
    "item_count",
    "read_volume_tokens",
    "already_in_context",
    "output_ceiling_tokens",
    "verification",
    "description",
)


def _refusal(error: ValidationError) -> ToolOutput:
    """Turn a validation failure into something a caller can act on.

    A closed list that refuses without saying what was allowed is an obstacle
    rather than a contract, so the allowed values must appear here. They do — via
    the field validators, whose own message is "must be one of: ...".

    An earlier version restated those lists a second time in this function.
    Mutation testing removed that block and **nothing went red**, which is what
    redundant code looks like from the outside: the coverage came entirely from
    the validators. Deleted rather than kept as belt-and-braces, because two
    places spelling one list is how they stop agreeing.

    The field name is always included: a caller that omitted one field needs to
    know which, and reading that out of a nested Pydantic error location is work
    the tool should do once rather than every caller doing it badly.
    """
    lines = ["selectagents refused the request. Nothing was computed.", ""]
    for detail in error.errors():
        field = ".".join(str(part) for part in detail["loc"]) or "(request)"
        lines.append(f"- {field}: {detail['msg']}")
    return ToolOutput(
        status="error",
        content="\n".join(lines),
        content_type="text",
        metadata={"tool_name": "selectagents", "stub": True},
    )


class SelectAgentsRequest(ToolRequest):
    """The declared scope. Every field required; nothing defaulted.

    A default here is a decision made silently. An omitted `item_count` falling
    back to 1 turns a fan-out into a single agent, and nothing in the response
    would say the caller never asked for that.
    """

    # `extra="forbid"`, so the model agrees with the schema's
    # `additionalProperties: false`. Without it an unknown key was accepted and
    # discarded — measured — which is the same defect as declaring an `enum` and
    # typing the field `str`: a published constraint nobody enforces.
    #
    # It bites hardest on fields that do not exist YET. `budget` arrives in #109;
    # a caller sending it today would be told the request succeeded and would
    # believe it had bounded a run that is not bounded.
    model_config = ConfigDict(extra="forbid")

    kind_of_work: str = Field(..., description=f"One of: {', '.join(KIND_OF_WORK)}.")
    item_count: int = Field(..., ge=1, description="How many separate items the scope contains.")
    read_volume_tokens: int = Field(..., ge=0, description="Tokens that must be read to do the work.")
    already_in_context: bool = Field(..., description="Whether that volume is already in the caller's context.")
    output_ceiling_tokens: int = Field(..., ge=1, description="Most tokens the result may occupy.")
    verification: str = Field(..., description=f"One of: {', '.join(VERIFICATION)}.")
    description: str = Field(
        ...,
        min_length=1,
        description=(
            "The work in your own words. Used ONLY to map it onto a capability axis — "
            "never as an input to the ranking arithmetic."
        ),
    )

    # Validated against the same tuples the schema publishes. The first version
    # typed these as plain `str` and declared the `enum` only in the JSON schema:
    # the advertisement said closed and the edge accepted anything, so a caller
    # that ignored the schema — or a client that does not validate — got a
    # nonsense category straight through. A published constraint nobody enforces
    # is worse than none, because it reads as enforcement.
    @field_validator("kind_of_work")
    @classmethod
    def _known_kind_of_work(cls, value: str) -> str:
        if value not in KIND_OF_WORK:
            raise ValueError(f"must be one of: {', '.join(KIND_OF_WORK)}")
        return value

    @field_validator("verification")
    @classmethod
    def _known_verification(cls, value: str) -> str:
        if value not in VERIFICATION:
            raise ValueError(f"must be one of: {', '.join(VERIFICATION)}")
        return value

    @field_validator("description")
    @classmethod
    def _description_says_something(cls, value: str) -> str:
        # `min_length=1` counts characters, and whitespace is characters — `"   "`
        # was accepted, measured. This field is the ONLY input to the
        # capability-axis mapping, so a blank one leaves that mapping with nothing
        # while the record shows a description was supplied: missing data that
        # does not look missing.
        if not value.strip():
            raise ValueError("must describe the work; whitespace is not a description")
        return value


# Said in the payload, not only in this docstring. A placeholder that reads like
# a real answer is worse than an error: #96 exists because a delegation resting
# on something nobody measured is the failure, and a confident-looking plan from
# a tool that ranks nothing is exactly that failure wearing the fix's clothes.
_STUB_CONTENT = (
    "selectagents is not implemented yet.\n\n"
    "Your scope was accepted and is echoed in the metadata, which is all this "
    "response proves (#99, #101). It does not rank models, read a dataset, or "
    "compute a plan — do not treat anything here as a delegation decision. The "
    "model dataset lands in #102 and the first real ranking in #104."
)


class SelectAgentsTool(BaseTool):
    """The selection layer's entry point."""

    def get_name(self) -> str:
        return "selectagents"

    def get_description(self) -> str:
        # The warning goes FIRST. This string is what a client model reads when it
        # decides which tool to call, and a capability claim followed by a caveat
        # is read as a capability -- which would have an agent delegate on the
        # strength of a plan that does not exist. That is the exact failure #96
        # was written to remove.
        return (
            "NOT IMPLEMENTED YET (#99) — returns a stub, computes nothing, do not act on its output. "
            "When built, it will compute a delegation plan — whether to delegate, to how many agents, "
            "and on which model and effort each — from a measured model dataset rather than from "
            "recollection, returning the planned agents, the criteria the choice rested on, ranked "
            "alternatives with their cost deltas, and an identity for the plan."
        )

    def get_annotations(self) -> dict[str, Any] | None:
        """Read-only, declared the way the other model-less tools declare it.

        `listmodels` and `version` both publish `readOnlyHint`. Omitting it here
        would advertise a tool that returns a constant as one a client must
        assume can mutate something.
        """
        return {"readOnlyHint": True}

    def get_input_schema(self) -> dict[str, Any]:
        # Deliberately empty of required fields. The real contract — fixed fields
        # plus a closed kind-of-work enumeration — is #101's deliverable, and
        # declaring a guessed version here would give callers a shape to write
        # against that #101 then has to break.
        # The enumerations are published as `enum`, not described in prose. A
        # client validates against the schema; a sentence saying "one of: ..." is
        # read by nobody but a human, and a closed list only closes anything if
        # the machine can see it.
        return {
            "type": "object",
            "properties": {
                "kind_of_work": {
                    "type": "string",
                    "enum": list(KIND_OF_WORK),
                    "description": "What kind of work this is. Decides which capability axis is ranked on.",
                },
                "item_count": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "How many separate items the scope contains.",
                },
                "read_volume_tokens": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Tokens that must be read to do the work.",
                },
                "already_in_context": {
                    "type": "boolean",
                    "description": "Whether that volume is already in the caller's context.",
                },
                "output_ceiling_tokens": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Most tokens the result may occupy.",
                },
                "verification": {
                    "type": "string",
                    "enum": list(VERIFICATION),
                    "description": "How the caller will know the result is right.",
                },
                "description": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "The work in your own words. Used ONLY to map it onto a capability axis — "
                        "never as an input to the ranking arithmetic."
                    ),
                },
            },
            "required": [
                "kind_of_work",
                "item_count",
                "read_volume_tokens",
                "already_in_context",
                "output_ceiling_tokens",
                "verification",
                "description",
            ],
            "additionalProperties": False,
        }

    def get_system_prompt(self) -> str:
        """No model is asked anything; the plan is computed."""
        return ""

    def get_request_model(self):
        return SelectAgentsRequest

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
        try:
            request = SelectAgentsRequest(**arguments)
        except ValidationError as exc:
            return [TextContent(type="text", text=_refusal(exc).model_dump_json())]

        # The scope is echoed so the caller can see what was understood. #96 wants
        # the criteria a plan rested on returned with it, and the scope is the
        # first half of that -- a coerced or misread field is otherwise invisible
        # until the plan looks wrong.
        scope = request.model_dump(include=set(_SCOPE_FIELDS))

        output = ToolOutput(
            status="success",
            content=_STUB_CONTENT,
            content_type="text",
            metadata={"tool_name": self.name, "stub": True, "scope": scope},
        )
        return [TextContent(type="text", text=output.model_dump_json())]
