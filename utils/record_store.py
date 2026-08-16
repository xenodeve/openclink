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
# mints it. Anchored and deliberately narrow: a leading alphanumeric rules out
# `.`, `..` and dotfiles in one clause, and the absence of `/`, `\` and `:`
# means no identity can address anything outside the store directory.
_SAFE_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

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


class RecordStore:
    """Records keyed by identity, added and never mutated in place."""

    def __init__(self, directory: Path | str | None = None) -> None:
        self.directory = Path(directory) if directory is not None else default_store_dir()

    def path_for(self, identity: str) -> Path:
        if not _SAFE_IDENTITY.match(identity or ""):
            raise ValueError(
                f"unusable record identity {identity!r}: expected [A-Za-z0-9][A-Za-z0-9._-]*, "
                "so that an identity cannot address anything outside the store directory"
            )
        return self.directory / f"{identity}.json"

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
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

        if not raw.strip():
            raise StoreCorruptError(f"record {identity!r} at {path} is empty — a torn write, not an empty record")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise StoreCorruptError(f"record {identity!r} at {path} is not readable JSON: {exc}") from exc
