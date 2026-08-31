# Ship Log

What shipped in this fork, newest on top, one dated `##` entry per unit. The record a future
agent reads to learn how a change was validated. Fork-specific; upstream history is in git.

## 2026-08-16 — the PowerShell quality gate stopped rewriting the tree (#121, PR #143)

#63 was fixed on `code_quality_checks.sh` and the guard test was anchored to that one path, so
`code_quality_checks.ps1` ran `ruff --fix`, `black` and `isort` in **write** mode for six weeks — on
Windows, which is the copy that actually runs here. **The guard passed on the platform that did not
need it and was silent on the one that did.**

Also removed: the script's "Verifying all linting passes..." re-run. It only ever existed because the
first ruff pass auto-fixed, and a second pass after an auto-fix cannot fail — the mechanism that made
#63 invisible in the first place.

**Validated by running it**, not only by reading it: the fixed gate reports `Linting (ruff): PASSED /
Formatting (black): PASSED / Import sorting (isort): PASSED`, exits 0, and `git status` afterwards
shows **only the files this change edited**. That last part is the whole claim.

**Running it also surfaced a live lint error** — `B007` in `scripts/blueprint.py`, an unused loop
variable — which the auto-fixing version would have rewritten silently. Fixed here, per the precedent
#63 set: a gate turned honest while the tree is dirty just moves the failure from silent to permanent.

**Validated** — the guard is now parametrized over both scripts, plus a new test asserting the covered
set equals every `code_quality_checks.*` in the repo, because *the defect was a file nobody asserted
on, not a wrong assertion*. Suite 1280 → 1285. Five mutations red, including dropping the `.ps1` from
the covered set.

One self-inflicted catch worth keeping: the `--fix` assertion searched the whole file, so the **comment
explaining why `--fix` is absent** made it red. The check now strips full-line comments — a flag search
over raw text cannot tell a command from a note about one.

**#121's third item does not apply, and the measurement says so.** It asked whether `black --check`
needs `--fast` under Python 3.11 against a `py313` target. Measured: `--check` warns and exits 0, and
with a deliberately misformatted file it correctly reports `would reformat`. The safety check only
fires when black actually writes, so neither gate needs `--fast` — and adding it would skip a real
check for nothing. The earlier session note claiming `--check` refuses was wrong; it was write mode.

Noted, not fixed: neither script auto-discovers `.venv` (both look for `.openclink_venv`, then fall
back to an activated `VIRTUAL_ENV`). Recorded in `CLAUDE.md` rather than changed, since it is not what
#121 asked for.

## 2026-08-16 — a budget bounds the whole plan, not one seat (#138, PR #142)

#109 compared the budget against one seat's `cost_per_task`. That was right while the count was fixed
at one — #109's docstring said so explicitly — and #111 made it wrong **without touching #109's code**,
so nothing failed. An N-agent plan could pass a budget it exceeded by nearly N times.

