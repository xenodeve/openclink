# SelectAgents Tool

> ⚠️ **Partly implemented.** The tool ranks real candidates on cost per task (#104), filters on context
> window before pricing (#108), honours an optional budget (#109), returns up to five priced routes with
> a count of what the bound cut (#110) and derives the agent count from the chosen window (#111) —
> against a **committed fixture whose prices and output volumes are constructed, not measured** (#102
> replaces it with fetched data), and partitions the scope across the planned agents (#113). Still
> unbuilt: every seat names the same model and effort — the fields sit on the agent so a survey seat
> and a working seat *can* differ, but nothing here yet decides that one should. Every response says the same thing in its own body, and that list is guarded by a
> test in both directions — it must name everything unbuilt and nothing already shipped.
>
> This banner said "does not rank models, read a dataset, or compute anything" for two slices after it
> had begun doing all three. A stale disclaimer understates a tool exactly as confidently as an
> overstated one oversells it, so it is a change site for every slice — not documentation to revisit
> at the end.

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

## What You Pass It

Seven required fields and one optional. Nothing is defaulted, because a default here is a decision made
silently — an omitted `item_count` falling back to 1 would turn a fan-out into a single agent and
nothing in the response would say you never asked for that.

| Field | Meaning |
|---|---|
| `kind_of_work` | One of `implementation`, `refactor`, `bulk_transform`, `research`, `review`, `analysis`. Closed, because it decides the capability axis. |
| `item_count` | How many separate items the scope contains. |
| `read_volume_tokens` | Tokens that must be read to do the work. |
| `already_in_context` | Whether that volume is already in your context. |
| `output_ceiling_tokens` | Most tokens the result may occupy. Added to the read volume to size the context window a candidate must have. |
| `verification` | One of `automated_tests`, `diff_review`, `spot_check`, `unverifiable`. What will confirm the result — work a suite checks tolerates a weaker seat. |
| `description` | The work in your own words. Used **only** to map it onto a capability axis, never as an input to the arithmetic. |
| `budget_usd` *(optional)* | A ceiling in USD for one task. See below. |

Unknown fields are refused rather than dropped. A caller that sent a budget before #109 existed would
otherwise have been told the request succeeded, and would have believed it had bounded a run that was
not bounded.

### The budget changes which rule runs

**Omit it and you get the cheapest qualifying candidate.** Frugality is the default rather than a
setting you have to remember.

**Supply it and you get the best candidate on the axis whose *whole plan* fits inside it.** You have
already said what you will spend, so the layer spends it on capability instead of handing back change.
This is why the same scope can return a different — and better — model once a budget is named.

**The budget bounds the plan, not one seat (#138).** A model with a small window needs several agents
and emits several answers, so its plan costs more than its seat does. The read is charged **once**
across the agents — it is partitioned, not repeated — and only the answers multiply. The figure the
budget was tested against comes back as `plan_cost_usd`, and the per-agent costs sum to it.

If nothing fits, it **refuses and names the cheapest qualifying candidate and its cost**, rather than
returning a plan your own ceiling forbids and letting you find out from the bill. A budget of `0` is a
contract error, not a refusal: omitting the field is how you say "choose on cost".

The same figure decides the no-budget rule, so "cheapest" means the cheapest **plan** — a layer that
budgeted on one number and ranked on another would recommend a candidate its own budget rule refuses.

### The agent count is derived, not chosen

How many agents the plan contains falls out of **how many item-shares the chosen model's window holds
at once**. A scope of 100 items reading 100,000 tokens is a 1,000-token share; a model with 10,000
usable tokens seats ten items and needs ten agents, while a million-token model needs one. A smaller
window forces a *finer split* rather than a truncation nobody sees.

The derivation comes back with the count — the per-item share, the usable window, the items per agent,
and the formula — because a bare number is indistinguishable from a number someone picked, which is the
thing this layer exists to replace.

Two consequences worth stating plainly:

- **`output_ceiling_tokens` is subtracted from the window before anything is divided.** A model sized
  exactly to what it reads has nowhere to put its answer.
- **A candidate is excluded only if it cannot hold one item.** Splitting stops at the item, so no
  number of agents rescues a window below that bar.

**Difficulty is not an input.** #111 names it, and the request contract has no field for it — so the
count derives from volume and window only, and the criteria say so rather than implying a factor that
is not there.

## What It Will Return

- The planned agents, each carrying its own model, effort and **share of the scope** — which items it
  owns and how much reading that is. The partition is decided once here rather than by each worker
  separately: every item has exactly one owner, and the shares sum to the declared scope on both axes.
  The read follows the items, so an agent holding four of ten reads four tenths — an even split across
  seats would hand the largest seat an average seat's budget, and #111 sized its context window on the
  item share, so the mismatch would land as a truncation.

  A count the scope cannot be divided into is **refused, never rebalanced**: adjusting it quietly would
  move the width decision out of the frozen phase and into the partitioner.
- The criteria the choice rested on, so you can disagree with a reason.
- Five ranked routes carrying the same fields, with the cost delta to the one above. A lane outage
  should leave you a route, and availability is not a cost axis — so a route is kept even when another
  candidate beats it on every measured one. **The winner leads the list**, so the deltas chain from the
  route you were actually given, and the first entry's delta is `null` because nothing sits above it.
  The delta is **signed**: falling back is often cheaper, and a magnitude alone would not tell a saving
  from a surcharge. Anything the five-route bound cut is reported as `alternatives_dropped`, so a list
  of five is never mistaken for a field of five.

  The routes follow the rule that picked the winner. With no budget that is ascending cost; with a
  budget it is descending capability. Ranking them by price under a budget would offer fallbacks for a
  decision nobody made.
- **An identity for the plan**, so a spawn can be tied back to the decision that authorised it. The
  plan is written to the on-disk store *before* the response exists — an identity you hold that is not
  yet on disk is one a gate cannot validate. If the store cannot be written, the tool **refuses**
  rather than returning a plan whose identity resolves to nothing.

  Look one up with `tools.plan_record.fetch(identity)`. An unknown identity raises `PlanNotFound`; it
  never resolves to an empty plan, because "never authorised" and "authorised to do nothing" demand
  opposite responses.

- **The dataset's fetch time and fingerprint**, so the decision can be reproduced later. Until #102
  fetches, `source` reads `committed_fixture` and `fetched_at` is the file's modification time — said
  plainly, so the field does not quietly become a claim about a network call when #102 lands.

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
