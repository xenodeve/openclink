"""A durable record of a multi-agent run, one record per agent return (#149).

#89 asked for this as "append-only JSONL on disk, one file per run". #98 had
already measured that shape and rejected it (`utils/record_store.py:9-20`): an
`O_APPEND` write is atomic only below a platform-specific size and "Windows
guarantees nothing here", and a log's characteristic damage is a torn final line
that lands on every reader. A phased run is concurrent by construction — that is
what a fan-out is — so the interleaving objection is the normal case here rather
than an edge one.

So this keeps the store's one-file-per-record primitive and gives each agent
return its own identity, `run-<id>.<phase>.<agent>`, reconstructing the run by
prefix over `RecordStore.identities()`. That yields what the PRD wanted — one
durable record per agent return, a partial run salvageable — without
reintroducing the torn line, and it builds on #98 rather than beside it.

**The caller supplies the sequence.** The journal cannot observe production order
without inventing it: deriving a counter from the records already present is a
read-then-write race, and a fan-out is exactly where two agents return at once,
so the counter would collide precisely when it mattered. The orchestrator that
dispatched the work is the thing that knows the order, so it says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from utils.record_store import RecordStore

# The compound identity is split on `.`, so `.` is a separator here and may not
# appear inside a part. `RecordStore.path_for` permits it — its own grammar is
# `[a-z0-9][a-z0-9._-]*` — which is why the refusal has to live at this layer:
# an agent named `x.y` would otherwise file its record under a run nobody wrote
# to, and the run it belonged to would read back short by one.
#
# Lowercase for the same reason the store is: NTFS is case-insensitive, so two
# parts differing only by case name one file.
_SAFE_PART = re.compile(r"[a-z0-9][a-z0-9_-]*")

_PREFIX = "run-"
_SEPARATOR = "."


def _checked(part: str, role: str) -> str:
    if not _SAFE_PART.fullmatch(part or ""):
        raise ValueError(
            f"unusable {role} {part!r}: expected [a-z0-9][a-z0-9_-]*, so that it cannot "
            f"contain the {_SEPARATOR!r} that separates a run from its phase and agent"
        )
    return part


@dataclass(frozen=True)
class JournalEntry:
    """One agent return, read back."""

    sequence: int
    phase: str
    agent: str
    record: dict


class RunJournal:
    """The journal of one run, over the shared record store."""

    def __init__(self, run_id: str, store: RecordStore | None = None) -> None:
        self.run_id = _checked(run_id, "run identifier")
        self.store = store if store is not None else RecordStore()

    def _identity(self, phase: str, agent: str) -> str:
        return _SEPARATOR.join((f"{_PREFIX}{self.run_id}", phase, agent))

    def append(self, *, phase: str, agent: str, sequence: int, record: dict) -> None:
        """Record what one agent returned.

        The length limits are left to `RecordStore.path_for`, which already caps
        the identity and the whole path and explains both — the compound is built
        from caller-supplied parts, so overrunning them is reachable from here,
        but there is no second version of that rule worth keeping in sync.
        """
        identity = self._identity(_checked(phase, "phase"), _checked(agent, "agent identifier"))
        # `phase` and `agent` are stored as well as encoded in the identity: the
        # reader takes them from the record, so nothing downstream has to parse a
        # filename back into fields.
        self.store.put(identity, {"sequence": sequence, "phase": phase, "agent": agent, "record": record})

    def read(self) -> list[JournalEntry]:
        """Every agent return of this run, in the order it was produced.

        Ordered by the sequence carried in the record. `identities()` documents
        itself as returning identities "in no particular order", so ordering by
        that listing — or by the identity, which sorts alphabetically — would be
        a fact nobody established. The identity is the tie-break only, so that a
        caller who reuses a sequence still gets a stable read rather than an
        arbitrary one.

        A run that died mid-phase needs no marker: what is on disk is what
        completed, and an agent that never returned is simply absent, which is
        what distinguishes it from one that returned an empty record.
        """
        prefix = f"{_PREFIX}{self.run_id}{_SEPARATOR}"
        found = []
        for identity in self.store.identities():
            if not identity.startswith(prefix):
                continue
            stored = self.store.get(identity)
            found.append(
                (
                    identity,
                    JournalEntry(
                        sequence=stored["sequence"],
                        phase=stored["phase"],
                        agent=stored["agent"],
                        record=stored["record"],
                    ),
                )
            )
        found.sort(key=lambda pair: (pair[1].sequence, pair[0]))
        return [entry for _, entry in found]
