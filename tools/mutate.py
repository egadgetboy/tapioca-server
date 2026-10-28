#!/usr/bin/env python3
"""Mutation testing (the plan's release gate, DL369: tests that prove
something). Each small change a bug could make to a key decision (a
comparison turned around, an `and` made `or`, a test negated, a constant
flipped) is made in turn, and the decision's tests run against it. A change
the tests still pass, a surviving mutant, is a missing test.

    python3 tools/mutate.py run [<target> ...] [--out <file>]
    python3 tools/mutate.py list [<target> ...]

The targets are `tools/mutation_targets.json`: each a file, the functions in
it that make the decision, and the command that runs its tests. Python is
changed through its syntax tree; Kotlin and Swift by their operators, inside
the named functions' braces. A survivor that can't be a bug (the change means
the same thing) is accepted only in `tools/mutation_accepted.json`, by its ID,
with the reason. Each mutant is restored before the next; the tests must pass
first, unchanged. The same file in both repositories. Standard library only.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / "tools" / "mutation_targets.json"
ACCEPTED = ROOT / "tools" / "mutation_accepted.json"
TIMEOUT_FACTOR = (
    3  # a mutant whose tests run this many times longer than the clean run is killed (it hung)
)


@dataclass
class Mutant:
    id: str  # "<target>/<function>#<n> <what>": stable while the function's own code doesn't change
    path: Path
    source: str  # the whole file, mutated


# Python, through the syntax tree ----------------------------------------------

SWAP = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.GtE: ast.Lt,
    ast.Gt: ast.LtE,
    ast.LtE: ast.Gt,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
}
# (and the boundary each comparison could be off by: `>=` written `>`)
BOUNDARY = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt}
NAMES = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.GtE: ">=",
    ast.Gt: ">",
    ast.LtE: "<=",
    ast.In: "in",
    ast.NotIn: "not in",
    ast.Is: "is",
    ast.IsNot: "is not",
}


def functions(tree: ast.Module) -> dict[str, ast.AST]:
    out: dict[str, ast.AST] = {}

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[prefix + child.name] = child
                visit(child, prefix + child.name + ".")
            elif isinstance(child, ast.ClassDef):
                visit(child, prefix + child.name + ".")

    visit(tree, "")
    return out


def _compare(node: ast.Compare) -> list[tuple[str, str]]:
    found = []
    for i, op in enumerate(node.ops):
        kind = type(op)
        if kind in SWAP:
            found.append((f"op{i}", f"{NAMES[kind]} -> {NAMES[SWAP[kind]]}"))
        if kind in BOUNDARY:
            found.append((f"edge{i}", f"{NAMES[kind]} -> {NAMES[BOUNDARY[kind]]}"))
    return found


RETURNED = (ast.Compare, ast.BoolOp, ast.Name, ast.Call, ast.Attribute)


def _one(node: ast.AST) -> list[tuple[str, str]]:
    """The mutations one node takes: (how, what)."""
    if isinstance(node, ast.Compare):
        return _compare(node)
    if isinstance(node, ast.BoolOp):
        return [("boolop", "and -> or" if isinstance(node.op, ast.And) else "or -> and")]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return [("unnot", "not dropped")]
    if isinstance(node, (ast.If, ast.While, ast.IfExp)):
        return [("negate", "condition negated")]
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return [("bool", f"{node.value} -> {not node.value}")]
    if isinstance(node, ast.Return) and isinstance(node.value, RETURNED):
        return [("return", "return value negated")]
    return []


def points(func: ast.AST) -> list[tuple[ast.AST, str, str]]:
    """Each place in a function a mutation goes: (node, how, what)."""
    return [(node, how, what) for node in ast.walk(func) for how, what in _one(node)]


def apply(node: ast.AST, how: str) -> None:
    """Every mutation but dropping a `not`, which DropNot makes."""
    if how.startswith("op"):
        i = int(how[2:])
        node.ops[i] = SWAP[type(node.ops[i])]()
    elif how.startswith("edge"):
        i = int(how[4:])
        node.ops[i] = BOUNDARY[type(node.ops[i])]()
    elif how == "boolop":
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif how == "negate":
        node.test = ast.UnaryOp(ast.Not(), node.test)
    elif how == "bool":
        node.value = not node.value
    elif how == "return":
        node.value = ast.UnaryOp(ast.Not(), node.value)


class DropNot(ast.NodeTransformer):
    def __init__(self, target: ast.AST) -> None:
        self.target = target

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        self.generic_visit(node)
        return node.operand if node is self.target else node


def python_mutants(name: str, path: Path, wanted: list[str]) -> list[Mutant]:
    text = path.read_text()
    out = []
    probe = functions(ast.parse(text))
    missing = [f for f in wanted if f not in probe]
    if missing:
        raise SystemExit(
            f"mutate: {name}: {path.relative_to(ROOT)} has no function {', '.join(missing)}"
        )
    for fname in wanted:
        count = len(points(probe[fname]))
        for n in range(count):
            tree = ast.parse(text)  # (a fresh tree for each mutant)
            node, how, what = points(functions(tree)[fname])[n]
            if how == "unnot":
                tree = DropNot(node).visit(tree)
            else:
                apply(node, how)
            ast.fix_missing_locations(tree)
            out.append(Mutant(f"{name}/{fname}#{n} {what}", path, ast.unparse(tree) + "\n"))
    return out


# Kotlin and Swift, by their operators -----------------------------------------

TEXT_SWAPS = [
    ("==", "!="),
    ("!=", "=="),
    ("<=", ">"),
    (">=", "<"),
    ("<=", "<"),
    (">=", ">"),
    ("&&", "||"),
    ("||", "&&"),
    (" < ", " >= "),
    (" > ", " <= "),
    (" < ", " <= "),
    (" > ", " >= "),
    ("true", "false"),
    ("false", "true"),
]


def body_lines(lines: list[str], fname: str) -> range:
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if re.search(rf"\b(fun|func)\s+{re.escape(fname)}\b", line)
        ),
        None,
    )
    if start is None:
        raise SystemExit(f"mutate: no function {fname}")
    depth, opened = 0, False
    for i in range(start, len(lines)):
        code = re.sub(r'"(?:\\.|[^"\\])*"', '""', lines[i].split("//")[0])
        depth += code.count("{") - code.count("}")
        opened = opened or "{" in code
        if opened and depth <= 0:
            return range(start + 1, i + 1)
    return range(start + 1, len(lines))


def text_mutants(name: str, path: Path, wanted: list[str]) -> list[Mutant]:
    lines = path.read_text().split("\n")
    out = []
    for fname in wanted:
        n = 0
        for i in body_lines(lines, fname):
            code = lines[i].split("//")[0]
            masked = re.sub(r'"(?:\\.|[^"\\])*"', lambda m: " " * len(m.group()), code)
            for old, new in TEXT_SWAPS:
                for m in re.finditer(
                    re.escape(old) if old[0] != "t" and old[0] != "f" else rf"\b{old}\b", masked
                ):
                    changed = lines[:]
                    changed[i] = lines[i][: m.start()] + new + lines[i][m.end() :]
                    out.append(
                        Mutant(
                            f"{name}/{fname}#{n} {old.strip()} -> {new.strip()}",
                            path,
                            "\n".join(changed),
                        )
                    )
                    n += 1
    return out


# Running ----------------------------------------------------------------------


def mutants_of(name: str, target: dict) -> list[Mutant]:
    path = ROOT / target["file"]
    make = python_mutants if path.suffix == ".py" else text_mutants
    return make(name, path, target["functions"])


def fresh(path: Path) -> None:
    """Python's compiled copies of a changed file go: two mutants of the same
    size written in the same second would otherwise run the first one's."""
    for old in (path.parent / "__pycache__").glob(f"{path.stem}.*.pyc"):
        old.unlink()


