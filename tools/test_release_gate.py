"""The release gate's own tests (tools/release_gate.py), each on a fixture
with the fault it must catch. Standard library only:

    python3 tools/test_release_gate.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import release_gate as g

GOOD_REPORT = "# Review\n\nAll fine.\n\n## Quality bar\n\nNo duplicated logic added.\n"


def ctx(**over) -> g.Context:
    files = {
        "docs/reviews/r/self.md": GOOD_REPORT,
        "docs/reviews/r/audit-1.md": GOOD_REPORT,
        "docs/reviews/r/audit-2.md": GOOD_REPORT,
        "docs/threat-models/r.md": "# Threats\n",
    }
    files.update(over.pop("files", {}))
    base = dict(
        files=files,
        readiness={"r-record": "R3"},
        code_since=["c2", "c3"],  # the release's code commits, oldest first
        commits=["c0", "c1", "c2", "c3", "c4"],  # history, oldest first
        parity_rows={"Titles keep their last two words"},
        register_ids={"F-101"},
        apps=True,
    )
    base.update(over)
    return g.Context(**base)


def patch_b(**over) -> dict:
    m = {
        "release": "A title's last two words",
        "row": 139,
        "class": "B",
        "features": [],
        "parity": ["Titles keep their last two words"],
        "server": "1.44.1",
        "review": [{"kind": "self-review", "report": "docs/reviews/r/self.md", "commit": "c3"}],
        "modularity": {
            "component": "ShellTitles",
            "contract": "shared/cases/words.json",
            "off": "not optional",
            "deleted": ["the old helper"],
        },
    }
    m.update(over)
    return m


def class_d(**over) -> dict:
    m = patch_b(
        **{
            "class": "D",
            "readiness": "r-record",
            "readiness_commit": "c1",
            "threat_model": "docs/threat-models/r.md",
            "soak": "quality 123: two hours, no failure",
            "review": [
                {"kind": "cold-audit", "report": "docs/reviews/r/audit-1.md", "commit": "c3"},
                {"kind": "cold-audit", "report": "docs/reviews/r/audit-2.md", "commit": "c4"},
            ],
        }
    )
    m.update(over)
    return m


def problems(manifest: dict, version: str = "0.15.1", **over) -> list[str]:
    return g.problems(manifest, version, ctx(**over))


def has(found: list[str], words: str) -> bool:
    return any(words in p for p in found)


class GoodManifestsPass(unittest.TestCase):
    def test_a_class_b_patch(self):
        self.assertEqual(problems(patch_b()), [])

    def test_a_class_d_patch(self):
        self.assertEqual(problems(class_d()), [])

    def test_a_feature_release(self):
        m = patch_b(features=["F-101"], minimums={"android": "0.16.0", "server": "1.45.0"})
        self.assertEqual(problems(m, "0.16.0"), [])

    def test_a_class_c_release(self):
        m = patch_b(
            **{"class": "C", "fg": {"FG-01": "x", "FG-06": "x", "FG-08": "x", "FG-09": "x"}}
        )
        self.assertEqual(problems(m), [])


class TheFaultsItCatches(unittest.TestCase):
    def test_no_class(self):
        m = patch_b()
        del m["class"]
        self.assertTrue(has(problems(m), "class"))

    def test_an_unknown_class(self):
        self.assertTrue(has(problems(patch_b(**{"class": "E"})), "class"))

    def test_a_minor_version_with_no_feature(self):
        self.assertTrue(has(problems(patch_b(), "0.16.0"), "feature register ID"))

    def test_a_patch_with_a_feature(self):
        self.assertTrue(has(problems(patch_b(features=["F-101"]), "0.15.1"), "feature register ID"))

    def test_an_unknown_feature(self):
        m = patch_b(features=["F-999"], minimums={"android": "0.16.0"})
        self.assertTrue(has(problems(m, "0.16.0"), "F-999"))

    def test_a_feature_release_with_no_minimums(self):
        self.assertTrue(has(problems(patch_b(features=["F-101"]), "0.16.0"), "minimums"))

    def test_no_review(self):
        self.assertTrue(has(problems(patch_b(review=[])), "review"))

    def test_a_review_report_missing(self):
        m = patch_b(
            review=[{"kind": "self-review", "report": "docs/reviews/r/gone.md", "commit": "c3"}]
        )
        self.assertTrue(has(problems(m), "gone.md"))

    def test_a_review_with_no_quality_bar(self):
        found = problems(patch_b(), files={"docs/reviews/r/self.md": "# Review\n\nAll fine.\n"})
        self.assertTrue(has(found, "Quality bar"))

    def test_a_review_of_an_unknown_commit(self):
        m = patch_b(
            review=[{"kind": "self-review", "report": "docs/reviews/r/self.md", "commit": "zz"}]
        )
        self.assertTrue(has(problems(m), "zz"))

    def test_a_release_that_starts_the_history_still_names_its_reviewed_commit(self):
        m = patch_b(review=[{"kind": "self-review", "report": "docs/reviews/r/self.md", "commit": ""}])
        self.assertTrue(has(problems(m, starts_history=True), "review"))


class AHistoryThatStartsAtARelease(unittest.TestCase):
    """A repository started afresh at a release: that release's reviews named
    commits from before it, which this history doesn't have."""

    def test_its_reviewed_commit_isnt_looked_up(self):
        m = patch_b(
            review=[{"kind": "self-review", "report": "docs/reviews/r/self.md", "commit": "f002d11"}]
        )
        self.assertEqual(problems(m, starts_history=True), [])
        self.assertTrue(has(problems(m), "f002d11"))

    def git(self, where: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(where), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def repository(self) -> Path:
        where = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, where)
        self.git(where, "init", "-q")
        for n in ("1", "2", "3"):
            (where / "f").write_text(n)
            self.git(where, "add", "f")
            self.git(where, "commit", "-q", "-m", n)
            self.git(where, "tag", f"v1.0.{n}")
        return where

    def starts(self, where: Path, tag: str) -> bool:
        kept, g.ROOT = g.ROOT, where
        try:
            return g.starts_history(tag)
        finally:
            g.ROOT = kept

    def test_a_tag_on_the_first_commit_starts_it(self):
        where = self.repository()
        self.assertTrue(self.starts(where, "v1.0.1"))
        self.assertFalse(self.starts(where, "v1.0.2"))
        self.assertFalse(self.starts(where, "v1.0.9"))

    def test_a_shallow_copys_first_commit_doesnt(self):
        where = self.repository()
        copy = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, copy)
        self.git(copy, "clone", "-q", "--depth", "1", "--no-local", f"file://{where}", "c")
        self.git(copy / "c", "fetch", "-q", "--depth", "1", "origin", "tag", "v1.0.3")
        self.assertFalse(self.starts(copy / "c", "v1.0.3"))

    def test_a_class_c_without_its_fg_notes(self):
        m = patch_b(**{"class": "C", "fg": {"FG-01": "x", "FG-06": "x"}})
        found = problems(m)
        self.assertTrue(has(found, "FG-08"))
        self.assertTrue(has(found, "FG-09"))

    def test_a_class_d_without_a_readiness_record(self):
        m = class_d()
        del m["readiness"]
        self.assertTrue(has(problems(m), "readiness"))

    def test_a_class_d_whose_record_is_below_r3(self):
        self.assertTrue(has(problems(class_d(), readiness={"r-record": "R2"}), "R3"))

    def test_a_class_d_whose_record_is_not_in_the_plan(self):
        self.assertTrue(has(problems(class_d(), readiness={}), "r-record"))

    def test_a_class_d_whose_record_came_after_its_code(self):
        self.assertTrue(has(problems(class_d(readiness_commit="c3")), "after"))

    def test_a_class_d_whose_record_commit_is_unknown(self):
        self.assertTrue(has(problems(class_d(readiness_commit="zz")), "zz"))

    def test_a_class_d_without_a_threat_model(self):
        m = class_d()
        del m["threat_model"]
        self.assertTrue(has(problems(m), "threat model"))

    def test_a_class_d_whose_threat_model_is_missing(self):
        self.assertTrue(
            has(problems(class_d(threat_model="docs/threat-models/gone.md")), "gone.md")
        )

    def test_a_class_d_with_one_cold_audit(self):
        m = class_d()
        m["review"] = m["review"][:1]
        self.assertTrue(has(problems(m), "two cold audits"))

    def test_a_class_d_without_a_soak(self):
        m = class_d()
        del m["soak"]
        self.assertTrue(has(problems(m), "soak"))

    def test_a_real_device_step_marked_passed(self):
        m = patch_b(device_only=[{"step": "Roku's measuring", "state": "passed"}])
        self.assertTrue(has(problems(m), "real device"))

    def test_a_real_device_step_marked_as_planned(self):
        m = patch_b(
            device_only=[{"step": "Roku's measuring", "state": "NOT RUN, real device, at 1.0"}]
        )
        self.assertEqual(problems(m), [])

    def test_a_parity_row_that_isnt_there(self):
        self.assertTrue(has(problems(patch_b(parity=["No such row"])), "No such row"))

    def test_a_parity_name_that_starts_two_rows(self):
        found = problems(
            patch_b(parity=["Titles"]),
            parity_rows={"Titles keep their last two words", "Titles in Title Case"},
        )
        self.assertTrue(has(found, "2 PARITY.md rows"))

    def test_a_parity_row_named_by_how_it_starts(self):
        self.assertEqual(problems(patch_b(parity=["Titles keep"])), [])

    def test_no_parity_rows_without_a_reason(self):
        self.assertTrue(has(problems(patch_b(parity=[])), "parity"))

    def test_no_parity_rows_with_a_reason(self):
        self.assertEqual(problems(patch_b(parity=[], parity_none_because="the server's alone")), [])

    def test_an_app_release_without_its_server_version(self):
        m = patch_b()
        del m["server"]
        self.assertTrue(has(problems(m), "server"))

    def test_the_server_needs_no_server_version(self):
        m = patch_b()
        del m["server"]
        self.assertEqual(problems(m, apps=False), [])

    def test_no_modularity(self):
        m = patch_b()
        del m["modularity"]
        self.assertTrue(has(problems(m), "modularity"))

    def test_modularity_without_what_was_deleted(self):
        m = patch_b(modularity={"component": "x", "contract": "y", "off": "not optional"})
        self.assertTrue(has(problems(m), "deleted"))

    def test_no_release_name_or_row(self):
        m = patch_b()
        del m["release"], m["row"]
        found = problems(m)
        self.assertTrue(has(found, "release"))
        self.assertTrue(has(found, "row"))


