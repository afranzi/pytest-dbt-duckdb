import json

from absl import logging
from dbt.artifacts.schemas.results import TestStatus
from dbt.cli.main import dbtRunner, dbtRunnerResult
from dbt.contracts.graph.nodes import ModelNode, SourceDefinition


class DbtExecException(Exception):
    pass


_PARSE_CACHE: dict[tuple, dict] = {}


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

    def execute(self, command: str, params: list | None = None) -> dbtRunnerResult:
        dbt = dbtRunner()
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
        return dbt.invoke(dbt_command)

    def parse_project(self) -> dict[str, SourceDefinition | ModelNode]:
        cache_key = (
            self.dbt_project_dir,
            self.profiles_dir,
            json.dumps(self.extra_vars, sort_keys=True, default=str),
        )
        cached = _PARSE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        res: dbtRunnerResult = self.execute(command="parse")

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
