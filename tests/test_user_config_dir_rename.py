"""User config in the old directory keeps being read after the rename (#94).

`~/.pal/cli_clients` is where a user puts their own clink client overrides, and
`CHANGES-FORK.md` recommends it specifically because it survives
`uv tool upgrade`. It lives outside the repository, so no rename sweep can reach
it.

Pointing the registry at `~/.openclink/cli_clients` alone does not error — the
new directory is simply empty, the user's override silently stops applying, and
the client falls back to the bundled preset. On this fork that failure is
concrete: the documented Windows fix for cursor (`"env": {"SHELL": "cmd.exe"}`)
lives in exactly such a file, and losing it turns every cursor delegation into a
text-only responder that answers from the prompt with exit 0.

So both directories are searched, and the new one wins when both define the same
client — an explicit new override should beat a stale one.
"""

from __future__ import annotations

import json
import logging

import pytest

from clink.registry import ClinkRegistry


def _client_config(name: str, command: str) -> dict:
    return {
        "name": name,
        "command": command,
        "additional_args": [],
        "env": {},
        "roles": {"default": {"prompt_path": "systemprompts/clink/default.txt", "role_args": []}},
    }


@pytest.fixture()
def two_config_dirs(tmp_path, monkeypatch):
    """Point the registry's user directories at temp dirs, leaving bundled configs alone."""
    legacy = tmp_path / "legacy" / "cli_clients"
    current = tmp_path / "current" / "cli_clients"
    legacy.mkdir(parents=True)
    current.mkdir(parents=True)
    monkeypatch.setattr("clink.registry.LEGACY_USER_CONFIG_DIR", legacy, raising=False)
    monkeypatch.setattr("clink.registry.USER_CONFIG_DIR", current, raising=False)
    return legacy, current


# A real client name, because the registry refuses one it has no internal defaults
# for. That makes these tests stronger rather than weaker: the assertion is that the
# user's file *overrode the bundled preset*, which is the whole point of the
# directory — asserting the name merely appeared would pass on the bundled config
# alone, with the user directory never read at all.
CLIENT = "opencode"


def test_an_override_in_the_old_directory_is_still_applied(two_config_dirs):
    legacy, _ = two_config_dirs
    (legacy / f"{CLIENT}.json").write_text(json.dumps(_client_config(CLIENT, "old-cli")), encoding="utf-8")

    executable = ClinkRegistry().get_client(CLIENT).executable[-1]

    assert executable.endswith("old-cli"), (
        f"the bundled preset won ({executable!r}) — the previous user config directory "
        "was not read, so every existing user's override silently stopped applying"
    )


def test_using_the_old_directory_tells_the_user_where_to_move_it(two_config_dirs, caplog):
    """Reading it silently is only half of what #94 asked for.

    The issue says: "Read both locations for a deprecation period, **with the old
    one logged when used**" — and the acceptance criterion is that no user's
    config "stops being read *without being told*". Reading it forever and never
    saying so satisfies the first half and quietly fails the second: the
    deprecation never ends, because nobody is ever told it started.

    `debug` would not do. The registry loads at server start, where the default
    level hides it, so the one user who needs the message is the one who cannot
    see it. The message must also name the new directory — "deprecated" without a
    destination is a complaint, not an instruction.
    """
    legacy, _ = two_config_dirs
    (legacy / f"{CLIENT}.json").write_text(json.dumps(_client_config(CLIENT, "old-cli")), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="clink.registry"):
        ClinkRegistry()

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(str(legacy) in message for message in warnings), (
        "loading an override from the previous config directory produced no warning naming it — "
        f"the user is never told to move it. warnings seen: {warnings}"
    )


def test_a_user_only_on_the_new_directory_is_not_nagged(two_config_dirs, caplog):
    """The other direction, so the fix cannot be "warn unconditionally".

    A warning every start for a path the user does not use is noise that trains
    them to ignore the one that matters.
    """
    _, current = two_config_dirs
    (current / f"{CLIENT}.json").write_text(json.dumps(_client_config(CLIENT, "new-cli")), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="clink.registry"):
        ClinkRegistry()

    nags = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING and ".pal" in r.getMessage()]
    assert not nags, f"warned about the previous directory when nothing was there: {nags}"


def test_the_new_directory_wins_when_both_define_the_same_client(two_config_dirs):
    legacy, current = two_config_dirs
    (legacy / f"{CLIENT}.json").write_text(json.dumps(_client_config(CLIENT, "old-cli")), encoding="utf-8")
    (current / f"{CLIENT}.json").write_text(json.dumps(_client_config(CLIENT, "new-cli")), encoding="utf-8")

    executable = ClinkRegistry().get_client(CLIENT).executable[-1]

    assert executable.endswith("new-cli"), (
        f"got {executable!r} — the old directory overrode the new one, so a stale "
        "override would outlive the one the user just wrote"
    )
