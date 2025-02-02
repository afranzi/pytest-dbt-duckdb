import os

import pytest

from pytest_dbt_duckdb.conftest import DuckFixture, TestFixture, load_yaml_test, load_yaml_tests
from tests import resources_folder

yaml_data = list(load_yaml_tests(resources_folder))


@pytest.mark.parametrize("fixture", yaml_data, ids=[x.id for x in yaml_data])
def test_dbt_yamls(fixture: TestFixture, duckdb_fixture: DuckFixture) -> None:
    duckdb_fixture.execute_dbt(
        nodes_to_load=fixture.given, seed=fixture.seed, build=fixture.build, nodes_to_validate=fixture.then
    )


wip_test_path = os.path.join(resources_folder, "test_tasks.yaml")
wip_fixtures = list(load_yaml_test(file_path=wip_test_path))


@pytest.mark.parametrize("fixture", wip_fixtures, ids=[x.id for x in wip_fixtures])
def test_dbt_yaml(fixture: TestFixture, duckdb_fixture: DuckFixture) -> None:
    duckdb_fixture.execute_dbt(
        nodes_to_load=fixture.given, seed=fixture.seed, build=fixture.build, nodes_to_validate=fixture.then
    )
