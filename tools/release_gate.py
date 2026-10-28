#!/usr/bin/env python3
"""The release gate, checked by CI instead of by hand.

Each release has a manifest beside its notes (`<app>/releases/v<version>.toml`
in the apps' repository, `docs/releases/v<version>.toml` in the server's),
committed with the tested code, never with the notes. It says what the release
is and the proof its class requires. This checks it, failing closed:

    python3 tools/release_gate.py check android 0.15.1          # the apps' release jobs
    python3 tools/release_gate.py check server 1.45.0 <commit>  # the server's, at its tested commit
    python3 tools/release_gate.py lint                          # every push: every manifest present

In CI, `--fetch` first fetches what a shallow checkout lacks (with GH_TOKEN).
The apps' repository also reads the plan (release order, readiness records,
feature register) from its `plan-update` branch. The server's reads it for a
Class D release with PLAN_READ_TOKEN (read-only, the apps repository's contents
alone), comparing the record's commit time with its first code commit's; with
no token, or a token that fails, a Class D release fails. The same file in both
repositories. Standard library only.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The same file in both repositories: the server's has no app folders.
SERVER = not (ROOT / "android").exists()
PLATFORMS = (
    {"server": "docs/releases"}
    if SERVER
    else {"android": "android/releases", "apple": "ios/releases", "roku": "roku/releases"}
)
TAGS = {"server": "v", "android": "android-v", "apple": "apple-v", "roku": "roku-v"}
CODE = (
    ("app/",)
    if SERVER
    else (
        "android/app/",
        "ios/StationPlay/",
        "ios/Core/",
        "roku/components/",
        "roku/source/",
        "shared/cases/",
    )
)
NOT_RUN = "NOT RUN, real device, at 1.0"
LEVELS = ("R0", "R1", "R2", "R3", "R4", "R5")
FG_FOR_C = ("FG-01", "FG-06", "FG-08", "FG-09")
# Part 2's gates (screens, accessibility, limits, mutation, the soak's record)
# apply to each platform's releases after these, its last before them.
PART2_AFTER = {"server": "1.44.2", "android": "0.15.1", "apple": "0.14.1", "roku": "0.18.1"}


@dataclass
class Context:
    """What a manifest is checked against: the files at the release's commit,
    the plan's readiness records and feature register, and the history."""

    files: dict[str, str]  # path -> text, as committed (only the paths asked for need be here)
    readiness: dict[str, str]  # a readiness row's Feature cell -> its level, R0 to R5
    code_since: list[str]  # this release's code commits since the last release, oldest first
    commits: list[str]  # the history up to the release, oldest first
    parity_rows: set[str]  # PARITY.md's rows (a manifest names one by how it starts)
    register_ids: set[str]  # the plan's feature register IDs
    apps: bool = True  # an app release (it names the server version it was checked against, and its PARITY.md rows)
    plan_known: bool = True  # the plan was read
    plan_unread: str = ""  # why it couldn't be: a Class D release fails on it
    record_before_code: bool | None = (
        None  # (the server's: its record and its code are in two repositories)
    )
    platform: str = ""  # android, apple, roku or server
    changed: set[str] = field(
        default_factory=set
    )  # the files the release changes, since the platform's last tag
    limits: dict = field(default_factory=dict)  # tools/limits_baseline.json, as committed
    mutation_files: set[str] = field(
        default_factory=set
    )  # the files tools/mutation_targets.json names
    starts_history: bool = False  # the release's tag is the repository's first commit: what its reviews name came before it
    _order: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    def position(self, commit: str) -> int | None:
        if not self._order:
            self._order = {c: i for i, c in enumerate(self.commits)}
        hits = [i for c, i in self._order.items() if c.startswith(commit)]
        return hits[0] if len(hits) == 1 else None


def is_patch(version: str) -> bool:
    return not version.endswith(".0")


def numbers(version: str) -> list[int]:
    return [int(x) for x in version.split(".")]