class TheServersRepository(unittest.TestCase):
    """(The same file there: it can't read the plan, so a Class D release's
    record is checked for presence, and there's no PARITY.md.)"""

    def test_a_class_d_when_the_plan_cant_be_read(self):
        m = class_d()
        del m["server"], m["parity"]
        found = problems(
            m, apps=False, plan_known=False, plan_unread="PLAN_READ_TOKEN isn't set", readiness={}
        )
        self.assertTrue(has(found, "PLAN_READ_TOKEN"))

    def test_a_class_d_read_from_the_apps_repository(self):
        m = class_d()
        del m["server"], m["parity"]
        self.assertEqual(problems(m, apps=False, record_before_code=True), [])

    def test_a_class_d_whose_record_came_after_its_code_in_the_other_repository(self):
        m = class_d()
        del m["server"], m["parity"]
        self.assertTrue(has(problems(m, apps=False, record_before_code=False), "after"))

    def test_a_class_d_below_r3_read_from_the_apps_repository(self):
        m = class_d()
        del m["server"], m["parity"]
        self.assertTrue(
            has(
                problems(m, apps=False, record_before_code=True, readiness={"r-record": "R2"}), "R3"
            )
        )

    def test_a_class_d_with_no_record_commit(self):
        m = class_d()
        del m["server"], m["readiness_commit"]
        self.assertTrue(
            has(problems(m, apps=False, plan_known=False, plan_unread="x"), "readiness_commit")
        )

    def test_a_feature_id_it_cant_look_up(self):
        m = patch_b(features=["F-999"], minimums={"server": "1.45.0"})
        del m["server"]
        self.assertEqual(problems(m, "1.45.0", apps=False, plan_known=False), [])


