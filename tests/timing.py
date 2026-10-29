"""A timing test's limit, with what it measured written down (the CI audit,
October 29, P13): each run records its time and its limit, so the margin is
known before a slow machine finds it. The image run's Test step lists them,
the thinnest first (tools/suite_times.py)."""

from __future__ import annotations

import inspect
import os


def within(took: float, limit: float, said: str | None = None) -> None:
    caller = inspect.stack()[1]
    where = f"{os.path.relpath(caller.filename)}::{caller.function}:{caller.lineno}"
    kept = os.environ.get("TAPIOCA_TIMINGS")
    if kept:
        with open(kept, "a", encoding="utf-8") as f:
            f.write(f"{where}\t{took:.4f}\t{limit}\n")
    assert took < limit, said or f"{took:.3f} s, over its {limit} s"