def tests_pass(command: str, timeout: float | None) -> bool | None:
    """True if they pass, False if they fail, None if they ran past the timeout."""
    import os

    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        return (
            subprocess.run(
                command, shell=True, cwd=ROOT, env=env, capture_output=True, timeout=timeout
            ).returncode
            == 0
        )
    except subprocess.TimeoutExpired:
        return None


def run_target(name: str, target: dict) -> list[str]:
    """The target's survivors."""
    path = ROOT / target["file"]
    clean = path.read_text()
    began = time.monotonic()
    if not tests_pass(target["tests"], None):
        raise SystemExit(
            f"mutate: {name}: its tests fail before any change, so nothing can be measured"
        )
    took = time.monotonic() - began
    survivors = []
    mutants = mutants_of(name, target)
    try:
        for k, m in enumerate(mutants, 1):
            m.path.write_text(m.source)
            fresh(m.path)
            passed = tests_pass(target["tests"], max(60.0, took * TIMEOUT_FACTOR))
            if passed:
                survivors.append(m.id)
                print(f"  survived {k}/{len(mutants)}: {m.id}", flush=True)
            elif (
                passed is None
            ):  # (killed, as a mutant that hangs is; said, so a slow machine shows)
                print(f"  timed out {k}/{len(mutants)}: {m.id}", flush=True)
    finally:
        path.write_text(clean)
        fresh(path)
    print(f"{name}: {len(mutants) - len(survivors)} of {len(mutants)} mutants killed", flush=True)
    return survivors


def load(names: list[str]) -> dict[str, dict]:
    targets = json.loads(TARGETS.read_text())["targets"]
    unknown = [n for n in names if n not in targets]
    if unknown:
        raise SystemExit(f"mutate: no target {', '.join(unknown)}")
    return {n: t for n, t in targets.items() if not names or n in names}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("run", "list"):
        print(__doc__)
        return 2
    args = [a for a in argv[2:] if not a.startswith("--")]
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else None
    if out:
        args = [a for a in args if a != str(out)]
    targets = load(args)
    if argv[1] == "list":
        for name, t in targets.items():
            for m in mutants_of(name, t):
                print(m.id)
        return 0
    accepted = json.loads(ACCEPTED.read_text()).get("accepted", {}) if ACCEPTED.exists() else {}
    survivors = [s for name, t in targets.items() for s in run_target(name, t)]
    missing = [s for s in survivors if s not in accepted]
    if out:
        out.write_text(
            json.dumps({"survivors": survivors, "missing_tests": missing}, indent=2) + "\n"
        )
    for s in missing:
        print(f"::error::mutation survived (a missing test): {s}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