LIMITS = {
    "android": {
        "approved": "the owner, October 28",
        "values": {
            "startup_ms": {"value": 800, "worse_by": 0.2},
            "memory_mb": {"value": 150, "worse_by": 0.1},
        },
    }
}


def part2(**over) -> dict:
    """A release after part 2 that meets it."""
    m = patch_b(
        screens={"compare": "android-screens 1: 68 of 68 as approved"},
        accessibility={"audit": "android-screens 1: 68 screens, no new problems"},
        limits={"run": "android-screens 1", "startup_ms": 790, "memory_mb": 140},
    )
    m.update(over)
    return m


def p2(manifest: dict, version: str = "0.15.2", **over) -> list[str]:
    over.setdefault("platform", "android")
    over.setdefault("limits", LIMITS)
    return g.problems(manifest, version, ctx(**over))


class Part2(unittest.TestCase):
    def test_a_release_that_meets_it(self):
        self.assertEqual(p2(part2()), [])

    def test_the_releases_before_it_arent_held_to_it(self):
        self.assertEqual(p2(patch_b(), "0.15.1"), [])

    def test_no_screens_comparison(self):
        m = part2()
        del m["screens"]
        self.assertTrue(has(p2(m), "screens"))

    def test_no_screen_changed_says_so(self):
        self.assertEqual(p2(part2(screens={"none_because": "no screen changed"})), [])

    def test_no_accessibility_audit(self):
        m = part2()
        del m["accessibility"]
        self.assertTrue(has(p2(m), "accessibility"))

    def test_the_servers_releases_have_no_screens(self):
        m = part2()
        del m["screens"], m["accessibility"], m["server"], m["parity"]
        self.assertEqual(
            p2(
                m, "1.44.3", apps=False, platform="server", limits={"server": {**LIMITS["android"]}}
            ),
            [],
        )

    def test_no_limits(self):
        m = part2()
        del m["limits"]
        self.assertTrue(has(p2(m), "limits"))

    def test_a_grown_limit_fails(self):
        self.assertTrue(
            has(p2(part2(limits={"run": "r", "startup_ms": 1000, "memory_mb": 140})), "startup_ms")
        )

    def test_a_grown_limit_with_the_owners_ok(self):
        self.assertEqual(
            p2(
                part2(
                    limits={"run": "r", "startup_ms": 1000, "memory_mb": 140, "owner_ok": "DL400"}
                )
            ),
            [],
        )

    def test_a_limit_within_its_noise(self):
        self.assertEqual(p2(part2(limits={"run": "r", "startup_ms": 950, "memory_mb": 160})), [])

    def test_a_missing_measurement(self):
        self.assertTrue(
            has(p2(part2(limits={"run": "r", "startup_ms": 790})), "memory_mb is missing")
        )

    def test_no_approved_baseline_fails_closed(self):
        unapproved = {"android": {**LIMITS["android"], "approved": None}}
        self.assertTrue(has(p2(part2(), limits=unapproved), "approved"))

    def test_a_key_decision_changed_with_no_mutation_run(self):
        found = p2(part2(), changed={"app/viewing.py"}, mutation_files={"app/viewing.py"})
        self.assertTrue(has(found, "mutation"))

    def test_a_mutation_run_with_survivors(self):
        found = p2(
            part2(mutation={"run": "quality 9", "missing_tests": 2}),
            changed={"app/viewing.py"},
            mutation_files={"app/viewing.py"},
        )
        self.assertTrue(has(found, "missing tests"))

    def test_a_mutation_run_that_killed_them_all(self):
        found = p2(
            part2(mutation={"run": "quality 9", "missing_tests": 0}),
            changed={"app/viewing.py"},
            mutation_files={"app/viewing.py"},
        )
        self.assertEqual(found, [])

    def test_a_class_d_with_no_soak_record(self):
        m = class_d(
            **{k: v for k, v in part2().items() if k in ("screens", "accessibility", "limits")}
        )
        self.assertTrue(has(p2(m), "soak"))

    def test_a_class_d_soaked_on_another_platform_only(self):
        m = class_d(
            **{k: v for k, v in part2().items() if k in ("screens", "accessibility", "limits")},
            soak=[{"platform": "apple", "run": "r", "minutes": 30, "result": "passed"}],
        )
        self.assertTrue(has(p2(m), "no soak record for android"))

    def test_a_class_d_soak_that_failed(self):
        m = class_d(
            **{k: v for k, v in part2().items() if k in ("screens", "accessibility", "limits")},
            soak=[{"platform": "android", "run": "r", "minutes": 180, "result": "failed"}],
        )
        self.assertTrue(has(p2(m), "not passed"))

    def test_a_class_d_that_soaked(self):
        m = class_d(
            **{k: v for k, v in part2().items() if k in ("screens", "accessibility", "limits")},
            soak=[{"platform": "android", "run": "r", "minutes": 180, "result": "passed"}],
        )
        self.assertEqual(p2(m), [])


