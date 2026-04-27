"""Unit tests for the per-test isolation and manifest-cache behaviour
that enables parallel test execution under pytest-xdist."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pytest_dbt_duckdb import dbt_executor as dbt_executor_module
from pytest_dbt_duckdb.dbt_executor import DbtExecutor
from pytest_dbt_duckdb.plugin import PyDuckSettings


@pytest.fixture(autouse=True)
def _clear_parse_cache() -> None:
    """Each test gets a clean cache so memoisation assertions are deterministic."""
    dbt_executor_module._PARSE_CACHE.clear()


class TestPyDuckSettings:
    def test_target_path_is_under_temp_dir(self, tmp_path) -> None:
        settings = PyDuckSettings(temp_dir=str(tmp_path))
        assert settings.target_path == os.path.join(str(tmp_path), "dbt_target")

    def test_log_path_is_under_temp_dir(self, tmp_path) -> None:
        settings = PyDuckSettings(temp_dir=str(tmp_path))
        assert settings.log_path == os.path.join(str(tmp_path), "dbt_logs")

    def test_target_and_log_paths_are_unique_per_settings_instance(self, tmp_path) -> None:
        a = PyDuckSettings(temp_dir=str(tmp_path / "a"))
        b = PyDuckSettings(temp_dir=str(tmp_path / "b"))
        assert a.target_path != b.target_path
        assert a.log_path != b.log_path


class TestDbtExecutorCommandConstruction:
    def _capture_invoke(self, executor: DbtExecutor, command: str = "build") -> list[str]:
        """Run executor.execute and capture the argv passed to dbtRunner.invoke."""
        with patch.object(dbt_executor_module, "dbtRunner") as runner_cls:
            runner = MagicMock()
            runner_cls.return_value = runner
            executor.execute(command=command)
            args, _ = runner.invoke.call_args
        return list(args[0])

    def test_omits_target_and_log_path_flags_when_unset(self) -> None:
        executor = DbtExecutor(dbt_project_dir="/proj", profiles_dir="/profiles")
        argv = self._capture_invoke(executor)
        assert "--target-path" not in argv
        assert "--log-path" not in argv

    def test_appends_target_path_after_subcommand(self) -> None:
        executor = DbtExecutor(
            dbt_project_dir="/proj",
            profiles_dir="/profiles",
            target_path="/tmp/test_target",
        )
        argv = self._capture_invoke(executor, command="build")
        assert "--target-path" in argv
        assert argv[argv.index("--target-path") + 1] == "/tmp/test_target"
        # subcommand must precede --target-path (per dbt CLI convention)
        assert argv.index("build") < argv.index("--target-path")

    def test_prepends_log_path_before_subcommand(self) -> None:
        executor = DbtExecutor(
            dbt_project_dir="/proj",
            profiles_dir="/profiles",
            log_path="/tmp/test_logs",
        )
        argv = self._capture_invoke(executor, command="parse")
        assert "--log-path" in argv
        assert argv[argv.index("--log-path") + 1] == "/tmp/test_logs"
        # --log-path is a global flag and must precede the subcommand
        assert argv.index("--log-path") < argv.index("parse")

    def test_target_path_does_not_collide_across_executors(self) -> None:
        a = DbtExecutor(dbt_project_dir="/p", profiles_dir="/pf", target_path="/tmp/a")
        b = DbtExecutor(dbt_project_dir="/p", profiles_dir="/pf", target_path="/tmp/b")
        argv_a = self._capture_invoke(a)
        argv_b = self._capture_invoke(b)
        assert argv_a[argv_a.index("--target-path") + 1] == "/tmp/a"
        assert argv_b[argv_b.index("--target-path") + 1] == "/tmp/b"


class TestParseProjectMemoisation:
    def _make_executor(self, **overrides: Any) -> DbtExecutor:
        kwargs: dict[str, Any] = {"dbt_project_dir": "/proj", "profiles_dir": "/profiles"}
        kwargs.update(overrides)
        return DbtExecutor(**kwargs)

    def _patched_parse(self, executor: DbtExecutor):
        """Run parse_project with a stubbed dbt parse result, returning the call count."""
        sentinel_node = MagicMock()
        sentinel_node.schema = "s"
        sentinel_node.identifier = "t"
        sentinel_node.columns = {"id": MagicMock()}

        fake_result = MagicMock()
        fake_result.result.sources.values.return_value = []
        fake_result.result.nodes.values.return_value = [sentinel_node]

        execute = MagicMock(return_value=fake_result)
        with patch.object(executor, "execute", execute):
            manifest = executor.parse_project()
        return manifest, execute.call_count

    def test_first_call_invokes_dbt_parse(self) -> None:
        executor = self._make_executor()
        manifest, calls = self._patched_parse(executor)
        assert "s.t" in manifest
        assert calls == 1

    def test_second_call_with_same_key_skips_dbt_parse(self) -> None:
        executor = self._make_executor()
        self._patched_parse(executor)  # warm cache
        _, calls = self._patched_parse(executor)
        assert calls == 0

    def test_different_extra_vars_yield_different_cache_entries(self) -> None:
        a = self._make_executor(extra_vars={"x": 1})
        b = self._make_executor(extra_vars={"x": 2})
        _, calls_a = self._patched_parse(a)
        _, calls_b = self._patched_parse(b)
        assert calls_a == 1
        assert calls_b == 1  # different vars => cache miss => second parse

    def test_extra_vars_key_is_order_independent(self) -> None:
        a = self._make_executor(extra_vars={"x": 1, "y": 2})
        b = self._make_executor(extra_vars={"y": 2, "x": 1})
        self._patched_parse(a)
        _, calls_b = self._patched_parse(b)
        assert calls_b == 0  # same key after sort => cache hit

    def test_target_path_does_not_affect_cache_key(self) -> None:
        a = self._make_executor(target_path="/tmp/a")
        b = self._make_executor(target_path="/tmp/b")
        self._patched_parse(a)
        _, calls_b = self._patched_parse(b)
        # Manifest is invariant w.r.t. target_path; target_path only affects on-disk artifacts.
        assert calls_b == 0
