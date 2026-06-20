import os
import tempfile
from typing import Iterable

import duckdb
import pytest
from duckdb import DuckDBPyConnection
from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict
from ruamel.yaml import YAML

from pytest_dbt_duckdb import profiler
from pytest_dbt_duckdb.connector import DuckConnector, ExtraFunctions
from pytest_dbt_duckdb.dbt_executor import DbtExecutor
from pytest_dbt_duckdb.dbt_validator import DbtTestNode, DbtValidator

PROFILE_PROPERTY = "dbt_duckdb_profile"


class TestFixture(BaseModel):
    id: str
    given: list[DbtTestNode]
    build: str | list[str] | None = None
    seed: str | None = None
    then: list[DbtTestNode]
    extra_args: list[str] | None = None


class PyDuckSettings(BaseSettings):
    temp_dir: str
    database_name: str = "dbt_duck"
    debug_output: bool = False
    dbt_artifacts_dir: str | None = None
    model_config = SettingsConfigDict(env_prefix="dbt_")

    @property
    def _root(self) -> str:
        # When dbt_artifacts_dir is set (per-worker stable path), all artifacts including
        # the DuckDB file live there — that's what keeps DBT_DUCKDB_PATH stable across tests
        # and lets dbt's partial_parse cache survive between tests.
        return self.dbt_artifacts_dir or self.temp_dir

    @property
    def db_file_path(self) -> str:
        return os.path.join(self._root, self.database_file)

    @property
    def database_file(self) -> str:
        return f"{self.database_name}.duckdb"

    @property
    def target_path(self) -> str:
        return os.path.join(self._root, "dbt_target")

    @property
    def log_path(self) -> str:
        return os.path.join(self._root, "dbt_logs")


class DuckFixture(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    conn: DuckDBPyConnection
    settings: PyDuckSettings

    def execute_dbt(
        self,
        dbt_project_dir: str,
        resources_folder: str,
        nodes_to_load: list[DbtTestNode],
        nodes_to_validate: list[DbtTestNode],
        seed: str | None = None,
        build: str | list[str] | None = None,
        extra_functions: ExtraFunctions | None = None,
        extra_vars: dict | None = None,
        extra_args: list[str] | None = None,
    ) -> None:
        connector = DuckConnector(conn=self.conn, extra_functions=extra_functions)
        os.environ["DBT_DUCKDB_PATH"] = self.settings.db_file_path
        os.environ["DBT_DUCKDB_DATABASE"] = self.settings.database_name

        executor = DbtExecutor(
            dbt_project_dir=dbt_project_dir,
            profiles_dir=resources_folder,
            extra_vars=extra_vars,
            target_path=self.settings.target_path,
            log_path=self.settings.log_path,
        )
        validator = DbtValidator(
            connector=connector,
            executor=executor,
            resources_folder=resources_folder,
            debug_output=self.settings.debug_output,
        )
        validator.validate(
            nodes_to_load=nodes_to_load,
            nodes_to_validate=nodes_to_validate,
            seed=seed,
            build=build,
            extra_args=extra_args,
        )


def load_yaml_test(file_path: str, yaml: YAML = YAML(typ="safe", pure=True)) -> Iterable[TestFixture]:
    with open(file_path, "r") as file:
        tests: list[dict] = yaml.load(file)["tests"]
        for test_fixture in tests:
            yield TestFixture(**test_fixture)


def load_yaml_tests(directory: str) -> Iterable[TestFixture]:
    yaml = YAML(typ="safe", pure=True)
    for filename in os.listdir(directory):
        if filename.startswith("test") & (filename.endswith(".yaml") or filename.endswith(".yml")):
            file_path = os.path.join(directory, filename)
            yield from load_yaml_test(file_path=file_path, yaml=yaml)


SYSTEM_SCHEMAS = frozenset({"main", "information_schema", "pg_catalog", "system", "temp"})


def reset_user_schemas(conn: DuckDBPyConnection) -> None:
    """Drop every non-system schema in the connected DuckDB. Used between tests to
    clear all dbt-created data while keeping the file (and its registered UDFs) intact —
    that's what lets us hold DBT_DUCKDB_PATH stable per worker."""
    user_schemas = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT schema_name FROM information_schema.schemata WHERE schema_name NOT IN "
            f"({', '.join(['?'] * len(SYSTEM_SCHEMAS))})",
            list(SYSTEM_SCHEMAS),
        ).fetchall()
    ]
    for schema in user_schemas:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def worker_artifacts_prefix() -> str:
    """Prefix for the per-xdist-worker dbt artifacts tempdir."""
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    return f"pytest-dbt-duckdb-{worker}-"


@pytest.fixture(scope="session")
def _dbt_artifacts_dir() -> Iterable[str]:
    """Per-worker dir holding the DuckDB file and dbt's target/log dirs across the whole
    pytest session. This is what makes DBT_DUCKDB_PATH stable across tests, which keeps
    dbt's partial_parse cache valid and lets the in-memory manifest cache hit."""
    with tempfile.TemporaryDirectory(prefix=worker_artifacts_prefix()) as artifacts_dir:
        yield artifacts_dir


