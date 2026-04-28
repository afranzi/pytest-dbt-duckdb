from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Callable

import numpy as np
import pandas as pd
from absl import logging
from duckdb import DuckDBPyConnection
from duckdb.typing import DATE, INTEGER, VARCHAR, DuckDBPyType
from pydantic import BaseModel, ConfigDict

from pytest_dbt_duckdb.snowflake_functions import (
    array_size,
    array_union_agg,
    bitand,
    current_timestamp,
    date_add,
    div0,
    iff,
    to_char,
    to_decimal,
)


class DuckFunction(BaseModel):
    name: str
    function: Callable
    parameters: list[DuckDBPyType | Any] | None = None
    return_type: DuckDBPyType | Any | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ExtraFunctions(BaseModel):
    macros: list[str] | None = None
    functions: list[DuckFunction] | None = None


_CREATE_MACRO_PATTERN = re.compile(r"\bCREATE\s+MACRO\b(?!\s+IF\s+NOT\s+EXISTS)", re.IGNORECASE)


def _make_macro_idempotent(sql: str) -> str:
    """Rewrite `CREATE MACRO` -> `CREATE OR REPLACE MACRO` (case-insensitive) so the
    same macro can be re-registered safely when the underlying DuckDB DB is reused
    across tests. Already-idempotent forms (`CREATE OR REPLACE MACRO`,
    `CREATE MACRO IF NOT EXISTS`) are left alone."""
    if "OR REPLACE" in sql.upper():
        return sql
    return _CREATE_MACRO_PATTERN.sub("CREATE OR REPLACE MACRO", sql, count=1)


class DuckConnector:
    def __init__(self, conn: DuckDBPyConnection, extra_functions: ExtraFunctions | None) -> None:
        self.conn = conn
        self.register_snowflake_functions()

        if extra_functions:
            for macro in extra_functions.macros or []:
                self.execute(query=_make_macro_idempotent(macro))
            for fn in extra_functions.functions or []:
                self._register_udf_if_absent(
                    name=fn.name,
                    function=fn.function,
                    parameters=fn.parameters or [],
                    return_type=fn.return_type,
                )

    def execute(self, query: str, parameters: dict[str, Any] | None = None) -> DuckDBPyConnection:
        logging.info(f"Running query = {query}")
        return self.conn.execute(query, parameters=parameters)

    def clone_table(self, source: str, target: str) -> DuckDBPyConnection:
        return self.execute(f"CREATE OR REPLACE TABLE {target} AS SELECT * FROM {source} WHERE 1=0;")

    def insert_data(self, table: str, data_path: str, columns: dict[str, str] | None = None) -> DuckDBPyConnection:
        if data_path.endswith(".csv"):
            if columns:
                return self.execute(f"""
                    INSERT INTO {table}
                    SELECT * FROM read_csv(
                        '{data_path}',
                        header = true,
                        allow_quoted_nulls = false,
                        auto_detect = true,
                        columns={columns}
                    )
                """)
            return self.execute(f"INSERT INTO {table} SELECT * FROM read_csv_auto('{data_path}')")
        elif data_path.endswith(".json"):
            if columns:
                return self.execute(f"""
                    INSERT INTO {table}
                    SELECT * FROM read_json(
                        '{data_path}',
                        format='array',
                        columns={columns}
                    )
                """)
            return self.execute(f"INSERT INTO {table} SELECT * FROM read_json_auto('{data_path}')")
        else:
            raise RuntimeError(f"File {data_path} not supported")

    def fetch_data(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict]:
        return self.execute(query, parameters=parameters).arrow().to_pylist()

    @staticmethod
    def sort_df(df: pd.DataFrame) -> pd.DataFrame:
        def make_hashable(value: Any) -> Any:
            if isinstance(value, np.ndarray):
                return make_hashable(value.tolist())
            elif isinstance(value, (list, dict)):
                return json.dumps(value, sort_keys=True)
            elif isinstance(value, (datetime, date)):
                return value.isoformat()
            return value

        df = df.map(make_hashable)
        df = df.reindex(sorted(df.columns), axis=1)
        return df.sort_values(by=list(df.columns), axis=0).reset_index(drop=True)

    def fetch_sorted_df(self, query: str, parameters: dict[str, Any] | None = None) -> pd.DataFrame:
        df = self.execute(query, parameters=parameters).fetch_df()
        return self.sort_df(df)

    def fetch_table(self, schema: str, table: str) -> pd.DataFrame:
        return self.fetch_sorted_df(f"SELECT * FROM {schema}.{table}")

    def describe_table(self, schema: str, table: str) -> pd.DataFrame:
        return self.fetch_sorted_df(f"SHOW {schema}.{table}")

    def get_table_columns(self, table: str) -> list[str]:
        columns = self.execute(f"SELECT name FROM pragma_table_info('{table}')").arrow().to_pydict()["name"]
        return columns

    def create_tmp_table(self, table: str, data_path: str) -> DuckDBPyConnection:
        if data_path.endswith(".csv"):
            return self.execute(f"CREATE TEMP TABLE {table} AS SELECT * FROM read_csv_auto('{data_path}');")
        elif data_path.endswith(".json"):
            return self.execute(f"CREATE TEMP TABLE {table} AS SELECT * FROM read_json_auto('{data_path}');")
        else:
            raise RuntimeError(f"File {data_path} not supported")

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def __exit__(
        self,
        exception_type: str,
        exception_value: str,
        traceback: str,
    ) -> None:
        self.conn.close()
        logging.info("Closing connection...")

    def __enter__(self) -> DuckConnector:
        return self

    def register_snowflake_functions(self) -> None:
        # Macros use CREATE MACRO IF NOT EXISTS — already idempotent.
        self.execute(query=iff())
        self.execute(query=bitand())
        self.execute(query=array_size())
        self.execute(query=array_union_agg())
        self.execute(query=div0())
        self.execute(query=to_decimal())
        self.execute(query=current_timestamp())

        # UDFs registered via conn.create_function are not idempotent — DuckDB raises
        # NotImplementedException on duplicate registration. When DBT_DUCKDB_PATH stays
        # stable across tests, DuckDB's process-wide DB cache remembers prior UDFs, so
        # we must skip already-registered ones.
        self._register_udf_if_absent("to_char", to_char, [DATE, VARCHAR], VARCHAR)
        self._register_udf_if_absent("dateadd", date_add, [VARCHAR, INTEGER, DATE], DATE)

    def _register_udf_if_absent(
        self,
        name: str,
        function: Callable,
        parameters: list[Any],
        return_type: Any,
    ) -> None:
        existing = self.conn.execute(
            "SELECT 1 FROM duckdb_functions() WHERE function_name = ? LIMIT 1",
            [name],
        ).fetchone()
        if existing:
            return
        self.conn.create_function(
            name=name,
            function=function,
            parameters=parameters,
            return_type=return_type,
        )
