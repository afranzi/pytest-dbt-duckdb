"""Unit tests for the opt-in test-stage profiler."""

from __future__ import annotations

import time

import pytest

from pytest_dbt_duckdb import profiler
from pytest_dbt_duckdb.plugin import compute_total, primary_stage_order


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


class TestComputeTotal:
    def test_sums_all_primary_stages_including_parse_project(self) -> None:
        stages = {
            "load_given": 0.10,
            "parse_project:miss": 30.00,
            "dbt_seed": 5.00,
            "dbt_build": 20.00,
            "validate_then": 0.05,
        }
        # parse_project runs in DbtValidator.__init__, BEFORE validate(), so it must
        # be included in total to reflect the real per-test wall cost.
        assert compute_total(stages) == pytest.approx(55.15)

    def test_excludes_dbt_invoke_substages(self) -> None:
        stages = {
            "dbt_seed": 5.00,
            "dbt_invoke:seed": 5.00,  # sub-stage of dbt_seed; would double-count
            "dbt_build": 10.00,
            "dbt_invoke:build": 10.00,
        }
        assert compute_total(stages) == pytest.approx(15.00)

    def test_handles_missing_stages(self) -> None:
        # build-only test (no seed): dbt_seed absent, must not error
        stages = {"load_given": 0.01, "parse_project:miss": 30.0, "dbt_build": 30.0, "validate_then": 0.02}
        assert compute_total(stages) == pytest.approx(60.03)

    def test_includes_parse_project_hit(self) -> None:
        stages = {"load_given": 0.01, "parse_project:hit": 0.001, "dbt_build": 20.0, "validate_then": 0.01}
        assert compute_total(stages) == pytest.approx(20.021, abs=1e-3)


class TestPrimaryStageOrder:
    def test_chronological_order_with_parse_project_after_load_given(self) -> None:
        order = primary_stage_order()
        assert order.index("load_given") < order.index("parse_project:miss")
        assert order.index("parse_project:miss") < order.index("dbt_seed")
        assert order.index("dbt_seed") < order.index("dbt_build")
        assert order.index("dbt_build") < order.index("validate_then")
