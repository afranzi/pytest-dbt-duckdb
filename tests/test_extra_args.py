"""extra_args must be appended verbatim to the dbt build/seed invocation."""

from unittest.mock import MagicMock

from pytest_dbt_duckdb.dbt_validator import DbtValidator


def _validator_with_mock_executor() -> tuple[DbtValidator, MagicMock]:
    executor = MagicMock()
    executor.parse_project.return_value = {}
    # Bypass __init__ to avoid a real dbt parse; there is no lightweight test-double constructor.
    validator = DbtValidator.__new__(DbtValidator)
    validator.connector = MagicMock()
    validator.executor = executor
    validator.resources_folder = "/tmp"
    validator.nodes = {}
    validator.debug_output = False
    return validator, executor


def test_extra_args_appended_to_build():
    validator, executor = _validator_with_mock_executor()
    validator.dbt_load_nodes = MagicMock()
    validator.dbt_validate_nodes = MagicMock()

    validator.validate(
        nodes_to_load=[],
        nodes_to_validate=[],
        build="stg_cdc_events",
        extra_args=["--event-time-start", "2025-10-10", "--event-time-end", "2025-10-11"],
    )

    _, kwargs = executor.execute.call_args
    params = kwargs["params"]
    assert len(params) == 6
    assert params[:2] == ["--select", "stg_cdc_events"]
    assert params[-4:] == ["--event-time-start", "2025-10-10", "--event-time-end", "2025-10-11"]


def test_extra_args_appended_to_seed():
    validator, executor = _validator_with_mock_executor()
    validator.dbt_load_nodes = MagicMock()
    validator.dbt_validate_nodes = MagicMock()

    validator.validate(
        nodes_to_load=[],
        nodes_to_validate=[],
        seed="my_seed",
        extra_args=["--full-refresh"],
    )

    _, kwargs = executor.execute.call_args
    assert kwargs["params"] == ["--select", "my_seed", "--full-refresh"]


def test_extra_args_default_is_noop():
    validator, executor = _validator_with_mock_executor()
    validator.dbt_load_nodes = MagicMock()
    validator.dbt_validate_nodes = MagicMock()

    validator.validate(nodes_to_load=[], nodes_to_validate=[], build="m")

    _, kwargs = executor.execute.call_args
    assert kwargs["params"] == ["--select", "m"]
