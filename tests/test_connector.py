"""Unit tests for DuckConnector — focused on UDF registration idempotency.

Idempotent registration is required when DBT_DUCKDB_PATH stays stable across tests
within a worker. DuckDB caches the database per-path within a Python process, so
reconnecting to the same path returns a DB that still has previously-registered UDFs.
A second `register_snowflake_functions` would raise without idempotency.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
import pytest

from pytest_dbt_duckdb.connector import DuckConnector
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
