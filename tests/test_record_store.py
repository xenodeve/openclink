"""An on-disk record store that survives the process (#98).

This repository had no persistence of any kind. `utils/storage_backend.py` is an
in-memory key/value cache with a TTL whose own docstring says it is
"confined to a single Python process" — it dies with the server, which is why
neither #96's dataset cache nor #89's phased-run journal could be built on it.

**Why a file per record rather than an append-only log.** "Append-only records
keyed by an identity" reads like a JSONL log, and that was the first design. It
was dropped for a reason the acceptance criteria name directly:

- *"Two concurrent writers do not interleave a record."* An `O_APPEND` write is
  atomic only below a platform-specific size, and Windows — the platform this
  repository is developed on — makes no such guarantee at all. Getting it right
  needs a lock, and a lock file is a second failure mode (a stale one after a
  crash) traded for the first.
- *"A corrupt or truncated file is reported, not silently treated as empty."* A
  log's characteristic failure is a torn final line, which every reader must then
  decide about. Writing each record through a temp file and `os.replace` means a
  half-written record is never visible under its own name: the atomicity is the
  filesystem's, not ours.

`clink/agents/base.py` already writes through `tempfile.mkstemp` for the same
reason, so this follows an existing pattern rather than inventing one.

Nothing calls this yet, by design — #98 is the prefactor, and its callers arrive
in #103 and #89.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

from utils.record_store import RecordStore, StoreCorruptError, default_store_dir


def test_a_record_survives_the_process_that_wrote_it(tmp_path):
    """The whole point, and the thing the in-memory backend cannot do.

    A second `RecordStore` over the same directory stands in for a restart: it
    shares no state with the first, so anything it reads came off the disk. A
    test that reused one instance would pass against a dictionary.
    """
    RecordStore(tmp_path).put("plan-1", {"agents": 3, "model": "gpt-5.6-luna"})

    reopened = RecordStore(tmp_path)

    assert reopened.get("plan-1") == {"agents": 3, "model": "gpt-5.6-luna"}


def test_a_record_is_retrievable_by_its_identity(tmp_path):
    store = RecordStore(tmp_path)
    store.put("plan-a", {"n": 1})
    store.put("plan-b", {"n": 2})

    assert store.get("plan-a") == {"n": 1}
    assert store.get("plan-b") == {"n": 2}


def test_an_unknown_identity_is_absent_rather_than_an_error(tmp_path):
    """Absence is an answer; a missing plan is not a broken store."""
    assert RecordStore(tmp_path).get("never-written") is None


def test_a_corrupt_record_is_reported_rather_than_read_as_absent(tmp_path):
    """The failure this store exists to make loud.

    Returning `None` here would be indistinguishable from "never written", and a
    caller would go on to recompute — or worse, treat a damaged dataset cache as
    a cold one and quietly act on nothing. The store cannot repair the file, so
    the only honest options are an error or a lie.
    """
    store = RecordStore(tmp_path)
    store.put("plan-1", {"n": 1})
    # Truncated mid-object, the shape a crashed writer would leave if the write
    # were not atomic — and the shape an external tool or disk fault still can.
    store.path_for("plan-1").write_text('{"n": 1', encoding="utf-8")

    with pytest.raises(StoreCorruptError) as caught:
        store.get("plan-1")

    assert "plan-1" in str(caught.value)


def test_a_record_torn_mid_character_is_corrupt_rather_than_an_unhandled_error(tmp_path):
    """The corruption a torn write actually produces, and it escaped.

    Every other corruption test writes *text*, which can only ever fail as
    invalid JSON. A real interrupted write cuts a multi-byte UTF-8 sequence in
    half, and that raises `UnicodeDecodeError` from `read_text` — outside the
    `try` that was meant to catch it, so the guard was dead code. Measured: this
    payload produced `UnicodeDecodeError`, not `StoreCorruptError`.

    A caller that catches the store's own error to recover would not catch this.
    """
    store = RecordStore(tmp_path)
    store.put("torn", {"n": "ก"})
    store.path_for("torn").write_bytes(b'{"n": "\xe0\xa4')

    with pytest.raises(StoreCorruptError):
        store.get("torn")


def test_an_identity_may_not_differ_from_another_only_by_case(tmp_path):
    """NTFS is case-insensitive, so two identities would silently share a record.

    Measured before the fix: `put("Plan-1", {"a": 1})` then
    `put("plan-1", {"b": 2})` left ONE file, and both `get`s returned `{"b": 2}`.
    A caller holding two distinct plan identities would read one plan's decision
    under the other's name, on the platform this fork is developed on.

    Refused rather than normalised: silently lowercasing would make `get` succeed
    for an identity that was never written, which is the same lie one step later.
    """
    store = RecordStore(tmp_path)

    with pytest.raises(ValueError) as caught:
        store.put("Plan-1", {"a": 1})

    assert "lowercase" in str(caught.value)


def test_an_identity_with_a_trailing_newline_is_refused(tmp_path):
    """`$` matches before a final newline — `re.match(r"...$", "abc\\n")` is truthy.

    Measured. The identity then reaches the filesystem and dies as
    `OSError [Errno 22] Invalid argument`, which is the class of raw platform
    error the length checks exist to replace.
    """
    with pytest.raises(ValueError):
        RecordStore(tmp_path).put("abc\n", {"n": 1})


def test_the_stored_identities_can_be_listed(tmp_path):
    """#89's journal reads its whole run back; keyed `get` alone cannot serve it.

    #98 exists to be shared by #96's dataset cache and #89's phased-run journal.
    A cache needs `get` by key; a journal needs to enumerate what a run wrote.
    Without this the store serves one of its two stated callers.

    Temp files must not appear — they are named `.tmp-*` precisely so a scan can
    tell them apart, and a listing that included one would hand out an identity
    that no `get` can read.
    """
    store = RecordStore(tmp_path)
    store.put("plan-1", {"n": 1})
    store.put("plan-2", {"n": 2})
    (tmp_path / ".tmp-leftover.json").write_text("{}", encoding="utf-8")

    assert sorted(store.identities()) == ["plan-1", "plan-2"]


def test_listing_an_absent_store_is_empty_rather_than_an_error(tmp_path):
    """First run, before anything has been written."""
    assert list(RecordStore(tmp_path / "not-created-yet").identities()) == []


def test_an_empty_file_is_corrupt_not_an_empty_record(tmp_path):
    """Zero bytes is the classic torn write, and `{}` is a plausible-looking lie."""
    store = RecordStore(tmp_path)
    store.put("plan-1", {"n": 1})
    store.path_for("plan-1").write_text("", encoding="utf-8")

    with pytest.raises(StoreCorruptError):
        store.get("plan-1")


def test_concurrent_writers_never_leave_a_spliced_record(tmp_path):
    """Two writers, one identity — the only way they can collide.

    Distinct identities cannot interleave when each record owns its file, so the
    contended case is the same key written twice at once. The record that lands
    must be one of the two written, never a splice of both. Payloads are sized so
    a non-atomic write would be visibly torn.

    **The failure this test was first blind to.** It originally let the writer
    threads die on their own exceptions and only inspected the final record —
    which passed, while `os.replace` was raising `PermissionError: [WinError 5]`
    on nearly every contended write. On Windows a rename fails outright if the
    destination is open, so a concurrent writer does not interleave, it *loses*.
    Asserting the outcome without asserting that both writers succeeded tested
    the easy half of the criterion.
    """
    store = RecordStore(tmp_path)
    first = {"who": "a", "pad": "a" * 50_000}
    second = {"who": "b", "pad": "b" * 50_000}
    failures: list[BaseException] = []

    def write(payload):
        for _ in range(20):
            try:
                store.put("contended", payload)
            except BaseException as exc:  # noqa: BLE001 - recorded, then asserted on
                failures.append(exc)
                return

    threads = [threading.Thread(target=write, args=(p,)) for p in (first, second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not failures, f"a concurrent write failed instead of racing cleanly: {failures[0]!r}"

    landed = store.get("contended")
    assert landed in (first, second), "the stored record is neither payload — it was spliced"


def test_a_reader_running_during_the_writes_never_sees_a_torn_record(tmp_path):
    """The criterion the test above only *looked* like it covered.

    `test_concurrent_writers_never_leave_a_spliced_record` inspects the store
    after both threads join — when nothing is in flight — so a torn state is
    unobservable by construction. Measured: with `put` replaced by a bare
    `path.write_text(payload)`, fully non-atomic, that test passed 3 runs out of
    3. It pins that the writers do not crash; it cannot pin atomicity.

    Contention is only visible from inside it. This reader runs while both
    writers do, and every read must be one of the two complete payloads — never
    a splice, never a `StoreCorruptError` from catching a half-written file.
    """
    store = RecordStore(tmp_path)
    first = {"who": "a", "pad": "a" * 200_000}
    second = {"who": "b", "pad": "b" * 200_000}
    store.put("contended", first)

    stop = threading.Event()
    bad: list[object] = []

    def write(payload):
        while not stop.is_set():
            store.put("contended", payload)

    def read():
        while not stop.is_set():
            try:
                seen = store.get("contended")
            except BaseException as exc:  # noqa: BLE001 - recorded, then asserted on
                bad.append(exc)
                return
            if seen not in (first, second):
                bad.append(seen)
                return

    workers = [threading.Thread(target=write, args=(p,)) for p in (first, second)]
    workers.append(threading.Thread(target=read))
    for w in workers:
        w.start()
    time.sleep(0.5)
    stop.set()
    for w in workers:
        w.join(timeout=5)

    assert not bad, f"a reader observed a record that was neither payload: {bad[0]!r}"


def test_a_briefly_held_destination_is_waited_out(tmp_path):
    """The transient case the retry exists for, reached without threads.

    On Windows `os.replace` onto an open destination raises
    `PermissionError: [WinError 5]`; on POSIX it succeeds. The holder here
    releases after a few milliseconds, which is what a competing writer or a
    passing reader actually looks like — so the write must land rather than fail.
    """
    store = RecordStore(tmp_path)
    store.put("held", {"n": 1})

    handle = store.path_for("held").open("r", encoding="utf-8")
    timer = threading.Timer(0.05, handle.close)
    timer.start()
    try:
        store.put("held", {"n": 2})
    finally:
        timer.cancel()
        handle.close()

    assert store.get("held") == {"n": 2}


def test_a_destination_held_open_indefinitely_raises_rather_than_losing_the_write(tmp_path):
    """A platform constraint stated, not retried away.

    Windows will not let a rename land while anyone holds the destination open,
    and no amount of backoff changes that — the honest outcome is an error. What
    must NOT happen is the write silently not landing: a caller told nothing,
    whose record is gone, is the worse half of the concurrency criterion.

    Nothing in this repository holds a record open — `get` uses `read_text`,
    which closes immediately — so this is the pathological case, pinned so the
    bounded retry cannot quietly become an unbounded one or a swallowed failure.

    POSIX has no such restriction, so the rename simply succeeds there.
    """
    store = RecordStore(tmp_path)
    store.put("held", {"n": 1})

    with store.path_for("held").open("r", encoding="utf-8"):
        if os.name == "nt":
            with pytest.raises(PermissionError):
                store.put("held", {"n": 2})
            assert store.get("held") == {"n": 1}, "the previous record must survive a write that did not land"
        else:
            store.put("held", {"n": 2})
            assert store.get("held") == {"n": 2}


def test_a_failed_write_leaves_the_previous_record_intact(tmp_path):
    """Atomicity has a second half: the old value must survive a bad new one.

    A store that truncated the target before serialising would destroy a good
    record whenever the new one could not be encoded.
    """
    store = RecordStore(tmp_path)
    store.put("plan-1", {"n": 1})

    with pytest.raises(TypeError):
        store.put("plan-1", {"bad": object()})

    assert store.get("plan-1") == {"n": 1}


def test_no_temporary_file_is_left_behind(tmp_path):
    """A temp file that survived would be read back as a record on the next scan."""
    store = RecordStore(tmp_path)
    store.put("plan-1", {"n": 1})

    assert [p.name for p in tmp_path.iterdir()] == [store.path_for("plan-1").name]


def test_an_identity_cannot_escape_the_store_directory(tmp_path):
    """The identity becomes a filename, so it is untrusted input.

    #103 mints these, but the store must not depend on its caller being careful:
    a traversal here writes wherever the server can write.
    """
    store = RecordStore(tmp_path)

    for hostile in ("../escape", "a/b", "..", ""):
        with pytest.raises(ValueError):
            store.put(hostile, {"n": 1})


def test_an_over_long_identity_is_refused_with_a_readable_reason(tmp_path):
    """Found by scrutinizing this module, not by a criterion.

    A 300-character identity produced
    `FileNotFoundError: [WinError 3] The system cannot find the path specified`
    — measured. The path exists; the *filename component* exceeds the platform
    limit, and every word of that message points the reader at a missing
    directory instead. Filesystem limits are not something a caller should have
    to know to use a keyed store, so the store states its own bound.
    """
    store = RecordStore(tmp_path)

    with pytest.raises(ValueError) as caught:
        store.put("a" * 300, {"n": 1})

    assert "too long" in str(caught.value)
    # Generous next to what #103 actually mints — a UUID is 36 characters.
    store.put("a" * 60, {"n": 1})


def test_a_store_directory_too_deep_for_the_identity_names_the_directory(tmp_path):
    """The same misleading error, reached the other way.

    Windows caps the WHOLE path at 260 by default, so a deep store directory
    shrinks the usable identity below the component limit and fails with the same
    `cannot find the path specified`. Reported here naming the DIRECTORY, because
    that is the part the caller configured and can change; the identity usually
    is not theirs to shorten.
    """
    deep = tmp_path.joinpath(*[f"segment{n:03d}" for n in range(20)])
    store = RecordStore(deep)

    with pytest.raises(ValueError) as caught:
        store.put("plan-1", {"n": 1})

    message = str(caught.value)
    assert "too long" in message
    assert "OPENCLINK_STORE_DIR" in message


def test_the_default_location_is_outside_the_repository(monkeypatch):
    """A store inside the tree gets committed, or wiped by a clean checkout.

    Matches `clink/constants.py`'s `~/.openclink/cli_clients` rather than
    inventing a second home for this project's own files.
    """
    monkeypatch.delenv("OPENCLINK_STORE_DIR", raising=False)

    location = default_store_dir()

    # Exact equality, and nothing weaker beside it. A first version also asserted
    # `Path.cwd() not in location.parents`, which reads like a repo-tree check and
    # is not one: run from `tests/`, it passes for a location plainly inside the
    # repository. A check that can be satisfied by the wrong thing is worse than
    # no check, because it looks like coverage.
    assert location == Path.home() / ".openclink" / "store"


def test_the_location_is_configurable(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCLINK_STORE_DIR", str(tmp_path / "elsewhere"))

    assert default_store_dir() == tmp_path / "elsewhere"


def test_the_store_creates_its_directory_rather_than_requiring_one(tmp_path):
    """First run on a fresh machine has no `~/.openclink/store`."""
    nested = tmp_path / "not" / "yet" / "there"
    RecordStore(nested).put("plan-1", {"n": 1})

    assert json.loads((nested / "plan-1.json").read_text(encoding="utf-8")) == {"n": 1}
