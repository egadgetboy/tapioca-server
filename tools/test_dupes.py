"""The duplicate-code check's own tests (tools/dupes.py). Standard library only:

    python3 tools/test_dupes.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dupes as d

BLOCK = "\n".join(f"val x{i} = compute({i}) + other({i})" for i in range(8))


class FindingCopies(unittest.TestCase):
    def test_one_block_in_two_files(self):
        counts = d.duplicated({"a.kt": BLOCK, "b.kt": "fun f() {\n" + BLOCK + "\n}"})
        self.assertGreater(counts["a.kt"], 0)
        self.assertGreater(counts["b.kt"], 0)

    def test_comments_blanks_and_braces_dont_count(self):
        noise = "\n".join(["}", "", "// a comment", "end if", "{", ")"] * 4)
        self.assertEqual(d.duplicated({"a.kt": noise, "b.kt": noise}), {})

    def test_different_code(self):
        other = "\n".join(f"val y{i} = render({i})" for i in range(8))
        self.assertEqual(d.duplicated({"a.kt": BLOCK, "b.kt": other}), {})

    def test_a_block_repeated_in_one_file(self):
        self.assertGreater(d.duplicated({"a.kt": BLOCK + "\nval z = 1\n" + BLOCK})["a.kt"], 0)


class TheRatchet(unittest.TestCase):
    def test_more_copies_than_the_baseline(self):
        found = d.problems({"a.kt": 3}, {"a.kt": 1})
        self.assertTrue(any("a.kt" in p for p in found))

    def test_fewer_lowers_the_baseline(self):
        found = d.problems({"a.kt": 1}, {"a.kt": 3})
        self.assertTrue(any("lower" in p for p in found))

    def test_a_new_file_with_copies(self):
        self.assertTrue(d.problems({"new.kt": 2}, {}))

    def test_as_before(self):
        self.assertEqual(d.problems({"a.kt": 2}, {"a.kt": 2}), [])


if __name__ == "__main__":
    unittest.main()
