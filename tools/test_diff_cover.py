"""The changed-lines coverage check's own tests (tools/diff_cover.py). Standard library only:

    python3 tools/test_diff_cover.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parent))

import diff_cover as d

JACOCO = """<?xml version="1.0"?><report name="x">
<package name="com/egadgetboy/stationplay/core">
<sourcefile name="Words.kt">
<line nr="10" mi="0" ci="4" mb="0" cb="0"/>
<line nr="11" mi="3" ci="0" mb="0" cb="0"/>
<line nr="12" mi="1" ci="2" mb="1" cb="1"/>
</sourcefile></package></report>"""

LCOV = """SF:/w/ios/Core/Sources/StationPlayCore/Words.swift
DA:5,3
DA:6,0
end_of_record
"""

ROOT_K = "android/app/src/main/java/"


class Reading(unittest.TestCase):
    def test_jacoco(self):
        self.assertEqual(
            d.jacoco(JACOCO, ROOT_K),
            {ROOT_K + "com/egadgetboy/stationplay/core/Words.kt": {10: True, 11: False, 12: True}},
        )

    def test_lcov(self):
        self.assertEqual(d.lcov(LCOV, "/w/"), {"ios/Core/Sources/StationPlayCore/Words.swift": {5: True, 6: False}})


class Checking(unittest.TestCase):
    cov: ClassVar[dict] = {"core/A.kt": {10: True, 11: False, 12: True}}

    def test_a_changed_line_no_test_runs(self):
        found = d.uncovered(self.cov, {"core/A.kt": {11, 12}}, ("core/",))
        self.assertEqual(found, ["core/A.kt:11"])

    def test_changed_lines_all_run(self):
        self.assertEqual(d.uncovered(self.cov, {"core/A.kt": {10, 12}}, ("core/",)), [])

    def test_a_line_with_no_code(self):
        self.assertEqual(d.uncovered(self.cov, {"core/A.kt": {20}}, ("core/",)), [])

    def test_outside_the_core(self):
        self.assertEqual(d.uncovered({"ui/B.kt": {3: False}}, {"ui/B.kt": {3}}, ("core/",)), [])

    def test_a_changed_core_file_with_no_coverage_at_all(self):
        self.assertEqual(d.uncovered({}, {"core/New.kt": {1}}, ("core/",), {"core/New.kt"}), ["core/New.kt: no test runs it"])


if __name__ == "__main__":
    unittest.main()