def feature(**over) -> dict:
    """A feature release after part 2 that meets it, its comparison beside Jellyfin included."""
    m = part2(
        features=["F-101"],
        minimums={"android": "0.16.0", "server": "1.45.0"},
        jellyfin={"run": "compare-jellyfin 1", "heavier": []},
    )
    m.update(over)
    return m


class BesideJellyfin(unittest.TestCase):
    """A feature release's like-for-like run beside Jellyfin's open-source apps and server
    (DL375): where tapiOca measures heavier, it's said and captured."""

    def test_a_feature_release_that_meets_it(self):
        self.assertEqual(p2(feature(), "0.16.0"), [])

    def test_a_feature_release_with_no_comparison(self):
        m = feature()
        del m["jellyfin"]
        self.assertTrue(has(p2(m, "0.16.0"), "jellyfin"))

    def test_a_comparison_with_no_run(self):
        self.assertTrue(has(p2(feature(jellyfin={"heavier": []}), "0.16.0"), "jellyfin"))

    def test_heavier_but_not_captured(self):
        m = feature(jellyfin={"run": "r", "heavier": [{"measure": "startup_ms", "by": 0.1}]})
        self.assertTrue(has(p2(m, "0.16.0"), "startup_ms"))

    def test_heavier_and_captured(self):
        m = feature(
            jellyfin={"run": "r", "heavier": [{"measure": "startup_ms", "by": 0.1, "captured": "next.md, the startup pass"}]}
        )
        self.assertEqual(p2(m, "0.16.0"), [])

    def test_heavier_by_how_much_unsaid(self):
        m = feature(jellyfin={"run": "r", "heavier": [{"measure": "startup_ms", "captured": "next.md"}]})
        self.assertTrue(has(p2(m, "0.16.0"), "by how much"))

    def test_past_the_tolerance_halts(self):
        m = feature(
            jellyfin={"run": "r", "heavier": [{"measure": "startup_ms", "by": 0.5, "captured": "next.md"}]}
        )
        self.assertTrue(has(p2(m, "0.16.0"), "halt"))

    def test_past_the_tolerance_with_the_owners_ok(self):
        m = feature(
            jellyfin={
                "run": "r",
                "heavier": [{"measure": "startup_ms", "by": 0.5, "captured": "next.md", "owner_ok": "DL400"}],
            }
        )
        self.assertEqual(p2(m, "0.16.0"), [])

    def test_heavier_left_unsaid(self):
        self.assertTrue(has(p2(feature(jellyfin={"run": "r"}), "0.16.0"), "heavier"))

    def test_a_patch_needs_none(self):
        self.assertEqual(p2(part2()), [])

    def test_the_servers_feature_release_needs_one(self):
        m = feature()
        del m["jellyfin"], m["screens"], m["accessibility"], m["server"], m["parity"]
        found = p2(m, "1.45.0", apps=False, platform="server", limits={"server": {**LIMITS["android"]}})
        self.assertTrue(has(found, "jellyfin"))

    def test_apple_isnt_compared_yet(self):
        m = feature()
        del m["jellyfin"]
        self.assertEqual(p2(m, "0.15.0", platform="apple", limits={"apple": {**LIMITS["android"]}}), [])


class ReadingAManifest(unittest.TestCase):
    def test_a_manifest_that_isnt_toml(self):
        manifest, found = g.parse("class = \n")
        self.assertIsNone(manifest)
        self.assertTrue(has(found, "TOML"))

    def test_a_good_one(self):
        manifest, found = g.parse('class = "B"\nrow = 139\n')
        self.assertEqual(found, [])
        self.assertEqual(manifest, {"class": "B", "row": 139})


if __name__ == "__main__":
    unittest.main()
