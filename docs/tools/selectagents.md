# SelectAgents Tool

> ⚠️ **Not implemented yet.** As of #99 the tool is registered and reachable and returns a stub that says
> so. It does not rank models, read a dataset, or compute anything. Do not treat its response as a
> delegation decision. This page describes what it is being built to do, and is marked up front so it
> cannot be mistaken for a description of what it does today.

The `selectagents` tool computes a **delegation plan** — whether to delegate at all, to how many agents,
and on which model and effort each — from a measured model dataset rather than from an agent's
recollection.

## Why Use This Tool?

Every agent that reaches OpenClink picks its delegate from memory, and the data that would decide it
correctly is not reachable from inside a skill file. Three consequences, each measured rather than
supposed:

**The obvious heuristic is wrong.** Ranking by price per token says a smaller model is cheaper. Ranking
by cost per *task* — the figure actually spent — reverses it at the measured points: one vendor's mid
tier costs the same as a larger model's low tier and scores nine index points lower, because it emits
twice the output tokens per task.

**One number cannot decide it.** Different models lead different axes, and the composite index is
measured with tools in the loop for only about a third of its weight. Ranking a delegation by the
composite therefore imports a majority signal about something a delegation is not.

**A worker with a loose scope bills the caller for work nobody asked for.** Nothing today bounds what a
spawned agent may do, and nothing records what it was authorised to do.

## What It Will Return

- The planned agents, each carrying its own model, effort and share of the scope — a survey seat and a
  working seat can differ.
- The criteria the choice rested on, so you can disagree with a reason.
- Five ranked alternatives carrying the same fields, with the cost delta to the one above. A lane
  outage should leave you a route, and availability is not a cost axis — so an alternative is kept even
  when another candidate beats it on every measured one.
- An identity for the plan, so a spawn can be tied back to the decision that authorised it.
- The dataset's fetch time and fingerprint, so the decision can be reproduced later.

## What It Will Not Do

**It will not guess.** With no dataset there are no prices and no rankings, so there is nothing to
compute and it refuses at once, naming the missing setting. There is no middle rung for that case —
silent degradation would hand back a plan that looks computed and is not, which is the failure the
whole layer exists to remove.

**It will not take weights from the caller.** Cost always matters, because that is the point of the
layer. Speed is not an objective. The capability axis comes from the declared kind of work rather than
from a free-text guess. Context window is a hard filter applied before pricing, not a weight — a
candidate that cannot hold its share is excluded rather than discounted.

## Why It Lives Here Rather Than in a Skill

OpenClink already holds provider credentials and a settings mechanism for them. The paired skills
repository has no way to hold a secret at all. And OpenClink needs the same computation internally to
size a phased run, so putting it anywhere else would mean building it twice.

## Configuration

Nothing to configure yet. When the dataset lands (#102) it will read its API key through the existing
settings mechanism rather than introducing a new credential route, and cache the dataset in the on-disk
store described in [configuration.md](../configuration.md).

## Related

The PRD is issue #96. The slices are #98–#113.
