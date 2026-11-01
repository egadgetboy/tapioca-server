"""The manual's release check (the plan's The manuals; DL422). Run from the repo root before a release's notes go up:

    python3 tools/manual/check.py

Fails unless: there's exactly one manual PDF, at the path manual/manual.json names, and no other manual anywhere in the
repo; its cover names exactly the release(s) being published (the server's app/__init__.py version, or each app's newest
release notes) and a date; the PDF was built from the current chapters (its source hash matches); README.md links it;
and the chapters follow the wording rules. Needs no third-party package.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
MAN = ROOT / "manual"
KIT = Path(__file__).resolve().parent
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"

# Words people read never use (both repos' CLAUDE.md: Legal care, the product's names). Code spans are skipped.
BANNED = [
    (r"\bchannels?\b", 'say "Station"'),
    (r"\bLibrar(?:y|ies)\b", 'say "Media"'),
    (r"\bIPTV\b", "never IPTV"),
    (r"\bpasscode\b", 'say "PIN"'),
    (r"\b(?:Tapioca|TAPIOCA|TapiOca|TapiOCA)\b", "tapiOca: a lowercase t and a capital O"),
    (r"\bcut(?:ting)? the cord\b|\bcord[- ]cutt", "no cord-cutting"),
    (r"\bfree TV\b", "never free TV"),
    (r"\balpha\b", "never alpha"),
]
APPS_ONLY = [(r"\b(?:Sonarr|Radarr)\b", "the apps never name a Media Manager"), (r"\bdownload(?:s|ing|ed)?\b", "the apps never mention downloading")]


def digest() -> str:
    h = hashlib.sha256()
    for f in [MAN / "manual.json", *sorted((MAN / "src").glob("*.md")), KIT / "build.py", KIT / "manual.css"]:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def newest(folder: str) -> str:
    vs = [p.stem.lstrip("v") for p in (ROOT / folder).glob("v*.md")]
    return max(vs, key=lambda v: tuple(int(x) for x in v.split(".")))


def expected() -> list[list[str]]:
    init = ROOT / "app" / "__init__.py"
    if init.exists():
        return [["Server", re.search(r'__version__ = "([^"]+)"', init.read_text()).group(1)]]
    return [["Android", newest("android/releases")], ["iPhone and iPad", newest("ios/releases")], ["Roku", newest("roku/releases")]]


def file_problems(meta: dict, pdf: Path) -> list[str]:
    """One manual, at the path the cover names, and none other tracked."""
    out = []
    if not pdf.exists():
        out.append(f"no {pdf.relative_to(ROOT)}: build it with tools/manual/build.py manual")
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    others = [t for t in tracked if t.lower().endswith(".pdf") and "manual" in t.lower() and t != f"manual/{meta['file']}"]
    if others:
        out.append(f"only one manual is published: remove {', '.join(others)}")
    return out


def cover_problems(meta: dict) -> list[str]:
    """The cover names the release being published, and a date."""
    out = []
    if meta["releases"] != expected():
        out.append(f"the cover says {meta['releases']}, but the release is {expected()}")
    if not re.fullmatch(rf"(?:{MONTHS}) \d{{1,2}}, 20\d\d", meta.get("date", "")):
        out.append(f"the cover's date {meta.get('date')!r} isn't like \"November 1, 2026\"")
    return out


def lock_problems(meta: dict, pdf: Path) -> list[str]:
    """The PDF is the one the last build made, from the current chapters and cover."""
    if not pdf.exists():
        return []
    lock_file = MAN / "manual.lock"
    lock = json.loads(lock_file.read_text()) if lock_file.exists() else {}
    out = []
    if lock.get("pdf_sha256") != hashlib.sha256(pdf.read_bytes()).hexdigest():
        out.append("the PDF isn't the one the last build made (manual/manual.lock): build it again")
    if lock.get("src") != digest():
        out.append("the PDF is older than its chapters or cover: build it again")
    if lock.get("releases") != meta["releases"] or lock.get("date") != meta["date"]:
        out.append("the PDF's cover isn't manual.json's: build it again")
    return out


def wording_problems() -> list[str]:
    """The chapters follow the wording rules (a line ending in <!-- wording-ok --> is a reviewed quote)."""
    rules = BANNED + ([] if (ROOT / "app" / "__init__.py").exists() else APPS_ONLY)
    out = []
    for f in sorted((MAN / "src").glob("*.md")):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if line.rstrip().endswith("<!-- wording-ok -->"):
                continue
            text = re.sub(r"`[^`]*`", "", line)
            out += [f"{f.relative_to(ROOT)}:{n}: {why}: {line.strip()[:90]}" for pat, why in rules if re.search(pat, text)]
    return out


def main() -> int:
    meta = json.loads((MAN / "manual.json").read_text())
    pdf = MAN / meta["file"]
    problems = file_problems(meta, pdf) + cover_problems(meta) + lock_problems(meta, pdf) + wording_problems()
    if f"manual/{meta['file']}" not in (ROOT / "README.md").read_text():
        problems.append(f"README.md doesn't link manual/{meta['file']}")
    for p in problems:
        print("FAIL:", p)
    if not problems:
        print(f"manual OK: {meta['file']}, {meta['releases']}, {meta['date']}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
