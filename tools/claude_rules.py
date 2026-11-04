#!/usr/bin/env python3
"""The standing rules: every one kept, each in exactly one place, and the
always-loaded CLAUDE.md kept small (the owner, November 4: shorter CLAUDE.md
files, with nothing lost, weakened or duplicated).

CLAUDE.md holds the rules every task needs. The rest live word for word in
`.claude/rules/*.md`, each scoped by `paths:` so it loads with the files it
covers, and each named in CLAUDE.md's "Rules that load with the work" with
when to open it. `tools/claude_rules.json` lists every rule (its text's hash)
and the one file it lives in. The same file in both repositories.

    python3 tools/claude_rules.py            # the checks
    python3 tools/claude_rules.py --record   # after an owner-approved edit of a rule: rewrites the list, printing each change
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = not (ROOT / "android").exists()
LIST = ROOT / "tools" / "claude_rules.json"
INDEX = "## Rules that load with the work"

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


def frontmatter(text: str) -> tuple[list[str] | None, str]:
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None, text
    paths = re.findall(r'^\s+- "([^"]+)"$', m.group(1), re.M)
    return paths, text[m.end():]


def norm(t: str) -> str:
    t = re.sub(r"^\s*(?:- )?", "", t)
    return re.sub(r"\s+", " ", re.sub(r"\n\s*(?:- )?", " ", t)).strip()


def units(text: str, skip_index: bool = True) -> list[str]:
    """Each bullet at any depth (its own lines), and each paragraph; headings
    and the index of rule files left out."""
    out: list[list[str]] = []
    cur: list[str] | None = None
    in_index = False
    for line in text.split("\n"):
        if line.startswith("#"):
            cur = None
            in_index = line == INDEX
            continue
        if in_index and skip_index:
            continue
        if re.match(r"^ *- ", line):
            cur = [line]
            out.append(cur)
        elif not line.strip():
            cur = None
        elif cur is None:
            cur = [line]
            out.append(cur)
        else:
            cur.append(line)
    return [norm("\n".join(u)) for u in out]


def digest(u: str) -> str:
    return hashlib.sha256(u.encode()).hexdigest()[:16]


def glob_re(glob: str) -> re.Pattern[str]:
    parts = re.split(r"(\*\*/|\*\*|\*)", glob)
    rx = "".join({"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*"}.get(p, re.escape(p)) for p in parts)
    return re.compile(rf"\A{rx}\Z")


def files(root: Path) -> dict[str, str]:
    found = {"CLAUDE.md": (root / "CLAUDE.md").read_text()}
    for f in sorted((root / ".claude" / "rules").glob("*.md")):
        found[f".claude/rules/{f.name}"] = f.read_text()
    return found


def where(found: dict[str, str]) -> dict[str, list[str]]:
    seen: dict[str, list[str]] = {}
    for name, text in found.items():
        for u in units(frontmatter(text)[1]):
            seen.setdefault(digest(u), []).append(name)
    return seen


def structure(root: Path, listed: dict, tracked: list[str]) -> list[str]:
    found = files(root)
    out = problems("\n".join(frontmatter(t)[1] for t in found.values()))
    for r in RULES:
        n = sum(len(re.findall(rf"^- \*\*{re.escape(r)}:?\*\*", t, re.M)) for t in found.values())
        if n > 1:
            out.append(f"the standing rule {r!r} is written {n} times")
    seen = where(found)
    for h, rule in listed["rules"].items():
        places = seen.get(h, [])
        if not places:
            out.append(f"a rule is missing or changed ({rule['file']}: {rule['starts']!r})")
        elif len(places) > 1:
            out.append(f"a rule is written {len(places)} times ({', '.join(places)}: {rule['starts']!r})")
        elif places[0] != rule["file"]:
            out.append(f"a rule moved from {rule['file']} to {places[0]} ({rule['starts']!r})")
    for h, places in seen.items():
        if h not in listed["rules"]:
            out.append(f"a rule in {places[0]} isn't in tools/claude_rules.json (an owner-approved edit is recorded with --record)")
    claude = found["CLAUDE.md"]
    lines, size = claude.count("\n"), len(claude.encode())
    if lines > listed["budget"]["lines"] or size > listed["budget"]["bytes"]:
        out.append(f"CLAUDE.md is {lines} lines and {size} bytes, past its budget of {listed['budget']['lines']} and {listed['budget']['bytes']}")
    index = claude.split(INDEX, 1)[1].split("\n## ", 1)[0] if INDEX in claude else ""
    for name, text in found.items():
        if name == "CLAUDE.md":
            continue
        paths, _ = frontmatter(text)
        meta = listed["files"].get(name)
        if not paths:
            out.append(f"{name} has no paths: it would load in every session")
        if meta is None:
            out.append(f"{name} isn't in tools/claude_rules.json")
            continue
        if paths != meta["paths"]:
            out.append(f"{name}'s paths differ from tools/claude_rules.json")
        if f"`{name}`" not in index:
            out.append(f"{name} isn't named in CLAUDE.md's {INDEX!r}")
        if not meta.get("future"):
            for p in paths or []:
                if not any(glob_re(p).match(t) for t in tracked):
                    out.append(f"{name}: {p!r} matches no file, so it never loads")
    for name in listed["files"]:
        if name not in found:
            out.append(f"{name} is listed but missing")
    return out


def record(root: Path, listed: dict) -> dict:
    found = files(root)
    rules = {}
    for name, text in found.items():
        for u in units(frontmatter(text)[1]):
            rules[digest(u)] = {"file": name, "starts": u[:70]}
    for h in set(listed.get("rules", {})) ^ set(rules):
        r = rules.get(h) or listed["rules"][h]
        print("added" if h in rules else "removed", r["file"], repr(r["starts"]))
    for name in found:
        if name != "CLAUDE.md":
            listed["files"].setdefault(name, {})["paths"] = frontmatter(found[name])[0] or []
    listed["rules"] = rules
    return listed


def main() -> int:
    listed = json.loads(LIST.read_text())
    if "--record" in sys.argv:
        LIST.write_text(json.dumps(record(ROOT, listed), indent=1, ensure_ascii=False) + "\n")
        return 0
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    found = structure(ROOT, listed, tracked)
    for p in found:
        print("FAIL", p)
    if not found:
        print(f"Every standing rule is kept once ({len(listed['rules'])} rules; CLAUDE.md within its budget)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
