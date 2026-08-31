"""Give every plan an identity, and put it on disk before anyone is told (#103).

**The order is the point.** An identity handed to a caller that does not yet
exist on disk is an identity an external gate cannot validate — and the gate in
the paired repository is the whole reason the identity exists. A plan written
after the response is emitted has a window in which a spawn can quote an identity
that resolves to nothing, and that window is exactly when a fast caller acts.

**Not-found is an error, never an empty plan.** A gate that reads a missing plan
as `{}` cannot tell "this spawn was never authorised" from "this spawn was
authorised to do nothing", and the two demand opposite responses.

**Provenance travels with the plan** so the decision can be reproduced: what the
dataset said and when it was last written. Until #102 fetches, that is the
committed fixture's own content hash and modification time, and the record says
which of the two it is rather than implying a network fetch that never happened.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.selection import DATASET_PATH
from utils.record_store import RecordStore

# `[a-z0-9][a-z0-9._-]*` is what the store accepts, so a lowercase hex uuid with
# a readable prefix fits without transformation. The prefix is not decoration: a
# store shared with the phased-run journal (#96 builds one storage layer, not
# two) needs its identities to say what they are.
_IDENTITY_PREFIX = "plan-"


class PlanNotFound(LookupError):
    """No plan is stored under that identity.

    Raised rather than returning `None` or `{}`: a gate that cannot distinguish
    "never authorised" from "authorised to do nothing" will eventually let one
    through as the other.
    """


def new_identity() -> str:
    """A fresh, unguessable identity for one plan.

    Random rather than derived from the scope. Two identical scopes are two
    separate authorisations — the identity ties a spawn to the decision that
    permitted it, not to the shape of the request, so collapsing them would let
    one plan's identity authorise a different plan's run.
    """
    return f"{_IDENTITY_PREFIX}{uuid.uuid4().hex}"


def dataset_provenance(path: Path | None = None) -> dict[str, Any]:
    """What the ranking rested on, in a form that can be checked later.

    A fingerprint of the exact bytes, so a plan can be re-derived and the answer
    compared. `source` is stated explicitly because the field will keep its name
    when #102 starts fetching, and a `fetched_at` that is really a file's
    modification time would quietly become a claim about a network call.
    """
    source = path or DATASET_PATH
    raw = source.read_bytes()
    return {
        "source": "committed_fixture",
        "fingerprint_sha256": hashlib.sha256(raw).hexdigest(),
        "fetched_at": datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc).isoformat(),
    }


def _store() -> RecordStore:
    # Constructed per call rather than at import, so `OPENCLINK_STORE_DIR` is
    # read when the store is used. Bound at import, a process that set it after
    # loading this module would write somewhere else and never be told.
    return RecordStore()


def save(identity: str, plan: dict[str, Any], provenance: dict[str, Any]) -> None:
    """Write the plan whole, under its identity, before the caller hears about it."""
    _store().put(identity, {"identity": identity, "plan": plan, "dataset": provenance})


def fetch(identity: str) -> dict[str, Any]:
    """The stored plan, or a refusal that names what was looked for."""
    record = _store().get(identity)
    if record is None:
        raise PlanNotFound(
            f"no plan is stored under identity {identity!r}. " "A spawn quoting it was not authorised by this layer."
        )
    return record
