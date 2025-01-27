import os
import tempfile
from typing import Iterable

import duckdb
import pytest
from duckdb import DuckDBPyConnection
from pydantic import BaseModel, ConfigDict
from ruamel.yaml import YAML

from pytest_dbt_duckdb.connector import DuckConnector
from pytest_dbt_duckdb.dbt_executor import DbtExecutor
from pytest_dbt_duckdb.dbt_validator import DbtTestNode, DbtValidator


class TestFixture(BaseModel):
    id: str
    given: list[DbtTestNode]
    build: str | list[str] | None = None
    seed: str | None = None
    then: list[DbtTestNode]


class DuckFixture(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    conn: DuckDBPyConnection
    path: str

    def execute_dbt(
        self,
        dbt_project_dir: str,
        resources_folder: str,
        nodes_to_load: list[DbtTestNode],
        nodes_to_validate: list[DbtTestNode],
        seed: str | None = None,
        build: str | list[str] | None = None,
    ) -> None:
        connector = DuckConnector(conn=self.conn)
        os.environ["DBT_DUCKDB_PATH"] = str(self.path)

        executor = DbtExecutor(dbt_project_dir=dbt_project_dir, profiles_dir=resources_folder)
        validator = DbtValidator(connector=connector, executor=executor, resources_folder=resources_folder)
        validator.validate(nodes_to_load=nodes_to_load, nodes_to_validate=nodes_to_validate, seed=seed, build=build)


@pytest.fixture(scope="function")
def duckdb_fixture() -> Iterable[DuckFixture]:
    temp_dir = tempfile.gettempdir()
    db_file_path = os.path.join(temp_dir, "raw.duckdb")

    conn = duckdb.connect(db_file_path)
    try:
        yield DuckFixture(conn=conn, path=db_file_path)
    finally:
        conn.close()

    # Remove the file after the test
    if os.path.exists(db_file_path):
        os.remove(db_file_path)


def load_yaml_test(file_path: str, yaml: YAML = YAML(typ="safe", pure=True)) -> Iterable[TestFixture]:
    with open(file_path, "r") as file:
        tests: list[dict] = yaml.load(file)["tests"]
        for test_fixture in tests:
            yield TestFixture(**test_fixture)


def load_yaml_tests(directory: str) -> Iterable[TestFixture]:
    yaml = YAML(typ="safe", pure=True)
    for filename in os.listdir(directory):
        if filename.startswith("test_") & filename.endswith(".yaml"):
            file_path = os.path.join(directory, filename)
            yield from load_yaml_test(file_path=file_path, yaml=yaml)


# yaml_data = list(load_yaml_tests(resources_folder))