@pytest.fixture(scope="function")
def duckdb_fixture(_dbt_artifacts_dir: str) -> Iterable[DuckFixture]:
    """Per-test fixture. The DuckDB FILE PATH is stable across tests in this worker
    (see _dbt_artifacts_dir); per-test isolation comes from dropping all user schemas
    between tests rather than recreating the file. Reusing the file keeps registered
    UDFs alive (DuckDB's process-wide DB cache), which combined with idempotent UDF
    registration in DuckConnector makes this safe."""
    settings = PyDuckSettings(temp_dir=_dbt_artifacts_dir, dbt_artifacts_dir=_dbt_artifacts_dir)
    conn = duckdb.connect(settings.db_file_path)
    try:
        # Reset on entry as well as exit: a previous test may have crashed mid-flight
        # and left state behind. Belt and braces — both are cheap (a single SELECT plus
        # one DROP per leftover schema).
        reset_user_schemas(conn)
        yield DuckFixture(conn=conn, settings=settings)
    finally:
        try:
            reset_user_schemas(conn)
        finally:
            conn.close()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--duckdb-profile",
        action="store_true",
        default=False,
        help="Print a per-stage timing breakdown for each pytest-dbt-duckdb test at session end.",
    )


def pytest_configure(config: pytest.Config) -> None:
    if config.getoption("--duckdb-profile"):
        profiler.enable()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item: pytest.Item):  # type: ignore[no-untyped-def]
    if profiler.is_active():
        profiler.reset()
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):  # type: ignore[no-untyped-def]
    outcome = yield
    if not profiler.is_active():
        return
    report = outcome.get_result()
    if report.when != "call":
        return
    stages = profiler.snapshot()
    if not stages:
        return
    payload = {
        "stages": stages,
        "counts": profiler.snapshot_counts(),
        "worker": os.environ.get("PYTEST_XDIST_WORKER", "main"),
    }
    report.user_properties.append((PROFILE_PROPERTY, payload))


def _collect_profile_rows(terminalreporter: "pytest.TerminalReporter") -> list[dict]:
    rows: list[dict] = []
    for outcome in ("passed", "failed"):
        for report in terminalreporter.stats.get(outcome, []):
            for name, payload in getattr(report, "user_properties", []) or []:
                if name != PROFILE_PROPERTY:
                    continue
                rows.append(
                    {
                        "nodeid": report.nodeid,
                        "outcome": outcome,
                        **payload,
                    }
                )
    return rows


def _format_table(title: str, headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    widths = [max(len(headers[i]), *(len(r[i]) for r in rows)) for i in range(len(headers))]
    sep = "  "
    head = sep.join(h.ljust(widths[i]) for i, h in enumerate(headers))
    bar = sep.join("-" * widths[i] for i in range(len(headers)))
    body = "\n".join(sep.join(r[i].ljust(widths[i]) for i in range(len(headers))) for r in rows)
    return f"\n{title}\n{head}\n{bar}\n{body}\n"


def primary_stage_order() -> list[str]:
    """Stages reflecting per-test wall time, in chronological order.
    parse_project runs in DbtValidator.__init__ (before validate()), so it sits between
    load_given and dbt_seed in the timeline."""
    return [
        "load_given",
        "parse_project:hit",
        "parse_project:miss",
        "dbt_seed",
        "dbt_build",
        "validate_then",
    ]


def compute_total(stages: dict[str, float]) -> float:
    """Sum of primary stages only — excludes dbt_invoke:* sub-stages, which are
    counted inside dbt_seed / dbt_build / parse_project:miss and would double-count."""
    return sum(stages.get(s, 0.0) for s in primary_stage_order())


def pytest_terminal_summary(terminalreporter: "pytest.TerminalReporter") -> None:
    if not terminalreporter.config.getoption("--duckdb-profile"):
        return
    rows = _collect_profile_rows(terminalreporter)
    if not rows:
        return

    primary = primary_stage_order()
    extra_stages: set[str] = set()
    for row in rows:
        extra_stages.update(row["stages"].keys())
    stage_cols = primary + sorted(extra_stages - set(primary))

    by_worker: dict[str, list[dict]] = {}
    for row in rows:
        by_worker.setdefault(row["worker"], []).append(row)

    out: list[str] = ["", "=== pytest-dbt-duckdb profile ==="]

    for worker in sorted(by_worker):
        worker_rows = by_worker[worker]
        headers = ["test"] + stage_cols + ["total"]
        table_rows: list[list[str]] = []
        for r in worker_rows:
            stages = r["stages"]
            cells = [r["nodeid"].split("::")[-1]]
            cells += [f"{stages[s]:.2f}s" if s in stages else "-" for s in stage_cols]
            cells.append(f"{compute_total(stages):.2f}s")
            table_rows.append(cells)
        out.append(_format_table(f"Worker: {worker} ({len(worker_rows)} tests)", headers, table_rows))

    if len(by_worker) > 1 or len(rows) > 1:
        agg: dict[str, list[float]] = {}
        for r in rows:
            for stage, t in r["stages"].items():
                agg.setdefault(stage, []).append(t)
        agg_headers = ["stage", "n", "sum", "mean", "max"]
        agg_rows: list[list[str]] = []
        for stage in stage_cols:
            if stage not in agg:
                continue
            ts = agg[stage]
            agg_rows.append(
                [
                    stage,
                    str(len(ts)),
                    f"{sum(ts):.2f}s",
                    f"{sum(ts) / len(ts):.2f}s",
                    f"{max(ts):.2f}s",
                ]
            )
        out.append(_format_table("Aggregated across all workers", agg_headers, agg_rows))

    terminalreporter.write_sep("=", "duckdb profile")
    terminalreporter.write_line("\n".join(out))
