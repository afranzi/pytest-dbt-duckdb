from dbt.contracts.graph.nodes import ColumnInfo

from pytest_dbt_duckdb.connector import DuckConnector


def create_schema(connector: DuckConnector, schema: str) -> None:
    connector.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")


def create_table(connector: DuckConnector, schema: str, table: str, columns: list[ColumnInfo]) -> None:
    for column in columns:
        if column.data_type and column.data_type.startswith("MAP"):
            column.data_type = "JSON"

    columns_sql = [f'"{column.name}" {column.data_type or "varchar"}' for column in columns]
    columns_str = ",".join(columns_sql)
    ddl = f"CREATE OR REPLACE TABLE {schema}.{table} ({columns_str})"
    connector.execute(ddl)
