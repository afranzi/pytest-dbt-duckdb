"""Opt-in stage profiler for pytest-dbt-duckdb test runs.

State is process-local (one set of timings per pytest worker). Reset between tests
by the plugin's `pytest_runtest_logstart` hook; enabled by `--duckdb-profile`.

When disabled, `record(...)` is a no-op context manager — zero allocation, zero timing
overhead beyond a constant boolean check, so leaving instrumentation in production
code is free.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

_active: bool = False
_stages: dict[str, float] = {}
_counts: dict[str, int] = {}


def enable() -> None:
    global _active
    _active = True


def disable() -> None:
    global _active
    _active = False


def is_active() -> bool:
    return _active


def reset() -> None:
    _stages.clear()
    _counts.clear()


@contextmanager
def record(stage: str) -> Iterator[None]:
    if not _active:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        _stages[stage] = _stages.get(stage, 0.0) + elapsed
        _counts[stage] = _counts.get(stage, 0) + 1


def current() -> dict[str, float]:
    return _stages


def counts() -> dict[str, int]:
    return _counts


def snapshot() -> dict[str, float]:
    """Copy of the current stage totals — safe to attach to a pytest report."""
    return dict(_stages)


def snapshot_counts() -> dict[str, int]:
    return dict(_counts)