def parse(text: str) -> tuple[dict | None, list[str]]:
    try:
        return tomllib.loads(text), []
    except tomllib.TOMLDecodeError as e:
        return None, [f"the manifest isn't TOML: {e}"]


def problems(m: dict, version: str, ctx: Context) -> list[str]:
    out: list[str] = []
    out += _what_it_is(m)
    cls = m.get("class")
    if cls not in ("A", "B", "C", "D"):
        out.append(f"class must be A, B, C or D, not {cls!r}")
        cls = None
    out += _features(m, version, ctx)
    out += _reviews(m, ctx)
    if ctx.apps:
        out += _parity(m, ctx)
    out += _modularity(m)
    if ctx.apps and not m.get("server"):
        out.append("server: name the server version whose security suite passed for this release")
    for step in m.get("device_only", []):
        if step.get("state") != NOT_RUN:
            out.append(
                f"device_only: {step.get('step')!r} is {step.get('state')!r}; a real device's step is {NOT_RUN!r} until 1.0"
            )
    if cls == "C":
        fg = m.get("fg", {})
        out += [f"fg: Class C needs its {g} note" for g in FG_FOR_C if not fg.get(g)]
    if cls == "D":
        out += _class_d(m, ctx)
    if ctx.platform in PART2_AFTER and numbers(version) > numbers(PART2_AFTER[ctx.platform]):
        out += _part2(m, version, cls, ctx)
    return out


def _part2(m: dict, version: str, cls: str | None, ctx: Context) -> list[str]:
    """Gates that enforce themselves, part 2: the screens and accessibility
    runs (apps), the hard limits, the mutation run where a key decision
    changed, for Class D a soak record for this platform, and for a feature
    release its run beside Jellyfin."""
    out = []
    if ctx.apps:
        for key, what in (
            ("screens", "the screens comparison"),
            ("accessibility", "the accessibility audit"),
        ):
            got = m.get(key, {})
            ran = got.get("compare" if key == "screens" else "audit")
            if not ran and not got.get("none_because"):
                out.append(f"{key}: name {what}'s run, or give none_because (no screen changed)")
    out += _limits(m, ctx)
    if ctx.changed & ctx.mutation_files:
        mut = m.get("mutation", {})
        if not mut.get("run"):
            out.append(
                f"mutation: it changes {', '.join(sorted(ctx.changed & ctx.mutation_files))}, a key decision: name its mutation run"
            )
        elif mut.get("missing_tests") != 0:
            out.append(
                f"mutation: its run has {mut.get('missing_tests')!r} missing tests; a surviving mutant is a missing test"
            )
    if cls == "D":
        out += _soak(m, ctx)
    out += _beside_jellyfin(m, version, ctx)
    return out


# The platforms the like-for-like run beside Jellyfin measures (DL375): its Android TV app and
# Roku package, and its server; Android's stands for Apple's, by the owner's choice.
COMPARED = {"server", "android", "roku"}
# How much heavier than Jellyfin a measure may come out before the work halts and the owner is
# told (the owner, October 28: "halt and report if testing shows results that are not acceptable
# tolerance"): past it, a release needs his OK.
JELLYFIN_TOLERANCE = 0.2


def _beside_jellyfin(m: dict, version: str, ctx: Context) -> list[str]:
    """A feature release names its run beside Jellyfin's open-source apps and server, and each
    measure where tapiOca is heavier, with where that's captured (DL375)."""
    if is_patch(version) or ctx.platform not in COMPARED:
        return []
    got = m.get("jellyfin", {})
    if not got.get("run"):
        return ["jellyfin: a feature release names its run beside Jellyfin (compare-jellyfin.yml)"]
    heavier = got.get("heavier")
    if not isinstance(heavier, list):
        return ["jellyfin: say where tapiOca measured heavier, as heavier = [] when nowhere"]
    out = []
    for h in heavier:
        name, by = h.get("measure"), h.get("by")
        if not h.get("captured"):
            out.append(f"jellyfin: {name!r} is heavier than Jellyfin's: say where it's captured")
        if not isinstance(by, (int, float)):
            out.append(f"jellyfin: say by how much {name!r} is heavier, as a fraction (by = 0.25)")
        elif by > JELLYFIN_TOLERANCE and not h.get("owner_ok"):
            out.append(
                f"jellyfin: {name!r} is {by:.0%} heavier than Jellyfin's, past {JELLYFIN_TOLERANCE:.0%}:"
                " halt and report to the owner; it needs his owner_ok"
            )
    return out


