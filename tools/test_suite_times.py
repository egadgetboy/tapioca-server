"""The suite's times' own tests (tools/suite_times.py). Standard library only:

    python3 tools/test_suite_times.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import suite_times as t

XML = """<testsuites><testsuite>
<testcase classname="tests.test_a" name="x" time="2.5"/>
<testcase classname="tests.test_a.Thing" name="y" time="1.5"/>
<testcase classname="tests.security.test_b" name="z" time="10"/>
</testsuite></testsuites>"""


class Times(unittest.TestCase):
    def test_by_file_with_classes_and_folders(self):
        self.assertEqual(t.by_file(XML), {"tests/test_a.py": 4.0, "tests/security/test_b.py": 10.0})

    def test_one_notice_the_slowest_first(self):
        said = t.notice(t.by_file(XML), 1)
        self.assertTrue(said.startswith("::notice title=Test times::"))
        self.assertIn("0.2 min in all, 2 files", said)
        self.assertIn("tests/security/test_b.py", said)
        self.assertNotIn("test_a", said)


class Margins(unittest.TestCase):
    def test_the_thinnest_first(self):
        said = t.margins("tests/test_a.py::fast:9\t0.1000\t4\ntests/test_b.py::close:3\t0.9000\t1.0\n")
        self.assertTrue(said.startswith("::notice title=Timing margins::2 timed checks"))
        self.assertLess(said.index("test_b.py::close"), said.index("test_a.py::fast"))
        self.assertIn("90% of its limit: 0.900 s of 1 s", said)


if __name__ == "__main__":
    unittest.main()
