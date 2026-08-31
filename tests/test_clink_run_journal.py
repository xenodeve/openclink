"""The durable run journal (#149, Deliverable 1a of #89).

#89 asked for append-only JSONL, one file per run. #98 had already measured and
rejected that shape (`utils/record_store.py:9-20`): an `O_APPEND` write is atomic
only below a platform-specific size and "Windows guarantees nothing here", and a
torn final line lands on every reader. A phased run is concurrent by
construction, so that is the normal case rather than an edge one.

So the journal is built on the store's one-file-per-record primitive, with each
agent return carrying its own compound identity. These tests are the acceptance
criteria of #149, one test per criterion.
"""

from __future__ import annotations

import threading

import pytest

from clink.run_journal import RunJournal
from utils.record_store import RecordStore


def test_an_agent_return_survives_the_process_that_wrote_it(tmp_path):
    """Criterion: one record per agent return, durable across a process restart.

    The store is reopened rather than reused, which is the only way to assert
    that the record reached the disk instead of an in-process dict — the exact
    thing #89 says PAL lacks today.
    """
    RunJournal("run1", store=RecordStore(tmp_path)).append(
        phase="plan", agent="a1", sequence=0, record={"verdict": "ok"}
    )

    reopened = RunJournal("run1", store=RecordStore(tmp_path))

    assert [entry.record for entry in reopened.read()] == [{"verdict": "ok"}]


def test_a_whole_run_is_readable_back_by_its_run_identifier(tmp_path):
    """Criterion: a whole run is readable back by run identifier."""
    journal = RunJournal("run1", store=RecordStore(tmp_path))
    journal.append(phase="plan", agent="a1", sequence=0, record={"n": 1})
    journal.append(phase="plan", agent="a2", sequence=1, record={"n": 2})
    journal.append(phase="check", agent="a1", sequence=2, record={"n": 3})

    assert [entry.record for entry in journal.read()] == [{"n": 1}, {"n": 2}, {"n": 3}]


def test_another_runs_records_are_not_read_as_this_ones(tmp_path):
    """The store is shared with #96's dataset cache, so a scan must be scoped.

    `run1` and `run10` share a string prefix; the separator is what keeps them
    apart, and asserting it here is the difference between a scoped scan and one
    that happens to pass on the identifiers a test happened to pick.
    """
    store = RecordStore(tmp_path)
    RunJournal("run1", store=store).append(phase="plan", agent="a1", sequence=0, record={"mine": True})
    RunJournal("run10", store=store).append(phase="plan", agent="a1", sequence=0, record={"mine": False})
    store.put("model-dataset", {"not": "a journal record"})

    assert [entry.record for entry in RunJournal("run1", store=store).read()] == [{"mine": True}]


def test_records_are_ordered_by_their_own_sequence_not_by_directory_order(tmp_path):
    """Criterion: order comes from data in the record, not from directory order.

    `RecordStore.identities()` documents itself as returning identities "in no
    particular order", so ordering by that listing would be a fact nobody
    established. The identities here are deliberately written in an order whose
    alphabetical sort disagrees with the sequence, so an implementation that
    leaned on either the listing or the name fails this.
    """
    journal = RunJournal("run1", store=RecordStore(tmp_path))
    journal.append(phase="plan", agent="zulu", sequence=0, record={"first": True})
    journal.append(phase="plan", agent="alpha", sequence=1, record={"first": False})

    assert [entry.record for entry in journal.read()] == [{"first": True}, {"first": False}]
    assert [entry.sequence for entry in journal.read()] == [0, 1]


def test_a_run_that_stopped_mid_phase_still_reads_back_every_completed_return(tmp_path):
    """Criterion: a run that stops mid-phase leaves every completed return readable.

    Two of three agents returned before the run died. Nothing marks the run as
    finished, so the salvageable part must be readable without one.
    """
    journal = RunJournal("run1", store=RecordStore(tmp_path))
    journal.append(phase="plan", agent="a1", sequence=0, record={"done": 1})
    journal.append(phase="plan", agent="a2", sequence=1, record={"done": 2})
    # a3 never returned — the process died here.

    survivors = RunJournal("run1", store=RecordStore(tmp_path)).read()

    assert [entry.agent for entry in survivors] == ["a1", "a2"]


