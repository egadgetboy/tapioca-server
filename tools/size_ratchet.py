#!/usr/bin/env python3
"""The size ratchet: the files new feature code never goes into may shrink,
never grow. Each one's line count is held in size_baseline.json, from October
27 (apps f08aed7, server b44895e); a file that shrinks lowers its number in the same commit, so it
can never grow back. A new file of the same kind (another MainScene*.brs) fails
too: new code goes in its own module.

    python3 tools/size_ratchet.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = Path(__file__).with_name("size_baseline.json")
# The same file in both repositories: the server's watches app/main.py.
SERVER = not (ROOT / "android").exists()
WATCHED = ("app/main.py",) if SERVER else (
    "android/app/src/main/java/com/egadgetboy/stationplay/app/AppModel.kt",
    "ios/Core/Sources/StationPlayCore/Flow/AppFlow.swift",
    "roku/components/MainScene*.brs",
)


def problems(baseline: dict[str, int], now: dict[str, int]) -> list[str]:
    out = []
    for path, lines in sorted(now.items()):
        was = baseline.get(path)
        if was is None:
            out.append(f"{path}: new, and of a kind new code never goes into: put it in a module of its own")
        elif lines > was:
            out.append(f"{path}: grew to {lines} lines from {was} (it may only shrink; the new code goes in a module of its own)")
        elif lines < was:
            out.append(f"{path}: now {lines} lines: lower its baseline in tools/size_baseline.json from {was} to {lines}, so it can't grow back")
    out += [f"{path}: gone, so take it out of tools/size_baseline.json" for path in sorted(baseline.keys() - now.keys())]
    return out


def sizes() -> dict[str, int]:
    found = {}
    for pattern in WATCHED:
        for f in ROOT.glob(pattern):
            found[str(f.relative_to(ROOT))] = len(f.read_text().splitlines())
    return found


def main() -> int:
    found = problems(json.loads(BASELINE.read_text()), sizes())
    for p in found:
        print("FAIL", p)
    if not found:
        print(f"The size ratchet: none of the {len(sizes())} files grew")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
