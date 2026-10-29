#!/usr/bin/env python3
"""How long the full suite's files took, from pytest's JUnit XML: one notice
on the run's page, the slowest first (the CI audit, October 29, P4: measured
before the tests are split into parts balanced by these times).

    python3 tools/suite_times.py junit.xml [--top 60]
    python3 tools/suite_times.py --timings timings.txt

--timings: the timing tests' own measures (tests/timing.py: where, took,
limit), one notice, the thinnest margin first (the CI audit, P13).
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


def by_file(xml: str) -> dict[str, float]:
    took: dict[str, float] = defaultdict(float)
    for case in ET.fromstring(xml).iter("testcase"):
        # (classname is the module's dotted path, then any class: tests.test_x.Thing)
        parts = case.get("classname", "").split(".")
        module = next((i for i, p in enumerate(parts) if p.startswith("test_")), len(parts) - 1)
        took["/".join(parts[: module + 1]) + ".py"] += float(case.get("time", "0"))
    return dict(took)


def notice(took: dict[str, float], top: int) -> str:
    total = sum(took.values())
    rows = sorted(took.items(), key=lambda kv: -kv[1])[:top]
    lines = [f"{seconds:7.1f} s  {name}" for name, seconds in rows]
    head = f"The suite's files by time: {total / 60:.1f} min in all, {len(took)} files (the slowest {len(rows)})"
    return f"::notice title=Test times::{head}%0A" + "%0A".join(lines)


def margins(text: str, top: int = 30) -> str:
    rows = []
    for line in text.splitlines():
        where, took, limit = line.split("\t")
        rows.append((float(took) / float(limit), where, float(took), float(limit)))
    rows.sort(reverse=True)
    lines = [f"{share:4.0%} of its limit: {took:.3f} s of {limit:g} s  {where}" for share, where, took, limit in rows[:top]]
    return f"::notice title=Timing margins::{len(rows)} timed checks, the thinnest first%0A" + "%0A".join(lines)


def main(argv: list[str]) -> int:
    if argv[1:2] == ["--timings"] and len(argv) == 3:
        print(margins(Path(argv[2]).read_text()))
        return 0
    if len(argv) < 2:
        print(__doc__)
        return 2
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 60
    print(notice(by_file(Path(argv[1]).read_text()), top))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
