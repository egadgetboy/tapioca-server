"""The release check for tapiOca's PDFs (the plan's The manuals; DL422, DL426). Run from the repo root before a
release's notes go up:

    python3 tools/manual/check.py            (every document: manual/, and remaining/server and remaining/apps)
    python3 tools/manual/check.py manual     (one of them)

Each document is a folder with manual.json (its cover; "kind" is "manual", the default, or "remaining" for a Remaining
Development handoff), src/*.md, its one PDF and manual.lock. Fails unless: each has exactly its one PDF, and the repo no
other manual; the cover names the release(s) being published (a manual: the server's app/__init__.py version, or each
app's newest release notes; a Remaining Development handoff: each app's newest release notes and the server's version)
and a date; the PDF was built from the current chapters (manual.lock); README.md links it; and the chapters follow the
wording rules. Needs no third-party package.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
KIT = Path(__file__).resolve().parent
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
SERVER = (ROOT / "app" / "__init__.py").exists()

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
MANAGERS = [(r"\b(?:Sonarr|Radarr)\b", "the Movie Manager and the Show Manager (DL419)")]
APPS_ONLY = [(r"\bdownload(?:s|ing|ed)?\b", "the apps never mention downloading")]


def folders() -> list[Path]:
    return [p.parent for p in [ROOT / "manual" / "manual.json", *sorted(ROOT.glob("remaining/*/manual.json"))] if p.exists()]


def digest(doc: Path) -> str:
    h = hashlib.sha256()
    for f in [doc / "manual.json", *sorted((doc / "src").glob("*.md")), KIT / "build.py", KIT / "manual.css"]:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def newest(folder: str) -> str:
    vs = [p.stem.lstrip("v") for p in (ROOT / folder).glob("v*.md")]
    return max(vs, key=lambda v: tuple(int(x) for x in v.split(".")))


def apps_releases() -> list[list[str]]:
    return [["Android", newest("android/releases")], ["iPhone and iPad", newest("ios/releases")], ["Roku", newest("roku/releases")]]


def tracked() -> list[str]:
    return subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()


def file_problems(doc: Path, meta: dict) -> list[str]:
    """One PDF in the folder, the one the cover names; and one manual in the repo."""
    rel = doc.relative_to(ROOT).as_posix()
    mine = f"{rel}/{meta['file']}"
    out = [] if (doc / meta["file"]).exists() else [f"no {mine}: build it with tools/manual/build.py {rel}"]
    files = tracked()
    extra = [t for t in files if t.lower().endswith(".pdf") and t.startswith(rel + "/") and t != mine]
    if meta.get("kind", "manual") == "manual":
        extra += [t for t in files if t.lower().endswith(".pdf") and "manual" in t.lower() and t != mine and t not in extra]
    if extra:
        out.append(f"only the current edition is published: remove {', '.join(extra)}")
    return out


def cover_problems(meta: dict) -> list[str]:
    """The cover names the release being published, and a date."""
    out = []
    if meta.get("kind", "manual") == "remaining":
        apps = [r for r in meta["releases"] if r[0] != "Server"]
        server = [r for r in meta["releases"] if r[0] == "Server"]
        if apps != apps_releases():
            out.append(f"the cover says {apps}, but the apps' releases are {apps_releases()}")
        if len(server) != 1 or not re.fullmatch(r"\d+\.\d+\.\d+", server[0][1]):
            out.append("the cover names the server's release once, as Server x.y.z")
    else:
        want = [["Server", re.search(r'__version__ = "([^"]+)"', (ROOT / "app" / "__init__.py").read_text()).group(1)]] if SERVER else apps_releases()
        if meta["releases"] != want:
            out.append(f"the cover says {meta['releases']}, but the release is {want}")
    if not re.fullmatch(rf"(?:{MONTHS}) \d{{1,2}}, 20\d\d", meta.get("date", "")):
        out.append(f"the cover's date {meta.get('date')!r} isn't like \"November 1, 2026\"")
    return out


def lock_problems(doc: Path, meta: dict) -> list[str]:
    """The PDF is the one the last build made, from the current chapters and cover."""
    pdf = doc / meta["file"]
    if not pdf.exists():
        return []
    lock_file = doc / "manual.lock"
    lock = json.loads(lock_file.read_text()) if lock_file.exists() else {}
    out = []
    if lock.get("pdf_sha256") != hashlib.sha256(pdf.read_bytes()).hexdigest():
        out.append(f"the PDF isn't the one the last build made ({lock_file.relative_to(ROOT)}): build it again")
    if lock.get("src") != digest(doc):
        out.append("the PDF is older than its chapters or cover: build it again")
    if lock.get("releases") != meta["releases"] or lock.get("date") != meta["date"]:
        out.append("the PDF's cover isn't manual.json's: build it again")
    return out


def wording_problems(doc: Path, meta: dict) -> list[str]:
    """The chapters follow the wording rules (a line ending in <!-- wording-ok --> is a reviewed quote)."""
    rules = BANNED
    if not SERVER:
        rules = rules + MANAGERS + (APPS_ONLY if meta.get("kind", "manual") == "manual" else [])
    out = []
    for f in sorted((doc / "src").glob("*.md")):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if line.rstrip().endswith("<!-- wording-ok -->"):
                continue
            text = re.sub(r"`[^`]*`", "", line)
            out += [f"{f.relative_to(ROOT)}:{n}: {why}: {line.strip()[:90]}" for pat, why in rules if re.search(pat, text)]
    return out


def doc_problems(doc: Path) -> list[str]:
    meta = json.loads((doc / "manual.json").read_text())
    out = file_problems(doc, meta) + cover_problems(meta) + lock_problems(doc, meta) + wording_problems(doc, meta)
    link = f"{doc.relative_to(ROOT).as_posix()}/{meta['file']}"
    if link not in (ROOT / "README.md").read_text():
        out.append(f"README.md doesn't link {link}")
    return out


def main(argv: list[str]) -> int:
    docs = [ROOT / a for a in argv] or folders()
    failed = 0
    for doc in docs:
        problems = doc_problems(doc)
        for p in problems:
            print(f"FAIL: {doc.relative_to(ROOT)}: {p}")
        if not problems:
            meta = json.loads((doc / "manual.json").read_text())
            print(f"OK: {doc.relative_to(ROOT)}/{meta['file']}, {meta['releases']}, {meta['date']}")
        failed |= bool(problems)
    return 1 if failed or not docs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
