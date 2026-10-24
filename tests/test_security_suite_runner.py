"""Fail-closed regressions for tools.security_suite (no server or network required)."""

from __future__ import annotations

import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import security_suite as runner


class RunnerFailureTests(unittest.TestCase):
    def test_unit_collection_error_is_not_accepted(self):
        result = subprocess.CompletedProcess(
            args=["pytest"], returncode=5, stdout="no tests ran", stderr="ImportError: broken fixture"
        )
        with patch.object(runner.subprocess, "run", return_value=result):
            passed, failed, tail, code, unexecuted = runner.unit_layer()
        self.assertEqual(code, 5)
        self.assertEqual(sum(map(len, passed.values())), 0)
        self.assertEqual(sum(map(len, failed.values())), 0)
        self.assertIn("ImportError", tail)

    def test_pytest_failure_with_no_recognized_results_blocks_unit_only_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tools").mkdir()
            (root / "tools" / "security_corpus.json").write_text('{"checks": 1138, "merges": []}')
            (root / "tools" / "security_exceptions.json").write_text("[]")
            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "CORPUS", root / "tools" / "security_corpus.json"),
                patch.object(runner, "EXCEPTIONS", root / "tools" / "security_exceptions.json"),
                patch.object(runner, "unit_layer", return_value=(
                    {k: [] for k in runner.LAYERS}, {k: [] for k in runner.LAYERS},
                    "pytest collection crashed", 2, [],
                )),
                redirect_stdout(io.StringIO()) as output,
            ):
                status = runner.main(["--no-live"])
            self.assertEqual(status, 1)
            self.assertIn("Pytest exited 2", output.getvalue())
            self.assertIn("live harness was NOT RUN", output.getvalue())
            self.assertFalse((root / "docs" / "security").exists())

    def test_live_nonzero_exit_blocks_even_with_full_pass_count(self):
        result = subprocess.CompletedProcess(
            args=["attack_check"], returncode=1,
            stdout="812/812 checks passed\nUnexpected finalization error",
            stderr="failed to finish",
        )
        with patch.object(runner.subprocess, "run", return_value=result):
            passed, failed, detail = runner.live_harness()
        self.assertEqual(passed, 812)
        self.assertGreaterEqual(failed, 1)
        self.assertIn("exited 1", detail)

    def test_unit_happy_case_records_results_and_zero_exit(self):
        result = subprocess.CompletedProcess(
            args=["pytest"], returncode=0,
            stdout="PASSED tests/security/test_auth.py::test_signed_in\n1 passed",
            stderr="",
        )
        with patch.object(runner.subprocess, "run", return_value=result):
            passed, failed, _, code, unexecuted = runner.unit_layer()
        self.assertEqual(code, 0)
        self.assertEqual(passed["test_auth.py"], ["test_signed_in"])
        self.assertFalse(any(failed.values()))

    def test_unrelated_historic_merge_cannot_waive_corpus_shrink(self):
        corpus = {
            "checks": 1138,
            "merges": [{
                "from_checks": 1138,
                "to_checks": 1137,
                "removed_case_ids": ["authz::duplicate-old"],
                "reason": "Duplicate case with identical result removed after review.",
                "review_sha": "1" * 40,
            }],
        }
        self.assertFalse(runner.merge_explains_shrink(corpus, 1000))
        self.assertTrue(runner.merge_explains_shrink(corpus, 1137))

    def test_unreviewed_or_inaccurate_merges_cannot_waive_loss(self):
        corpus = {"checks": 1138, "merges": [{"count": 138, "reason": "historical"}]}
        self.assertFalse(runner.merge_explains_shrink(corpus, 1000))
        corpus["merges"] = [{
            "from_checks": 1138,
            "to_checks": 1136,
            "removed_case_ids": ["one-id"],
            "reason": "Two tests consolidated into one reviewed test.",
            "review_sha": "a" * 40,
        }]
        self.assertFalse(runner.merge_explains_shrink(corpus, 1136))
        corpus["merges"][0]["removed_case_ids"] = ["one-id", "one-id"]
        self.assertFalse(runner.merge_explains_shrink(corpus, 1136))
        corpus["merges"][0]["removed_case_ids"] = ["one-id", "two-id"]
        self.assertTrue(runner.merge_explains_shrink(corpus, 1136))

    def test_corpus_count_growth_is_allowed_without_a_merge(self):
        corpus = {"checks": 1138, "merges": []}
        self.assertFalse(runner.merge_explains_shrink(corpus, 1137))
        self.assertTrue(runner.merge_explains_shrink(corpus, 1138))
        self.assertTrue(runner.merge_explains_shrink(corpus, 1139))


    def test_skipped_security_case_is_not_silently_ignored(self):
        result = subprocess.CompletedProcess(
            args=["pytest"], returncode=0,
            stdout=(
                "PASSED tests/security/test_auth.py::test_ok\n"
                "SKIPPED [1] tests/security/test_authz.py:10: missing device\n"
                "1 passed, 1 skipped"
            ),
            stderr="",
        )
        with patch.object(runner.subprocess, "run", return_value=result):
            passed, failed, _, code, unexecuted = runner.unit_layer()
        self.assertEqual(code, 0)
        self.assertEqual(len(passed["test_auth.py"]), 1)
        self.assertFalse(failed["test_auth.py"])
        self.assertTrue(unexecuted)

    def test_missing_security_test_layer_is_release_blocking(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tools").mkdir()
            (root / "tools" / "security_corpus.json").write_text('{"checks": 1138, "merges": []}')
            (root / "tools" / "security_exceptions.json").write_text("[]")
            good = {name: ["case_ok"] for name in runner.LAYERS}
            good["test_authz.py"] = []
            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "CORPUS", root / "tools" / "security_corpus.json"),
                patch.object(runner, "EXCEPTIONS", root / "tools" / "security_exceptions.json"),
                patch.object(runner, "unit_layer", return_value=(
                    good, {name: [] for name in runner.LAYERS},
                    "unit layer complete", 0, [],
                )),
                redirect_stdout(io.StringIO()) as output,
            ):
                status = runner.main(["--no-live"])
            self.assertEqual(status, 1)
            self.assertIn("Missing expected security test layers: test_authz.py", output.getvalue())

    def test_unknown_security_test_source_is_release_blocking(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tools").mkdir()
            (root / "tests" / "security").mkdir(parents=True)
            (root / "tests" / "security" / "test_new_layer.py").write_text("def test_x(): pass")
            (root / "tools" / "security_corpus.json").write_text('{"checks": 1138, "merges": []}')
            (root / "tools" / "security_exceptions.json").write_text("[]")
            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "CORPUS", root / "tools" / "security_corpus.json"),
                patch.object(runner, "EXCEPTIONS", root / "tools" / "security_exceptions.json"),
                patch.object(runner, "unit_layer", return_value=(
                    {name: ["case_ok"] for name in runner.LAYERS},
                    {name: [] for name in runner.LAYERS}, "all ran", 0, [],
                )),
                redirect_stdout(io.StringIO()) as output,
            ):
                status = runner.main(["--no-live"])
            self.assertEqual(status, 1)
            self.assertIn("Unregistered security-test source files: test_new_layer.py", output.getvalue())


