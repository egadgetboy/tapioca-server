"""Every tool a test imports is in the image's test stage (1.43.0's first
CI run failed on this: tests/test_picture_speed.py imports tools.picture_load,
which the Dockerfile's test stage and .dockerignore left out)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_every_tool_the_tests_import_is_copied_into_the_test_stage():
    imported: set[str] = set()
    for test in (ROOT / "tests").glob("*.py"):
        text = test.read_text(encoding="utf-8")
        imported |= set(re.findall(r"(?:import|from) tools\.(\w+)", text))
    copied = set(re.findall(r"tools/(\w+)\.py", (ROOT / "Dockerfile").read_text(encoding="utf-8")))
    kept = set(
        re.findall(
            r"^!tools/(\w+)\.py$", (ROOT / ".dockerignore").read_text(encoding="utf-8"), re.M
        )
    )
    assert imported, "the tests import tools"
    assert imported <= copied, sorted(imported - copied)
    assert imported <= kept, sorted(imported - kept)