**The arithmetic is not "seat cost times seats".** The read is partitioned across the seats (#113), so
the input term is paid once however many seats there are; each seat emits its own answer, so only the
output term multiplies. Multiplying the whole per-seat figure would overstate a read-heavy plan — the
direction that refuses work the caller could afford.

**Ranking had to move to the same figure.** Budgeting on the plan total while ranking on the per-seat
cost puts the incoherence back one function along: "cheapest qualifying" would name a candidate the
budget rule refuses, from the same data in the same call. #96 wants "the figure I optimise" to be "the
figure I spend"; there is one such figure. At a single seat it equals `cost_per_task`, so #104's
arithmetic is extended rather than replaced, and a test pins that.

**Validated** — 6 plan-cost tests plus the tool seam. Suite 1273 → 1280. Four mutations red (plan cost
reverts to per-seat → 5; read charged once per seat → 3; cheapest rule falls back to per-seat order →
1; budget compares one seat → 1).

**Fifth hand-written expectation caught by its own assertion**, twice in this slice alone: a budget
figure that did not sit between the per-seat and total costs, and then a seam test asserting the total
would *differ* from seat-cost times seats. The second confused two multiplications — per-**share** cost
times seats is correct and equals the total; per-**whole-read** cost times seats is the bug. The test
now pins that the seats add up to the total, which is the property a caller actually needs.

**How #138 got closed without being fixed.** Commit `9c33a2b` (#111) said *"Filed rather than fixed:
#138"* and GitHub parsed `fixed: #138` as a closing keyword. Reopened, with the cause recorded on the
issue. **Any closing verb adjacent to `#n` closes it, whatever the surrounding prose means** — negating
it in words does not help.

## 2026-08-16 — plan identity, persisted before the response (#103, PR #141)

Every plan carries a fresh random identity, is written whole to #98's store **before** the response
object exists, and is retrievable by that identity. An unknown identity raises `PlanNotFound` rather
than returning `{}`: a gate that reads a missing plan as an empty one cannot tell "never authorised"
from "authorised to do nothing", and the two demand opposite responses. A store that cannot be written
refuses rather than handing back a plan whose identity resolves to nothing — otherwise the failure
surfaces at spawn time, in another process, with nothing pointing back here.

**Validated** — 8 tests. Suite 1265 → 1273. Six mutations red, including the one that matters:
**moving `save()` to after the `ToolOutput` is constructed**, which is the actual defect the criterion
names and which "look in the store afterwards" cannot see.

**"Asserted, not assumed" was taken literally, because this repo has the scar.** Inspecting the store
after the call proves only that both steps happened — both orders leave the same directory behind. So
each step appends to a log as it runs and the log is asserted. This is the same shape as #98's
concurrency test, which passed 3 runs out of 3 against a fully non-atomic implementation for exactly
this reason: it looked after the fact.

**Identity is random, not derived from the scope.** Two identical scopes are two separate
authorisations; deriving it would let one plan's identity authorise a different plan's run.

**Provenance says what it is.** Until #102 fetches, `source` is `committed_fixture` and `fetched_at` is
the file's mtime — named explicitly so that when #102 lands, `fetched_at` keeping its name does not
turn a file timestamp into a claim about a network call.

One #101 test needed narrowing: it pins that two descriptions produce identical output, and the
identity now legitimately differs per call. The identity alone is popped — not every key that varies —
because a blanket "compare what matches" would absorb the next field that starts depending on the
description, which is what that test exists to catch.

## 2026-08-16 — every agent owns its share of the scope (#113, PR #140)

The partition is decided once, in `partition()`, rather than by each worker separately. Every item has
exactly one owner, the shares sum to the scope on **both** axes — items and read volume — and a count
the scope cannot be divided into is refused rather than silently rebalanced, because quietly adjusting
it would move the width decision out of the frozen phase and into the partitioner.

Two arithmetic decisions that a plausible implementation gets wrong: **the read follows the items**
(an agent holding four of ten reads four tenths, because #111 sized its window on the item share, so
an even split across seats would hand the largest seat an average seat's budget), and **the boundaries
are cumulative rather than per-share rounded** (100 tokens over 3 seats is three 33s that lose a token
or three 34s that invent two; differences between cumulative marks telescope back to exactly the
input).

**Validated** — 10 partition tests plus 2 at the tool seam, both run against a scope whose count
genuinely exceeds one. Suite 1253 → 1265. Five mutations red: remainder piled on the last seat → 2;
read split evenly across seats → 1; per-share rounding → 1; unpartitionable count rebalanced → 1;
shares overlap by one item → 3.

**And the assertion caught my hand-written expectation again.** I asserted the odd token lands on the
FIRST seat, reasoning from the item rule — the item remainder is spread from the front, because the
widest seat is the one a phase waits on. The token remainder falls wherever the cumulative marks put
it, which is the end, and one token of reading is not a load imbalance. Two remainders, two rules, and
the comment computed the answer from the wrong one. Third instance this epic.

**Not delivered, and said in the response rather than implied:** every seat names the same model and
effort. The fields sit on the agent so a survey seat and a working seat *can* differ (#96, story 9),
but nothing in this layer decides that one should — that reason is phase-level and does not exist yet.

## 2026-08-16 — the agent count is derived, and it corrected #108's filter (#111, PR #139)

The count comes from how many item-shares the winner's window holds at once, with the derivation
returned beside it. A smaller window forces a finer split rather than a truncation nobody sees.

**#111 could not be satisfied without correcting #108.** #108 sized the required window on the WHOLE
read, because the count did not exist yet and with one agent the whole read is the share. Keep that
reading and every surviving candidate holds the entire scope alone — so no candidate could ever need
more than one seat and "a smaller context window yields a higher count" was **unobservable by
construction**. The bar is now one item, the smallest share a seat can be given. It is a
generalisation, not a reversal: at `item_count=1` it returns exactly what #108 returned, and a test
pins that so it cannot quietly become one.

**Validated** — 12 width tests plus 2 at the tool seam. Suite 1239 → 1252. Six mutations, three of
which came back **0 red and all three were real gaps**:

- **count floor instead of ceiling → 0 red.** Every case divided exactly, so floor and ceiling agreed
  everywhere. 100 items at 30 per seat is 4 seats; floor plans 3 and leaves 10 items with no owner —
  which #113 needs, since the partitions must sum with no gap.
- **capacity not clamped to the item count → 0 red.** The clamp does not change the count
  (`ceil(3/90)` and `ceil(3/3)` are both 1), only what the plan says about itself: "90 items per agent"
  on a scope of three items is a figure a caller would check, find consistent, and be misled by.
- **`range(count)` → `range(1)` at the tool seam → 0 red.** The test asserting one agent per declared
  seat used 40 items over 400,000 tokens — a 10,000-token share against million-token windows, so the
  count was 1 and the identity held trivially. **The vacuous green again**, in a test written to
  prevent exactly that. It now asserts the count exceeds one before asserting the identity.

**Filed, not fixed: #138.** A budget still bounds one seat while the plan now has N, so an N-agent plan
can cost up to N times the cap. It is not circular — `width()` depends only on the candidate and the
scope, never on the budget — so a per-candidate total is computable and the fix is real work rather
than a redesign. Disclosed in the response, the docs and the module docstring.

## 2026-08-16 — five priced routes, and a count of what the bound cut (#110, PR #137)

Up to five routes come back, winner first, each carrying the same fields as the winner and the
**signed** cost delta to the route above it, with anything the bound cut reported as
`alternatives_dropped`. Nothing qualifying is culled on merit: a candidate beaten on every axis in
play is still the only route once the winner's lane is down, and availability is not one of the axes
being compared.

**Validated** — 9 alternatives tests plus the tool seam. Suite 1229 → 1239. Six mutations red (bound
never applies → 1; dropped always 0 → 1; delta from the winner instead of the predecessor → 1;
unsigned delta → 1; budgeted slate falls back to cost order → 7; an alternative loses a field the
winner has → 1).

**The design decision worth keeping: the routes follow the rule that picked the winner, not the price
list.** #109 made those two orders diverge — under a budget the winner is the best that fits while
cost order still leads with the cheapest — so alternatives ranked by price would be a fallback list
for a decision nobody made, and a caller dropping to one would move from a capability choice to a
frugality choice without being told the basis had changed. `Choice` now carries `ranked` rather than a
lone winner so that order is available downstream.

Two smaller ones, both stated in code so they are not re-litigated: the winner **leads** the slate,
because "the cost delta to the one above it" needs something above the first entry — its own delta is
`null`, not `0.0`, which would read as "same price as the route above". And the delta is **signed**,
because under the budget rule falling back is usually cheaper and a magnitude cannot tell a saving
from a surcharge.

## 2026-08-16 — an optional budget, and frugality without one (#109, PR #136)

No budget takes the cheapest qualifying candidate; a budget takes the best on the axis that fits
inside it. **That reading is forced, not preferred:** #109 requires both "no budget yields the
cheapest" and "a fixture case exists where a budget changes the winner", and a ceiling-only budget
makes the second unsatisfiable — the cheapest would win whenever anything fit. A budget nothing fits
refuses and names the cheapest qualifying candidate and its price. A budget of `0` is a contract
error, because absent means "choose on cost" and zero means "spend nothing".

**Validated** — 10 budget tests plus 3 at the tool seam. Suite 1215 → 1229. Six mutations red
(budget ignored → 3; boundary `<=`→`<` → 1; cheapest-affordable instead of best → 5; priced-out
unreported → 2; zero accepted → 1; disclosure re-adds a shipped slice → 1).

**The finding: a rule enforced by an accident of its input.** Deleting the cost tiebreak from
`choose`'s sort key reddened **nothing** — `max` returns the first maximal element and `rank` had
already ordered by cost, so "ties go to the cheaper" held by luck rather than by the code claiming to
hold it, and would have left silently the first time anything handed `choose` a differently-ordered
list. Unlike #101's genuine redundancy, the rule is real, so it was made load-bearing instead of
deleted: a test hands `choose` a deliberately unranked list, dearer twin first.

**The second finding: the INCOMPLETE disclosure had gone a slice stale.** #108 shipped the
context-window filter while the response, `docs/tools/selectagents.md` and the module docstring all
still called it unbuilt. A caller reads "the context window is not applied" and hand-splits a scope
the layer already filtered — an understated capability misleads exactly as confidently as an
overstated one. The old test only failed when the list was too SHORT; a new one fails when it is too
LONG, which is the direction a list nobody prunes actually drifts.

## 2026-08-16 — context window as a hard filter, applied before pricing (#108, PR #135)

A candidate whose window cannot hold the share it would be given is removed, not down-ranked. A
weight would let a cheap-enough model outrank the constraint and be handed work it silently
truncates. `rank()` now returns a `Ranking` carrying `excluded_by_window` and `excluded_by_axis`
**separately** — "your scope is larger than most context windows" is actionable, "nobody measured
these on your axis" is not, and one number loses the half a caller can act on.

**Validated** — 10 filter tests plus the tool seam. Suite 1213 → 1215. Three mutations, each with an
assert that it applied: filter records but does not remove → 5 red; `<` → `<=` at the boundary → 1
red; `required_window` drops the ceiling term → **1 red, and that was the finding**.

**The finding: a fail-open default on a hard filter, and no test that could see it.**
`output_ceiling_tokens` defaulted to `0`, sizing the requirement on the read alone — the exact
mistake `required_window` exists to prevent, reachable by not passing the argument. Fail-open is the
bad direction: it admits *more* candidates, so nothing errors and a model that cannot hold its own
answer is quietly eligible. Now required, with a test pinning the `TypeError`, because a default that
has to stay gone is one keyword away from coming back.

Deleting the ceiling term entirely reddened **only the hand-checked arithmetic identity** and no
behaviour at all: every candidate in the file was comfortably over the requirement or far under it,
and nothing sat in the gap between the read and the read-plus-answer — the only place the ceiling
decides anything. A 44,000 window against a 40,000 read and an 8,000 answer now does, and it is the
cheaper of the pair. **The identity assertion was true; true is not the same as load-bearing.**

One criteria key was renamed: `candidates_scored_on_axis` → `candidates_ranked`. It described one of
the two filters while counting both, and a count whose name says "on axis" while it also excludes for
context window is a label that will be believed.

**Not claimed:** the "excluded candidates never return as alternatives" half of the criterion is
structural (the sort runs over survivors only) and cannot be asserted end to end until #110 exists.

## 2026-08-16 — ranking on cost per task, one axis, from a committed fixture (#104, PR #134)

The arithmetic core of #96, split from the language half on purpose: mapping described work onto a
capability axis is a language task, ranking candidates once the axis is fixed is arithmetic, and only
the second is testable by assertion. `tools/selection.py` is pure — no network, no key, no clock —
for the same reason `clink/pricing.py` is.

**Validated** — 15 ranking tests plus 6 at the tool seam. Suite 1187 → 1205.

**The case the slice exists for: price per token and cost per task order the same pair differently.**
A model 2.5× cheaper per token costs MORE per task when it emits 3× the output to finish the same
work, and scores lower on the axis while doing it. A layer ranking by price recommends it.

**And my hand-computed docstring was wrong, which the test caught.** The first version of that case
used figures where both output costs came out identical, so the input term decided and the cheap model
still won — the assertion failed against a comment that had already computed the "answer". A comment
that computes the result is worth exactly what the assertion checking it is worth.

A second test pins the flip: on a large read the input term dominates and the cheap-per-token model
genuinely wins. Without it, someone "fixes" the ranking into always preferring the terser model, which
is the same rule-of-thumb error in the other direction.

**A blank axis score excludes a candidate rather than scoring it zero.** The source publishes only its
top 25 per axis, so a blank is *not published* — absence of a measurement, not a measurement of
absence. Zero-filling would rank the unmeasured candidates last on quality while their cheapness pulled
them first on cost, and on this dataset the unmeasured ones are exactly the cheap ones.

**Half the fixture is constructed and it says so in the file.** The axis scores come from a published
table; per-token prices and output-per-task do not exist in that table and were built to make the
disagreement expressible. A test asserts the provenance block still says `CONSTRUCTED`, because #102
replaces the file wholesale and the distinction has to survive until it does.

**The response now declares itself INCOMPLETE and names the six unbuilt promises** (#102, #108–#111,
#113). The honesty requirement got harder rather than easier at this point: there is a real plan now,
so a caller can no longer tell from the shape of the response what the layer does not yet do.

Mutations, each applied with an assert that it applied, observed red, reverted: ranked on price per
token → 1 red; missing axis score no longer excludes → 3 red; axis fixed instead of derived → 6 red.

## 2026-08-16 — the selectagents input contract (#101, PR #133)

Seven required fields plus one free-text description, validated at the edge. The closed kind-of-work
list is the substance: a caller able to invent a category moves the mapping from work to capability
axis out of tested code and into an agent's head, which is what #96 exists to stop.

The list is grounded rather than invented — its members are the shapes `clink-subagents` already names
as delegable leaves, plus the two judgment shapes that skill routes elsewhere, because a caller will
ask for those and the tool must be able to say what it is looking at.

**Validated** — 19 contract tests. Suite 1168 → 1187.

**The lesson, and it recurred inside one slice: a published constraint nobody enforces is worse than
none.** Three instances, all found by probing rather than reading:

1. The enumerations were declared `enum` in the JSON schema while the fields were typed plain `str`.
   The advertisement said closed and the edge accepted anything.
2. The schema said `additionalProperties: false` while the model silently accepted and discarded
   unknown keys. That bites hardest on fields that do not exist *yet* — a caller sending `budget`
   (#109) today would be told it succeeded and would believe it had bounded a run that is not bounded.
3. `min_length=1` on the description counts characters, and whitespace is characters. `"   "` passed —
   and that field is the ONLY input to the capability-axis mapping, so a blank one is missing data
   that does not look missing.

Each reads as enforcement to anyone who looks at the schema. All three now check against the same
tuples the schema publishes, so there is one source for the list, the docs and the validation.

**Mutation found redundant code rather than a gap.** `_refusal` restated the allowed values a second
time; removing that block reddened nothing, because the coverage came entirely from the validator
messages. Deleted — two places spelling one list is how they stop agreeing. The 0-red result was only
believed after asserting the mutation had actually applied; an earlier attempt reported 0 red because
the shell had mangled the pattern and the replacement never happened.

**The description-isolation rule is pinned now, not with #104.** Two requests differing only in the
description must produce identical output apart from the echo. Written before there is anything to
compute, because by #104 the coupling it forbids would already exist and the test would document it
instead of preventing it.

## 2026-08-16 — the selectagents skeleton, registered and reachable (#99, PR #132)

A tracer bullet for #96's selection layer: the whole path proven before anything worth computing runs
through it. Registered, advertised, dispatched by name, returns a stub. `docs/adding_tools.md` followed
rather than invented, including the end-to-end simulator scenario it requires.

**Validated** — 8 unit tests, the advertised list read through `handle_list_tools()`, and a simulator
case (`selectagents_reachable`). Suite 1160 → 1168.

**The stub announces itself in three places, and the description leads with it.** A placeholder that
reads like a real answer is worse than an error here — #96 exists because a delegation resting on
something nobody measured IS the failure. The review caught that `get_description()` opened with the
capability claim and buried "NOT IMPLEMENTED YET" in the final sentence; that string is what a client
model reads when choosing a tool, and a caveat after a claim is read as a claim.

**Disabled by default.** An advertised tool spends context window in every client that connects, and
this one computes nothing. It comes off the `DISABLED_TOOLS` default when #104 lands.

**Two docstrings claimed coverage the tests did not have**, both found by review and both fixed:
- The simulator scenario said it drove "initialize, list tools, call by name". `base_test.py` sends no
  `tools/list` request at all — verified, zero occurrences — so the advertisement leg is covered
  in-process instead, and the docstring now says which half it does.
- The dispatch test claimed it exercised "the disabled-tools filter and the server's argument
  handling". With `requires_model()` False the handler dispatches immediately, and the filter runs once
  at import. It covers the name lookup, and now says only that.

The first RED was a construction failure — `BaseTool.__init__` calls `get_name()`, so a stub raising
`NotImplementedError` made six tests *error* rather than fail. Same weak-red family as an uncollectable
module. The stub was changed to return deliberately wrong values, and all 8 reds became behavioural.

## 2026-08-16 — an on-disk record store, the prefactor under #96 and #89 (#98, PR #131)

First persistence in this repository. `utils/storage_backend.py` is an in-memory cache whose own
docstring says it is "confined to a single Python process", so neither #96's dataset cache nor #89's
phased-run journal could be built on it. Built once, with no callers, so they share a storage layer
rather than growing one each.

**One file per record, through a temp file and `os.replace`** — not the append-only JSONL the issue's
wording suggests, and the two hard acceptance criteria are why. An `O_APPEND` write is atomic only
below a platform-specific size and Windows guarantees nothing; making it safe needs a lock file, which
trades a rare failure for a stale lock after a crash. And a log's characteristic damage is a torn final
line that every reader must then decide about, where under `os.replace` a half-written record is never
visible under its own name at all.

**Validated** — 22 tests, every assertion mutation-checked. Suite 1152 → 1160.

**The finding worth carrying: my headline test could not fail.**
`test_concurrent_writers_never_leave_a_spliced_record` inspected the store *after* both threads
joined, when nothing was in flight, so a torn state was unobservable by construction. Measured: with
`put` replaced by a bare `path.write_text(payload)`, fully non-atomic, it passed **3 runs out of 3**.
It pinned that the writers do not crash — never that the write is atomic, which is the whole criterion.

A reader that runs *during* the writes reds 3 of 3 under the same mutation. And it immediately found a
real defect: `os.replace` is atomic for writers but not transparent to readers, so a `read_bytes`
racing a rename raises `PermissionError(13)` on Windows — `get` could fail during any concurrent write.

That is the second time in this session a test was strengthened once and remained blind: an earlier
pass had already fixed this same test for swallowing its threads' exceptions.

**Five more, each reproduced before being acted on.** The `UnicodeDecodeError` guard was dead code —
`read_text` decodes outside the `try`, and a record cut mid-character is exactly what a torn write
produces. `Plan-1` and `plan-1` shared one file on NTFS, one plan silently reading another's decision.
`$` matches before a trailing newline, so `"abc\n"` reached the filesystem. The store had no way to
enumerate, serving #96 but not #89. And two claims in the branch's own prose were false — a docstring
saying records are "never mutated in place" while `put` overwrites, and a `Path.cwd() not in parents`
assertion that passes from `tests/` for a location inside the repo.

**Stated, not fixed:** no `fsync` before the rename, so a crash can make the rename durable and the
content not. The zero-length check reports that as corruption rather than as an empty record.

## 2026-08-16 — opencode is fully supported: effort, its own cost, and the class it was dropping (#125, #126, #127, PR #128)

The client shipped working in #86. Three things it was doing badly enough to call it "not fully
supported", each found by comparing what the CLI actually reports against what OpenClink did with it.

**Validated end to end on the real binary with the branch's code**, not through `_build_command`:
the registry resolved the executable, the agent ran it, the tool projected the result.

```
--model opencode/deepseek-v4-flash-free --variant high
resolved_effort: "high"
normalized_usage.cached_input_tokens: 1792
cli_reported_cost: {value: 0.0, unit: "USD", source: "opencode_jsonl"}
```

Every fix is visible in that one payload: the flag reached the CLI, the effort came back, the nested
cache class landed **non-zero** (so the walk found real data rather than coincidentally matching a
zero), and a genuinely free call reported `0.0` instead of being swallowed. Suite 1122 → 1133.

- **`reasoning_effort` was accepted and discarded (#125).** `--variant` is a real flag;
  `OpenCodeAgent` inherited the base `_model_args`, which drops effort because claude and gemini bake
  the tier into the model name. Third instance of this class — #27 for codex, #43 for antigravity.
  Both halves shipped: the emission, and `EFFORT_FLAGS` so `_resolve_model_effort` can read it back.
  **Two measured caveats:** an invalid variant is accepted and *silently ignored* by the CLI, and no
  observable effect could be demonstrated on `deepseek-v4-flash` across three controlled runs. So
  OpenClink writes the flag and reads it back; whether the provider acts on it is **unverified**.
- **OpenCode measured its own cost and it never reached the accounting block (#126).** #77 framed the
  choice as *ship a rate card* or *reduce the surface*; both assume OpenClink must compute the price.
  This client makes that false. `cli_reported_cost` carries value, unit and provenance, keyed on the
  metadata rather than the `cli_name`.
- **The largest token class on a real run was being dropped (#127).** `cache.read` had the right field
  and the flat map could not walk into a dict — 144,256 against 102,535 input. `USAGE_FIELD_MAP` now
  takes a dotted key. `cache.write` stays unmapped; that one is a schema question and still #56's.

**The review caught a crash I had introduced**, and that is the part worth carrying. `_call_accounting`
read `result.parser_name`, and `result` is `AgentOutput | CLIAgentError` — only the first had it, so
any failed opencode run would have raised `AttributeError` from inside the error handler and cost the
caller the whole diagnostic block. `CLIAgentError`'s docstring states the invariant that broke: its
field names match `AgentOutput`'s so one projection serves both (#41). Fixed by restoring the
invariant, not by `getattr`.

**And the first regression test for it was green under mutation.** It built the error by hand, so
deleting `parser_name=self._parser.name` from the raise site changed nothing. Rewritten to drive
`finalize_output` with a non-zero return code, it reds at `assert None == 'opencode_jsonl'`.

The review also found that **"the caller was told nothing" was false** — parser metadata is merged
wholesale, so the bare float always reached them; what was missing was a place in `accounting`, a unit
and a provenance. Corrected in the module docstring, `CHANGES-FORK.md`, and on the issue. And it found
that **deleting one parser line reverted the whole feature with a green suite**, because every
projection test hand-fed the metadata: two parser tests now pin the unit and the key name.

Every new assertion was mutation-tested — eight mutations, each applied, observed red, and reverted.

**Gate debt, paid after the merge (#129, PR #130).** PR #128 shipped with `scrutinize=not-run`. Paying
it afterwards found what the missing gate would have caught: `sum_thread_accounts` reads only
`account["cost"]`, so the figure #126 filed under `cli_reported_cost` never reached the thread total.
Every opencode turn fell to `unpriced_turns`, and with `priced_turns == 0` the cost branch never ran —
**a thread of opencode calls returned usage and complete silence about money**, while every turn in it
carried a measured number. Not a regression; an incompleteness the per-call fix made visible and, for
the first time, fixable. Now two totals that are never merged, from one accumulator called twice so the
mixed-unit refusal cannot drift between them. A second finding came from reviewing my own fix: the
extraction turned one pass over `accounts` into three, and annotating the helper `Iterable` would have
invited a one-shot iterator that the first pass exhausts — two totals silently summing nothing.
`Sequence` says so instead.

**The lesson is about the gate, not the bug.** `scrutinize` is the outsider pass, and this is precisely
the class it exists for: the change was correct everywhere the diff touched, and wrong one layer up
where it did not.

## 2026-08-16 — the project is OpenClink (#94, PR #114, merged at `7effad8`)

Renamed from PAL MCP. `pal-mcp-server` is taken on PyPI at 10.4.3 by something that is not this
project, so the name was the blocker under #93 for anyone installing without cloning. 22 commits,
176 files. PR #86 (OpenCode client, #85) rode along — its branch was an ancestor — and merged with it.

**The rename was the easy half.** Three things live outside the repository and could not be
substituted: `~/.pal/cli_clients` (user overrides, recommended by `CHANGES-FORK.md` precisely because
it survives `uv tool upgrade`), the `PAL_MCP_*` env vars in people's `.env`, and the tool prefix
`mcp__pal__<tool>`, which `xeno-skills` names 25 times. All three still work; the prefix moves in a
sequenced cutover tracked separately.

**Validated** — 1119 passed, 4 skipped. `bash -n`, PowerShell's own parser, `black`, `isort` clean.
**CI did not run**: the account is billing-locked and every job failed in 2–3 seconds without
starting. The local suite is the evidence, and it is the only evidence.

**Both review gates were paid before merge, and neither came back clean.** Four defects, each fixed
with the assertion that would have caught it:

- **A second cleanup list, at a deletion site, deleting the one name the first list spares.** #94 said
  "reuse `LEGACY_MCP_NAMES`; do not invent a second one". Three of four sites obeyed; the fourth
  hardcoded `for key in ('openclink', 'pal')`. The existing test read the *declaration line*, which
  this deletion never consulted. The new one anchors on the deletion *statement*.
- **`~/.pal/cli_clients` was read in silence**, against an acceptance criterion that says "without
  being told". Now a `warning`, not a `debug` — the registry loads at server start, where the default
  level hides it from exactly the user who needs it.
- **The freshness check compared `server.py`, never the interpreter.** `expected_cmd` was computed and
  thrown away. Latent on `main` and harmless there; this rename moved `VENV_PATH` from `.pal_venv` to
  `.openclink_venv` and left `server.py` in place, so every existing registration was declared current
  and left on a virtualenv setup no longer installs into. Nothing errors — the old directory is still
  on disk. `tests/test_registration_freshness.py`.
- **Nothing refreshed an existing `pal` entry.** Now refreshed to the current command, *guarded* so it
  is never created; unguarded it registers every client under both names. In `run-server.ps1` too,
  because fixing only the `.sh` rebuilds the split fixed earlier in the same branch.

**Two reported findings did not survive verification**, and that is the point of verifying: the
"two different keys per client" split is deliberate and both scripts agree (line by line), and my own
worry that removing the hardcoded delete stranded a Docker `pal` was wrong — the ordinary path never
removed it either.

**What the guards now cover, and what they missed first.** `tests/test_product_name.py` walks every
tracked file; it shipped with a pattern that never matched the bare word `pal` (293 occurrences
survived a green run) and with a URL exemption applied per *line*, so a link to somebody else's
repository exempted a live product name at the other end of the sentence. Both closed.
`tests/test_embedded_python_parses.py` compiles all ten Python blocks embedded in `run-server.sh` — a
syntax error there does not fail setup, because `|| true` and `2>/dev/null` swallow it. Its coverage
assertion exists because two separate extractors written for that job found 1-of-4 and 6-of-10 and
both printed success.

**Counts** — all five patterns from the issue are at zero on the live surface; the remainder is quoted
history, the guards themselves, three deliberate back-compat shims, and the upstream project's own
name. Per-file breakdown, and why the issue's own baseline turned out not to be reproducible:
https://github.com/xenodeve/openclink/issues/94#issuecomment-5304165489

**Still open, deliberately** — the Claude and Codex CLIs remain registered as `pal`, because that is
where the skills calling `mcp__pal__` run. They move only after `xeno-skills#206` merges *and* users
pull it. `tests/test_mcp_server_key.py` requires both halves to flip together.

## 2026-08-09 — the hooks layer finally has tests (retroactive TDD, #83, PR #84)

The #36 layer (earlier today) shipped with manual demonstrations and zero committed tests — a future edit could
silently break the gate. Retroactive TDD over it, merged at `d08fca1`.

**Validated** — the repo's #25 rule held: **every test was falsified by mutation, not by intent.** Twelve
mutations (M1–M12), each applied, each confirmed to flip its target test red, each reverted.

- **`tests/test_t4_hooks_layer.py`** — 17 tests at two seams. Config seam: `.claude/t4.json` valid JSON with
  armed `"verify"` targeting the fast unit suite (pinned *not* to `code_quality_checks.sh`, which aborts on the
  `.venv`/`.openclink_venv` split); `settings.json` registers the three hooks with `startup|clear|compact` and
  preserves `permissions`; hook files + snapshot exist; `.gitattributes` LF pin. Gate seam: the *real* `t4-gate`
  run against PreToolUse payloads in a temp-dir sandbox (so no test runs the 38s verify): deny bare `gh pr
  create`; allow with ref in body/`--body-file`; deny dangerous git; allow reset `--hard` under `"afk": true`;
  `ask` on merge with passing verify, `deny` with failing verify; marker-guard silence; command-position
  anchoring; session-start snapshot injection.
- **M12 caught a real defect in the test, not the gate.** The first assertion checked the word `using-t4` in the
  injected context — but the fallback directive contains that word too, so breaking the snapshot fallback passed.
  Now asserts a snapshot-only marker (`Re-route at every phase boundary`). The mutation step is the only reason
  this was found.
- **Environment realities recorded in the file** — subprocess output decodes as cp1252 on this box (mojibake'd
  em-dashes/arrows), so assertions are pure-ASCII; the body-file test passes a forward-slash path because bash
  `[ -f ]` can't stat `C:\...` backslash paths.
- **Known-unguarded forms deliberately unpinned** — quoted absolute-path `gh` and `mcp__github__*` stay
  unpinned pending `xeno-skills#83/#84`; pinning them as "allowed" would claim enforcement that does not exist.

**Gates:** `/simplify` ran · `/code-review` ran · `/scrutinize` ran · `/security-review` n-a (test-only diff:
`git diff --name-only` = one `tests/` file) · `/verify` ran (**1067 passed**, 4 skipped, 16 deselected — was
1050). `ruff`/`black`/`isort` clean.

## 2026-08-09 — the enforcement layer the docs promised (#36, PR #82)

Slice 2 of the T4 retrofit: the repo had the prose and no gate, so every rule described as *mechanically
enforced* was fiction. Now it is not. Shipped on `main` at `4aef920`.

**Validated** — every acceptance criterion carried its evidence into the closing comment, and the honest-gap
rule held: **the two forms this machine's agent actually uses were measured and recorded as unguarded, not
claimed as enforced.**

- **`.claude/t4.json`** — marker + `"verify"` = `.venv/Scripts/python.exe -m pytest tests/ -q -m "not
  integration"`, **timed at 38s (1050 passed, 4 skipped, 16 deselected)**. The full `code_quality_checks.sh`
  was not wired: it aborts on this box because the checkout has `.venv` and the script demands `.openclink_venv`
  (the two-venv ledger item) — the issue's own guidance says wire the fast unit suite and leave the
  formatters to `/simplify`.
- **Hook scripts** — copied **byte-identical** to the canonical `t4-project-bootstrap/references/hooks/`
  copies (SHA-256 verified), incl. `run-hook.cmd`. `using-t4.snapshot.md` is SHA-256-identical to the
  current `using-t4` SKILL.md.
- **`.claude/settings.json`** — `hooks` merged in; the pre-existing `permissions` block left untouched;
  session-start matcher `startup|clear|compact`.
- **`.gitattributes`** — `.claude/hooks/*` pinned `text eol=lf`. **The issue did not ask for this file, and
  it is why the hooks survive this repo:** `core.autocrlf=true` would otherwise check the extensionless bash
  scripts out with CRLF (`\r: command not found`). Added because the ACs were untestable without it.
- **Gate demonstrably fires** — fed real PreToolUse payloads through both `bash .claude/hooks/t4-gate` and
  the `run-hook.cmd` launcher `settings.json` actually invokes: bare `gh pr create` no-issue → **deny**;
  `git reset --hard` / `git clean -f` → **deny**; `gh pr merge` → **ask** (and it ran the configured
  `"verify"` itself first, so the ship gate is real, not claimed); `git commit -m "...pr create..."` →
  silence (command-position anchoring holds).
- **Known-unguarded, recorded** — `"C:\Program Files\GitHub CLI\gh.exe" pr create …` (quoted absolute path)
  and `mcp__github__create_pull_request` are **silent**. These were measured, pasted in the PR, and left as
  upstream work (`xeno-skills#83/#84`) because the hooks must stay byte-identical to the plugin's copies.
  Ticking AC-7 without stating this would have recorded enforcement that does not exist — the exact failure
  the issue was filed against.

**Gates:** `/simplify` ran · `/code-review` + `/scrutinize` ran (all ACs traced; the gap-recording is itself
a scrutinize result) · `/security-review` n-a (`git diff --name-only` is `.claude/*` + `.gitattributes`
only) · `/verify` ran (wired command passed; gate executed it live on `gh pr merge`).

## 2026-08-05 — the cost line: usage normalised for every client, then priced (#54, #49, #24, #25)

Four merged (PRs #53, #55, #57, #58), two opened (#56, and #54's own correction). The thread joining
them: **a value that could not be told apart from a different value.** A timeout that read as a model
problem; a silent lint fix that read as a clean tree; "no adapter written" that read as "the CLI
reports nothing"; and an unconfigured rate card that would have read as a live signal.

**Validated** — each mutation-tested; the red-first status of each is stated individually because one
of them was not.

- **#49** (PR #53) `agy --print-timeout` (default 5m0s) is a client-side deadline *inside* clink's
  1800s child timeout, and every non-zero exit was reported as "a requested model may be
  unsupported/rejected" — the wrong cause, which costs more than a vague one because it sends the
  reader somewhere. **The first measurement was of the wrong code path and nearly became the fix:**
  it used `--output-format json`, which the antigravity config never passes. Re-measured in text mode,
  a 20s bound on a much longer prompt **succeeded** — the flag bounds the wait for the FIRST response,
  not the whole call. Forced at 3s: exit 1, stdout 0 bytes, stderr `Error: timeout waiting for
  response`. Red first: 2 failed, 1 passed; the one that passed is a control asserting a *non*-timeout
  still names the model, which is what stopped the fix from being a blanket message rewrite.
- **#54** (PR #55) `clink/registry.py` had an unsorted import block. **The issue's own premise was
  wrong and the correction is worth more than the fix:** `code_quality_checks.sh` does *not* fail on a
  clean tree — it runs `ruff check --fix`, which fixed it and exited 0. Reproduced by stashing the fix
  and running the script's exact command. What is actually wrong is quieter: **the gate silently
  rewrites tracked files on every run** (`ruff`, `black` and `isort` all run in write mode), which is
  the mechanism by which `git add -A` swept unrelated changes into a behaviour commit twice on
  2026-08-04. `black` would rewrite **10 files** under `tests/` and `simulator_tests/`; inventoried in
  the PR, deliberately not fixed there. The issue body and title were corrected.
- **#24** (PR #57) Usage normalised for all six clients, in four slices. **The blocker was one the
  issue's own wording hid:** `_extract_token_usage` hardcoded `metadata.get("usage")`, but gemini
  publishes under `token_usage` and never writes `usage` at all — so a field map alone could never
  reach it, and every adapter written before a per-agent key would have been a correct map hung off a
  key that never appears. Found by the change-site survey, which is the whole reason it runs before
  the plan. `cursor` had **no agent class at all** — it fell through to the same `BaseCLIAgent` an
  unknown client gets, so it could not say anything about itself a stranger would not also say.
  **The strongest test in the set came from the pre-merge review, not the loop:** every other test
  builds its agent by hand and so would still pass if a client were wired to the wrong class; the
  registry-walking test is the only one that notices, and unregistering `CursorAgent` fails it by
  name. That review also **checked a claim an earlier commit message had asserted without evidence** —
  that `claude-9arm` inherits `ClaudeAgent`. It does, via `runner: "claude"`.
- **#25** (PR #58) Rate cards in per-client config, cost carrying its unit, cached input priced at its
  own rate (folding it into input overstates a cache-heavy call ~10×). **The change site the issue did
  not name:** `cost` already existed as `float | None` and was already emitted **with no unit** — so
  the AC was a contract change across three sites, not an addition. Safe because `grep -rn "cost=" clink/`
  found **no assignment anywhere**: the field was declared by #23 and never populated.
  **The review found a real defect again** — `finalize_output` prices every call and no bundled client
  ships a card, so `cost_unavailable: no_rate_card` would have appeared on *every response of every
  client*. It also contradicted a decision made hours earlier in the same series: #24 slice 4 ruled
  that a fact about *OpenClink* stays silent so a marker always means a fact about the *CLI or the call*.
  Fixed in `4274130`.

**No real vendor rate is shipped.** None was fetched and verified, and an unchecked price in a bundled
config is an unverified claim wearing a config file. Populating it is #26's input.

**Opened, not closed:** **#56** — the normalised account has **no field for cache-creation tokens**,
and in a run recorded 2026-08-05 that class was **24477 tokens against 2 input tokens**. Folding it
into `cached_input_tokens` would be *worse* than dropping it, because that field means cache *reads*
for every other client — the account would be wrong rather than incomplete. Pinned by a test so it
cannot be closed by accident. **It must land before #26 puts a number in front of anyone.**

**Process, recorded because it changes what the evidence is worth:** #25 slice 1 was **not red-first**
— the implementation was written before the tests were run, so removing it produced only a collection
error, the vacuous red this repo has been bitten by before. Its falsification is mutation and only
mutation. The other cycles were properly red-first with behavioural failures.

**Suite:** 960 → **1008 passed**, 4 skipped, 16 deselected. `ruff check .` clean on `main` for the
first time.

## 2026-08-04 — an AFK batch on the clink honesty line, plus the Phase 0 spike (#12, #43, #37, #41, #29)

Five items cleared unattended. The thread joining four of them: **a knob, a default, a payload or a
failure that the caller could not see.** #43 dropped `reasoning_effort` silently; #29 resolved an
omitted model to a config default and reported it like a choice; #37 forwarded a parser's whole
payload beside a field that was capped; #41 reported what a failed run spent but not what ran it.

**Validated** — each red observed before its implementation, each mutation-tested:

- **#43** (PR #45) `agy --effort low|medium|high` is real. Measured against the binary: the two knobs
  are mutually exclusive for every model it serves (`agy models` shows every id either bakes its tier
  in or has no ladder), so the client refuses the pair before spawn. Honoured, not merely accepted —
  same prompt, `--effort low` → 0 thinking tokens, `--effort high` → 446. The refusal probes cost no
  quota: agy validates argv before calling a model (`duration_seconds: 0`).
- **#37** (PR #46) `raw` / `raw_events` dropped in `_prune_metadata`, the one point both paths pass
  through. Dropped rather than capped because a repo-wide grep found **no production reader** — only
  two parser-level test assertions. Mutation: pruning one key, or one path, reddens the other.
- **#41** (PR #47) `CLIAgentError` carries the same field names as `AgentOutput`, so `_call_accounting`
  is one projection for both outcomes. `observed_model` is now omitted when unobserved rather than
  reported as `"unknown"` — which is what the function's own docstring already promised two lines up.
- **#29** (PR #48) **Breaking.** `model` is required. 12 test call sites had to carry one; one test
  asserted `requested_model` absent, a state that no longer exists through the tool, and was rewritten
  rather than patched. `CHANGES-FORK.md` gained a Breaking-changes section because its intro claimed
  every fork change was additive.
- **#12** (PR #44) Phase 0 spike. All four live clients are resumable headlessly; only Claude Code
  demonstrably has a pre-tool hook that can block, so Phase 4 must be proven there first rather than
  shipped uniformly. **The epic's transport premise is now an open question, not a finding** — the
  60–108s figure was not measured on Claude Code, and the fault is intermittent, so five successful
  calls prove nothing about it either way.

**Two corrections landed on the spike report itself**, both from the owner: the premise is host-scoped
(OpenClink is an MCP server on all four hosts, one was measured), and the fault is random, so a rate is
needed rather than a verdict. Recorded in `docs/reports/2026-08-04-clink-phase0-spike-host-followup-and-cli-capability.md`.

**The owed gates were paid on 2026-08-04, after the batch and before any merge.** `/simplify`,
`/code-review` and `/scrutinize` had run zero times across the batch, against `t4-afk`'s own gate list.
Run afterwards across all ten open PRs (six here, four in `xeno-skills`), they found a real defect in
**seven** of them — so the omission was not harmless, and none of it would have surfaced at merge:

- **#46** `/simplify` — `events` was already pruned with exactly the shape this PR added for
  `raw`/`raw_events`: same marker convention, same debug log, written twice. One loop over three keys.
  Mutation-checked (dropping `events` from the tuple reddens 3 tests).
- **#47** `/code-review` — `_call_accounting` was annotated `result: AgentOutput` while the error path
  passes it a `CLIAgentError`. Nothing type-checks this repo, so the declaration was free to be wrong.
- **#48** `/code-review` — the schema's `model` description said "Required" while `required` stayed
  `["prompt"]`. A validating MCP client would accept the omission and meet the refusal at execution
  time. Red observed first, then `["prompt", "model"]`.
- **#44 · xeno #100** `/scrutinize` — **the same defect in both, and it is the one worth remembering:**
  a correction was appended to the body and never propagated to the summary, so the top of each
  document still asserted the claim its own body withdrew. #44's Status section also pointed at a
  section that does not exist.
- **xeno #103** `/code-review` — a test whose description read "each claim carries the date it was last
  verified" checked only that the *column header* existed. Replaced with a row count; mutation-checked.
- **xeno #101** `/code-review` — an assertion anchored on a 7-character generic substring.
- **#45 · xeno #102** — clean. On #45 a reuse candidate was considered and rejected: `_model_args`
  could delegate its `--model` half to `super()`, but `codex.py`'s override writes the same shape
  explicitly, and matching the sibling won.

Also caught while listing each branch's files: a `git add -A` during the review had swept 19 untracked
`.playwright-mcp/` files and `aa-home-snapshot.md` into #47. Removed.

**`/security-review` did not trigger, and here is the checkable fact:** `git diff --name-only main...`
for all five branches lists `clink/agents/{antigravity,base}.py`, `tools/clink.py`, `CHANGES-FORK.md`,
one report, and test files. No file under an auth, secret, token, entitlement or payment path.

## 2026-08-03 — the clink model is read back from every spelling, and reported three ways (#27 PR #35, #28 PR #40)

Two slices that only make sense together: #27 refuses a model the client cannot serve *before* spawning,
and #28 reports `requested` / `resolved` / `observed` so a backend that ran something else is visible
*after*. Both merged onto a `main` that already had #13.

**The lesson worth keeping is that both were fixed twice.** Each shipped a first version that closed the
case in front of it, and a pre-merge review found the same defect one layer out:

- #27's first fix handled `-c model=X`. Probing the real binary found **five more spellings that all
  reached the API** — `-mX`, `--model=X`, `-cmodel=X`, `--config model=X`, `--config=model=X`. The fix
  covered three of eight while its own commit message argued against enumerating spellings. Parsing is
  now one function, `flag_values`, and *both* the model and effort knobs derive from it; the effort knob
  had the identical hole.
- #28's `model_substituted` compared names with `!=`. The shipped claude config asks for `sonnet` and
  the parser reports `claude-sonnet-4-5-20250929`, so the flag fired on **every ordinary run of that
  client** — worse than absent, because a flag that fires constantly cannot carry the one signal it
  exists for.

**Verified against the real CLI, and that phrase needed care.** Two codex binaries are installed:
`which codex` gives **0.142.4**, while clink spawns `codex.CMD` **0.144.4**, and they disagree — the
older one 400s on a model the newer serves. A shell probe silently tests the wrong one. Precedence was
measured, not assumed: a two-token model flag beats a config-key spelling regardless of token order.

**Stated rather than overstated.** `refuse_unservable` reads the command, and codex also takes a model
from `~/.codex/config.toml` (line 1 here is `model = "gpt-5.6-luna"`) and from `--profile`. The catalog
therefore cannot be enforced from argv at all. Closing that is a public-contract change, so it is #39,
and the docstring now says plainly that the check guards what OpenClink builds and does not guarantee what the
CLI runs.

**Validated:** `960 passed, 4 skipped` on `main`. Red was genuine throughout — the refusal tests failed
with `a process was spawned for a request that should have been refused`, each logging the command that
actually spawned. Ten mutants across the two slices, all killed. Two survived on first run and both
pointed at real coverage gaps rather than dead code: the antigravity parser had no test at all, and the
punctuation-normalisation step in the name comparison was unexercised.

Follow-ups filed rather than absorbed: #37, #39, #41 · and #36 for the missing enforcement layer.

## 2026-08-03 — a clink run that failed is now reported as failed (#13, `e3c7c5b`)

A non-zero exit used to be re-parsed by the recovery hook and, if the output parsed, returned as a
successful `AgentOutput` with the exit code discarded. A master agent cannot supervise a subagent
whose failures arrive labelled as completions, and no test asserted otherwise — the masking path was
entirely uncovered.

The outcome is now stated rather than inferred from parseability, and decided in exactly one place:
`BaseCLIAgent.finalize_output`. That seam only exists because #23 routed all five construction sites
through it — including `AntigravityAgent`, which overrides `run` wholesale and could never have
inherited a fix applied to the base loop. Recovery keeps its real job: salvaged content and the
normalised token account now travel on `CLIAgentError` (`parsed`, `token_usage`) and are surfaced by
`_build_error_metadata`, so #23's guarantee that a failed call still reports what it consumed holds —
only its address moved from the result to the error.

**The issue's second case was mis-specified and the correction is the durable part.** It described
"exit 0 with empty output"; no parser in the tree can produce that, since all four raise on empty
content. The real mechanism is that `clink/parsers/antigravity.py` returns *stderr as the content*
when stdout is empty, tagging it `empty_stdout` (**renamed later the same day** — the tag is now the
shared `NO_ANSWER_METADATA_KEY`, because the gemini parser spelled the same concept `empty_response`
and `finalize_output` checked only one of them) — so an empty run arrives with non-empty text and
that tag is the only thing separating a diagnostic from a reply. The parser had been labelling it all
along and nothing read the label.

**Validated:** three tests observed failing first (all `DID NOT RAISE CLIAgentError`), then green.
Three existing tests asserted the removed behaviour: two rewritten to the new contract, one removed
outright with a comment in its place explaining that its rewrite would have duplicated a new test
verbatim. `pytest tests/ -m "not integration"` → **906 passed / 0 failed**. Verified end to end
against the **real codex binary** — driving it with a nonexistent model exits 1 with JSONL that
parses cleanly (the exact shape that used to become a success) and is now reported as a failure
carrying the API's own 400 message; `token_usage` correctly absent because the turn never completed.

## 2026-08-01 — T4 operating layer (Seed) + clink research relocated (#4)

The fork now runs agent-primary: a fresh session recovers state from `Obsidian-OpenClink/Home.md`
(MoC + 7 durable notes), `docs/OPEN-WORK-LEDGER.md`, and this log, with the conventions in
`docs/agents/{domain,workflow,issue-tracker,triage-labels}.md`, decisions in `docs/adr/` (0001–0003),
and the clink-*code* research reports that belong here (delegation-routing research was moved onward
to `xeno-skills` — see `docs/reports/README.md`). `CLAUDE.md` gained an "Operating standard (T4,
fork)" section; the upstream guide is preserved. Adapted to Python/uv/pytest/ruff, not Bun.
**Validated:** docs-only — `git diff --name-only origin/main...HEAD` is 23 `.md` + `.gitignore`, no
`.py`; unit suite on this machine after `mcp<2` local pin + merge of main: **851 passed, 25 failed,
4 skipped** — same 25 failures on clean `origin/main` (Windows POSIX-path test portability, not
this diff). The layer's real test is that the epic filed on top of it (#11 → #12–#16) was written
from these files.

## 2026-08-01 — Bound the `mcp` pin in `requirements.txt` + add `pywinpty` (#17)

`requirements.txt` carried an unbounded `mcp>=1.0.0` and no `pywinpty`, while `pyproject.toml` had
both right — so any installer reading `requirements.txt` (run-server, agents) built an unimportable
tree, because `mcp` 2.0.0 removed `Server.list_tools` which `server.py` decorates with at import.
Fixed by making the two manifests agree, guarded by a new `tests/test_dependency_pins.py` that fails
on any drift between them. **Validated red→green:** the guard test failed first, naming both defects
(`drift: 'mcp>=1.0.0,<2' (pyproject) vs 'mcp>=1.0.0' (requirements)` + `absent from requirements.txt:
"pywinpty>=2.0.0; sys_platform=='win32'"`), then passed. **Validated end-to-end in a clean venv**
(`python -m venv` + `pip install -r requirements.txt -r requirements-dev.txt`): resolved
`mcp==1.29.0` and `pywinpty==3.0.5`, `hasattr(Server('x'),'list_tools')` → `True`, `import server`
→ OK, and `pytest tests/ -q -m "not integration"` → **25 failed, 852 passed, 4 skipped, 16
deselected** — i.e. it *collects and runs* (it previously produced 7 collection errors and 0 tests
run), with the 25 failures matching the pre-existing Windows POSIX-path baseline on clean `main`.
ruff/black/isort clean. Adoption of the `mcp` 2.x API is deliberately **not** decided here — split
to **#18**.

## 2026-07-16 — Zero-setup CLI discovery + active `claude-9arm` (#3, `d44ae01`)

Installing OpenClink normally exposes `codex` / `antigravity` / `claude-9arm` with no extra setup; an
absent CLI reports "not found". `clink/discovery.py` resolves a bare command via PATH → per-CLI
known install locations (winget, `%LOCALAPPDATA%\agy\bin`, npm); the registry expands `~`/`%VAR%`
in `config_args`; `conf/cli_clients/claude-9arm.json` ships active. **Validated:** loaded the
registry from bundled config alone (no `~/.pal` overrides) → antigravity → `…\agy.exe`,
claude-9arm → winget `claude.exe` with `~` expanded, codex via PATH; `tests/test_clink_discovery.py`
(4) + `tests/test_clink_model_effort.py` (6) green; live clink calls confirmed.

## 2026-07-16 — Antigravity `--model` order fix + fail-closed (#2, `7e80e42`)

`agy --print` is value-taking; the old order let it swallow `--model` → silent default. Fixed by
placing model options before `--print` in the Antigravity runner + raising on a non-zero exit.
**Validated:** independent PowerShell repro (wrong order → *Gemini 3.5 Flash*, right order →
requested model); live via OpenClink clink: `Claude Sonnet 4.6 (Thinking)` → Claude Sonnet, `Gemini 3.1
Pro (High)` → Gemini 3.1 Pro, invalid model → exit 1 + catalog (fail-closed).

## 2026-07-16 — Per-call `model` + `reasoning_effort` for clink (#1, `97a7072`)

Optional per-call params mapped per back-end (codex `-m`/`-c`, others `--model`), appended after
config args (backward compatible), via a `_model_args()` hook `CodexAgent` overrides. **Validated:**
`tests/test_clink_model_effort.py` (red→green); live — codex effort scales reasoning tokens
(low=0 vs high=45+), invalid model → hard 400, `gpt-5.6-luna` accessible.
