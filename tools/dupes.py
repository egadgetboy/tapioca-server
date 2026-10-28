#!/usr/bin/env python3
"""Duplicated code (the quality bar: no duplicated logic): the apps' Kotlin,
Swift and BrightScript, or the server's Python. A run of WINDOW lines of real code (blank
lines, comments and lone braces or `end if`s left out, spaces ignored) found
again anywhere counts against each file it's in. Each file's count is held in
dupes_baseline.json from October 27: it may fall, never rise, so new code
can't copy and old copies are cleaned as their modules are.

    python3 tools/dupes.py             # the check
    python3 tools/dupes.py --where F   # the copied runs in one file
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = Path(__file__).with_name("dupes_baseline.json")
WINDOW = 6
# The same file in both repositories: the server's reads its Python.
SERVER = not (ROOT / "android").exists()
SOURCES = ("app/**/*.py",) if SERVER else (
    "android/app/src/main/java/**/*.kt",
    "ios/Core/Sources/**/*.swift",
    "ios/StationPlay/**/*.swift",
    "roku/components/**/*.brs",
    "roku/source/**/*.brs",
)
TRIVIAL = re.compile(r"^(?:[{}()\[\],;]+|end (?:if|for|while|function|sub)|else|\)\s*\{|\}\s*else\s*\{|return|break|continue)$", re.I)
COMMENT = re.compile(r"^(?://|/\*|\*|'|#|rem\b)", re.I)


def code_lines(text: str) -> list[tuple[int, str]]:
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        s = re.sub(r"\s+", " ", line.strip())
        if s and not COMMENT.match(s) and not TRIVIAL.match(s):
            out.append((n, s))
    return out


def windows(text: str) -> list[tuple[int, str]]:
    lines = code_lines(text)
    return [
        (lines[i][0], hashlib.sha1("\n".join(s for _, s in lines[i : i + WINDOW]).encode()).hexdigest())
        for i in range(len(lines) - WINDOW + 1)
    ]


def duplicated(files: dict[str, str]) -> dict[str, int]:
    """Each file's count of windows found more than once (anywhere)."""
    seen: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for path, text in files.items():
        for line, h in windows(text):
            seen[h].append((path, line))
    counts: dict[str, int] = defaultdict(int)
    for places in seen.values():
        if len(places) > 1:
            for path, _ in places:
                counts[path] += 1
    return dict(counts)


def problems(now: dict[str, int], baseline: dict[str, int]) -> list[str]:
    out = []
    for path, n in sorted(now.items()):
        was = baseline.get(path, 0)
        if n > was:
            out.append(f"{path}: {n} copied runs of {WINDOW} lines, up from {was} (use the one that's there; `python3 tools/dupes.py --where {path}`)")
        elif n < was:
            out.append(f"{path}: {n} copied runs, down from {was}: lower its number in tools/dupes_baseline.json")
    out += [f"{path}: no copied runs now: take it out of tools/dupes_baseline.json" for path in sorted(baseline.keys() - now.keys())]
    return out


def sources() -> dict[str, str]:
    return {str(f.relative_to(ROOT)): f.read_text(errors="replace") for pattern in SOURCES for f in sorted(ROOT.glob(pattern))}


def main(argv: list[str]) -> int:
    files = sources()
    if argv[1:2] == ["--where"]:
        target = argv[2]
        mine = {h: line for line, h in windows(files[target])}
        for path, text in files.items():
            for line, h in windows(text):
                if h in mine and (path, line) != (target, mine[h]):
                    print(f"{target}:{mine[h]} also at {path}:{line}")
        return 0
    if argv[1:2] == ["--baseline"]:
        BASELINE.write_text(json.dumps(dict(sorted(duplicated(files).items())), indent=2) + "\n")
        return 0
    found = problems(duplicated(files), json.loads(BASELINE.read_text()))
    for p in found:
        print("FAIL", p)
    if not found:
        print(f"Duplicated code: no file has more copies than on October 27 ({len(files)} files)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
