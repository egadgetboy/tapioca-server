#!/usr/bin/env python3
"""A linter's findings on changed lines only (DL368: each tool starts on
changed code, so old code never fails the build overnight). Reads a linter's
"path:line:..." output on stdin and keeps the findings on lines added since
the platform's last release (its newest tag), failing if any are left.

    swiftlint lint --quiet ios | python3 tools/changed_lines.py apple --strip /w/
    python3 tools/changed_lines.py --files android 'android/app/src/test/**/*.kt'   # the files changed
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAGS = {"android": "android-v", "apple": "apple-v", "roku": "roku-v", "server": "v"}
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
FINDING = re.compile(r"^(?P<path>[^:\s][^:]*):(?P<line>\d+):")


def added_lines(diff: str) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    path = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = None if line[4:] == "/dev/null" else line[4:].removeprefix("b/")
        elif path and (m := HUNK.match(line)):
            start, count = int(m.group(1)), int(m.group(2) or 1)
            if count:
                out.setdefault(path, set()).update(range(start, start + count))
    return out


def on_changed(output: str, added: dict[str, set[int]], strip: str = "") -> list[str]:
    kept = []
    for line in output.splitlines():
        m = FINDING.match(line.removeprefix(strip) if strip else line)
        if m and int(m.group("line")) in added.get(m.group("path"), set()):
            kept.append(line.removeprefix(strip) if strip else line)
    return kept


def since_release(platform: str) -> str:
    prefix = TAGS[platform]
    tags = subprocess.run(["git", "tag", "--list", f"{prefix}*", "--merged", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    tags = [t for t in tags if re.fullmatch(re.escape(prefix) + r"\d+\.\d+\.\d+", t)]
    if not tags:
        raise SystemExit(f"changed_lines: no {prefix}* tag to compare with (fetch the tags)")
    return max(tags, key=lambda t: [int(x) for x in t[len(prefix):].split(".")])


def changed_files(platform: str, *patterns: str) -> list[str]:
    """The files matching `patterns` added or changed since the platform's last release."""
    out = subprocess.run(["git", "diff", "--name-only", "--diff-filter=AM", since_release(platform), "HEAD", "--", *patterns],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return out.split()


def main(argv: list[str]) -> int:
    if argv[1:2] == ["--files"] and len(argv) >= 4:
        print("\n".join(changed_files(argv[2], *argv[3:])))
        return 0
    if len(argv) < 2 or argv[1] not in TAGS:
        print(__doc__)
        return 2
    strip = argv[argv.index("--strip") + 1] if "--strip" in argv else ""
    base = since_release(argv[1])
    diff = subprocess.run(["git", "diff", "-U0", "--no-color", base, "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    found = on_changed(sys.stdin.read(), added_lines(diff), strip)
    for f in found:
        print(f"::error::{f}")
    print(f"{len(found)} finding(s) on lines changed since {base}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
