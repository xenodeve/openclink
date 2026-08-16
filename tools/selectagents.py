"""Compute a delegation plan from measured data rather than from judgement (#96).

**It validates its input (#101) and computes a real, partial plan.** Candidates
are filtered on context window before anything is priced (#108), then ranked on
what the whole PLAN costs along the axis the declared kind of work maps to
(#104, #138) — or, with a budget in force, the best on that axis whose plan fits
inside it (#109). A budget bounds the plan rather than one seat: the read is
charged once across the agents and each agent's answer once. Up to five routes come
back, winner first, each priced against the one above it, with anything the bound
cut counted rather than silently omitted (#110). The agent count is derived from
how many item-shares the chosen window holds at once, and the derivation comes
back with it (#111). Each agent owns a named share of the scope, decided once
here rather than by each worker separately (#113). Registered, advertised and
dispatched by name.

**What it still does not do is stated in the response itself**, not only here:
the dataset is a committed fixture whose prices are constructed (#102 replaces
it), and every seat names the same model and effort because nothing here yet
decides one should differ. That list is guarded in both directions
— a test fails if it omits an unbuilt slice, and another fails if it still names
a shipped one. The second half exists because this docstring and the tool's own
disclosure both went stale by a slice before anything noticed.

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
from tools.plan_record import dataset_provenance, new_identity, save
from tools.selection import (
    DatasetError,
    axis_for,
    choose,
    load_candidates,
    partition,
    plan_cost,
    rank,
    required_window,
    slate,
    width,
)
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
    # It bites hardest on fields that do not exist YET. A caller sending an
    # unknown key today is told so, rather than told the request succeeded and
    # left believing it had bounded a run that is not bounded — which is what
    # `budget_usd` (below, #109) would have done had it stayed unrecognised.
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

    # The one optional field, and optional on purpose (#109). Every other field
    # is required because a default would decide something silently; here the
    # absence IS the decision, and it is the frugal one — no budget means the
    # cheapest qualifying candidate, so a caller that has no figure in mind is
    # not made to invent one.
    budget_usd: float | None = Field(
        None,
        description=(
            "Optional ceiling in USD for one task. Omit it and the cheapest qualifying "
            "candidate is chosen; supply it and the best candidate that fits is chosen instead."
        ),
    )

    @field_validator("budget_usd")
    @classmethod
    def _budget_can_buy_something(cls, value: float | None) -> float | None:
        # `None` and `0` are different answers wearing similar clothes: absent
        # means "choose frugally", while zero means "spend nothing", which no
        # candidate can satisfy. Accepting zero would turn a plausible typo into
        # a refusal that reads like an empty dataset.
        if value is not None and value <= 0:
            raise ValueError("must be greater than 0; omit the field entirely to select on cost alone")
        return value

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
#
# This list must SHRINK as slices land. It went one merge stale — #108 shipped
# the context-window filter and this text still called it unbuilt — which is the
# same defect pointing the other way: a disclosure nobody maintains understates
# the tool exactly as confidently as it once overstated it.
_PARTIAL_CONTENT = (
    # The EPIC, not the newest slice. Naming the last thing that shipped told a
    # caller nothing and dated the string on every merge; #96 is where the whole
    # plan is, and it stays right until the layer is finished.
    "selectagents is INCOMPLETE (#96).\n\n"
    "Candidates that cannot hold their share of the read plus your output "
    "ceiling are excluded before anything is priced, and the winner is then the "
    "lowest-cost PLAN — or, if you named a budget, the best on the axis whose "
    "whole plan fits inside it. A budget bounds the plan, not one seat: the read "
    "is charged once across the agents and each agent's answer once. Up to five "
    "routes are returned, winner first, "
    "each priced against the one above it, with anything the bound cut counted. "
    "The agent count is derived from how many item-shares the chosen window "
    "holds at once, the derivation comes back with it, and each agent owns a "
    "named share of the scope that sums with its neighbours to the whole. That "
    "much is real arithmetic on a committed fixture.\n\n"
    "What is NOT here yet, and what you must not assume: the dataset is a "
    "committed fixture whose prices and output volumes are CONSTRUCTED rather "
    "than measured (#102 replaces it with fetched data); difficulty is not an "
    "input, because the request contract carries no field for it; and every agent names the same "
    "model and effort — the fields sit on the agent so a survey seat and a "
    "working seat CAN differ, but nothing here yet decides that one should."
)


def _dataset_refusal(reason: str) -> ToolOutput:
    """No dataset means no plan, said at once rather than degraded.

    #96 gives the missing dataset no middle rung on purpose: with no prices and
    no rankings there is nothing to compute, and a plan produced anyway would be
    the unmeasured decision the whole layer exists to remove.
    """
    return ToolOutput(
        status="error",
        content=(
            "selectagents cannot compute a plan: the model dataset is unavailable. " f"Nothing was ranked.\n\n{reason}"
        ),
        content_type="text",
        metadata={"tool_name": "selectagents", "partial": True},
    )


def _no_candidate_refusal(axis: str) -> ToolOutput:
    """Nothing was measured on the axis this work needs.

    Distinct from a missing dataset: the dataset loaded and simply carries no
    score on this axis for anything. Reported rather than answered with the
    cheapest unmeasured candidate, which is what a zero-fill would have done.
    """
    return ToolOutput(
        status="error",
        content=(
            f"selectagents found no candidate measured on the '{axis}' axis, which is the one "
            "your declared kind of work ranks on. Nothing was ranked — a candidate with no "
            "score on an axis has not been measured on it, and ranking it anyway would invent "
            "the number this layer exists to avoid inventing."
        ),
        content_type="text",
        metadata={"tool_name": "selectagents", "partial": True},
    )


def _unstorable_refusal(reason: str) -> ToolOutput:
    """The plan could not be persisted, so no plan is returned (#103).

    Returning it anyway would hand the caller an identity that resolves to
    nothing. The gate rejecting it would fail at spawn time, in a different
    process, with nothing pointing back at the write that never landed — so the
    refusal happens here, where the cause is still in hand.
    """
    return ToolOutput(
        status="error",
        content=(
            "selectagents computed a plan and could not store it, so no plan was returned. "
            "An identity that is not on disk cannot be validated by anything that receives it.\n\n"
            f"{reason}\n\n"
            "Check that the store directory is writable, or set OPENCLINK_STORE_DIR to one that is."
        ),
        content_type="text",
        metadata={"tool_name": "selectagents", "partial": True},
    )


def _route(candidate, cost_delta_usd: float | None, axis: str, read_volume_tokens: int) -> dict[str, Any]:
    """One route in the plan's shape — used for the winner and every alternative.

    #110 asks that each alternative carry "the same criteria fields as the
    winner", so that substituting is decided on the same evidence. One function
    is how that stays true: two literals spelling one shape would drift, and the
    drift would land exactly where a caller is comparing them.
    """
    return {
        "model": candidate.model,
        "effort": candidate.effort,
        "cost_per_task": round(candidate.cost_per_task(read_volume_tokens), 6),
        "axis_score": candidate.score_on(axis),
        "context_window": candidate.context_window,
        "cost_delta_usd": cost_delta_usd,
    }


def _over_budget_refusal(budget_usd: float, cheapest: float, model: str) -> ToolOutput:
    """The budget fits nothing, said plainly rather than exceeded quietly (#109).

    Returning the cheapest anyway would hand back a plan the caller's own stated
    ceiling forbids, and nothing in the response would say so until the bill
    arrived. The cheapest qualifying figure is named because a refusal that does
    not say what it would take leaves the caller guessing at the next budget.
    """
    return ToolOutput(
        status="error",
        content=(
            f"selectagents found no candidate within a budget of ${budget_usd:.4f} per task. "
            f"Nothing was planned rather than a plan returned over budget.\n\n"
            f"The cheapest qualifying candidate is {model} at ${cheapest:.4f} per task. "
            "Raise the budget, reduce the read volume, or omit the budget to select on cost alone."
        ),
        content_type="text",
        metadata={"tool_name": "selectagents", "partial": True},
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

        try:
            candidates = load_candidates()
        except DatasetError as exc:
            # No prices and no rankings means nothing to compute, and #96 refuses
            # at once rather than degrading: a plan produced without a dataset is
            # precisely the unmeasured decision this layer exists to remove.
            return [TextContent(type="text", text=_dataset_refusal(str(exc)).model_dump_json())]

        axis = axis_for(request.kind_of_work)
        ranking = rank(
            candidates,
            kind_of_work=request.kind_of_work,
            read_volume_tokens=request.read_volume_tokens,
            output_ceiling_tokens=request.output_ceiling_tokens,
            item_count=request.item_count,
        )
        ordered = ranking.ordered
        if not ordered:
            return [TextContent(type="text", text=_no_candidate_refusal(axis).model_dump_json())]

        choice = choose(
            ordered,
            axis=axis,
            read_volume_tokens=request.read_volume_tokens,
            item_count=request.item_count,
            output_ceiling_tokens=request.output_ceiling_tokens,
            budget_usd=request.budget_usd,
        )
        if choice.winner is None:
            # Only reachable with a budget in force: `ordered` is non-empty by the
            # check above, and the no-budget rule always takes its first element.
            cheapest = ordered[0]
            return [
                TextContent(
                    type="text",
                    text=_over_budget_refusal(
                        request.budget_usd,
                        cheapest.cost_per_task(request.read_volume_tokens),
                        cheapest.model,
                    ).model_dump_json(),
                )
            ]

        winner = choice.winner
        routes = slate(
            choice,
            read_volume_tokens=request.read_volume_tokens,
            item_count=request.item_count,
            output_ceiling_tokens=request.output_ceiling_tokens,
        )

        # The count is fixed HERE, before a single agent is described, and every
        # seat below is generated from it (#111). Describing agents first and
        # counting them afterwards is how a width grows mid-flight — the failure
        # the per-phase freeze exists to prevent.
        seats = width(
            winner,
            read_volume_tokens=request.read_volume_tokens,
            item_count=request.item_count,
            output_ceiling_tokens=request.output_ceiling_tokens,
        )

        # The partition is decided once, here, rather than by each worker
        # separately (#113). `width` never produces a count above the item count,
        # so this cannot refuse today — but `partition` checks anyway, because
        # #111 makes a phase sizeable from a previous phase's result and a count
        # can arrive from outside the function that computed this one.
        shares = partition(
            item_count=request.item_count,
            read_volume_tokens=request.read_volume_tokens,
            agent_count=seats.count,
        )

        plan = {
            # Model and effort sit on the AGENT, not on the plan, so a survey
            # seat and a working seat can differ (#96, story 9). Every seat names
            # the winner today because nothing here decides that a seat should
            # differ — that reason is a phase-level one and does not exist yet.
            # The shape allows it; the layer does not yet exercise it, and the
            # response says so rather than letting the shape imply otherwise.
            "agents": [
                {
                    "model": winner.model,
                    "effort": winner.effort,
                    "cost_per_task": round(winner.cost_per_task(share.read_volume_tokens), 6),
                    "scope_share": {
                        "first_item": share.first_item,
                        "item_count": share.item_count,
                        "read_volume_tokens": share.read_volume_tokens,
                    },
                }
                for share in shares
            ],
            # The routes, winner first, each carrying the SAME fields as the
            # winner so a substitution is decided on the same evidence (#110).
            # Built from one helper rather than two literals, because two places
            # spelling one shape is how they stop agreeing — and the whole point
            # is that an alternative is comparable to the winner.
            "alternatives": [
                _route(entry.candidate, entry.cost_delta_usd, axis, request.read_volume_tokens)
                for entry in routes.entries
            ],
            # Never silently omitted. A caller reading five routes cannot tell a
            # field of five from a field of eighty without this, and would rule
            # out routes it was never shown (#96, #110).
            "alternatives_dropped": routes.dropped,
            # The criteria the choice rested on, returned with it, so a caller can
            # disagree with a reason rather than with a feeling (#96).
            "criteria": {
                "axis": axis,
                "axis_score": winner.score_on(axis),
                "ranked_on": "cost_per_task",
                "candidates_considered": len(candidates),
                "candidates_ranked": len(ordered),
                # Both exclusions named, not counted. "Your scope is larger than
                # most context windows" is actionable — split it — and "nobody
                # measured these on your axis" is not, so collapsing the two into
                # one number throws away the only half a caller can act on (#108).
                "excluded_by_context_window": ranking.excluded_by_window,
                "excluded_by_axis": ranking.excluded_by_axis,
                # The budget in force, and which rule it put in play (#109). Both,
                # because the winner alone cannot say which ran: `null` here with
                # `cheapest_qualifying` is a caller that named no ceiling, and a
                # figure with `best_within_budget` is one that did and got the best
                # seat that fit rather than the cheapest.
                "budget_usd": request.budget_usd,
                "selection_rule": choice.rule,
                "excluded_by_budget": choice.excluded_by_budget,
                # Beside the budget, because that is what the budget is compared
                # against (#138). The read is charged once and each seat's answer
                # once, so this is NOT the per-agent figure multiplied by the
                # count — a caller checking it against `agent_count` would
                # otherwise find a mismatch and trust the wrong one.
                "plan_cost_usd": round(
                    plan_cost(
                        winner,
                        read_volume_tokens=request.read_volume_tokens,
                        item_count=request.item_count,
                        output_ceiling_tokens=request.output_ceiling_tokens,
                    ),
                    6,
                ),
                "context_window_required": required_window(
                    read_volume_tokens=request.read_volume_tokens,
                    output_ceiling_tokens=request.output_ceiling_tokens,
                    item_count=request.item_count,
                ),
                # The count AND what it was derived from (#111). A bare number is
                # indistinguishable from a number someone picked, which is the
                # thing this slice replaces — so the components a caller would
                # need to check the arithmetic travel with it.
                "agent_count": seats.count,
                "agent_count_derivation": {
                    "per_item_read_tokens": seats.per_item_read_tokens,
                    "usable_window_tokens": seats.usable_window_tokens,
                    "items_per_agent": seats.items_per_agent,
                    "item_count": request.item_count,
                    "formula": "ceil(item_count / min(item_count, (context_window - output_ceiling) // per_item_read))",
                    # Named because #111's prose lists it and the contract has no
                    # field for it. Silence here would read as "difficulty was
                    # weighed", which is the unmeasured input the layer removes.
                    "difficulty": "NOT AN INPUT — the request contract carries no difficulty field (#101)",
                },
            },
        }

        # On disk BEFORE the response exists (#103). An identity handed to a
        # caller that does not yet exist on disk is one the paired repository's
        # gate cannot validate, and the window between the two is exactly when a
        # fast caller acts. A test records the order rather than inspecting the
        # store afterwards, because afterwards both orders look the same.
        plan["identity"] = new_identity()
        provenance = dataset_provenance()
        try:
            save(plan["identity"], plan, provenance)
        except (OSError, ValueError) as exc:
            # Refuse rather than return a plan whose identity was never stored:
            # otherwise the failure surfaces at spawn time, in another process,
            # with nothing pointing back here.
            return [TextContent(type="text", text=_unstorable_refusal(str(exc)).model_dump_json())]

        plan["dataset"] = provenance
        output = ToolOutput(
            status="success",
            content=_PARTIAL_CONTENT,
            content_type="text",
            metadata={"tool_name": self.name, "partial": True, "scope": scope, "plan": plan},
        )
        return [TextContent(type="text", text=output.model_dump_json())]
