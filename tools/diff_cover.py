#!/usr/bin/env python3
"""Changed core lines are covered: a line of the core changed since the
platform's last release, with code on it, that no test runs, fails. Reads
JaCoCo's XML (Android) or an LCOV file (Swift's llvm-cov, Python's coverage).

    python3 tools/diff_cover.py android jacoco report.xml
    python3 tools/diff_cover.py apple lcov coverage.lcov --strip /home/runner/work/x/x/
    python3 tools/diff_cover.py server lcov coverage.lcov --strip /app/
    python3 tools/diff_cover.py server --local [tests/test_x.py ...]

--local, in the session before pushing a candidate (the CI audit, P8): the
tests named, or else those changed since the last release, run here under
coverage, then the same check CI makes. A line it names may be one only
another test reaches: run that test too, or the full suite.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import changed_lines

ROOT = Path(__file__).resolve().parent.parent
# Each platform's core: the code its tests are expected to reach.
CORE = {
    "android": ("android/app/src/main/java/com/egadgetboy/stationplay/core/",),
    "apple": ("ios/Core/Sources/",),
    "server": ("app/",),
}
KOTLIN_ROOT = "android/app/src/main/java/"

Coverage = dict[str, dict[int, bool]]


def jacoco(xml: str, root: str) -> Coverage:
    out: Coverage = {}
    for package in ET.fromstring(xml).iter("package"):
        for source in package.iter("sourcefile"):
            path = f"{root}{package.get('name')}/{source.get('name')}"
            out[path] = {int(line.get("nr")): int(line.get("ci", "0")) > 0 for line in source.iter("line")}
    return out


def lcov(text: str, strip: str = "") -> Coverage:
    out: Coverage = {}
    path = None
    for line in text.splitlines():
        if line.startswith("SF:"):
            path = line[3:].removeprefix(strip)
            out.setdefault(path, {})
        elif line.startswith("DA:") and path:
            n, count = line[3:].split(",")[:2]
            out[path][int(n)] = out[path].get(int(n), False) or int(count) > 0
    return out


def uncovered(cov: Coverage, added: dict[str, set[int]], core: tuple[str, ...], must_have: set[str] = frozenset()) -> list[str]:
    out = []
    for path, lines in sorted(added.items()):
        if not path.startswith(core):
            continue
        if path not in cov:
            if path in must_have:
                out.append(f"{path}: no test runs it")
            continue
        out += [f"{path}:{n}" for n in sorted(lines) if cov[path].get(n) is False]
    return out


def local(tests: list[str]) -> int:
    tests = tests or changed_lines.changed_files("server", "tests/test_*.py", "tests/**/test_*.py")
    if not tests:
        print("No test changed since the last release: name the tests to run")
        return 2
    with tempfile.TemporaryDirectory(prefix="diff-cover-") as folder:
        data, report = Path(folder) / ".coverage", Path(folder) / "coverage.lcov"
        ran = subprocess.run([sys.executable, "-m", "coverage", "run", f"--data-file={data}", "--source=app",
                              "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests], cwd=ROOT)  # fmt: skip
        if ran.returncode != 0:
            print("The tests failed: fix them first")
            return ran.returncode
        subprocess.run([sys.executable, "-m", "coverage", "lcov", f"--data-file={data}", "-o", str(report), "-q"],
                       cwd=ROOT, check=True)  # fmt: skip
        return main(["diff_cover.py", "server", "lcov", str(report), "--strip", f"{ROOT}/"])


def main(argv: list[str]) -> int:
    if argv[1:3] == ["server", "--local"]:
        return local(argv[3:])
    if len(argv) < 4 or argv[1] not in CORE or argv[2] not in ("jacoco", "lcov"):
        print(__doc__)
        return 2
    platform, kind, report = argv[1], argv[2], Path(argv[3]).read_text()
    strip = argv[argv.index("--strip") + 1] if "--strip" in argv else ""
    cov = jacoco(report, KOTLIN_ROOT) if kind == "jacoco" else lcov(report, strip)
    base = changed_lines.since_release(platform)
    diff = subprocess.run(["git", "diff", "-U0", "--no-color", base, "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    added = changed_lines.added_lines(diff)
    py_new = {p for p in added if p.endswith(".py")} if platform == "server" else set()
    found = uncovered(cov, added, CORE[platform], py_new)
    for f in found:
        print(f"::error::{f}: changed since {base}, and no test runs it")
    print(f"Coverage of changed core lines since {base}: {len(found)} line(s) no test runs")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
