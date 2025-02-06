import json

from absl import logging
from dbt.artifacts.schemas.results import TestStatus
from dbt.cli.main import dbtRunner, dbtRunnerResult
from dbt.contracts.graph.nodes import ModelNode, SourceDefinition


class DbtExecException(Exception):
    pass


class DbtExecutor:
    def __init__(self, dbt_project_dir: str, profiles_dir: str) -> None:
        self.dbt_project_dir = dbt_project_dir
        self.profiles_dir = profiles_dir

    def execute(self, command: str, params: list | None = None) -> dbtRunnerResult:
        dbt = dbtRunner()
        params = params or []
        invoke_command = [
            command,
            "--project-dir",
            self.dbt_project_dir,
            "--profiles-dir",
            self.profiles_dir,
            "--vars",
            json.dumps({"elementary_enabled": False}),
        ]
        dbt_command = list(filter(lambda x: x, invoke_command + params))
        logging.info(f"DBT execute {dbt_command}")
        return dbt.invoke(dbt_command)

    def parse_project(self) -> dict[str, SourceDefinition | ModelNode]:
        self.execute(command="deps")
        res: dbtRunnerResult = self.execute(command="parse")

        result_sources: list[SourceDefinition] = res.result.sources.values()  # type: ignore
        sources = [source for source in result_sources if source.columns]

        result_models: list[ModelNode] = res.result.nodes.values()  # type: ignore
        models = [model for model in result_models if model.columns]

        nodes = sources + models
        return {f"{node.schema}.{node.identifier}": node for node in nodes}

    @staticmethod
    def validate_execution(res: dbtRunnerResult) -> None:
        errors = (
            result
            for result in res.result.results  # type: ignore
            if result and result.status in [TestStatus.Fail, TestStatus.Error]  # type: ignore
        )
        for error in errors:
            raise DbtExecException(f"Issue in {error.node.name} - {error.message}")
