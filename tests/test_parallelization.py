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

    def test_db_file_path_uses_artifacts_dir_when_set(self, tmp_path) -> None:
        """When dbt_artifacts_dir is set (per-worker stable path), db_file_path lives there
        — not in temp_dir. This is what makes DBT_DUCKDB_PATH stable across tests, which
        in turn lets dbt's partial_parse cache survive between tests."""
        artifacts = str(tmp_path / "worker_dbt")
        settings = PyDuckSettings(temp_dir=str(tmp_path / "test"), dbt_artifacts_dir=artifacts)
        assert settings.db_file_path.startswith(artifacts)

    def test_target_and_log_paths_use_artifacts_dir_when_set(self, tmp_path) -> None:
        artifacts = str(tmp_path / "worker_dbt")
        settings = PyDuckSettings(temp_dir=str(tmp_path / "test"), dbt_artifacts_dir=artifacts)
        assert settings.target_path == os.path.join(artifacts, "dbt_target")
        assert settings.log_path == os.path.join(artifacts, "dbt_logs")

    def test_two_settings_with_same_artifacts_dir_resolve_to_same_db_path(self, tmp_path) -> None:
        artifacts = str(tmp_path / "worker_dbt")
        a = PyDuckSettings(temp_dir=str(tmp_path / "test_a"), dbt_artifacts_dir=artifacts)
        b = PyDuckSettings(temp_dir=str(tmp_path / "test_b"), dbt_artifacts_dir=artifacts)
        assert a.db_file_path == b.db_file_path
        assert a.target_path == b.target_path


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


class TestManifestCache:
    """The manifest cache is what eliminates the per-invoke parse cost: after the first
    `dbt parse` populates _MANIFEST_CACHE, every subsequent execute() call passes the
    cached manifest into `dbtRunner(manifest=...)`, which lets dbt skip the parse step
    entirely. This is the single biggest win: ~20s/invoke off `dbt build` and `dbt seed`."""

    def _make_executor(self, **overrides: Any) -> DbtExecutor:
        kwargs: dict[str, Any] = {"dbt_project_dir": "/proj", "profiles_dir": "/profiles"}
        kwargs.update(overrides)
        return DbtExecutor(**kwargs)

    def _capture_runner_kwargs(self, executor: DbtExecutor, command: str = "build"):
        """Run executor.execute and capture the kwargs passed to dbtRunner(...)."""
        with patch.object(dbt_executor_module, "dbtRunner") as runner_cls:
            runner = MagicMock()
            runner_cls.return_value = runner
            executor.execute(command=command)
            return runner_cls.call_args.kwargs if runner_cls.call_args.kwargs else {}

    def test_dbt_runner_is_constructed_without_manifest_when_cache_empty(self) -> None:
        dbt_executor_module._MANIFEST_CACHE.clear()
        executor = self._make_executor()
        kwargs = self._capture_runner_kwargs(executor)
        # Cold cache: dbtRunner called with no manifest, so dbt does its full parse.
        assert kwargs.get("manifest") is None

    def test_dbt_runner_receives_cached_manifest_after_parse(self) -> None:
        dbt_executor_module._MANIFEST_CACHE.clear()
        executor = self._make_executor()
        sentinel_manifest = MagicMock(name="cached_manifest")
        # Manually populate the cache the way parse_project would.
        cache_key = (
            executor.dbt_project_dir,
            executor.profiles_dir,
            "{}",
        )
        dbt_executor_module._MANIFEST_CACHE[cache_key] = sentinel_manifest

        kwargs = self._capture_runner_kwargs(executor)
        assert kwargs.get("manifest") is sentinel_manifest

    def test_different_extra_vars_get_separate_manifests(self) -> None:
        dbt_executor_module._MANIFEST_CACHE.clear()
        m_a = MagicMock(name="manifest_a")
        m_b = MagicMock(name="manifest_b")
        a = self._make_executor(extra_vars={"x": 1})
        b = self._make_executor(extra_vars={"x": 2})

        import json as _json

        dbt_executor_module._MANIFEST_CACHE[
            (a.dbt_project_dir, a.profiles_dir, _json.dumps({"x": 1}, sort_keys=True, default=str))
        ] = m_a
        dbt_executor_module._MANIFEST_CACHE[
            (b.dbt_project_dir, b.profiles_dir, _json.dumps({"x": 2}, sort_keys=True, default=str))
        ] = m_b

        assert self._capture_runner_kwargs(a).get("manifest") is m_a
        assert self._capture_runner_kwargs(b).get("manifest") is m_b

    def test_parse_project_populates_manifest_cache(self) -> None:
        dbt_executor_module._MANIFEST_CACHE.clear()
        executor = self._make_executor()

        # Simulate dbt parse returning a result. parse_project should stash result.result
        # in _MANIFEST_CACHE under the same key as _PARSE_CACHE.
        sentinel_node = MagicMock()
        sentinel_node.schema = "s"
        sentinel_node.identifier = "t"
        sentinel_node.columns = {"id": MagicMock()}

        fake_result = MagicMock()
        fake_result.result.sources.values.return_value = []
        fake_result.result.nodes.values.return_value = [sentinel_node]

        with patch.object(executor, "execute", return_value=fake_result) as mock_execute:
            executor.parse_project()

        cache_key = (executor.dbt_project_dir, executor.profiles_dir, "{}")
        assert cache_key in dbt_executor_module._MANIFEST_CACHE
        # The cached manifest is whatever dbtRunnerResult.result was — i.e. fake_result.result.
        assert dbt_executor_module._MANIFEST_CACHE[cache_key] is fake_result.result
        mock_execute.assert_called_once()
