#!/usr/bin/env python3
"""Dependencies pinned and scanned (DL369): each one the release ships, at its
exact version, looked up on deps.dev (Google's open-source insights service,
from CI only): a known High or Critical advisory (CVSS 7 or more) fails, and so
does a license that isn't allowed (tools/dep_licenses.json). It writes a bill
of materials (CycloneDX's JSON form) for the release.

    python3 tools/dep_scan.py maven deps.txt sbom.json   # Gradle's dependency tree
    python3 tools/dep_scan.py pypi requirements.txt sbom.json
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

LICENSES = Path(__file__).with_name("dep_licenses.json")
HIGH = 7.0
API = "https://api.deps.dev/v3"
# "+--- group:artifact:version", "\--- group:artifact:req -> resolved", constraints "(c)" aside.
TREE = re.compile(r"^[\s|+\\-]*--- ([\w.\-]+):([\w.\-]+):(?:\S+ -> )?([\w.\-]+)(?: \(\*\))?$")
PIN = re.compile(r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-]+)$")

Lookup = Callable[[str, str, str], dict]


def maven(tree: str) -> set[tuple[str, str]]:
    found = set()
    for line in tree.splitlines():
        line = re.sub(r"\{strictly [^}]*\}", "x", line.rstrip())
        m = TREE.match(line)
        if m and not line.endswith("(c)"):
            found.add((f"{m.group(1)}:{m.group(2)}", m.group(3)))
    return found


def pypi(text: str) -> set[tuple[str, str]]:
    found = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = PIN.match(line)
        if not m:
            raise SystemExit(f"dep_scan: {line!r} isn't pinned to one version (name==version)")
        found.add((m.group(1).lower(), m.group(2)))
    return found


def _get(url: str, body: dict | None = None) -> dict | None:
    """A JSON answer, or None for a package the service doesn't know (404)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def lookup(system: str, name: str, version: str) -> dict:
    """Its licenses from deps.dev (None when deps.dev doesn't know it), and its
    advisories from OSV.dev, each with its severity: OSV's own word for it
    (GitHub's advisories give one), else deps.dev's CVSS score, else None."""
    quoted = urllib.parse.quote(name, safe="")
    v = _get(f"{API}/systems/{system}/packages/{quoted}/versions/{urllib.parse.quote(version, safe='')}")
    eco = {"maven": "Maven", "pypi": "PyPI"}[system]
    found = _get("https://api.osv.dev/v1/query", {"package": {"name": name, "ecosystem": eco}, "version": version}) or {}
    advisories = []
    for vuln in found.get("vulns", []):
        word = (vuln.get("database_specific") or {}).get("severity", "")
        score = {"CRITICAL": 9.0, "HIGH": 7.0, "MODERATE": 5.0, "MEDIUM": 5.0, "LOW": 2.0}.get(word.upper())
        if score is None:
            a = _get(f"{API}/advisories/{urllib.parse.quote(vuln['id'], safe='')}") or {}
            score = a.get("cvss3Score")
        fixed = sorted({e["fixed"] for a in vuln.get("affected", []) for r in a.get("ranges", []) for e in r.get("events", []) if "fixed" in e})
        note = f"{vuln.get('summary', '').strip()[:120]}; fixed in {', '.join(fixed) or 'no release yet'}"
        advisories.append((f"{vuln['id']} ({note})", None if score is None else float(score)))
    return {"licenses": None if v is None else v.get("licenses", []), "advisories": advisories}


def scan(system: str, packages: set[tuple[str, str]], lookup: Lookup) -> tuple[list[str], dict]:
    rules = json.loads(LICENSES.read_text())
    allowed, excused = set(rules["allowed"]), rules["packages"]
    problems, components = [], []
    for name, version in sorted(packages):
        info = lookup(system, name, version)
        for key, score in info["advisories"]:
            if score is None:
                problems.append(f"{name} {version}: {key}, its severity unknown: read it, and update or list why not")
            elif score >= HIGH:
                problems.append(f"{name} {version}: {key}, CVSS {score} (High or Critical): update it")
        licenses = info["licenses"] or []
        if name not in excused:
            if not licenses:
                problems.append(f"{name} {version}: no license known (deps.dev): check it and list it in tools/dep_licenses.json")
            problems += [
                f"{name} {version}: its license {lic} isn't one tools/dep_licenses.json allows"
                for lic in licenses
                if not all(part.strip("() ") in allowed for part in re.split(r" (?:OR|AND) ", lic))
            ]
        purl_name = name.replace(":", "/") if system == "maven" else name
        components.append({"type": "library", "name": name, "version": version, "purl": f"pkg:{system}/{purl_name}@{version}",
                           "licenses": [{"expression": lic} for lic in licenses]})
    return problems, {"bomFormat": "CycloneDX", "specVersion": "1.5", "components": components}


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in ("maven", "pypi"):
        print(__doc__)
        return 2
    text = Path(argv[2]).read_text()
    packages = maven(text) if argv[1] == "maven" else pypi(text)
    try:
        problems, sbom = scan(argv[1], packages, lookup)
    except OSError as e:  # (the services unreachable: the scan fails, never passes unread)
        print(f"::error::dep_scan: couldn't read the advisories: {e}")
        return 1
    Path(argv[3]).write_text(json.dumps(sbom, indent=2) + "\n")
    for p in problems:
        print(f"::error::{p}")
    print(f"{len(packages)} dependencies scanned; {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
