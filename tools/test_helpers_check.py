"""tools/helpers_check.py: the hook refuses a helper's commit, push and gh and lets the main session's through; the
check fails settings, agent files and tracked files that don't hold DS-2 and DS-3.

    python3 tools/test_helpers_check.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import helpers_check as hc


def hook(given: object) -> subprocess.CompletedProcess[str]:
    text = given if isinstance(given, str) else json.dumps(given)
    return subprocess.run(["sh", "-c", hc.HOOK], input=text, capture_output=True, text=True)


def helper(command: str) -> dict:
    return {"agent_id": "a1", "agent_type": "routine-builder", "tool_name": "Bash", "tool_input": {"command": command}}


class Hook(unittest.TestCase):
    def test_a_helpers_commit_push_and_gh_are_refused(self):
        for command in ("git commit -m x", "git -c user.name=x commit -qm y", "git push -q origin HEAD:main", "cd x && git push",
                        "env -u GH_TOKEN gh run list", "gh api repos/x/y", "git stash && git commit --amend"):
            with self.subTest(command):
                done = hook(helper(command))
                self.assertEqual(done.returncode, 2)
                self.assertIn("main session alone", done.stderr)

    def test_the_main_sessions_calls_and_a_helpers_others_go_through(self):
        self.assertEqual(hook({"tool_name": "Bash", "tool_input": {"command": "git commit -m x && git push"}}).returncode, 0)
        for command in ("git status && git diff", "python3 -m pytest -q", "ls ghost/ high/", "grep -rn pushy src"):
            with self.subTest(command):
                self.assertEqual(hook(helper(command)).returncode, 0)

    def test_input_it_cant_read_is_refused(self):
        self.assertEqual(hook("not json").returncode, 2)


class Check(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude/agents").mkdir(parents=True)
        (self.root / ".claude/agents/a.md").write_text("---\nname: a\ntools: Read, Bash\n---\nBody.\n")
        hc.write(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_written_files_pass_and_keep_the_body(self):
        self.assertEqual(hc.problems(self.root, []), [])
        text = (self.root / ".claude/agents/a.md").read_text()
        self.assertTrue(text.endswith("---\nBody.\n"))
        hc.write(self.root)
        self.assertEqual((self.root / ".claude/agents/a.md").read_text(), text)

    def test_settings_without_the_hook_or_a_deny_rule_fail(self):
        settings = hc.settings()
        settings["permissions"]["deny"] = settings["permissions"]["deny"][1:]
        (self.root / ".claude/settings.json").write_text(json.dumps(settings))
        self.assertEqual(len(hc.problems(self.root, [])), 1)
        (self.root / ".claude/settings.json").write_text(json.dumps(hc.settings(hook="true")))
        self.assertEqual(len(hc.problems(self.root, [])), 1)

    def test_an_agent_file_without_its_tools_or_the_hook_fails(self):
        (self.root / ".claude/agents/b.md").write_text("---\nname: b\n---\nBody.\n")
        found = hc.problems(self.root, [])
        self.assertEqual(len(found), 2)
        self.assertIn("no tools list", found[0])

    def test_a_tracked_secret_shaped_file_fails_but_the_named_ones(self):
        tracked = [".env", "app/.env.local", "certs/server.pem", "x/credentials-prod.json", "a.p12", "android/keys/testing.keystore", "README.md"]
        self.assertEqual(len(hc.problems(self.root, tracked)), 5)

    def test_the_repository_holds_them(self):
        tracked = subprocess.run(["git", "ls-files"], cwd=hc.ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
        self.assertEqual(hc.problems(hc.ROOT, tracked), [])


if __name__ == "__main__":
    unittest.main()
