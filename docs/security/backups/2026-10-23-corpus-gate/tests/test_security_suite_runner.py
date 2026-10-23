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
            passed, failed, tail, code = runner.unit_layer()
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
                    "pytest collection crashed", 2,
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
            passed, failed, _, code = runner.unit_layer()
        self.assertEqual(code, 0)
        self.assertEqual(passed["test_auth.py"], ["test_signed_in"])
        self.assertFalse(any(failed.values()))


if __name__ == "__main__":
    unittest.main()
