#!/usr/bin/env python3
"""CLAUDE.md carries the standing rules of October 27, each as a rule of its
own (a bullet that starts with its name in bold), so no session works without
them. The same file in both repositories; the server's CLAUDE.md words them
generically.

    python3 tools/claude_rules.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = not (ROOT / "android").exists()
RULES = (
    "The order is frozen at the top",
    "The apps' look first" if SERVER else "The look first",
    "Every feature through intake",
    "Gates come from the class, checked by CI",
    "Modular, checkably",
    "One status source",
    "Decisions batched",
    "Until the launch (apps 1.0, server 2.0.0)",
    "No slop",
    "Quality gates",
    "After 1.0, only",
)


def problems(text: str) -> list[str]:
    return [
        f"CLAUDE.md doesn't carry the standing rule {r!r}"
        for r in RULES
        if not re.search(rf"^- \*\*{re.escape(r)}:?\*\*", text, re.M)
    ]


def main() -> int:
    found = problems((ROOT / "CLAUDE.md").read_text())
    for p in found:
        print("FAIL", p)
    if not found:
        print(f"CLAUDE.md carries all {len(RULES)} standing rules of October 27")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
