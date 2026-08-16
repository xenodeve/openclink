"""An on-disk record store that outlives the process (#98).

This repository had no persistence. `utils/storage_backend.py` is an in-memory
key/value cache whose own docstring says it is "confined to a single Python
process" — it dies with the server, so neither #96's dataset cache nor #89's
phased-run journal could be built on it. Built once here, with no callers yet,
so the two of them share a storage layer instead of growing one each.

**One file per record, written through a temp file and `os.replace`.** The
alternative — an append-only JSONL log — was dropped because of the two
acceptance criteria that are actually hard:

- *Two concurrent writers must not interleave a record.* An `O_APPEND` write is
  atomic only below a platform-specific size, and Windows guarantees nothing
  here. Making it safe needs a lock file, which trades a rare failure for a
  permanent one: a stale lock after a crash.
- *A corrupt or truncated file must be reported.* A log's characteristic damage
  is a torn final line, and every reader then has to decide what to do about it.
  Under `os.replace` a half-written record is never visible under its own name at
  all — the atomicity belongs to the filesystem rather than to this code.

`clink/agents/base.py` already writes through `tempfile.mkstemp` for the same
reason, so this follows the repository rather than inventing for it.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path

from utils.env import get_env

# The identity becomes a filename, so it is untrusted input even though #103
# mints it. Deliberately narrow: a leading alphanumeric rules out `.`, `..` and
# dotfiles in one clause, and the absence of `/`, `\` and `:` means no identity
# can address anything outside the store directory.
#
# Lowercase only, and matched with `fullmatch` rather than `match`: `$` matches BEFORE a
# final newline, so `re.match(r"...$", "abc\n")` is truthy — measured — and the
# identity then reaches the filesystem as `OSError [Errno 22] Invalid argument`.
#
# The case restriction is not tidiness. NTFS is case-insensitive, so `Plan-1` and
# `plan-1` name one file: measured, two `put`s left a single record and both
# `get`s returned the second payload. Two distinct plan identities would read
# each other's decision, on the platform this fork is developed on. Refused
# rather than silently lowercased, because normalising makes `get` succeed for an
# identity nobody wrote — the same lie, one step later.
_SAFE_IDENTITY = re.compile(r"[a-z0-9][a-z0-9._-]*")

# A filename component is capped at 255 on every filesystem this runs on, and
# `.json` takes five of them. Bounded here because the platform's own complaint
# is actively misleading: a 300-character identity raises
# `FileNotFoundError: [WinError 3] The system cannot find the path specified`,
# every word of which points the reader at a missing directory. Generous next to
# a UUID's 36.
_MAX_IDENTITY_LENGTH = 200

# Windows' default MAX_PATH, minus a little room for the temp file's own prefix.
_MAX_PATH_LENGTH = 240

STORE_DIR_ENV = "OPENCLINK_STORE_DIR"


class StoreCorruptError(RuntimeError):
    """A record exists on disk and could not be read as one.

    Distinct from absence on purpose. Returning `None` for damage would be
    indistinguishable from "never written", and a caller would recompute — or
    read a damaged dataset cache as a cold one and act on nothing.
    """


def default_store_dir() -> Path:
    """Where records live when nobody says otherwise.

    Outside the repository tree, matching `clink/constants.py`'s
    `~/.openclink/cli_clients` rather than opening a second home for this
    project's files. A store inside the tree gets committed, or wiped by a clean
    checkout — both silent.
    """
    configured = get_env(STORE_DIR_ENV)
    if configured and configured.strip():
        return Path(configured.strip()).expanduser()
    return Path.home() / ".openclink" / "store"


# Windows refuses a rename onto a destination anyone has open — reader or
# writer — with `PermissionError: [WinError 5]`, where POSIX just succeeds. So
# the failure mode of two concurrent writers there is not a spliced record, it is
# one of them LOSING, which is worse: the caller is told nothing and its record
# is gone. Measured while writing #98 — the first version raised on nearly every
# contended write while its test still passed, because the exception died in the
# worker thread.
#
# Retried rather than locked: the holder is typically gone within milliseconds,
# and a lock file trades this for a stale lock after a crash. Bounded, and the
# original error propagates if it never clears — a write that did not land must
# not look like one that did.
_REPLACE_ATTEMPTS = 20
_REPLACE_BACKOFF_SECONDS = 0.01


def _replace_with_retry(source: str, destination: Path) -> None:
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_BACKOFF_SECONDS)


def _read_with_retry(path: Path) -> bytes:
    """The reader's half of the same Windows rule.

    `os.replace` is atomic for WRITERS — a reader sees the old bytes or the new
    ones, never a splice. It is not transparent to readers: while the rename is
    in flight the destination is briefly inaccessible and `read_bytes` raises
    `PermissionError(13)`. Found by a test that reads *during* concurrent writes;
    the earlier tests only read after the writers had joined, so they never
    touched it.

    Same bounded wait as the writer, and the same rule: if it never clears, the
    error propagates. A read that could not happen must not look like absence.
    """
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            return path.read_bytes()
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_BACKOFF_SECONDS)
    raise AssertionError("unreachable")  # pragma: no cover


class RecordStore:
    """Records keyed by identity.

    `put` REPLACES the record under an identity — #96's dataset cache refreshes
    in place, so overwrite is required, and calling that "append-only" would be
    the class of docstring that reads true and is not. What is append-only is the
    set of identities: a record is written whole or not at all, never edited.
    """

    def __init__(self, directory: Path | str | None = None) -> None:
        self.directory = Path(directory) if directory is not None else default_store_dir()

    def path_for(self, identity: str) -> Path:
        candidate = identity or ""
        if not _SAFE_IDENTITY.fullmatch(candidate):
            if _SAFE_IDENTITY.fullmatch(candidate.lower()):
                raise ValueError(
                    f"record identity {identity!r} must be lowercase: a case-insensitive "
                    "filesystem would make it share a file with an identity differing only by case"
                )
            raise ValueError(
                f"unusable record identity {identity!r}: expected [a-z0-9][a-z0-9._-]*, "
                "so that an identity cannot address anything outside the store directory"
            )
        if len(identity) > _MAX_IDENTITY_LENGTH:
            raise ValueError(
                f"record identity is too long ({len(identity)} characters, limit "
                f"{_MAX_IDENTITY_LENGTH}) — the filesystem would reject the filename "
                "with a message about a missing path"
            )
        path = self.directory / f"{identity}.json"
        # The other half of the same trap, and it fails identically: Windows caps
        # the WHOLE path at 260 by default, so a deep store directory shrinks the
        # usable identity below the component limit above. Checked here because
        # the platform's complaint is the same misleading "cannot find the path
        # specified", and because the actionable part is the directory — which
        # the caller configured and can change — not the identity.
        if len(str(path)) > _MAX_PATH_LENGTH:
            raise ValueError(
                f"record path is too long ({len(str(path))} characters, limit {_MAX_PATH_LENGTH}): "
                f"the store directory {self.directory} is too deeply nested for identity {identity!r}. "
                f"Set {STORE_DIR_ENV} to a shorter path."
            )
        return path

    def put(self, identity: str, record: dict) -> None:
        path = self.path_for(identity)
        # Serialised BEFORE anything on disk is touched, so an unencodable record
        # raises without having destroyed the one already stored under that name.
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True)

        self.directory.mkdir(parents=True, exist_ok=True)
        # Same directory as the target: `os.replace` is only atomic within one
        # filesystem, and the system temp dir is routinely on another.
        fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            _replace_with_retry(tmp, path)
        except BaseException:
            # A leftover temp file would be read back as a record by anything
            # that scans the directory.
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def get(self, identity: str) -> dict | None:
        path = self.path_for(identity)
        # Read BYTES and decode inside the guard. `read_text` decodes as it reads,
        # so a `UnicodeDecodeError` was raised outside the `except` that named it
        # and the guard was dead code — measured. That matters more than it looks:
        # an interrupted write cuts a multi-byte UTF-8 sequence in half, so it is
        # the corruption a torn record actually has, and a caller catching
        # StoreCorruptError to recover would not have caught it.
        try:
            raw = _read_with_retry(path)
        except FileNotFoundError:
            return None

        if not raw.strip():
            raise StoreCorruptError(f"record {identity!r} at {path} is empty — a torn write, not an empty record")
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise StoreCorruptError(f"record {identity!r} at {path} is not readable JSON: {exc}") from exc

    def identities(self) -> list[str]:
        """Every identity currently stored, in no particular order.

        #98 is shared by #96's dataset cache and #89's phased-run journal, and
        those want different things: a cache reads by key, a journal reads its
        whole run back. Without this the store served one of its two callers.

        Temp files are excluded by their `.tmp-` prefix rather than by parsing —
        the prefix starts with a dot, which `_SAFE_IDENTITY` forbids, so no
        listed identity can ever collide with one in flight.
        """
        if not self.directory.is_dir():
            return []
        return [p.stem for p in self.directory.glob("*.json") if not p.name.startswith(".tmp-")]
