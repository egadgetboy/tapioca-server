"""The standing rules check's own tests (tools/claude_rules.py). Standard library only:

    python3 tools/test_claude_rules.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import claude_rules as c

ALL = "\n".join(f"- **{m}** the rule." for m in c.RULES)


class TheStandingRules(unittest.TestCase):
    def test_every_rule_there(self):
        self.assertEqual(c.problems(ALL), [])

    def test_one_left_out(self):
        text = ALL.replace(f"- **{c.RULES[3]}**", "- Something else")
        self.assertEqual(c.problems(text), [f"CLAUDE.md doesn't carry the standing rule {c.RULES[3]!r}"])

    def test_one_only_mentioned_in_passing(self):
        text = ALL.replace(f"- **{c.RULES[0]}** the rule.", f"- see {c.RULES[0]} somewhere")
        self.assertTrue(c.problems(text))


if __name__ == "__main__":
    unittest.main()
