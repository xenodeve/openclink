"""Every Python block embedded in `run-server.sh` is syntactically valid (#91, #94).

Setup does its JSON surgery in Python blocks embedded in the shell script — ten
of them, between 25 and 62 lines each. A syntax error in one does not fail the
script: `python3` exits non-zero, the surrounding `|| true` or `2>/dev/null`
swallows it, and setup reports success having silently skipped a client's
registration. That is why they need an assertion rather than a reading.

**This file exists because of how the first attempt to check them failed.** A
throwaway extractor was written for exactly this, found 1 of 4 blocks, and
printed that everything parsed. A later version found 6 of 10 and did the same —
its heredoc pattern required the tag to end the line, so every block launched as
`<<'PY' 2>/dev/null` or `<<'PY' | tr -d '\\n'` was skipped in silence. Both runs
were green. Both covered nothing that mattered.

So the coverage assertion comes first here, and it is the point of the file: the
count of blocks extracted must equal the count of `python3` invocations found
independently. A check that cannot prove what it looked at is not evidence, and a
partial check that prints "all OK" is worse than no check, because it retires the
question.

**Scope, stated.** This proves the blocks PARSE. It does not prove they do the
right thing to a real config file — that needs a run on a clean machine (#91).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "run-server.sh"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _invocations(lines: list[str]) -> list[int]:
    """Ground truth, found without reference to how blocks are extracted."""
    return [
        n
        for n, line in enumerate(lines, 1)
        if re.search(r"python3 -c \"|python3 - ", line) and not line.lstrip().startswith("#")
    ]


def _blocks(src: str) -> list[tuple[str, int, str]]:
    lines = src.splitlines()
    found: list[tuple[str, int, str]] = []

    i = 0
    while i < len(lines):
        if re.search(r"python3 -c \"$", lines[i]):
            body, j = [], i + 1
            while j < len(lines) and not re.match(r'^"( |$)', lines[j]):
                body.append(lines[j])
                j += 1
            if j >= len(lines):
                raise AssertionError(f"unterminated `python3 -c` block starting at line {i + 1}")
            found.append(("-c", i + 1, "\n".join(body)))
            i = j
        i += 1

    # `[^\n]*` after the tag is load-bearing: the blocks are launched with
    # trailing `2>/dev/null`, `| tr -d '\n'` and `|| true`, and requiring the tag
    # to end the line is what made an earlier version of this check cover 6 of 10.
    for match in re.finditer(r"python3 - [^\n]*<<'([A-Z_]+)'[^\n]*\n(.*?)\n\s*\1\s*$", src, re.S | re.M):
        found.append(("heredoc", src[: match.start()].count("\n") + 1, match.group(2)))

    return sorted(found, key=lambda b: b[1])


def test_the_extractor_reaches_every_embedded_block():
    """Without this, every assertion below is over an unknown subset."""
    src = _source()
    invocations = _invocations(src.splitlines())
    starts = {start for _, start, _ in _blocks(src)}

    assert len(starts) == len(invocations), (
        f"extracted {len(starts)} blocks but found {len(invocations)} `python3` invocations. "
        f"Missed: {sorted(set(invocations) - starts)}. Fix the extractor before trusting "
        "anything it reports — a partial check that passes retires the question."
    )


@pytest.mark.parametrize("index", range(10))
def test_each_embedded_block_compiles(index: int):
    """Parametrized so a failure names which block, not just that one failed.

    The range is fixed at the current count deliberately: adding an eleventh block
    without extending it fails `test_the_extractor_reaches_every_embedded_block`
    above, which is the signal to come back here.
    """
    blocks = _blocks(_source())
    assert index < len(blocks), f"only {len(blocks)} blocks found; expected at least {index + 1}"
    kind, start, code = blocks[index]

    # Shell interpolates `$var` before python ever sees it, so substitute a bare
    # name. `\"` is the shell's escaping inside a double-quoted `-c` argument.
    probe = re.sub(r"\\?\$\{?[A-Za-z_][A-Za-z_0-9]*\}?", "PLACEHOLDER", code).replace('\\"', '"')

    try:
        compile(probe, f"run-server.sh:{start}", "exec")
    except SyntaxError as exc:
        raise AssertionError(
            f"the {kind} block at run-server.sh:{start} is not valid Python: "
            f"{exc.msg} at block-line {exc.lineno}. Setup would swallow this and report success."
        ) from exc