def _limits(m: dict, ctx: Context) -> list[str]:
    """Startup, memory and download size (the server: its CPU and memory under
    the soak), each against the owner's approved baseline, never worse past
    its tolerance without his OK."""
    base = ctx.limits.get(ctx.platform)
    got = m.get("limits")
    if not got:
        return ["limits: give the hard limits' measurements and their run"]
    if not got.get("run"):
        return ["limits: name the run that measured them"]
    if not base or not base.get("approved"):
        return [
            f"limits: {ctx.platform} has no baseline the owner has approved yet (tools/limits_baseline.json)"
        ]
    out = []
    for name, rule in base["values"].items():
        value = got.get(name)
        if not isinstance(rule.get("value"), (int, float)):
            out.append(f"limits: {name} has no baseline value")
        elif not isinstance(value, (int, float)):
            out.append(f"limits: {name} is missing")
        elif value > rule["value"] * (1 + rule["worse_by"]) and not got.get("owner_ok"):
            out.append(
                f"limits: {name} is {value}, worse than its baseline {rule['value']} by more than {rule['worse_by']:.0%}:"
                " halt and report to the owner; it needs his owner_ok"
            )
    return out


def _soak(m: dict, ctx: Context) -> list[str]:
    runs = m.get("soak")
    if not isinstance(runs, list):
        return [
            "soak: a Class D release gives its soak as [[soak]] records (platform, run, minutes, result)"
        ]
    mine = [r for r in runs if r.get("platform") == ctx.platform]
    if not mine:
        return [f"soak: no soak record for {ctx.platform}"]
    out = []
    for r in mine:
        if not r.get("run") or not isinstance(r.get("minutes"), (int, float)) or r["minutes"] <= 0:
            out.append(
                f"soak: {ctx.platform}'s record needs its run and how many minutes it soaked"
            )
        if r.get("result") != "passed":
            out.append(f"soak: {ctx.platform}'s soak is {r.get('result')!r}, not passed")
    return out


def _what_it_is(m: dict) -> list[str]:
    out = []
    if not m.get("release"):
        out.append("release: name the release, as the plan's release order does")
    if not isinstance(m.get("row"), int):
        out.append("row: give its release-order row")
    return out


def _features(m: dict, version: str, ctx: Context) -> list[str]:
    features = m.get("features", [])
    out = [
        f"features: {f!r} isn't in the plan's feature register"
        for f in features
        if ctx.plan_known and f not in ctx.register_ids
    ]
    if is_patch(version) and features:
        out.append(
            f"{version} is a patch, so it names no feature register ID; this names {', '.join(features)}"
        )
    if not is_patch(version):
        if not features:
            out.append(
                f"{version} is a feature release, so it names at least one feature register ID"
            )
        if not m.get("minimums"):
            out.append(
                "minimums: a feature release until the launch sets the minimum versions it moves"
            )
    return out


def _reviews(m: dict, ctx: Context) -> list[str]:
    reviews = m.get("review", [])
    if not reviews:
        return ["review: name the release's review reports"]
    out = []
    for r in reviews:
        report, commit = r.get("report", ""), r.get("commit", "")
        text = ctx.files.get(report)
        if text is None:
            out.append(f"review: {report!r} isn't in the release's commit")
        elif not re.search(r"^#+ Quality bar\b", text, re.M):
            out.append(f"review: {report!r} has no Quality bar section")
        if not commit or (ctx.position(commit) is None and not ctx.starts_history):
            out.append(
                f"review: {report!r} reviewed {commit!r}, which isn't one commit in the release's history"
            )
    return out


