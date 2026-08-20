"""Unit tests for DuckConnector — focused on UDF registration idempotency.

Idempotent registration is required when DBT_DUCKDB_PATH stays stable across tests
within a worker. DuckDB caches the database per-path within a Python process, so
reconnecting to the same path returns a DB that still has previously-registered UDFs.
A second `register_snowflake_functions` would raise without idempotency.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest
from duckdb.sqltypes import INTEGER

from pytest_dbt_duckdb.connector import DuckConnector, DuckFunction, ExtraFunctions
from pytest_dbt_duckdb.plugin import reset_user_schemas


@pytest.fixture()
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield str(Path(tmp) / "test.duckdb")


class TestSnowflakeUdfIdempotency:
    def test_register_can_be_called_on_a_db_with_pre_existing_udfs(self, db_path) -> None:
        """Reconnect to a DuckDB file whose process-cached DB still has UDFs registered;
        DuckConnector must not raise."""
        conn1 = duckdb.connect(db_path)
        DuckConnector(conn=conn1, extra_functions=None)
        conn1.close()

        # Reopen — DuckDB's process-wide DB cache still has to_char and dateadd registered.
        conn2 = duckdb.connect(db_path)
        try:
            DuckConnector(conn=conn2, extra_functions=None)  # Must NOT raise.
            assert conn2.execute("SELECT to_char(DATE '2026-04-28', 'YYYY-MM-DD')").fetchone() == ("2026-04-28",)
        finally:
            conn2.close()

    def test_three_consecutive_reconnects_register_cleanly(self, db_path) -> None:
        """Stress: simulate many tests in a worker."""
        for _ in range(3):
            conn = duckdb.connect(db_path)
            try:
                DuckConnector(conn=conn, extra_functions=None)
            finally:
                conn.close()

    def test_macros_remain_callable_after_idempotent_register(self, db_path) -> None:
        conn1 = duckdb.connect(db_path)
        DuckConnector(conn=conn1, extra_functions=None)
        conn1.close()

        conn2 = duckdb.connect(db_path)
        try:
            DuckConnector(conn=conn2, extra_functions=None)
            # Macros are CREATE MACRO IF NOT EXISTS — already idempotent — but make sure
            # they still work after the second registration pass.
            assert conn2.execute("SELECT iff(true, 1, 2)").fetchone() == (1,)
            assert conn2.execute("SELECT div0(10, 0)").fetchone() == (0,)
        finally:
            conn2.close()


class TestResetUserSchemas:
    def test_drops_user_schemas_and_their_data(self, db_path) -> None:
        conn = duckdb.connect(db_path)
        try:
            conn.execute("CREATE SCHEMA myschema")
            conn.execute("CREATE TABLE myschema.t (x INT)")
            conn.execute("INSERT INTO myschema.t VALUES (42)")

            reset_user_schemas(conn)

            schemas = {r[0] for r in conn.execute("SELECT schema_name FROM information_schema.schemata").fetchall()}
            assert "myschema" not in schemas
        finally:
            conn.close()

    def test_keeps_system_schemas(self, db_path) -> None:
        conn = duckdb.connect(db_path)
        try:
            conn.execute("CREATE SCHEMA throwaway")
            reset_user_schemas(conn)
            schemas = {r[0] for r in conn.execute("SELECT schema_name FROM information_schema.schemata").fetchall()}
            # System schemas must survive.
            assert "main" in schemas
            assert "information_schema" in schemas
            assert "pg_catalog" in schemas
        finally:
            conn.close()

    def test_preserves_registered_udfs(self, db_path) -> None:
        """The whole point of resetting schemas instead of recreating the file is to keep
        UDFs registered (DuckDB's process-wide DB cache is per-path)."""
        conn = duckdb.connect(db_path)
        try:
            DuckConnector(conn=conn, extra_functions=None)
            conn.execute("CREATE SCHEMA myschema")
            conn.execute("CREATE TABLE myschema.t AS SELECT to_char(DATE '2026-04-28', 'YYYY-MM-DD') AS d")

            reset_user_schemas(conn)

            # to_char should still work after the reset (UDF survives schema drop).
            assert conn.execute("SELECT to_char(DATE '2026-04-28', 'YYYY-MM-DD')").fetchone() == ("2026-04-28",)
        finally:
            conn.close()

    def test_idempotent_when_no_user_schemas_exist(self, db_path) -> None:
        conn = duckdb.connect(db_path)
        try:
            reset_user_schemas(conn)  # No user schemas; must not raise.
            reset_user_schemas(conn)  # Idempotent.
        finally:
            conn.close()


class TestExtraFunctionsIdempotency:
    """Consumer-supplied extra_functions also need to be idempotent. With stable
    DBT_DUCKDB_PATH per worker, every test re-instantiates DuckConnector against
    the same DuckDB DB — so user macros (CREATE MACRO ...) and UDFs would otherwise
    error on the second test."""

    def test_user_macros_can_be_registered_twice(self, db_path) -> None:
        macros = [
            "CREATE MACRO my_double(x) AS (x * 2)",
            "CREATE MACRO my_triple(x) AS (x * 3)",
        ]
        extras = ExtraFunctions(macros=macros)

        conn1 = duckdb.connect(db_path)
        DuckConnector(conn=conn1, extra_functions=extras)
        conn1.close()

        conn2 = duckdb.connect(db_path)
        try:
            DuckConnector(conn=conn2, extra_functions=extras)  # Must NOT raise.
            assert conn2.execute("SELECT my_double(5), my_triple(4)").fetchone() == (10, 12)
        finally:
            conn2.close()

    def test_user_udfs_can_be_registered_twice(self, db_path) -> None:
        def square(n):
            return n * n

        extras = ExtraFunctions(
            functions=[DuckFunction(name="my_square", function=square, parameters=[INTEGER], return_type=INTEGER)]
        )

        conn1 = duckdb.connect(db_path)
        DuckConnector(conn=conn1, extra_functions=extras)
        conn1.close()

        conn2 = duckdb.connect(db_path)
        try:
            DuckConnector(conn=conn2, extra_functions=extras)  # Must NOT raise.
            assert conn2.execute("SELECT my_square(7)").fetchone() == (49,)
        finally:
            conn2.close()

    def test_create_or_replace_macros_pass_through(self, db_path) -> None:
        """Consumers who already wrote CREATE OR REPLACE MACRO must not have their
        SQL altered in any breaking way."""
        macros = ["CREATE OR REPLACE MACRO already_replace(x) AS (x + 100)"]
        conn = duckdb.connect(db_path)
        try:
            DuckConnector(conn=conn, extra_functions=ExtraFunctions(macros=macros))
            assert conn.execute("SELECT already_replace(1)").fetchone() == (101,)
        finally:
            conn.close()


class TestDuckDbApiCompat:
    """Regression cover for DuckDB API/parser behaviour the plugin depends on.

    Each assertion here corresponds to something that broke silently on the
    DuckDB 1.2 -> 1.5 upgrade and only surfaced via the e2e scenarios.
    """

    def test_to_decimal_macro_is_callable(self, db_path) -> None:
        """`precision` became a reserved keyword in the DuckDB 1.5 parser, so the
        to_decimal macro must quote it. Registration alone catches the parse error;
        calling it catches an accidental change to the argument order/arity."""
        conn = duckdb.connect(db_path)
        try:
            DuckConnector(conn=conn, extra_functions=None)
            assert conn.execute("SELECT to_decimal(3.14159265, 12, 5)").fetchone() == (Decimal("3.14159"),)
        finally:
            conn.close()

    def test_get_table_columns_returns_column_names(self, db_path) -> None:
        """Guards the arrow-table conversion: DuckDB 1.5 made `.arrow()` return a
        streaming RecordBatchReader, which has no `to_pydict`."""
        conn = duckdb.connect(db_path)
        try:
            connector = DuckConnector(conn=conn, extra_functions=None)
            conn.execute("CREATE TABLE t (a INTEGER, b VARCHAR, c DATE)")
            assert connector.get_table_columns("t") == ["a", "b", "c"]
        finally:
            conn.close()

    def test_fetch_data_returns_list_of_dicts(self, db_path) -> None:
        """Same arrow-conversion guard as above, for the `to_pylist` path."""
        conn = duckdb.connect(db_path)
        try:
            connector = DuckConnector(conn=conn, extra_functions=None)
            conn.execute("CREATE TABLE t AS SELECT 1 AS a, 'x' AS b")
            assert connector.fetch_data("SELECT a, b FROM t") == [{"a": 1, "b": "x"}]
        finally:
            conn.close()

    def test_list_column_with_apostrophe_round_trips(self, db_path) -> None:
        """DuckDB 1.5 stopped accepting apostrophes inside *unquoted* list elements
        when casting VARCHAR -> LIST. Fixture CSVs must quote such elements, so
        confirm the quoted form still decodes to the bare value."""
        conn = duckdb.connect(db_path)
        try:
            result = conn.execute("""SELECT CAST('["Vincent D''Onofrio", Will Smith]' AS VARCHAR[])""").fetchone()
            assert result == (["Vincent D'Onofrio", "Will Smith"],)
        finally:
            conn.close()
