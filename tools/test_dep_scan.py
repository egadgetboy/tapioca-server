"""The dependency scan's own tests (tools/dep_scan.py), with the scanning
service faked. Standard library only:

    python3 tools/test_dep_scan.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dep_scan as d

TREE = """releaseRuntimeClasspath - Runtime classpath of /release.
+--- com.squareup.okhttp3:okhttp:5.1.0
|    \\--- com.squareup.okio:okio:3.15.0 -> 3.16.0
+--- androidx.core:core-ktx:{strictly 1.17.0} -> 1.17.0 (c)
\\--- project :core
"""


def fake(packages):
    def lookup(system, name, version):
        return packages.get((name, version), {"licenses": ["Apache-2.0"], "advisories": []})

    return lookup


class Reading(unittest.TestCase):
    def test_gradles_tree(self):
        self.assertEqual(d.maven(TREE), {("com.squareup.okhttp3:okhttp", "5.1.0"), ("com.squareup.okio:okio", "3.16.0")})

    def test_pinned_requirements(self):
        text = "# pins\nfastapi==0.141.1\nuvicorn==0.46.0  # the server\n\n"
        self.assertEqual(d.pypi(text), {("fastapi", "0.141.1"), ("uvicorn", "0.46.0")})

    def test_an_unpinned_requirement(self):
        with self.assertRaises(SystemExit):
            d.pypi("fastapi>=0.1\n")


class Scanning(unittest.TestCase):
    pkgs: ClassVar[set] = {("com.squareup.okhttp3:okhttp", "5.1.0"), ("com.squareup.okio:okio", "3.16.0")}

    def test_nothing_known(self):
        problems, sbom = d.scan("maven", self.pkgs, fake({}))
        self.assertEqual(problems, [])
        self.assertEqual(len(sbom["components"]), 2)

    def test_a_high_advisory(self):
        found = fake({("com.squareup.okio:okio", "3.16.0"): {"licenses": ["Apache-2.0"], "advisories": [("GHSA-x", 7.5)]}})
        problems, _ = d.scan("maven", self.pkgs, found)
        self.assertTrue(any("GHSA-x" in p and "okio" in p for p in problems))

    def test_a_medium_advisory_passes(self):
        found = fake({("com.squareup.okio:okio", "3.16.0"): {"licenses": ["Apache-2.0"], "advisories": [("GHSA-y", 5.0)]}})
        self.assertEqual(d.scan("maven", self.pkgs, found)[0], [])

    def test_a_license_not_allowed(self):
        found = fake({("com.squareup.okio:okio", "3.16.0"): {"licenses": ["AGPL-3.0"], "advisories": []}})
        problems, _ = d.scan("maven", self.pkgs, found)
        self.assertTrue(any("AGPL-3.0" in p for p in problems))

    def test_an_advisory_of_unknown_severity(self):
        found = fake({("com.squareup.okio:okio", "3.16.0"): {"licenses": ["Apache-2.0"], "advisories": [("OSV-z", None)]}})
        self.assertTrue(any("OSV-z" in p for p in d.scan("maven", self.pkgs, found)[0]))

    def test_a_package_deps_dev_doesnt_know(self):
        found = fake({("com.squareup.okio:okio", "3.16.0"): {"licenses": None, "advisories": []}})
        self.assertTrue(any("license" in p for p in d.scan("maven", self.pkgs, found)[0]))

    def test_an_unknown_license(self):
        found = fake({("com.squareup.okio:okio", "3.16.0"): {"licenses": [], "advisories": []}})
        self.assertTrue(any("license" in p for p in d.scan("maven", self.pkgs, found)[0]))


if __name__ == "__main__":
    unittest.main()
