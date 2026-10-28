"""tools/mutate.py on fixtures: a weak test lets a mutant survive and the run
fails; a strong one kills it; an accepted survivor passes; the file is
restored; tests failing before any change stop the run; and the text mode
for Kotlin and Swift finds the operators inside a function only.

    python3 tools/test_mutate.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutate

DECIDE = """def may_watch(age, limit):
    return age >= limit


def other(x):
    return x == 1
"""
WEAK = "from decide import may_watch\nassert may_watch(20, 18)\n"
STRONG = WEAK + "assert not may_watch(10, 18)\nassert may_watch(18, 18)\n"


class Run(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "tools").mkdir()
        (self.root / "decide.py").write_text(DECIDE)
        mutate.ROOT = self.root
        mutate.TARGETS = self.root / "tools" / "mutation_targets.json"
        mutate.ACCEPTED = self.root / "tools" / "mutation_accepted.json"

    def target(self, test: str):
        (self.root / "test_decide.py").write_text(test)
        mutate.TARGETS.write_text(
            json.dumps(
                {
                    "targets": {
                        "age": {
                            "file": "decide.py",
                            "functions": ["may_watch"],
                            "tests": f"{sys.executable} test_decide.py",
                        }
                    }
                }
            )
        )

    def test_a_weak_test_leaves_a_survivor_and_fails(self):
        self.target(WEAK)
        self.assertEqual(mutate.main(["x", "run"]), 1)
        self.assertEqual((self.root / "decide.py").read_text(), DECIDE)

    def test_a_strong_test_kills_every_mutant(self):
        self.target(STRONG)
        self.assertEqual(mutate.main(["x", "run"]), 0)

    def test_an_accepted_survivor_passes(self):
        self.target(WEAK)
        out = self.root / "out.json"
        mutate.main(["x", "run", "--out", str(out)])
        survivors = json.loads(out.read_text())["survivors"]
        mutate.ACCEPTED.write_text(
            json.dumps({"accepted": {s: "the same meaning" for s in survivors}})
        )
        self.assertEqual(mutate.main(["x", "run"]), 0)

    def test_only_the_named_functions_are_changed(self):
        self.target(STRONG)
        ids = [
            m.id
            for m in mutate.mutants_of(
                "age", json.loads(mutate.TARGETS.read_text())["targets"]["age"]
            )
        ]
        self.assertTrue(ids and all("/may_watch#" in i for i in ids), ids)

    def test_failing_tests_stop_the_run(self):
        self.target("raise SystemExit(1)\n")
        with self.assertRaises(SystemExit):
            mutate.main(["x", "run"])


class Text(unittest.TestCase):
    def test_kotlin_operators_inside_the_function_only(self):
        root = Path(tempfile.mkdtemp())
        (root / "Decide.kt").write_text(
            "fun mayWatch(age: Int, limit: Int): Boolean {\n"
            '    val note = "a == b"  // not this\n'
            "    return age >= limit && limit > 0\n"
            "}\n\nfun other(x: Int) = x == 1\n"
        )
        mutate.ROOT = root
        ids = [m.id for m in mutate.text_mutants("k", root / "Decide.kt", ["mayWatch"])]
        self.assertEqual(
            sorted(i.split(" ", 1)[1] for i in ids),
            sorted([">= -> <", ">= -> >", "&& -> ||", "> -> <=", "> -> >="]),
        )


if __name__ == "__main__":
    unittest.main()