def test_an_absent_return_is_distinguishable_from_an_empty_one(tmp_path):
    """Criterion: an absent return is distinguishable from an empty one.

    An agent that returned nothing is a fact about the run; an agent that never
    returned is a fact about the failure. A journal that flattens them makes the
    partial run unsalvageable, which is the whole point of the deliverable.
    """
    journal = RunJournal("run1", store=RecordStore(tmp_path))
    journal.append(phase="plan", agent="returned-empty", sequence=0, record={})

    agents = {entry.agent: entry.record for entry in journal.read()}

    assert agents == {"returned-empty": {}}
    assert "never-returned" not in agents


def test_two_agents_returning_concurrently_never_damage_each_others_record(tmp_path):
    """Criterion: concurrent returns do not damage each other.

    This is the criterion that rejected JSONL. Distinct identities mean the two
    writes touch different files, so the assertion is that BOTH survive whole —
    under an append-only log the losing writer's record is the one that gets
    spliced.
    """
    journal = RunJournal("run1", store=RecordStore(tmp_path))
    failures: list[BaseException] = []

    def write(agent: str, sequence: int) -> None:
        try:
            for _ in range(20):
                journal.append(
                    phase="plan", agent=agent, sequence=sequence, record={"agent": agent, "payload": "x" * 4096}
                )
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            failures.append(exc)

    threads = [threading.Thread(target=write, args=args) for args in (("a1", 0), ("a2", 1))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not failures, f"a concurrent append failed instead of racing cleanly: {failures[0]!r}"
    assert [entry.record["agent"] for entry in journal.read()] == ["a1", "a2"]


def test_a_reader_during_concurrent_returns_never_sees_a_torn_record(tmp_path):
    """Criterion: a concurrent *reader* during a write, the assertion #98's own test initially missed.

    #98 found that `os.replace` is atomic for writers but not transparent to
    readers: while the rename is in flight the destination is briefly
    inaccessible. Reading only after the writers joined never touched that path,
    so the read happens *during* the writes here.
    """
    journal = RunJournal("run1", store=RecordStore(tmp_path))
    journal.append(phase="plan", agent="a1", sequence=0, record={"agent": "a1"})
    journal.append(phase="plan", agent="a2", sequence=1, record={"agent": "a2"})
    failures: list[BaseException] = []
    stop = threading.Event()

    def write(agent: str, sequence: int) -> None:
        try:
            while not stop.is_set():
                journal.append(
                    phase="plan", agent=agent, sequence=sequence, record={"agent": agent, "payload": "y" * 4096}
                )
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            failures.append(exc)

    def read() -> None:
        try:
            for _ in range(40):
                assert [entry.record["agent"] for entry in journal.read()] == ["a1", "a2"]
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            failures.append(exc)
        finally:
            stop.set()

    workers = [threading.Thread(target=write, args=args) for args in (("a1", 0), ("a2", 1))]
    workers.append(threading.Thread(target=read))
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert not failures, f"a read during concurrent appends failed: {failures[0]!r}"


@pytest.mark.parametrize("component", ["run", "phase", "agent"])
def test_a_component_containing_the_separator_is_refused(tmp_path, component):
    """The compound identity is split on `.`, so a component may not contain one.

    `RecordStore.path_for` would accept it — `[a-z0-9][a-z0-9._-]*` permits dots
    — and the record would then be filed under a run that nobody wrote to. The
    refusal belongs here because this layer is the one that gives `.` a meaning.
    """
    parts = {"run": "run1", "phase": "plan", "agent": "a1"}
    parts[component] = "has.a.dot"

    # Construction is inside the guard because the run identifier is refused
    # eagerly there, while the phase and agent are only known at append.
    with pytest.raises(ValueError, match="expected"):
        RunJournal(parts["run"], store=RecordStore(tmp_path)).append(
            phase=parts["phase"], agent=parts["agent"], sequence=0, record={"n": 1}
        )


def test_an_identity_too_long_for_the_store_is_refused_with_a_usable_message(tmp_path):
    """Criterion: the identity scheme stays inside `path_for`'s limits.

    The store caps an identity at 200 characters, and the platform's own
    complaint about overrunning it is a `FileNotFoundError` "cannot find the path
    specified" — which points the reader at a missing directory. The compound is
    built from three caller-supplied parts, so this layer is where the overrun
    becomes reachable.
    """
    journal = RunJournal("run1", store=RecordStore(tmp_path))

    with pytest.raises(ValueError, match="too long"):
        journal.append(phase="plan", agent="a" * 250, sequence=0, record={"n": 1})
