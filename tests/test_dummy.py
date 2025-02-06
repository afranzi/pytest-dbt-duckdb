import pytest

from pytest_dbt_duckdb.plugin import DuckFixture, TestFixture, load_yaml_tests
from tests import dbt_project_dir, resources_folder

yaml_data = list(load_yaml_tests(resources_folder))


@pytest.mark.parametrize("fixture", yaml_data, ids=[x.id for x in yaml_data])
def test_dbt_scenarios(fixture: TestFixture, duckdb_fixture: DuckFixture) -> None:
    duckdb_fixture.execute_dbt(
        nodes_to_load=fixture.given,
        seed=fixture.seed,
        build=fixture.build,
        nodes_to_validate=fixture.then,
        resources_folder=resources_folder,
        dbt_project_dir=dbt_project_dir,
    )
