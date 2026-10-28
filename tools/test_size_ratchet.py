"""The size ratchet's own tests (tools/size_ratchet.py). Standard library only:

    python3 tools/test_size_ratchet.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import size_ratchet as s

BASE = {"android/AppModel.kt": 100, "roku/MainScene.brs": 50}


class TheRatchet(unittest.TestCase):
    def test_the_same_size_passes(self):
        self.assertEqual(s.problems(BASE, dict(BASE)), [])

    def test_a_file_that_grows(self):
        found = s.problems(BASE, {**BASE, "android/AppModel.kt": 101})
        self.assertTrue(any("AppModel.kt" in p and "grew" in p for p in found))

    def test_a_file_that_shrinks_lowers_its_baseline(self):
        found = s.problems(BASE, {**BASE, "roku/MainScene.brs": 40})
        self.assertTrue(any("MainScene.brs" in p and "40" in p for p in found))

    def test_a_new_file_of_the_kind(self):
        found = s.problems(BASE, {**BASE, "roku/MainSceneNew.brs": 10})
        self.assertTrue(any("MainSceneNew.brs" in p for p in found))

    def test_a_file_taken_out(self):
        now = dict(BASE)
        del now["roku/MainScene.brs"]
        found = s.problems(BASE, now)
        self.assertTrue(any("MainScene.brs" in p and "baseline" in p for p in found))


if __name__ == "__main__":
    unittest.main()
