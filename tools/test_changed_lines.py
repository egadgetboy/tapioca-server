"""The changed-lines filter's own tests (tools/changed_lines.py). Standard library only:

    python3 tools/test_changed_lines.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import changed_lines as c

DIFF = """diff --git a/ios/Core/A.swift b/ios/Core/A.swift
--- a/ios/Core/A.swift
+++ b/ios/Core/A.swift
@@ -10,0 +11,2 @@ struct A {
+    let x = 1
+    let y = 2
@@ -40 +42 @@ func f() {
-    old()
+    new()
diff --git a/ios/Core/Gone.swift b/ios/Core/Gone.swift
--- a/ios/Core/Gone.swift
+++ /dev/null
@@ -1,3 +0,0 @@
-a
-b
-c
"""


class AddedLines(unittest.TestCase):
    def test_the_lines_a_diff_adds(self):
        self.assertEqual(c.added_lines(DIFF), {"ios/Core/A.swift": {11, 12, 42}})


class Filtering(unittest.TestCase):
    OUT = (
        "/w/ios/Core/A.swift:11:5: warning: Identifier Name Violation: x is too short (identifier_name)\n"
        "/w/ios/Core/A.swift:30:1: warning: Line Length Violation: too long (line_length)\n"
        "/w/ios/Core/B.swift:3:1: error: Force Cast Violation (force_cast)\n"
    )

    def test_only_findings_on_added_lines(self):
        found = c.on_changed(self.OUT, c.added_lines(DIFF), strip="/w/")
        self.assertEqual(len(found), 1)
        self.assertIn("A.swift:11", found[0])

    def test_nothing_changed_nothing_found(self):
        self.assertEqual(c.on_changed(self.OUT, {}, strip="/w/"), [])


if __name__ == "__main__":
    unittest.main()
