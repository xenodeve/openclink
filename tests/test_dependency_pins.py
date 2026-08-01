"""Guard against requirements.txt drifting from pyproject.toml.

`pyproject.toml` bounds `mcp` at `<2` because mcp 2.0.0 removed
`Server.list_tools`, which `server.py` uses as a decorator at import time.
`requirements.txt` carried an unbounded `mcp>=1.0.0` and omitted `pywinpty`
entirely, so installers that read it produced an unimportable tree while
`pyproject.toml` looked correct (#17).

Parsed as text on purpose: `tomllib` is 3.11+ and this project supports 3.9.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_runtime_dependencies() -> list[str]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"^dependencies = \[(.*?)^\]", text, re.S | re.M)
    assert block, "pyproject.toml has no [project] dependencies block"
    return re.findall(r'"([^"]+)"', block.group(1))


def _requirements_entries() -> list[str]:
    entries = []
    for raw in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            entries.append(line)
    return entries


def _distribution_name(specifier: str) -> str:
    return re.split(r"[<>=!;\[\s]", specifier, maxsplit=1)[0].strip().lower()


def test_requirements_declares_every_pyproject_runtime_dependency_identically():
    """Every pyproject runtime dependency appears in requirements.txt verbatim.

    One-directional on purpose: requirements.txt may carry extra entries
    (e.g. the 3.8-only `importlib-resources` backport) that pyproject omits.
    """
    requirements = {_distribution_name(entry): entry for entry in _requirements_entries()}

    problems = []
    for dependency in _pyproject_runtime_dependencies():
        name = _distribution_name(dependency)
        if name not in requirements:
            problems.append(f"absent from requirements.txt: {dependency!r}")
        elif requirements[name] != dependency:
            problems.append(f"drift: {dependency!r} (pyproject) vs {requirements[name]!r} (requirements)")

    assert not problems, "requirements.txt disagrees with pyproject.toml:\n  " + "\n  ".join(problems)
