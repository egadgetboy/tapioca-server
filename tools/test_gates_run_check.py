"""CG-22: release publication requires a successful Gates run on the exact SHA.

RED-first contract. This test module deliberately imports a helper not yet
implemented. The implementation must preserve the existing release-gate checks.
Run: python3 -m unittest discover -s tools -p test_gates_run_check.py -v
"""
from __future__ import annotations

import unittest.mock
import urllib.error

import gates_run_check as gate


SHA = "a" * 40
OTHER = "b" * 40


def run(run_id: int, conclusion: str | None, status: str = "completed",
        sha: str = SHA) -> dict:
    return {
        "id": run_id,
        "head_sha": sha,
        "status": status,
        "conclusion": conclusion,
        "workflow_id": 123,
        "path": ".github/workflows/gates.yml",
    }


class GatesForExactReleaseCommit(unittest.TestCase):
    def test_one_success_passes(self):
        self.assertIsNone(gate.evaluate_runs([run(10, "success")], SHA))

    def test_failed_run_refuses(self):
        self.assertIsNotNone(gate.evaluate_runs([run(10, "failure")], SHA))

    def test_newer_failure_overrides_older_success(self):
        self.assertIsNotNone(gate.evaluate_runs([
            run(10, "success"), run(11, "failure"),
        ], SHA))

    def test_in_progress_refuses_even_with_completed_success(self):
        self.assertIsNotNone(gate.evaluate_runs([
            run(10, "success"), run(11, None, "in_progress"),
        ], SHA))

    def test_missing_run_refuses(self):
        self.assertIsNotNone(gate.evaluate_runs([], SHA))

    def test_other_commit_cannot_authorize_publication(self):
        self.assertIsNotNone(gate.evaluate_runs([run(10, "success", sha=OTHER)], SHA))

    def test_workflow_display_name_is_not_authority(self):
        candidate = run(10, "success")
        candidate["name"] = "Something Else"
        self.assertIsNone(gate.evaluate_runs([candidate], SHA))

    def test_github_api_path_with_repository_and_ref_passes(self):
        candidate = run(10, "success")
        candidate["path"] = "egadgetboy/tapioca-server/.github/workflows/gates.yml@refs/heads/chatgpt/cg22-release-gates-required"
        self.assertIsNone(gate.evaluate_runs([candidate], SHA))

    def test_other_repository_workflow_path_refuses(self):
        candidate = run(10, "success")
        candidate["path"] = "other/repository/.github/workflows/gates.yml@refs/heads/main"
        self.assertIsNotNone(gate.evaluate_runs([candidate], SHA))

    def test_unrelated_workflow_cannot_authorize_publication(self):
        candidate = run(10, "success")
        candidate["path"] = ".github/workflows/quality.yml"
        self.assertIsNotNone(gate.evaluate_runs([candidate], SHA))

    def test_malformed_run_id_refuses_instead_of_crashing(self):
        candidate = run("not-a-number", "success")
        self.assertIsNotNone(gate.evaluate_runs([candidate], SHA))

    def test_api_error_refuses(self):
        with unittest.mock.patch.object(gate, "fetch_runs", side_effect=urllib.error.URLError("offline")):
            self.assertIsNotNone(gate.require_success("egadgetboy/tapioca-server", SHA))

    def test_api_timeout_refuses(self):
        with unittest.mock.patch.object(gate, "fetch_runs", side_effect=TimeoutError("timed out")):
            self.assertIsNotNone(gate.require_success("egadgetboy/tapioca-apps", SHA))


if __name__ == "__main__":
    unittest.main()