def _parity(m: dict, ctx: Context) -> list[str]:
    rows = m.get("parity")
    if rows is None or (not rows and not m.get("parity_none_because")):
        return ["parity: name the PARITY.md rows it adds or changes, or give parity_none_because"]
    out = []
    for r in rows:
        hits = [row for row in ctx.parity_rows if row.startswith(r)]
        if len(hits) != 1:
            out.append(f"parity: {r!r} starts {len(hits)} PARITY.md rows, not one")
    return out


def _modularity(m: dict) -> list[str]:
    mod = m.get("modularity")
    if not mod:
        return [
            "modularity: name the component it changes, its contract, how it's switched off and what it deleted"
        ]
    out = [
        f"modularity: {k} is missing" for k in ("component", "contract", "off") if not mod.get(k)
    ]
    if "deleted" not in mod and not mod.get("deleted_none_because"):
        out.append(
            "modularity: deleted is missing (the old code it deleted, or deleted_none_because)"
        )
    return out


def _readiness(m: dict, ctx: Context) -> list[str]:
    """A Class D release's readiness record: named, at R3 or above in the plan,
    and committed before the release's first code commit."""
    name = m.get("readiness")
    if not name:
        return ["readiness: a Class D release names its readiness record"]
    if not m.get("readiness_commit"):
        return [
            "readiness_commit: a Class D release names the commit that brought its readiness record to R3"
        ]
    if not ctx.plan_known:
        return [
            f"readiness: {ctx.plan_unread or 'the plan was not read'}, so this Class D release's record can't be checked"
        ]
    out = []
    rows = [k for k in ctx.readiness if name in k]
    if len(rows) != 1:
        out.append(
            f"readiness: {name!r} matches {len(rows)} readiness records in the plan, not one"
        )
    elif LEVELS.index(ctx.readiness[rows[0]]) < LEVELS.index("R3"):
        out.append(
            f"readiness: {name!r} is {ctx.readiness[rows[0]]}; a Class D release needs R3 or above before its code"
        )
    if ctx.record_before_code is not None:
        if not ctx.record_before_code:
            out.append("readiness: its record was committed after the release's first code commit")
        return out
    at, first = ctx.position(m["readiness_commit"]), ctx.code_since[:1]
    if at is None:
        out.append(
            f"readiness_commit: {m['readiness_commit']!r} isn't one commit in the release's history"
        )
    elif first and at >= (ctx.position(first[0]) or 0):
        out.append(
            f"readiness: its record was committed after the release's first code commit ({first[0][:8]})"
        )
    return out


def _class_d(m: dict, ctx: Context) -> list[str]:
    out = _readiness(m, ctx)
    model = m.get("threat_model")
    if not model:
        out.append("threat_model: a Class D release names its threat model")
    elif model not in ctx.files:
        out.append(f"threat_model: {model!r} isn't in the release's commit")
    if sum(r.get("kind") == "cold-audit" for r in m.get("review", [])) < 2:
        out.append("review: a Class D release names two cold audits")
    if not m.get("soak"):
        out.append("soak: a Class D release names the soak it passed")
    return out


# Reading the repository --------------------------------------------------------


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def at(rev: str, path: str) -> str | None:
    try:
        return git("show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return None


def starts_history(tag: str) -> bool:
    """The tag is on the repository's first commit (a shallow copy's oldest
    commit has parents it wasn't given, so it never counts)."""
    try:
        if git("rev-parse", "--is-shallow-repository").strip() != "false":
            return False
        return len(git("rev-list", "--parents", "-n", "1", f"refs/tags/{tag}").split()) == 1
    except subprocess.CalledProcessError:
        return False


def plan_tables(plan: str) -> tuple[dict[str, str], set[str]]:
    """The readiness records (Feature -> level) and the feature register's IDs."""
    readiness: dict[str, str] = {}
    a = plan.index("### Readiness records")
    for line in plan[a : plan.index("\n### ", a + 1)].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) > 1 and cells[1] in LEVELS:
            readiness[cells[0]] = cells[1]
    a = plan.index("## The feature register")
    end = plan.find("\n## ", a + 1)
    ids = set(re.findall(r"^\| ([a-z0-9][a-z0-9-]*) \|", plan[a : end if end > 0 else None], re.M))
    return readiness, ids


