import json

from absl import logging
from dbt.artifacts.schemas.results import TestStatus
from dbt.cli.main import dbtRunner, dbtRunnerResult
from dbt.contracts.graph.manifest import Manifest
from dbt.contracts.graph.nodes import ModelNode, SourceDefinition

from pytest_dbt_duckdb import profiler


class DbtExecException(Exception):
    pass


_PARSE_CACHE: dict[tuple, dict] = {}
# Parallel cache holding the actual dbt Manifest object so it can be passed back into
# `dbtRunner(manifest=...)` on subsequent invocations — that's what lets dbt skip the
# parse step on every `dbt build` / `dbt seed`. Same key shape as _PARSE_CACHE so the
# two stay aligned by construction.
#
# Assumption: dbt treats the manifest as effectively immutable across invocations after
# parse. Internal state (e.g., compiled SQL on individual nodes) may be set during a
# build, but it doesn't break a subsequent build that re-uses the same manifest. Verified
# empirically against the bundled e2e + a real consumer suite. If a future dbt-core
# release introduces destructive mutation, this is the assumption to revisit.
#
# The cache has no eviction. Bounded by unique (project_dir, profiles_dir, extra_vars)
# triples — typically one to a handful per worker. If consumers somehow drive that
# unbounded, an LRU cap would be the right fix.
_MANIFEST_CACHE: dict[tuple, Manifest] = {}


class DbtExecutor:
    def __init__(
        self,
        dbt_project_dir: str,
        profiles_dir: str,
        extra_vars: dict | None = None,
        target_path: str | None = None,
        log_path: str | None = None,
    ) -> None:
        self.dbt_project_dir = dbt_project_dir
        self.profiles_dir = profiles_dir
        self.extra_vars = extra_vars or {}
        self.target_path = target_path
        self.log_path = log_path

    def _cache_key(self) -> tuple:
        return (
            self.dbt_project_dir,
            self.profiles_dir,
            json.dumps(self.extra_vars, sort_keys=True, default=str),
        )

    def execute(self, command: str, params: list | None = None) -> dbtRunnerResult:
        cached_manifest = _MANIFEST_CACHE.get(self._cache_key())
        dbt = dbtRunner(manifest=cached_manifest) if cached_manifest is not None else dbtRunner()
        params = params or []
        extra_vars = [json.dumps({key: value}) for key, value in self.extra_vars.items()]
        extra_vars = [x for val in extra_vars for x in ("--vars", val)]

        invoke_command: list[str] = []
        if self.log_path:
            invoke_command += ["--log-path", self.log_path]

        invoke_command += [
            command,
            "--project-dir",
            self.dbt_project_dir,
            "--profiles-dir",
            self.profiles_dir,
            "--vars",
            json.dumps({"elementary_enabled": False}),
        ] + extra_vars

        if self.target_path:
            invoke_command += ["--target-path", self.target_path]

        dbt_command = list(filter(lambda x: x, invoke_command + params))
        logging.info(f"DBT execute {dbt_command}")
        with profiler.record(f"dbt_invoke:{command}"):
            return dbt.invoke(dbt_command)

    def parse_project(self) -> dict[str, SourceDefinition | ModelNode]:
        cache_key = self._cache_key()
        cached = _PARSE_CACHE.get(cache_key)
        if cached is not None:
            with profiler.record("parse_project:hit"):
                pass
            return cached

        with profiler.record("parse_project:miss"):
            res: dbtRunnerResult = self.execute(command="parse")

            # Stash the full manifest so subsequent execute() calls can reuse it via
            # dbtRunner(manifest=...) and skip the parse step entirely.
            _MANIFEST_CACHE[cache_key] = res.result  # type: ignore[assignment]

            result_sources: list[SourceDefinition] = res.result.sources.values()  # type: ignore
            sources = [source for source in result_sources if source.columns]

            result_models: list[ModelNode] = res.result.nodes.values()  # type: ignore
            models = [model for model in result_models if model.columns]

            nodes = sources + models
            parsed = {f"{node.schema}.{node.identifier}": node for node in nodes}
            _PARSE_CACHE[cache_key] = parsed
            return parsed

    @staticmethod
    def validate_execution(res: dbtRunnerResult) -> None:
        errors = (
            result
            for result in res.result.results  # type: ignore
            if result and result.status in [TestStatus.Fail, TestStatus.Error]  # type: ignore
        )
        for error in errors:
            raise DbtExecException(f"Issue in {error.node.name} - {error.message}")
