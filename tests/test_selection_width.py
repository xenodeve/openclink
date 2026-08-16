"""The agent count falls out of the work, and the derivation travels with it (#111).

**The count is a consequence, never a number chosen in the moment.** It comes
from how many item-shares the winner's window can hold at once: a bigger window
carries more items per seat and needs fewer seats, a smaller one forces a finer
split. #96: "a smaller window forces a finer split rather than a truncation
nobody sees."

**This slice had to correct #108's filter to be satisfiable at all.** #108 sized
the required window on the WHOLE read, because the count did not exist yet and
with one agent the whole read is the share. Keep that reading and every surviving
candidate can hold the entire scope alone — so no candidate could ever need more
than one seat, and #111's own criterion ("a smaller context window yields a
higher count") could never be observed. The bar is now one item, the smallest
share a seat can be given, and it is a generalisation rather than a reversal:
at `item_count=1` it returns exactly what #108 returned.

**Width is frozen per PHASE, not per run.** A later phase is sized from what an
earlier one found, so a run-level freeze cannot express it. That is why the
sizing is a pure function of a declared scope: a second phase is a second call
with the scope the first one discovered, and nothing can be added to a phase
already under way because its count was fixed when it started.
"""

from __future__ import annotations

from tools.selection import Candidate, per_item_read, rank, required_window, width


def _candidate(model: str, *, window: int, score: float = 70.0):
    return Candidate(
        model=model,
        effort="max",
        context_window=window,
        axes={"coding": score},
        input_price_per_mtok=1.0,
        output_price_per_mtok=1.0,
        output_tokens_per_task=1_000,
    )


def test_the_required_window_is_one_item_share_plus_the_answer():
    """The correction #111 makes to #108, stated as arithmetic.

    100,000 tokens across 10 items is a 10,000-token share; with an 8,000-token
    answer a candidate needs 18,000 — not the 108,000 the whole-scope reading
    demanded, which would have excluded every candidate that could in fact do the
    job across several seats.
    """
    assert required_window(read_volume_tokens=100_000, output_ceiling_tokens=8_000, item_count=10) == 18_000


def test_one_item_reproduces_what_108_required():
    """A generalisation, not a reversal — pinned so it cannot quietly become one.

    If this ever stops holding, #108's whole rationale has been discarded rather
    than extended, and the tests it left behind would be the only thing saying so.
    """
    assert required_window(read_volume_tokens=40_000, output_ceiling_tokens=8_000, item_count=1) == 48_000


def test_the_share_rounds_up_so_no_item_is_left_without_room():
    """Ceiling division, because the remainder still has to be read by someone.

    100 tokens across 3 items is 34 per share, not 33: floor would size every
    seat one token short of the largest item, and the shortfall lands as a
    truncation rather than as an error.
    """
    assert per_item_read(read_volume_tokens=100, item_count=3) == 34


def test_a_smaller_window_yields_more_seats_on_the_same_scope():
    """#111's own criterion, and the one #108's reading made unreachable.

    The same scope — 100,000 tokens over 100 items, so 1,000 per item — sized
    against two candidates. The roomy one holds the lot in one seat; the cramped
    one holds ten item-shares at a time and needs ten.
    """
    scope = {"read_volume_tokens": 100_000, "item_count": 100, "output_ceiling_tokens": 8_000}

    roomy = width(_candidate("roomy", window=1_000_000), **scope)
    cramped = width(_candidate("cramped", window=18_000), **scope)

    assert roomy.count == 1
    assert cramped.count > roomy.count
    assert cramped.count == 10


def test_the_derivation_travels_with_the_count():
    """A bare number is indistinguishable from a number someone picked.

    Each component is asserted, not merely present: a derivation that reports
    figures the count was not actually computed from is worse than none, because
    it invites a caller to check the arithmetic and find it consistent.
    """
    result = width(
        _candidate("c", window=18_000), read_volume_tokens=100_000, item_count=100, output_ceiling_tokens=8_000
    )

    assert result.per_item_read_tokens == 1_000
    assert result.usable_window_tokens == 10_000  # 18_000 window less the 8_000 answer
    assert result.items_per_agent == 10
    assert result.count == 10  # 100 items / 10 per seat