def parity_rows(text: str) -> set[str]:
    return {m.group(1).strip().strip("*") for m in re.finditer(r"^\| ([^|]+?) \|", text, re.M)} - {
        "---",
        "Feature",
        "What",
    }


APPS_REPO = "egadgetboy/tapioca-apps"


def github(path: str, raw: bool = False) -> bytes:
    """A read of the apps' repository from the server's, with PLAN_READ_TOKEN
    (read-only, that repository's contents alone)."""
    import os
    import urllib.request

    req = urllib.request.Request(
        f"https://api.github.com/repos/{APPS_REPO}/{path}",
        headers={
            "Authorization": f"Bearer {os.environ['PLAN_READ_TOKEN']}",
            "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def server_plan(manifest: dict, code: list[str]) -> dict:
    """For the server's repository: the plan read from the apps' repository,
    and whether the readiness record's commit there came before this
    release's first code commit here, by their commit times."""
    import os
    from datetime import datetime

    if not os.environ.get("PLAN_READ_TOKEN"):
        return {
            "plan_known": False,
            "plan_unread": "PLAN_READ_TOKEN isn't set, so the plan can't be read",
        }
    try:
        readiness, ids = plan_tables(github("contents/plan.md?ref=plan-update", raw=True).decode())
        before = None
        if manifest.get("readiness_commit") and code:
            made = json.loads(github(f"commits/{manifest['readiness_commit']}"))["commit"][
                "committer"
            ]["date"]
            first = git("log", "-1", "--format=%cI", code[0]).strip()
            before = datetime.fromisoformat(made.replace("Z", "+00:00")) < datetime.fromisoformat(
                first
            )
    except (
        OSError
    ) as e:  # (the token expired or was revoked, or GitHub didn't answer: never a pass)
        return {
            "plan_known": False,
            "plan_unread": f"the plan couldn't be read with PLAN_READ_TOKEN ({e})",
        }
    return {"readiness": readiness, "register_ids": ids, "record_before_code": before}


def context_at(rev: str, platform: str, paths: list[str], manifest: dict | None = None) -> Context:
    readiness: dict[str, str] = {}
    ids: set[str] = set()
    if not SERVER:
        plan = at("origin/plan-update", "plan.md")
        if plan is None:
            raise SystemExit(
                "release_gate: the plan isn't fetched (git fetch origin +refs/heads/plan-update:refs/remotes/origin/plan-update)"
            )
        readiness, ids = plan_tables(plan)
    prefix = TAGS[platform]
    tags = [
        t
        for t in git("tag", "--list", f"{prefix}*", "--merged", rev).split()
        if re.fullmatch(re.escape(prefix) + r"\d+\.\d+\.\d+", t)
    ]
    last = tags and max(tags, key=lambda t: [int(x) for x in t[len(prefix) :].split(".")])
    span = f"{last}..{rev}" if last else rev
    code = git("log", "--reverse", "--format=%H", span, "--", *CODE).split()
    files = {p: t for p in paths if (t := at(rev, p)) is not None}
    changed = set(git("diff", "--name-only", f"{last}..{rev}").split()) if last else set()
    targets = json.loads(at(rev, "tools/mutation_targets.json") or '{"targets": {}}')["targets"]
    ctx = Context(
        files=files,
        readiness=readiness,
        code_since=code,
        commits=git("log", "--reverse", "--format=%H", rev).split(),
        parity_rows=parity_rows(at(rev, "PARITY.md") or ""),
        register_ids=ids,
        apps=not SERVER,
        platform=platform,
        changed=changed,
        limits=json.loads(at(rev, "tools/limits_baseline.json") or "{}"),
        mutation_files={t["file"] for t in targets.values()},
    )
    if SERVER and (manifest or {}).get("class") == "D":
        for key, value in server_plan(manifest or {}, code).items():
            setattr(ctx, key, value)
    elif SERVER:
        ctx.plan_known = False  # (only a Class D release needs the plan: a feature ID is checked in the apps' repository)
    return ctx


def check(platform: str, version: str, rev: str = "HEAD") -> list[str]:
    path = f"{PLATFORMS[platform]}/v{version}.toml"
    text = at(rev, path)
    if text is None:
        return [f"{path}: no manifest, so no release (the plan's Gates that enforce themselves)"]
    m, found = parse(text)
    if m is None:
        return [f"{path}: {p}" for p in found]
    paths = [r.get("report", "") for r in m.get("review", [])] + [m.get("threat_model", "")]
    ctx = context_at(rev, platform, [p for p in paths if p], m)
    ctx.starts_history = starts_history(TAGS[platform] + version)
    return [f"{path}: {p}" for p in problems(m, version, ctx)]


def lint() -> list[str]:
    out = []
    for platform, folder in PLATFORMS.items():
        for f in sorted((ROOT / folder).glob("v*.toml")):
            out += check(platform, f.stem[1:], "HEAD")
    return out


def fetch() -> None:
    """In CI: the whole history, the release tags and the plan's branch, which
    a shallow checkout without kept credentials doesn't have (the token is
    passed for these fetches only)."""
    import base64
    import os

    token = os.environ.get("GH_TOKEN", "")
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    # (In this process's environment only, never in .git/config: a sparse
    # checkout fetches the files read later on demand, with the same header.)
    os.environ.update(
        GIT_CONFIG_COUNT="1",
        GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
        GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {auth}",
    )
    shallow = git("rev-parse", "--is-shallow-repository").strip() == "true"
    git("fetch", "-q", *(["--unshallow"] if shallow else []), "--tags", "origin")
    if not SERVER:
        git("fetch", "-q", "origin", "+refs/heads/plan-update:refs/remotes/origin/plan-update")


def check_plan_token() -> int:
    """The server's: PLAN_READ_TOKEN still reads the plan, so a Class D
    release isn't the first to find it expired."""
    plan = server_plan({}, [])
    if not plan.get("plan_known", True):
        print(f"::error::{plan['plan_unread']}: renew it, as the steps in the plan's next.md say")
        return 1
    print(f"PLAN_READ_TOKEN reads the plan ({len(plan['readiness'])} readiness records)")
    return 0


def run(argv: list[str], fetching: bool) -> list[str] | None:
    """The gate's problems for `check` or `lint`; None for anything else."""
    if len(argv) in (4, 5) and argv[1] == "check" and argv[2] in PLATFORMS:
        if fetching:
            fetch()
        return check(argv[2], argv[3], argv[4] if len(argv) == 5 else "HEAD")
    if len(argv) == 2 and argv[1] == "lint":
        if fetching and any((ROOT / folder).glob("v*.toml") for folder in PLATFORMS.values()):
            fetch()
        return lint()
    return None


def main(argv: list[str]) -> int:
    if argv[1:] == ["--check-plan-token"]:
        return check_plan_token()
    if argv[1:] == ["--fetch-only"]:
        fetch()  # (for the checks on changed lines, which compare with the last release's tag)
        return 0
    fetching = argv[1:2] == ["--fetch"]
    found = run(argv[:1] + argv[2:] if fetching else argv, fetching)
    if found is None:
        print(__doc__)
        return 2
    for p in found:
        print(f"::error::{p}")
    if not found:
        print("The release gate: nothing missing")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
