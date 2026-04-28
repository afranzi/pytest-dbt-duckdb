# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`pytest-dbt-duckdb` is a pytest plugin that tests dbt models end-to-end using an in-memory DuckDB instance. The plugin is registered via the `pytest11` entry point in `pyproject.toml` (`pytest_dbt_duckdb.plugin`) — installing the package automatically activates the `duckdb_fixture` for any consumer's pytest run.

## Common commands

Dependency management is via `uv`. The project requires Python ≥ 3.11.

```bash
# Install (mirrors CI)
uv sync --all-extras --dev

# Required before running tests: install dbt packages for the bundled sample project
uv run dbt deps --project-dir tests/dummy_gummy

# Type-check, then run the suite (matches .github/workflows/build.yml)
uv run mypy
uv run pytest -v

# Run a single YAML scenario by its id (id is the parametrize identifier)
uv run pytest -v -k "Validate full project"

# Lint / format
uv run ruff check .
uv run ruff format .
```

Pre-commit hooks (`uv-lock`, `uv-sync`, `ruff`, `ruff-format`) run on commit; `pre-commit install` once after cloning.

## Architecture

The plugin orchestrates a three-stage flow inside `DbtValidator.validate` (`pytest_dbt_duckdb/dbt_validator.py`):

1. **Load `given`** — for each input node, read the dbt model's declared columns from `parse`, `CREATE OR REPLACE TABLE` in DuckDB, then `INSERT` from the CSV/JSON fixture.
2. **Execute dbt** — invoke `dbt seed` and/or `dbt build --select <selector>` against the temporary DuckDB database via `dbtRunner` (`pytest_dbt_duckdb/dbt_executor.py`). `--vars '{"elementary_enabled": false}'` is always injected; user-supplied `extra_vars` are appended as additional `--vars` flags.
3. **Validate `then`** — fetch each output table and compare with `pandas.testing.assert_frame_equal` against an expected fixture loaded into a `<table>_test` companion table. DataFrames are sorted column-wise and row-wise (`DuckConnector.sort_df`) before comparison so row order is irrelevant.

**Per-test isolation**: `duckdb_fixture` (`plugin.py`) creates a fresh `tempfile.TemporaryDirectory` and DuckDB file per test function. The fixture writes `DBT_DUCKDB_PATH` / `DBT_DUCKDB_DATABASE` into the env so the consumer's `profiles.yml` (which must reference these via `env_var(...)`) routes dbt to the temp database.

**Snowflake compatibility layer**: `DuckConnector.register_snowflake_functions` is called on every connection setup and registers DuckDB macros / UDFs for `iff`, `bitand`, `array_size`, `array_union_agg`, `div0`, `to_decimal`, `current_timestamp`, `to_char`, `dateadd` (`pytest_dbt_duckdb/snowflake_functions.py`). This lets Snowflake-targeted dbt SQL run on DuckDB unchanged. Add new compat shims here when models reference unsupported Snowflake builtins.

**Extending DuckDB**: consumers pass `ExtraFunctions(macros=[...], functions=[DuckFunction(...)])` to `execute_dbt` to register extra SQL macros and Python UDFs alongside the Snowflake shims.

**Profiler** (`pytest_dbt_duckdb/profiler.py`): opt-in stage timer activated by `--duckdb-profile`. Wraps the four `DbtValidator.validate` stages (`load_given`, `dbt_seed`, `dbt_build`, `validate_then`) plus per-`dbtRunner.invoke` calls and `parse_project` cache hit/miss. Timings ride on `report.user_properties` so they cross xdist worker→controller. `pytest_terminal_summary` renders a per-worker table and an aggregate. When the flag is off, `record(...)` is a single boolean check, so the instrumentation in production code is free.

**Manifest cache** (`pytest_dbt_duckdb/dbt_executor.py:_MANIFEST_CACHE`): the first `dbt parse` invocation per worker populates a process-local cache of the parsed `Manifest` object, keyed by `(project_dir, profiles_dir, extra_vars)`. Every subsequent `DbtExecutor.execute()` constructs `dbtRunner(manifest=cached)` so dbt skips the parse step entirely. Cuts ~18s/invocation off `dbt build` and `dbt seed` on real projects.

**Stable per-worker DuckDB path** (`plugin.py:_dbt_artifacts_dir`): the DuckDB file lives in a session-scoped per-worker tempdir, not a per-test tempdir. `DBT_DUCKDB_PATH` stays stable across tests, which also keeps dbt's on-disk `partial_parse.msgpack` valid as a backup to the in-memory manifest cache. Per-test isolation comes from `reset_user_schemas(conn)` (drops every non-system schema), not from recreating the file. Reusing the file means DuckDB's process-wide DB cache keeps registered UDFs alive — which is why `register_snowflake_functions` queries `duckdb_functions()` and skips already-registered UDFs (`connector.py:_register_udf_if_absent`).

## Hard requirement: dbt column `data_type`

Every column referenced in a `given` or `then` node **must** have an explicit `data_type` in the dbt project's `schema.yml`. The validator reads `node.columns[*].data_type` from the dbt manifest to issue `CREATE TABLE` DDL; missing types cause schema mismatches that surface as opaque test failures rather than clear errors. `MAP<...>` types are auto-rewritten to `JSON` (see `dbt_validator.dbt_insert_model` and `sql_methods.create_table`).

## YAML test scenarios

Scenarios live in `*.yml` / `*.yaml` files starting with `test` and are loaded via `load_yaml_tests(directory)`. Schema:

```yaml
tests:
  - id: <unique id used as pytest parametrize id>
    given:                           # list[DbtTestNode] — inputs to seed
      - schema: <source schema>
        table:  <source table>
        path:   <CSV/JSON path relative to resources_folder>
    seed:  <dbt seed selector>       # optional
    build: <dbt build selector>      # optional, str or list[str]
    then:                            # list[DbtTestNode] — expected outputs
      - schema: <output schema>
        table:  <output table>
        path:   <expected CSV/JSON path>
```

The bundled example lives in `tests/resources/tests_e2e.yml` and runs against the sample dbt project at `tests/dummy_gummy/`.

## Repo layout notes

- `pytest_dbt_duckdb/` — the plugin (small, ~6 modules); `plugin.py` is the public surface, the rest is internal.
- `tests/dummy_gummy/` — a self-contained dbt project used as the suite's fixture target. Treat its `dbt_project.yml`, `models/`, and `seeds/` as test data — changes here will alter test expectations.
- `tests/resources/` — `profiles.yml` and YAML test scenarios consumed by `tests/test_dummy.py`.
- `tests/__init__.py` — exports `dbt_project_dir` and `resources_folder` as absolute paths; reuse these rather than recomputing.
