"""Unit tests for the opt-in test-stage profiler."""

from __future__ import annotations

import time

import pytest

from pytest_dbt_duckdb import profiler


@pytest.fixture(autouse=True)
def _reset_profiler():
    """Each test gets a fresh profiler state, and profiler is disabled on teardown
    so flags don't leak into the rest of the suite."""
    profiler.disable()
    profiler.reset()
    yield
    profiler.disable()
    profiler.reset()


class TestProfilerEnabled:
    def test_record_appends_named_stage_with_elapsed(self) -> None:
        profiler.enable()
        with profiler.record("seed"):
            time.sleep(0.01)
        stages = profiler.current()
        assert "seed" in stages
        assert stages["seed"] >= 0.01

    def test_multiple_stages_in_one_test_are_summed(self) -> None:
        profiler.enable()
        with profiler.record("seed"):
            time.sleep(0.01)
        with profiler.record("seed"):
            time.sleep(0.01)
        assert profiler.current()["seed"] >= 0.02

    def test_distinct_stages_are_kept_separate(self) -> None:
        profiler.enable()
        with profiler.record("seed"):
            pass
        with profiler.record("build"):
            pass
        assert set(profiler.current()) == {"seed", "build"}

    def test_count_tracks_invocations_per_stage(self) -> None:
        profiler.enable()
        for _ in range(3):
            with profiler.record("seed"):
                pass
        assert profiler.counts()["seed"] == 3


class TestProfilerDisabled:
    def test_record_does_not_track_when_disabled(self) -> None:
        with profiler.record("seed"):
            time.sleep(0.005)
        assert profiler.current() == {}

    def test_enable_disable_toggles(self) -> None:
        profiler.enable()
        with profiler.record("seed"):
            pass
        assert "seed" in profiler.current()
        profiler.reset()
        profiler.disable()
        with profiler.record("build"):
            pass
        assert profiler.current() == {}


class TestSnapshot:
    def test_snapshot_returns_copy(self) -> None:
        profiler.enable()
        with profiler.record("seed"):
            pass
        snap = profiler.snapshot()
        with profiler.record("build"):
            pass
        # snapshot was taken before "build" was recorded
        assert "build" not in snap
        assert "seed" in snap

    def test_reset_clears_state(self) -> None:
        profiler.enable()
        with profiler.record("seed"):
            pass
        profiler.reset()
        assert profiler.current() == {}
        assert profiler.counts() == {}