class FullRunTests(unittest.TestCase):
    # (The cold audit of 1.44.0: the image's test stage can't write docs/, and the report was
    # written before it was printed, so the CI step failed with no report in its log.)
    def _run(self, root: Path, argv: list[str], live=(812, 0, "812/812 checks passed")):
        (root / "tools").mkdir(exist_ok=True)
        (root / "tools" / "security_corpus.json").write_text('{"checks": 1, "merges": []}')
        (root / "tools" / "security_exceptions.json").write_text("[]")
        with (
            patch.object(runner, "ROOT", root),
            patch.object(runner, "CORPUS", root / "tools" / "security_corpus.json"),
            patch.object(runner, "EXCEPTIONS", root / "tools" / "security_exceptions.json"),
            patch.object(runner, "unit_layer", return_value=(
                {name: ["case_ok"] for name in runner.LAYERS},
                {name: [] for name in runner.LAYERS}, "all ran", 0, [],
            )),
            patch.object(runner, "live_harness", return_value=live),
            redirect_stdout(io.StringIO()) as output,
        ):
            status = runner.main(argv)
        return status, output.getvalue()

    def test_a_full_run_writes_its_report_where_its_told_and_prints_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "out" / "report.md"
            status, said = self._run(root, ["--report", str(target)])
            self.assertEqual(status, 0, said)
            self.assertTrue(target.exists())
            self.assertIn("# Security report", said)
            self.assertFalse((root / "docs").exists())

    def test_a_report_folder_it_cant_write_still_prints_the_report_and_fails(self):
        import os
        import stat

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            locked = root / "locked"
            locked.mkdir()
            locked.chmod(stat.S_IRUSR | stat.S_IXUSR)
            try:
                if os.access(locked, os.W_OK):
                    self.skipTest("running as root: a folder can't be made unwritable")
                status, said = self._run(root, ["--report", str(locked / "report.md")])
            finally:
                locked.chmod(stat.S_IRWXU)
            self.assertEqual(status, 1)
            self.assertIn("# Security report", said)
            self.assertIn("couldn't be written", said)

    def test_a_harness_check_that_wasnt_run_blocks_the_gate(self):
        # (The cold audit of 1.44.0: attack_check says "(not checked: this needs ffmpeg)" and still
        # counts as passing unless the total drops.)
        result = subprocess.CompletedProcess(
            args=["attack_check"], returncode=0,
            stdout="  ok  something\n  (not checked: this needs ffmpeg) a stream\n812/812 checks passed",
            stderr="",
        )
        with patch.object(runner.subprocess, "run", return_value=result):
            _, failed, detail = runner.live_harness()
        self.assertGreaterEqual(failed, 1)
        self.assertIn("not checked", detail)


if __name__ == "__main__":
    unittest.main()


class ReportProvenanceTests(unittest.TestCase):
    # (SEC-GATE-P1-05: a report says what it ran on: the commit, the run, Python and pytest.)
    def test_the_report_names_the_commit_run_and_versions(self):
        import os

        with patch.dict(os.environ, {"GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123"}):
            lines = runner.provenance()
        text = "\n".join(lines)
        self.assertIn("a" * 40, text)
        self.assertIn("123", text)
        self.assertIn("Python", text)
        self.assertIn("pytest", text)

    def test_without_ci_the_report_says_its_a_local_run(self):
        import os

        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_SHA", "GITHUB_RUN_ID")}
        with patch.dict(os.environ, env, clear=True):
            text = "\n".join(runner.provenance())
        self.assertIn("local run", text)
