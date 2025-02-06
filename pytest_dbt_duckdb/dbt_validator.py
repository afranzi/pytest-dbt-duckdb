import os

import pandas as pd
from pandas.testing import assert_frame_equal
from pydantic import BaseModel

from pytest_dbt_duckdb.connector import DuckConnector
from pytest_dbt_duckdb.dbt_executor import DbtExecutor
from pytest_dbt_duckdb.sql_methods import create_schema, create_table


class DbtTestNode(BaseModel):
    schema: str  # type: ignore
    table: str
    path: str

    @property
    def model(self) -> str:
        return f"{self.schema}.{self.table}"


class DbtValidator:
    def __init__(self, connector: DuckConnector, executor: DbtExecutor, resources_folder: str) -> None:
        self.connector = connector
        self.executor = executor
        self.resources_folder = resources_folder

        # Initialize validator
        self.nodes = self.executor.parse_project()

    def dbt_create_model(
        self,
        node: DbtTestNode,
        include_columns: list[str] | None = None,
        table_alias: str | None = None,
    ) -> None:
        source = self.nodes[node.model]
        create_schema(self.connector, source.schema)

        columns = source.columns
        if include_columns:
            columns = {column: columns[column] for column in include_columns}

        create_table(self.connector, source.schema, table_alias or source.identifier, list(columns.values()))

    def dbt_insert_model(
        self, node: DbtTestNode, include_columns: list[str] | None = None, table_alias: str | None = None
    ) -> None:
        file = os.path.join(self.resources_folder, node.path)

        columns = None
        if dbt_node := self.nodes.get(node.model):
            columns = {field.name: field.data_type for field in dbt_node.columns.values() if field.data_type}
            if include_columns:
                columns = {column: columns[column] for column in include_columns}

            for column, data_type in columns.items():
                if data_type and data_type.startswith("MAP"):
                    columns[column] = "JSON"

        self.connector.insert_data(
            table=table_alias or node.model,
            data_path=file,
            columns=columns,
        )

    def extract_node_columns(self, node: DbtTestNode) -> list[str]:
        file = os.path.join(self.resources_folder, node.path)
        self.connector.create_tmp_table(table=f"temp_{node.table}", data_path=file)
        return self.connector.get_table_columns(f"temp_{node.table}")

    def dbt_load_node(self, node: DbtTestNode) -> None:
        file_columns = self.extract_node_columns(node=node)

        try:
            self.dbt_create_model(node=node, include_columns=file_columns)
            self.dbt_insert_model(node=node, include_columns=file_columns)
        except Exception as error:
            print(f"Error  {error} at node {node}")
            raise error

    def dbt_load_nodes(self, nodes: list[DbtTestNode]) -> None:
        for node in nodes:
            self.dbt_load_node(node)

    def execute_dbt(self, seed: str | None = None, build: str | None = None, quiet: bool = True) -> None:
        quiet_param = "-q" if quiet else ""

        assert seed is not None or build is not None, "seed or build must be defined"

        self.executor.execute(command="deps", params=[quiet_param])
        if seed:
            seeds_res = self.executor.execute(command="seed", params=["--select", seed, quiet_param])
            self.executor.validate_execution(seeds_res)
        if build:
            build_res = self.executor.execute(command="build", params=["--select", build, quiet_param])
            self.executor.validate_execution(build_res)

    @staticmethod
    def display_df(node: DbtTestNode, df: pd.DataFrame, print_json: bool = False) -> None:
        pd.set_option("display.max_columns", None)
        pd.set_option("display.expand_frame_repr", True)
        pd.set_option("display.max_rows", None)
        pd.set_option("display.max_seq_items", None)
        pd.set_option("display.max_colwidth", 500)
        pd.set_option("expand_frame_repr", False)
        df = df.copy()  # Create a copy of the dataframe to avoid modifying the original
        for column in df.select_dtypes(include=["datetime"]):
            df[column] = df[column].astype(str)
        if print_json:
            # df.to_csv(
            #     path_or_buf=f".../print_{node.table}.csv",
            #     index=False,
            # )
            pass
        print(df)

    def dbt_validate_node(self, node: DbtTestNode) -> None:
        df = self.connector.fetch_table(schema=node.schema, table=node.table)

        expected_table = f"{node.table}_test"
        expected_model = f"{node.schema}.{expected_table}"

        fixture_columns = self.extract_node_columns(node=node)
        try:
            # Execute taking the dbt documentation as reference
            self.dbt_create_model(node=node, table_alias=expected_table, include_columns=fixture_columns)
            self.dbt_insert_model(node=node, table_alias=expected_model, include_columns=fixture_columns)
        except:  # noqa
            # Execute taking the dbt output as reference
            self.connector.clone_table(source=node.model, target=expected_model)
            self.dbt_insert_model(node=node, table_alias=expected_model)
        finally:
            expected_df = self.connector.fetch_table(schema=node.schema, table=expected_table)

            try:
                assert_frame_equal(df, expected_df, rtol=1e-5, atol=1e-8)
            except AssertionError as error:
                print(f"Error at node {node.table}")
                self.display_df(node=node, df=df, print_json=False)
                self.display_df(node=node, df=expected_df)
                raise error

    def dbt_validate_nodes(self, nodes: list[DbtTestNode]) -> None:
        for node in nodes:
            self.dbt_validate_node(node=node)

    def validate(
        self,
        nodes_to_load: list[DbtTestNode],
        nodes_to_validate: list[DbtTestNode],
        seed: str | None = None,
        build: str | list[str] | None = None,
    ) -> None:
        # STEP 1: Populate Source Tables with CSV/JSON files
        self.dbt_load_nodes(nodes=nodes_to_load)

        # STEP 2: Execute [seed|run|test] jobs & fail if execution errors
        if build and isinstance(build, list):
            build = " ".join(build)
        self.execute_dbt(seed=seed, build=str(build), quiet=False)

        # STEP 3: Validate Output Tables versus CSV files
        self.dbt_validate_nodes(nodes=nodes_to_validate)
