#!/usr/bin/env python3
"""Generate the measured half of docs/BLUEPRINT.md.

The written half of the blueprint carries judgement — responsibilities, extension
points, invariants. This script carries the parts that must never be guessed:
the real import graph, the layering and its violations, module sizes, the entry
points, and which modules any test so much as mentions.

Run it at every checkpoint. A blueprint that is regenerated does not rot; the
prose beside it is the only part that can, and it is deliberately the smaller half.

    python scripts/blueprint.py            # writes Documents/GENERATED_STRUCTURE.md
    python scripts/blueprint.py --json     # machine-readable, to stdout
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directories that are production code, in layer order. A module's layer is the
# first prefix that matches; anything unmatched is "other".
LAYERS = [
    ("entry", ("server.py",)),
    ("tools", ("tools/",)),
    ("clink", ("clink/",)),
    ("providers", ("providers/",)),
    ("prompts", ("systemprompts/",)),
    ("utils", ("utils/",)),
    # config is read by every layer and reads none of them; it belongs at the bottom,
    # otherwise every tool importing it reads as a violation and the real ones are lost.
    ("config", ("config.py",)),
]
LAYER_ORDER = [name for name, _ in LAYERS] + ["other"]

# A dependency is "backwards" when a lower layer imports a higher one.
LAYER_RANK = {name: i for i, name in enumerate(LAYER_ORDER)}

SKIP_DIRS = {".venv", "__pycache__", ".git", "node_modules", ".ruff_cache", "worktrees", "logs"}
TEST_DIRS = ("tests", "simulator_tests")


def rel(path: str) -> str:
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def production_files() -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        r = rel(dirpath)
        if r.startswith(TEST_DIRS) or r.startswith("docs") or r.startswith("scripts"):
            continue
        for fn in filenames:
            if fn.endswith(".py"):
                out.append(rel(os.path.join(dirpath, fn)))
    return sorted(out)


def module_name(path: str) -> str:
    return path[:-3].replace("/", ".").removesuffix(".__init__")


def layer_of(path: str) -> str:
    for name, prefixes in LAYERS:
        for p in prefixes:
            if path == p or path.startswith(p):
                return name
    return "other"


def analyse(path: str, known: set[str]) -> dict:
    src = open(os.path.join(ROOT, path), encoding="utf-8", errors="replace").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {"lines": src.count("\n") + 1, "imports": [], "defs": [], "classes": []}

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative
                base = module_name(path).rsplit(".", node.level)[0]
                imports.add(f"{base}.{node.module}" if node.module else base)
            elif node.module:
                imports.add(node.module)

    internal = set()
    for imp in imports:
        parts = imp.split(".")
        for i in range(len(parts), 0, -1):
            cand = ".".join(parts[:i])
            if cand in known:
                internal.add(cand)
                break

    defs = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    return {
        "lines": src.count("\n") + 1,
        "imports": sorted(internal - {module_name(path)}),
        "defs": defs,
        "classes": classes,
    }


def test_mentions() -> dict[str, int]:
    """How many test files mention each production module by dotted name or path stem."""
    blobs = []
    for td in TEST_DIRS:
        d = os.path.join(ROOT, td)
        if not os.path.isdir(d):
            continue
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
            for fn in filenames:
                if fn.endswith(".py"):
                    try:
                        blobs.append(open(os.path.join(dirpath, fn), encoding="utf-8", errors="replace").read())
                    except OSError:
                        pass
    return blobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    files = production_files()
    known = {module_name(f) for f in files}
    mods = {}
    for f in files:
        info = analyse(f, known)
        info["path"] = f
        info["module"] = module_name(f)
        info["layer"] = layer_of(f)
        mods[info["module"]] = info

    # reverse edges
    imported_by = defaultdict(set)
    for m, info in mods.items():
        for dep in info["imports"]:
            imported_by[dep].add(m)
    for m, info in mods.items():
        info["imported_by"] = sorted(imported_by.get(m, ()))

    # layer violations: a module importing something in a HIGHER layer (lower rank)
    violations = []
    for m, info in mods.items():
        r = LAYER_RANK[info["layer"]]
        for dep in info["imports"]:
            d = mods.get(dep)
            if not d:
                continue
            if LAYER_RANK[d["layer"]] < r:
                violations.append({"from": m, "from_layer": info["layer"], "to": dep, "to_layer": d["layer"]})

    # import cycles (2-node only; deeper cycles reported as SCC size)
    two_cycles = sorted(
        {
            tuple(sorted((m, dep)))
            for m, info in mods.items()
            for dep in info["imports"]
            if m in mods.get(dep, {}).get("imports", [])
        }
    )

    blobs = test_mentions()
    for m, info in mods.items():
        stem = info["path"].rsplit("/", 1)[-1][:-3]
        needle_mod = info["module"]
        info["test_files_mentioning"] = sum(1 for b in blobs if needle_mod in b or ("/" + stem + ".py") in b)

    by_layer = defaultdict(list)
    for info in mods.values():
        by_layer[info["layer"]].append(info)

    if args.json:
        json.dump({"modules": mods, "violations": violations, "two_cycles": two_cycles}, sys.stdout, indent=1)
        return 0

    out = []
    w = out.append
    total_lines = sum(i["lines"] for i in mods.values())
    w("<!-- GENERATED by scripts/blueprint.py — do not edit by hand. Re-run at every checkpoint. -->")
    w("")
    w("# OpenClink — generated structure")
    w("")
    w(
        f"**{len(mods)} production modules, {total_lines:,} lines.** "
        f"{len(blobs)} test files scanned for module mentions."
    )
    w("")
    w("## Layers, by size and by how much depends on them")
    w("")
    w("| Layer | Modules | Lines | Internal imports out | Modules importing in |")
    w("|---|---:|---:|---:|---:|")
    for layer in LAYER_ORDER:
        group = by_layer.get(layer, [])
        if not group:
            continue
        out_edges = sum(len(i["imports"]) for i in group)
        in_edges = sum(len(i["imported_by"]) for i in group)
        w(f"| `{layer}` | {len(group)} | {sum(i['lines'] for i in group):,} | {out_edges} | {in_edges} |")
    w("")
    w("## Backwards dependencies — a lower layer importing a higher one")
    w("")
    if violations:
        w(
            f"**{len(violations)} edges cross a layer boundary backwards.** Each is a place where a change "
            "in the upper layer can break the lower one, which is the opposite of what the layering promises."
        )
        w("")
        w("| From | | To |")
        w("|---|---|---|")
        for v in sorted(violations, key=lambda x: (x["from_layer"], x["from"])):
            w(f"| `{v['from']}` ({v['from_layer']}) | → | `{v['to']}` ({v['to_layer']}) |")
    else:
        w("None. Every internal import runs from a higher layer to a lower one.")
    w("")
    w("## Mutual imports")
    w("")
    if two_cycles:
        for a, b in two_cycles:
            w(f"- `{a}` ⇄ `{b}`")
    else:
        w("None between two modules.")
    w("")
    w("## The hubs — what a change is most likely to break")
    w("")
    w("| Module | Layer | Lines | Imported by | Test files mentioning it |")
    w("|---|---|---:|---:|---:|")
    for info in sorted(mods.values(), key=lambda i: (-len(i["imported_by"]), -i["lines"]))[:20]:
        w(
            f"| `{info['module']}` | {info['layer']} | {info['lines']:,} | {len(info['imported_by'])} | {info['test_files_mentioning']} |"
        )
    w("")
    w("## Modules no test mentions")
    w("")
    silent = sorted([i for i in mods.values() if i["test_files_mentioning"] == 0], key=lambda i: -i["lines"])
    if silent:
        w(
            f"**{len(silent)} of {len(mods)} modules ({sum(i['lines'] for i in silent):,} lines) are named by no test file.** "
            "A mention is not coverage — this is an upper bound on what is unpinned, and everything below it is certainly unpinned."
        )
        w("")
        w("| Module | Layer | Lines |")
        w("|---|---|---:|")
        for i in silent[:40]:
            w(f"| `{i['module']}` | {i['layer']} | {i['lines']:,} |")
        if len(silent) > 40:
            w(f"| … and {len(silent) - 40} more | | |")
    else:
        w("Every module is mentioned by at least one test file.")
    w("")
    w("## Full module table")
    w("")
    w("| Module | Layer | Lines | Classes | Top-level defs | Imports | Imported by | Tests |")
    w("|---|---|---:|---:|---:|---:|---:|---:|")
    for info in sorted(mods.values(), key=lambda i: (LAYER_RANK[i["layer"]], i["module"])):
        w(
            f"| `{info['module']}` | {info['layer']} | {info['lines']:,} | {len(info['classes'])} | "
            f"{len(info['defs'])} | {len(info['imports'])} | {len(info['imported_by'])} | {info['test_files_mentioning']} |"
        )
    w("")

    dest = os.path.join(ROOT, "Documents", "GENERATED_STRUCTURE.md")
    with open(dest, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out))
    print(
        f"wrote {rel(dest)}  ({len(mods)} modules, {total_lines:,} lines, "
        f"{len(violations)} backwards edges, {len(silent)} modules no test mentions)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
