"""Every agent owns its share, and the shares sum to the scope (#113).

**The partition is decided once, here.** #96: "so that the partition is decided
once rather than by each worker separately". Left to the workers, two agents read
the same file and a third reads nothing, and nobody finds out until the results
disagree.

**Coverage terminates a phase, never confidence.** A phase is complete when every
partition has exactly one owner and the partitions sum to the whole — so the sum
property is the criterion, not a sanity check on it, and it is asserted on both
axes: items and read volume.

**A scope that will not divide is reported, never rebalanced.** Quietly adjusting
the count to something divisible would move the width decision out of the frozen
phase and into the partitioner — the growth the per-phase freeze exists to
prevent, arriving as a correction nobody asked for.
"""

from __future__ import annotations

import pytest

from tools.selection import PartitionError, partition


def test_the_shares_sum_to_the_scope_on_both_axes():
    """#113's own criterion. Items AND tokens, because either can leak alone.

    A split that gets the items right and the tokens wrong hands an agent more
    reading than the plan priced, which is the overrun the layer exists to
    remove — and it would be invisible to a test that counted only items.
    """
    shares = partition(item_count=10, read_volume_tokens=100_000, agent_count=3)

    assert sum(s.item_count for s in shares) == 10
    assert sum(s.read_volume_tokens for s in shares) == 100_000


def test_every_item_has_exactly_one_owner():
    """No gap and no overlap, checked by rebuilding the scope from the shares.

    Asserted as a set identity rather than as a count: two agents both owning
    item 4 while nobody owns item 7 sums to the right total and is exactly the
    failure "exactly one owner" is written against.
    """
    shares = partition(item_count=10, read_volume_tokens=100_000, agent_count=3)

    owned = [i for s in shares for i in range(s.first_item, s.first_item + s.item_count)]

    assert sorted(owned) == list(range(10))
    assert len(owned) == len(set(owned)), "an item has two owners"


def test_a_remainder_is_spread_rather_than_piled_onto_the_last_agent():
    """10 items across 3 seats is 4/3/3, not 3/3/4 and never 3/3/3+1.

    Piling the remainder on one agent makes the widest seat the last one, which
    is the seat a phase waits on. The difference is one item here and a third of
    the wall-clock on a large fan-out.
    """
    shares = partition(item_count=10, read_volume_tokens=100_000, agent_count=3)

    assert [s.item_count for s in shares] == [4, 3, 3]


def test_an_exact_division_gives_identical_shares():
    """The simple case still has to be simple."""
    shares = partition(item_count=9, read_volume_tokens=90_000, agent_count=3)

    assert [s.item_count for s in shares] == [3, 3, 3]
    assert [s.read_volume_tokens for s in shares] == [30_000, 30_000, 30_000]


def test_the_read_split_never_loses_a_token_to_rounding():
    """Cumulative boundaries, not per-share rounding — the sums must telescope.

    Rounding each share independently is the obvious implementation and it leaks:
    at 100 tokens over 3 seats, three rounded-down shares of 33 lose a token, and
    three rounded-up shares of 34 invent two. Neither is a scope anyone declared.

    **The odd token lands on the LAST seat, and I asserted the opposite first.**
    The item remainder is spread from the front — that one matters, because the
    widest seat is the one a phase waits on. The token remainder falls wherever
    the cumulative marks put it, which is the end, and a single token of reading
    is not a load imbalance. Two different remainders, two different rules, and
    writing the expected list from the first rule was wrong: a comment that
    computes the answer is worth exactly what the assertion checking it is worth.
    """
    shares = partition(item_count=3, read_volume_tokens=100, agent_count=3)

    assert sum(s.read_volume_tokens for s in shares) == 100
    assert [s.read_volume_tokens for s in shares] == [33, 33, 34]


def test_the_read_follows_the_items_rather_than_the_seats():
    """An agent with more items reads more, or the pricing was for a fiction.

    Splitting the read evenly across seats while the items divide unevenly hands
    the agent with 4 items the reading budget for 3.33 — and #111 sized the
    context window on the item share, so the mismatch lands as a truncation.
    """
    shares = partition(item_count=10, read_volume_tokens=100_000, agent_count=3)

    assert shares[0].item_count > shares[1].item_count
    assert shares[0].read_volume_tokens > shares[1].read_volume_tokens


def test_one_agent_owns_the_whole_scope():
    """The degenerate case, which is also today's most common one."""
    shares = partition(item_count=7, read_volume_tokens=70_000, agent_count=1)

    assert len(shares) == 1
    assert shares[0].item_count == 7
    assert shares[0].read_volume_tokens == 70_000


def test_one_agent_per_item_is_the_finest_split_there_is():
    """The other boundary: an item is the atom, so this is where splitting stops."""
    shares = partition(item_count=4, read_volume_tokens=400, agent_count=4)

    assert [s.item_count for s in shares] == [1, 1, 1, 1]
    assert sum(s.read_volume_tokens for s in shares) == 400


def test_a_count_larger_than_the_item_count_is_refused_not_rebalanced():
    """#113's fourth criterion, and the one silence would answer wrongly.

    Five seats over three items cannot be honoured — two seats would own nothing,
    and an agent with no work is a seat the plan pays for and cannot use. Silently
    dropping to three would move the width decision from the frozen phase into
    this function, which is the growth the freeze exists to prevent.

    `width()` never produces such a count. This guard is for the OTHER callers:
    #111 makes a phase sizeable from a previous phase's result, so a count can
    arrive from outside and has to be checked where it is used.
    """
    with pytest.raises(PartitionError) as refusal:
        partition(item_count=3, read_volume_tokens=30_000, agent_count=5)

    assert "3" in str(refusal.value) and "5" in str(refusal.value)


def test_a_scope_with_nothing_to_read_still_partitions_its_items():
    """`read_volume_tokens` is `ge=0`, so zero is legal and must not break the split.

    Material already in the caller's context reads nothing, and the items still
    need owners — a phase whose shares are empty of tokens is not a phase with no
    work.
    """
    shares = partition(item_count=4, read_volume_tokens=0, agent_count=2)

    assert [s.item_count for s in shares] == [2, 2]
    assert all(s.read_volume_tokens == 0 for s in shares)
