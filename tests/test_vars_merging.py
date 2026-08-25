"""All extra_vars must reach dbt in a single --vars flag.

dbt's --vars is a single-value click option, so passing the flag more than once keeps
only the last occurrence. Emitting one flag per variable silently dropped all but the
last -- including the plugin's own elementary_enabled default.
"""

import json
from unittest.mock import MagicMock, patch

from pytest_dbt_duckdb.dbt_executor import DbtExecutor


def _invoked_command(extra_vars: dict | None) -> list[str]:
    executor = DbtExecutor(
        dbt_project_dir="/tmp/project",
        profiles_dir="/tmp/profiles",
        extra_vars=extra_vars,
    )
    with patch("pytest_dbt_duckdb.dbt_executor.dbtRunner") as runner:
        runner.return_value.invoke = MagicMock(return_value=MagicMock())
        executor.execute(command="build", params=["--select", "my_model"])
        (command,), _ = runner.return_value.invoke.call_args
    return command


def _vars_payloads(command: list[str]) -> list[dict]:
    return [json.loads(command[i + 1]) for i, arg in enumerate(command) if arg == "--vars"]


def test_vars_passed_as_single_flag():
    command = _invoked_command({"a": 1, "b": 2})
    assert command.count("--vars") == 1, "multiple --vars flags: all but the last are discarded by dbt"


def test_all_extra_vars_survive():
    payloads = _vars_payloads(_invoked_command({"a": 1, "b": 2, "c": 3}))
    assert payloads[0]["a"] == 1
    assert payloads[0]["b"] == 2
    assert payloads[0]["c"] == 3


def test_elementary_default_survives_alongside_extra_vars():
    payloads = _vars_payloads(_invoked_command({"translation_history_filter": 999}))
    assert payloads[0]["elementary_enabled"] is False
    assert payloads[0]["translation_history_filter"] == 999


def test_elementary_default_present_without_extra_vars():
    payloads = _vars_payloads(_invoked_command(None))
    assert payloads[0] == {"elementary_enabled": False}


def test_caller_var_overrides_elementary_default():
    payloads = _vars_payloads(_invoked_command({"elementary_enabled": True}))
    assert payloads[0]["elementary_enabled"] is True