def test_a_remainder_gets_its_own_seat_rather_than_being_dropped():
    """Ceiling on the count, and nothing in the file could see it.

    Every other case here divides exactly — 100 items at 10 per seat, 28 at 1 —
    so floor and ceiling agree and a mutation to floor reddened **nothing**. This
    is the case that separates them: 100 items at 30 per seat is 4 seats, and
    floor would plan 3 and leave 10 items with no owner.

    #113 requires the partitions to sum to the scope with no gap, so the missing
    seat is not a rounding preference — it is ten items nobody was asked to do.
    """
    # share 1_000, usable 30_000 -> 30 items per seat, 100 items -> 3 remainder 10
    result = width(
        _candidate("c", window=38_000), read_volume_tokens=100_000, item_count=100, output_ceiling_tokens=8_000
    )

    assert result.items_per_agent == 30
    assert result.count == 4


def test_the_reported_capacity_never_claims_more_items_than_exist():
    """The derivation has to be honest as well as arithmetically consistent.

    A roomy window could hold ninety item-shares on a scope of three items.
    Reporting "90 items per agent" is a figure about a scope nobody declared, and
    a caller checking the derivation would find it consistent and still be misled.

    Mutating the clamp reddened nothing, because it does not change the COUNT —
    `ceil(3/90)` and `ceil(3/3)` are both 1. It changes only what the plan says
    about itself, which is why the count alone could never pin it.
    """
    result = width(
        _candidate("roomy", window=1_000_000), read_volume_tokens=3_000, item_count=3, output_ceiling_tokens=8_000
    )

    assert result.items_per_agent == 3
    assert result.count == 1


def test_the_count_never_exceeds_the_number_of_items():
    """An agent with no item is a seat with nothing in it.

    #113 requires the partitions to sum to the scope with no gap and no overlap,
    so a count above the item count cannot be honoured — and inventing seats to
    fill would be exactly the "number chosen in the moment" this slice removes.
    """
    result = width(_candidate("c", window=20_000), read_volume_tokens=30_000, item_count=3, output_ceiling_tokens=8_000)

    assert result.count <= 3


def test_a_scope_with_nothing_to_read_is_one_seat():
    """`read_volume_tokens` is `ge=0`, so zero is legal input and must not divide.

    A scope whose material is already in the caller's context reads nothing, and
    the window constrains nothing — so the count falls to one rather than to a
    crash or to the item count.
    """
    result = width(_candidate("c", window=20_000), read_volume_tokens=0, item_count=7, output_ceiling_tokens=8_000)

    assert result.count == 1
    assert result.per_item_read_tokens == 0


def test_a_later_phase_is_sized_from_what_the_earlier_one_found():
    """#111's fixture criterion: width freezes per PHASE, not per run.

    The issue's own example — a 28-agent phase derived from a 6-agent one. Phase
    one surveys 6 items and is sized for them; it reports back 28 items worth of
    work; phase two is sized from THAT scope and comes out wider. A run-level
    freeze could not express this, because the second number did not exist when
    the run began.

    Nothing was added to phase one to get there: it is a second call, with a
    second scope, producing a second count. That is what makes "nothing may be
    added to a phase already under way" enforceable rather than aspirational.
    """
    candidate = _candidate("c", window=18_000)

    survey = width(candidate, read_volume_tokens=6_000, item_count=6, output_ceiling_tokens=8_000)
    # What the survey found: 28 items, and far more to read than it had itself.
    working = width(candidate, read_volume_tokens=280_000, item_count=28, output_ceiling_tokens=8_000)

    assert survey.count == 1
    assert working.count == 28
    # The earlier phase is untouched by the later one being sized.
    assert survey.count == 1


def test_the_filter_now_admits_a_candidate_that_needs_several_seats():
    """The two halves have to agree, or the count is computed for a ghost.

    A candidate that survives `rank` must be one `width` can actually seat. Under
    #108's whole-scope reading this candidate was excluded outright; under the
    share reading it is admitted and simply costs more seats — which is the
    behaviour #96 asks for.
    """
    cramped = _candidate("cramped", window=18_000)

    survivors = rank(
        [cramped],
        kind_of_work="implementation",
        read_volume_tokens=100_000,
        output_ceiling_tokens=8_000,
        item_count=100,
    )

    assert [c.model for c in survivors.ordered] == ["cramped"]
    assert survivors.excluded_by_window == []


def test_a_candidate_that_cannot_hold_even_one_item_is_still_excluded():
    """The filter loosened; it did not disappear.

    One item here reads 10,000 tokens and the answer needs 8,000, so a seat needs
    18,000. A 12,000-token window cannot take the smallest share that exists, and
    no number of seats fixes that — splitting stops at the item.
    """
    tiny = _candidate("tiny", window=12_000)

    survivors = rank(
        [tiny],
        kind_of_work="implementation",
        read_volume_tokens=100_000,
        output_ceiling_tokens=8_000,
        item_count=10,
    )

    assert survivors.ordered == []
    assert survivors.excluded_by_window == ["tiny"]
