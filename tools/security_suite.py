"""tapiOca's security suite (DL287): run at every release candidate.

It runs, against tapiOca itself and nothing else:
1. the unit layer, tests/security (also run on every push with the other
   tests): the census of every outbound request, started program and file
   write; every route from every vantage point; sign-in tokens; outbound
   requests by provenance; paths; the four scripted chains;
2. the live harness, tools/attack_check.py (absorbed here; `python -m
   tools.attack_check` still runs it alone): a real tapiOca on two ports,
   asked as the internet and the home network would;

then writes its report (docs/security/report-<version>.md, for the
release's readiness record) and exits non-zero on any failure. Every check
here is Critical or High, so any failure blocks the release; a Medium found
later needs a tracked exception in tools/security_exceptions.json, which the
report lists for the owner.

The regression corpus only grows: the report counts the checks, and a
count below tools/security_corpus.json's fails the run unless that file
logs why (a merge of duplicates, on purpose).

Run it from the repo root:  python -m tools.security_suite
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import __version__  # noqa: E402

CORPUS = ROOT / "tools" / "security_corpus.json"
EXCEPTIONS = ROOT / "tools" / "security_exceptions.json"

# Each file of the unit layer, what it covers, and its severity if it fails.
LAYERS = {
    "test_inventory.py": (
        "The census: every way out, program and write declared (A.1, DEP-03, DEP-04)",
        "High",
    ),
    "test_authz.py": (
        "Every route from every vantage point (AZ-01 to AZ-03, AUTH-01, AUTH-02)",
        "Critical",
    ),
    "test_auth.py": (
        "Sign-in tokens: ended at once, never in an address or a log, kinds kept apart (AUTH-06, 06b, 07)",
        "Critical",
    ),  # fmt: skip
    "test_ssrf.py": ("Outbound requests by provenance (SSRF-01 to SSRF-08)", "Critical"),
    "test_traversal.py": ("Paths on every route with a parameter (INJ-01)", "Critical"),
    "test_chains.py": ("The four scripted chains (CHAIN-01 to CHAIN-04)", "Critical"),
    "test_device_sign_ins.py": (
        "Only Sign out reads the device sign-ins' record, in code and as it runs (1.44.3)",
        "High",
    ),
}

_RESULT = re.compile(r"^(PASSED|FAILED|ERROR) tests/security/([a-z_]+\.py)::(\S+)")


def unit_layer() -> tuple[dict[str, list[str]], dict[str, list[str]], str, int, list[str]]:
    """Each file's passed and failed checks, and pytest's last lines."""
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider", "tests/security"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    passed: dict[str, list[str]] = {name: [] for name in LAYERS}
    failed: dict[str, list[str]] = {name: [] for name in LAYERS}
    unexecuted = []
    for line in ran.stdout.splitlines():
        found = _RESULT.match(line)
        if found:
            kind, name, test = found.groups()
            (passed if kind == "PASSED" else failed).setdefault(name, []).append(test)
        if re.match(r"^(SKIPPED|XFAIL|XPASS)\b", line):
            unexecuted.append(line)
    # Pytest summary lines are a second guard against a changed -rA format
    # omitting per-case SKIPPED/XFAIL/XPASS records.
    for kind in ("skipped", "xfailed", "xpassed"):
        if re.search(rf"\b[1-9]\d* {kind}\b", ran.stdout) and not any(
            kind.upper().replace("ED", "") in line for line in unexecuted
        ):
            unexecuted.append(f"pytest summary includes {kind} checks")
    # Never treat an import/collection/crash or incomplete run as a passed suite.
    tail = "\n".join((ran.stdout + ran.stderr).strip().splitlines()[-8:])
    return passed, failed, tail, ran.returncode, unexecuted


def live_harness() -> tuple[int, int, str]:
    """attack_check's passed and failed counts."""
    ran = subprocess.run(
        [sys.executable, "-m", "tools.attack_check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    found = re.search(r"(\d+)/(\d+) checks passed", ran.stdout)
    if not found:
        return 0, 1, (ran.stdout + ran.stderr)[-2000:]
    good, total = int(found.group(1)), int(found.group(2))
    unchecked = [line.strip() for line in ran.stdout.splitlines() if "(not checked" in line]
    if unchecked:
        # (A check the harness couldn't run, such as one that needs FFmpeg, is a gap, never a pass.)
        return good, len(unchecked), ("Not run:\n" + "\n".join(unchecked) + "\n" + ran.stdout)[-2000:]
    if total == 0 or good > total or ran.returncode != 0:
        # A subprocess error is a failing gate even if it printed "all passed"
        # before aborting. Keep its exit code and diagnostic in the report.
        return good, max(total - good, 1), (
            f"attack_check exited {ran.returncode}\n" + ran.stdout + ran.stderr
        )[-2000:]
    return good, total - good, ran.stdout[-2000:]


def merge_explains_shrink(corpus: dict, candidate_checks: int) -> bool:
    """Allow only a precisely reviewed, candidate-specific case-count reduction.

    An unrelated or historical entry under "merges" never waives the guard.
    A merge record must name the exact before/after counts, the individual
    removed case IDs, a reason and the full Git SHA of its review evidence.
    """
    baseline = corpus.get("checks", 0)
    if candidate_checks >= baseline:
        return True
    removed_count = baseline - candidate_checks
    entries = corpus.get("merges", [])
    if not isinstance(entries, list):
        return False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        removed = entry.get("removed_case_ids")
        reason = entry.get("reason")
        review_sha = entry.get("review_sha")
        if (
            entry.get("from_checks") == baseline
            and entry.get("to_checks") == candidate_checks
            and isinstance(removed, list)
            and len(removed) == removed_count
            and all(isinstance(v, str) and v.strip() for v in removed)
            and len(set(removed)) == len(removed)
            and isinstance(reason, str)
            and len(reason.strip()) >= 20
            and isinstance(review_sha, str)
            and re.fullmatch(r"[0-9a-f]{40}", review_sha) is not None
        ):
            return True
    return False


def provenance() -> list[str]:
    """What this run ran on (SEC-GATE-P1-05): the commit, the CI run, Python and pytest."""
    import os
    import platform
    from importlib import metadata

    sha, run = os.environ.get("GITHUB_SHA", ""), os.environ.get("GITHUB_RUN_ID", "")
    if sha:
        where = f"Commit {sha}, CI run {run or 'unknown'}."
    else:
        try:
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
            ).stdout.strip()
        except OSError:
            head = ""
        where = f"A local run, at commit {head}." if head else "A local run (no commit known)."
    try:
        pytest_version = metadata.version("pytest")
    except metadata.PackageNotFoundError:
        pytest_version = "not installed"
    return [where, f"Python {platform.python_version()}, pytest {pytest_version}."]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--no-live",
        action="store_true",
        help="the unit layer only (the live harness takes minutes)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="where the report goes (docs/security/report-<version>.md; in the image's CI, a folder it can write)",
    )
    args = parser.parse_args(argv)

    passed, failed, tail, unit_exit, unexecuted = unit_layer()
    live = (0, 0, "not run (--no-live)") if args.no_live else live_harness()
    unknown = sorted((set(passed) | set(failed)) - set(LAYERS))
    missing_layers = sorted(
        name for name in LAYERS if not passed.get(name) and not failed.get(name)
    )
    new_test_files = sorted(
        f.name for f in (ROOT / "tests" / "security").glob("test_*.py")
        if f.name not in LAYERS
    )
    checks = (
        sum(len(v) for v in passed.values())
        + sum(len(v) for v in failed.values())
        + live[0]
        + live[1]
    )

    corpus = (
        json.loads(CORPUS.read_text(encoding="utf-8"))
        if CORPUS.exists()
        else {"checks": 0, "merges": []}
    )
    shrank = not args.no_live and checks < corpus.get("checks", 0) and not merge_explains_shrink(corpus, checks)
    exceptions = json.loads(EXCEPTIONS.read_text(encoding="utf-8")) if EXCEPTIONS.exists() else []

    lines = [
        f"# Security report, tapiOca {__version__}",
        "",
        f"Run {date.today().isoformat()}.",
        *provenance(),
        "",
    ]
    lines += ["| Area | Severity | Passed | Failed |", "| --- | --- | --- | --- |"]
    for name, (what, severity) in LAYERS.items():
        lines.append(
            f"| {what} | {severity} | {len(passed.get(name, []))} | {len(failed.get(name, []))} |"
        )
    lines.append(f"| The live harness (attack_check) | Critical | {live[0]} | {live[1]} |")
    lines += [
        "",
        f"Checks in all: {checks} (the corpus last recorded {corpus.get('checks', 0)}).",
        "",
    ]
    if unit_exit != 0:
        lines += [f"Pytest exited {unit_exit}; the unit layer is FAILED (including collection errors).", ""]
    if not any(passed.values()) and not any(failed.values()):
        lines += ["No recognized unit test results; unit layer is FAILED.", ""]
    if args.no_live:
        lines += ["The live harness was NOT RUN (--no-live); this is not a release certification.", ""]
    if unknown:
        lines += [f"Reported test files not in the suite's table: {', '.join(unknown)}.", ""]
    if new_test_files:
        lines += [f"Unregistered security-test source files: {', '.join(new_test_files)}.", ""]
    if missing_layers:
        lines += [f"Missing expected security test layers: {', '.join(missing_layers)}.", ""]
    for status in unexecuted:
        lines += [f"Unexecuted security test: {status}", ""]
    lines += [
        "Tracked exceptions (Medium):",
        *(f"- {e}" for e in exceptions),
        "" if exceptions else "- none",
        "",
    ]
    for name, tests in failed.items():
        for test in tests:
            lines.append(f"FAILED ({LAYERS.get(name, ('', 'High'))[1]}): {name}::{test}")
    if live[1]:
        lines += ["", "The live harness:", "", "```", live[2], "```"]
    report = args.report or ROOT / "docs" / "security" / f"report-{__version__}.md"

    unit_failed = unit_exit != 0 or (not any(passed.values()) and not any(failed.values()))
    bad = sum(len(v) for v in failed.values()) + live[1] + len(unknown) + (1 if shrank else 0)
    bad += int(unit_failed) + len(missing_layers) + len(new_test_files) + len(unexecuted)
    # (Printed first, so the run's log always has it; then kept where it was asked to go.)
    print("\n".join(lines))
    print(tail)
    if not args.no_live:
        try:
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as e:
            print(f"The report couldn't be written to {report}: {e}")
            bad += 1
            report = None
    if shrank:
        print(
            f"The corpus shrank: {checks} checks, {corpus['checks']} recorded, with no exact reviewed merge for this transition."
        )
    print(
        f"Security: {checks} checks, {'unit-only PASS (live NOT RUN)' if args.no_live and not bad else 'all passing' if not bad else f'{bad} failing'}. "
        f"Report: {'not written (unit-only)' if args.no_live else report or 'not written'}"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
