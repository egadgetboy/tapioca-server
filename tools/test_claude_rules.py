"""The standing rules check's own tests (tools/claude_rules.py). Standard library only:

    python3 tools/test_claude_rules.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import claude_rules as c

ALL = "\n".join([f"- **{m}** the rule." for m in c.RULES] + [f"  - **{m}:** the rule." for m in c.UNIVERSAL])


class TheStandingRules(unittest.TestCase):
    def test_every_rule_there(self):
        self.assertEqual(c.problems(ALL), [])

    def test_one_left_out(self):
        text = ALL.replace(f"- **{c.RULES[3]}**", "- Something else")
        self.assertEqual(c.problems(text), [f"CLAUDE.md doesn't carry the standing rule {c.RULES[3]!r}"])

    def test_one_only_mentioned_in_passing(self):
        text = ALL.replace(f"- **{c.RULES[0]}** the rule.", f"- see {c.RULES[0]} somewhere")
        self.assertTrue(c.problems(text))


def tree(tmp: Path, claude: str, rules: dict[str, str]) -> Path:
    (tmp / ".claude" / "rules").mkdir(parents=True)
    (tmp / "CLAUDE.md").write_text(claude)
    for name, text in rules.items():
        (tmp / ".claude" / "rules" / name).write_text(text)
    return tmp


GOOD_CLAUDE = (
    "# Rules\n\n## Rules that load with the work\n- `.claude/rules/release.md`: when releasing.\n\n## How work runs\n"
    + "\n".join(f"- **{m}** the rule." for m in c.RULES)
    + "\n"
    + "\n".join(f"  - **{m}:** the rule." for m in c.UNIVERSAL)
    + "\n- **Never weaken a test:** ever.\n"
)
GOOD_RULE = '---\npaths:\n  - "docs/releases/**"\n---\n# Release rules\n\n- **Labels** the rule.\n  - **Halt and report:** at once.\n'
TRACKED = ["docs/releases/v1.md", "CLAUDE.md"]


class TheRulesKeptOnce(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())

    def listed(self, root: Path) -> dict:
        return c.record(root, {"budget": {"lines": 40, "bytes": 4000}, "files": {}})

    def check(self, claude=GOOD_CLAUDE, rules=None, listed_from=None, tracked=TRACKED):
        import tempfile
        rules = {"release.md": GOOD_RULE} if rules is None else rules
        base = tree(Path(tempfile.mkdtemp()), *(listed_from or (GOOD_CLAUDE, {"release.md": GOOD_RULE})))
        listed = self.listed(base)
        root = tree(self.tmp, claude, rules)
        return c.structure(root, listed, tracked)

    def test_all_kept_once(self):
        self.assertEqual(self.check(), [])

    def test_a_rule_every_task_needs_moved_to_a_file_that_loads_with_the_work(self):
        claude = GOOD_CLAUDE.replace(f"  - **{c.UNIVERSAL[0]}:** the rule.\n", "")
        rule = GOOD_RULE + f"  - **{c.UNIVERSAL[0]}:** the rule.\n"
        found = self.check(claude=claude, rules={"release.md": rule}, listed_from=(claude, {"release.md": rule}))
        self.assertIn(f"CLAUDE.md doesn't carry {c.UNIVERSAL[0]!r}, which every task needs", found)

    def test_a_standing_rule_only_in_a_file_that_loads_with_the_work(self):
        claude = GOOD_CLAUDE.replace("- **Quality gates** the rule.\n", "")
        rule = GOOD_RULE + "- **Quality gates** the rule.\n"
        found = self.check(claude=claude, rules={"release.md": rule}, listed_from=(claude, {"release.md": rule}))
        self.assertIn("CLAUDE.md doesn't carry the standing rule 'Quality gates'", found)

    def test_a_rule_left_out(self):
        found = self.check(rules={"release.md": GOOD_RULE.replace("  - **Halt and report:** at once.\n", "")})
        self.assertTrue(any("missing or changed" in p for p in found), found)

    def test_a_rule_reworded_is_caught(self):
        found = self.check(rules={"release.md": GOOD_RULE.replace("at once", "when convenient")})
        self.assertTrue(any("missing or changed" in p for p in found), found)
        self.assertTrue(any("isn't in tools/claude_rules.json" in p for p in found), found)

    def test_a_rule_in_two_places(self):
        found = self.check(claude=GOOD_CLAUDE + "- **Halt and report:** at once.\n")
        self.assertTrue(any("written 2 times" in p for p in found), found)

    def test_a_standing_rule_written_twice(self):
        found = self.check(claude=GOOD_CLAUDE + "- **Quality gates** the rule.\n")
        self.assertTrue(any("'Quality gates' is written 2 times" in p for p in found), found)

    def test_a_rule_moved_without_saying_so(self):
        moved = GOOD_CLAUDE + "- **Halt and report:** at once.\n"
        found = self.check(claude=moved, rules={"release.md": GOOD_RULE.replace("  - **Halt and report:** at once.\n", "")})
        self.assertTrue(any("moved from .claude/rules/release.md to CLAUDE.md" in p for p in found), found)

    def test_claude_md_past_its_budget(self):
        root = tree(self.tmp, GOOD_CLAUDE, {"release.md": GOOD_RULE})
        listed = self.listed(root)
        listed["budget"] = {"lines": 3, "bytes": 4000}
        self.assertTrue(any("past its budget" in p for p in c.structure(root, listed, TRACKED)))

    def test_a_rule_file_with_no_paths_would_load_always(self):
        bare = GOOD_RULE.split("---\n", 2)[2]
        found = self.check(rules={"release.md": bare}, listed_from=(GOOD_CLAUDE, {"release.md": bare}))
        self.assertTrue(any("has no paths" in p for p in found), found)

    def test_a_rule_file_not_named_in_the_index(self):
        claude = GOOD_CLAUDE.replace("- `.claude/rules/release.md`: when releasing.\n", "")
        found = self.check(claude=claude, listed_from=(claude, {"release.md": GOOD_RULE}))
        self.assertTrue(any("isn't named in CLAUDE.md" in p for p in found), found)

    def test_a_path_that_matches_nothing_never_loads(self):
        found = self.check(tracked=["CLAUDE.md"])
        self.assertTrue(any("matches no file" in p for p in found), found)

    def test_a_future_files_paths_may_match_nothing_yet(self):
        root = tree(self.tmp, GOOD_CLAUDE, {"release.md": GOOD_RULE})
        listed = self.listed(root)
        listed["files"][".claude/rules/release.md"]["future"] = True
        self.assertEqual(c.structure(root, listed, ["CLAUDE.md"]), [])

    def test_the_globs(self):
        self.assertTrue(c.glob_re("**/*Picture*").match("android/app/KeptPictures.kt"))
        self.assertTrue(c.glob_re("**/*Picture*").match("Pictures.swift"))
        self.assertFalse(c.glob_re("app/*.py").match("app/sub/x.py"))
        self.assertTrue(c.glob_re("docs/releases/**").match("docs/releases/v1.44.4.md"))


if __name__ == "__main__":
    unittest.main()
