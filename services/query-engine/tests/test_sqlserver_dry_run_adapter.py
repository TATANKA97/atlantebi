from __future__ import annotations

import asyncio
import json
import os
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.adapters import sqlserver_dry_run_adapter as adapter
from app.adapters.sqlserver_dry_run_adapter import (
    METADATA_COMMAND,
    SqlServerDryRunAuditContext,
    SqlServerDryRunConnectionPolicy,
    SqlServerDryRunTimeoutConfig,
    run_sqlserver_metadata_dry_run,
)
from app.controlled_dry_run import (
    ControlledDryRunPreparationReport,
    DryRunMetadataRequest,
    DryRunParameterBinding,
    DryRunSummary,
)
from app.drivers.base import ConnectionMetadata, DatabaseCredentials
from app.models import Engine
from app.query_result_validator import QueryResultColumnExpectation, QueryResultContract
from tests.test_controlled_dry_run import _grouped_artifacts, _prepare, _scalar_artifacts


TENANT_ID = "11111111-1111-4111-8111-111111111111"
USER_ID = "22222222-2222-4222-8222-222222222222"
CONNECTION_ID = "33333333-3333-4333-8333-333333333333"
HASH_A = "a" * 64
HASH_B = "b" * 64
_LIVE_ENV_PREFIXES = ("ATLANTE_SQLSERVER", "ADVENTUREWORKSLT")


def test_adapter_executes_only_constant_metadata_command_and_validates_scalar(monkeypatch) -> None:
    preparation = _scalar_preparation()
    fake = _fake_pyodbc(_metadata_rows(("metric_value", 1, "decimal(38,10)", False)))
    _stub_endpoint(monkeypatch)

    report = _run_adapter(preparation, fake)

    assert report.status in {"passed", "passed_with_warnings"}
    execution = fake.connection.cursor_obj.executions[0]
    assert execution[0] == METADATA_COMMAND
    assert execution[0] != preparation.metadata_request.tsql
    assert execution[1] == (
        preparation.metadata_request.tsql,
        preparation.metadata_request.params_declaration,
        0,
    )
    assert report.normalized_metadata_rows[0].name == "metric_value"
    assert fake.connection.cursor_obj.closed is True
    assert fake.connection.closed is True


def test_parameter_declaration_argument_shape_for_empty_single_multi_in_and_between(monkeypatch) -> None:
    _stub_endpoint(monkeypatch)
    cases = [
        (_manual_preparation(params_declaration="", bindings=[]), None),
        (_manual_preparation(params_declaration="@p0 int", bindings=[_binding("@p0", 0, "int")]), "@p0 int"),
        (
            _manual_preparation(
                params_declaration="@p0 date, @p1 date",
                bindings=[_binding("@p0", 0, "date"), _binding("@p1", 1, "date")],
            ),
            "@p0 date, @p1 date",
        ),
        (
            _manual_preparation(
                params_declaration="@p0 nvarchar(4000), @p1 nvarchar(4000), @p2 nvarchar(4000)",
                bindings=[
                    _binding("@p0", 0, "nvarchar(4000)", source="filter", operator="in"),
                    _binding("@p1", 1, "nvarchar(4000)", source="filter", operator="in"),
                    _binding("@p2", 2, "nvarchar(4000)", source="filter", operator="in"),
                ],
            ),
            "@p0 nvarchar(4000), @p1 nvarchar(4000), @p2 nvarchar(4000)",
        ),
        (
            _manual_preparation(
                params_declaration="@p0 decimal(38,10), @p1 decimal(38,10)",
                bindings=[
                    _binding("@p0", 0, "decimal(38,10)", source="filter", operator="between"),
                    _binding("@p1", 1, "decimal(38,10)", source="filter", operator="between"),
                ],
            ),
            "@p0 decimal(38,10), @p1 decimal(38,10)",
        ),
    ]

    for preparation, expected_params in cases:
        fake = _fake_pyodbc(_metadata_rows(("metric_value", 1, "int", False)))
        report = _run_adapter(preparation, fake)
        assert report.status in {"passed", "passed_with_warnings"}
        assert fake.connection.cursor_obj.executions[0][1][1] == expected_params

    unexpected = _manual_preparation(params_declaration="@p0 int", bindings=[])
    blocked = _run_adapter(unexpected, _fake_pyodbc([]))
    assert blocked.status == "blocked"
    assert _adapter_codes(blocked) == ["PARAMETER_DECLARATION_UNEXPECTED"]


def test_parameter_declaration_type_matrix_and_unsupported_types(monkeypatch) -> None:
    _stub_endpoint(monkeypatch)
    supported_declaration = (
        "@p0 int, @p1 bigint, @p2 decimal(38,10), @p3 date, @p4 datetime, "
        "@p5 datetime2, @p6 bit, @p7 nvarchar(4000), @p8 varchar(50), @p9 uniqueidentifier"
    )
    supported = _manual_preparation(
        params_declaration=supported_declaration,
        bindings=[
            _binding("@p0", 0, "int"),
            _binding("@p1", 1, "bigint"),
            _binding("@p2", 2, "decimal(38,10)"),
            _binding("@p3", 3, "date"),
            _binding("@p4", 4, "datetime"),
            _binding("@p5", 5, "datetime2"),
            _binding("@p6", 6, "bit"),
            _binding("@p7", 7, "nvarchar(4000)"),
            _binding("@p8", 8, "varchar(50)"),
            _binding("@p9", 9, "uniqueidentifier", value_fingerprint="nullable-fingerprint"),
        ],
    )
    fake = _fake_pyodbc(_metadata_rows(("metric_value", 1, "int", False)))

    report = _run_adapter(supported, fake)

    assert report.status in {"passed", "passed_with_warnings"}
    assert fake.connection.cursor_obj.executions[0][1][1] == supported_declaration

    unsupported = _manual_preparation(
        params_declaration="@p0 xml",
        bindings=[_binding("@p0", 0, "xml")],
    )
    blocked = _run_adapter(unsupported, _fake_pyodbc([]))
    assert blocked.status == "blocked"
    assert "PARAMETER_DECLARATION_TYPE_UNSUPPORTED" in _adapter_codes(blocked)


def test_grouped_view_and_case_sensitive_metadata_contract(monkeypatch) -> None:
    graph, layer, intent, schema_snapshot, preflight, compiled, validation = _grouped_artifacts()
    preparation = _prepare(intent, preflight, compiled, validation, layer, graph, schema_snapshot)
    _stub_endpoint(monkeypatch)

    valid = _run_adapter(
        preparation,
        _fake_pyodbc(
            _metadata_rows(
                ("dimension_0", 1, "nvarchar(100)", True, "erp", "v BI Output", "Diménsion ] Name"),
                ("metric_value", 2, "money", False, "erp", "v BI Output", "Amount"),
            )
        ),
    )

    assert valid.status in {"passed", "passed_with_warnings"}
    assert valid.normalized_metadata_rows[0].source_table == "v BI Output"
    assert valid.normalized_metadata_rows[0].source_column == "Diménsion ] Name"

    case_mismatch = _run_adapter(
        preparation,
        _fake_pyodbc(_metadata_rows(("Dimension_0", 1, "nvarchar(100)", True), ("metric_value", 2, "money", False))),
    )

    assert case_mismatch.status == "blocked"
    assert case_mismatch.validation_report is not None
    assert "METADATA_SHAPE_MISMATCH" in case_mismatch.validation_report.blocking_codes


def test_descriptor_and_connection_policy_blocks_before_db_io(monkeypatch) -> None:
    preparation = _scalar_preparation()
    _stub_endpoint(monkeypatch)

    unsupported_method = replace(
        preparation,
        metadata_request=replace(preparation.metadata_request, sqlserver_validation_method="showplan_xml"),
    )
    blocked_method = _run_adapter(unsupported_method, _fake_pyodbc([]))
    assert blocked_method.status == "blocked"
    assert "SQLSERVER_VALIDATION_METHOD_UNSUPPORTED" in _adapter_codes(blocked_method)

    unsupported_browse = replace(
        preparation,
        metadata_request=replace(preparation.metadata_request, browse_information_mode=1),
    )
    blocked_browse = _run_adapter(unsupported_browse, _fake_pyodbc([]))
    assert blocked_browse.status == "blocked"
    assert "BROWSE_INFORMATION_MODE_UNSUPPORTED" in _adapter_codes(blocked_browse)

    missing_db = _run_adapter(preparation, _fake_pyodbc([]), connection=_connection(database_name=""))
    assert missing_db.status == "blocked"
    assert "DATABASE_NAME_REQUIRED" in _adapter_codes(missing_db)

    tls_disabled = _run_adapter(preparation, _fake_pyodbc([]), connection=_connection(tls_required=False))
    assert tls_disabled.status == "blocked"
    assert "TLS_REQUIRED" in _adapter_codes(tls_disabled)

    unapproved_trust = _run_adapter(preparation, _fake_pyodbc([]), connection=_connection(trust_server_certificate=True))
    assert unapproved_trust.status == "blocked"
    assert "TRUST_SERVER_CERTIFICATE_NOT_ALLOWED" in _adapter_codes(unapproved_trust)


def test_connection_policy_is_forwarded_and_report_is_secret_safe(monkeypatch) -> None:
    preparation = _manual_preparation(
        params_declaration="@p0 nvarchar(4000)",
        bindings=[_binding("@p0", 0, "nvarchar(4000)", source="filter", operator="eq", value_fingerprint="fingerprint-only")],
    )
    fake = _fake_pyodbc(_metadata_rows(("metric_value", 1, "int", False)))
    _stub_endpoint(monkeypatch)

    report = _run_adapter(
        preparation,
        fake,
        connection=_connection(trust_server_certificate=True),
        credentials=DatabaseCredentials(password="SuperSecretPassword"),
        policy=SqlServerDryRunConnectionPolicy(allow_trust_server_certificate=True),
    )

    assert report.status in {"passed", "passed_with_warnings"}
    assert "Encrypt=yes" in fake.connection_string
    assert "TrustServerCertificate=yes" in fake.connection_string
    assert "Database={AnalyticsDb}" in fake.connection_string
    assert "UseFMTONLY=No" in fake.connection_string
    assert fake.connection_timeout == 15
    payload = json.dumps(report.to_debug_dict(), sort_keys=True)
    assert "SuperSecretPassword" not in payload
    assert "raw-value" not in payload
    assert "fingerprint-only" in payload


def test_cleanup_happens_on_error_timeout_driver_exception_and_validation_failure(monkeypatch) -> None:
    preparation = _scalar_preparation()
    _stub_endpoint(monkeypatch)

    metadata_error_fake = _fake_pyodbc([], execute_error=_fake_error("42000", 11529, "The metadata could not be determined."))
    metadata_error = _run_adapter(preparation, metadata_error_fake)
    assert metadata_error.status == "engine_error"
    assert metadata_error.decision_category == "sqlserver_metadata_error"
    assert metadata_error_fake.connection.cursor_obj.closed is True
    assert metadata_error_fake.connection.closed is True

    timeout_fake = _fake_pyodbc([], execute_error=TimeoutError("deadline"))
    timeout = _run_adapter(preparation, timeout_fake)
    assert timeout.status == "engine_error"
    assert timeout.decision_category == "timeout"
    assert timeout_fake.connection.cursor_obj.closed is True
    assert timeout_fake.connection.closed is True

    unexpected_fake = _fake_pyodbc([], execute_error=RuntimeError("boom"))
    unexpected = _run_adapter(preparation, unexpected_fake)
    assert unexpected.status == "engine_error"
    assert unexpected.decision_category == "driver_error"
    assert unexpected_fake.connection.cursor_obj.closed is True
    assert unexpected_fake.connection.closed is True

    validation_failure_fake = _fake_pyodbc(_metadata_rows(("wrong_metric", 1, "int", False)))
    validation_failure = _run_adapter(preparation, validation_failure_fake)
    assert validation_failure.status == "blocked"
    assert validation_failure.decision_category == "metadata_shape_mismatch"
    assert validation_failure_fake.connection.cursor_obj.closed is True
    assert validation_failure_fake.connection.closed is True


def test_sqlserver_error_mapping_prefers_structured_codes(monkeypatch) -> None:
    preparation = _scalar_preparation()
    _stub_endpoint(monkeypatch)
    cases = [
        (_fake_error("28000", 18456, "Login failed for user."), "authentication_error"),
        (_fake_error("08001", 0, "certificate verify failed"), "tls_error"),
        (_fake_error("42000", 229, "The SELECT permission was denied."), "permission_error"),
        (_fake_error("42S02", 208, "Invalid object name."), "object_not_found"),
        (_fake_error("42S22", 207, "Invalid column name."), "column_not_found"),
        (_fake_error("42000", 102, "Incorrect syntax near."), "syntax_error"),
        (_fake_error("42000", 11508, "The parameter declaration is invalid."), "parameter_binding_error"),
        (_fake_error("HY008", 0, "Operation cancelled."), "cancelled"),
        (_fake_error("HYT00", 0, "Timeout expired."), "timeout"),
        (_fake_error("08006", 0, "Connection failed."), "connection_error"),
    ]

    for error, expected_category in cases:
        report = _run_adapter(preparation, _fake_pyodbc([], execute_error=error))
        assert report.status == "engine_error"
        assert report.decision_category == expected_category


def test_driver_connection_failure_maps_to_connection_error(monkeypatch) -> None:
    preparation = _scalar_preparation()
    _stub_endpoint(monkeypatch)

    report = _run_adapter(
        preparation,
        _fake_pyodbc([], connect_error=RuntimeError("Database destination could not be resolved.")),
    )

    assert report.status == "engine_error"
    assert report.decision_category == "connection_error"


def test_malformed_metadata_is_delegated_to_core_validator(monkeypatch) -> None:
    preparation = _scalar_preparation()
    _stub_endpoint(monkeypatch)

    report = _run_adapter(preparation, _fake_pyodbc(_metadata_rows(("metric_value", 1, "varbinary(max)", False))))

    assert report.status == "blocked"
    assert report.validation_report is not None
    assert report.validation_report.decision_category == "metadata_shape_mismatch"
    assert "METADATA_SHAPE_MISMATCH" in report.validation_report.blocking_codes


def test_optional_live_adventureworks_scalar_date_range_metadata() -> None:
    if not _live_integration_enabled():
        pytest.skip("Live SQL Server dry-run integration fixture is not enabled.")
    preparation = _manual_preparation(
        tsql=(
            "SELECT SUM([SubTotal]) AS [metric_value] "
            "FROM [SalesLT].[SalesOrderHeader] "
            "WHERE [OrderDate] >= @p0 AND [OrderDate] < @p1"
        ),
        params_declaration="@p0 date, @p1 date",
        bindings=[
            _binding("@p0", 0, "date", logical_type="date", source="date_range", operator="gte"),
            _binding("@p1", 1, "date", logical_type="date", source="date_range", operator="lt"),
        ],
        metric_value_type="currency",
    )

    report = _run_live_adapter(preparation)

    assert report.status in {"passed", "passed_with_warnings"}
    assert report.normalized_metadata_rows[0].name == "metric_value"


def test_optional_live_adventureworks_grouped_join_metadata() -> None:
    if not _live_integration_enabled():
        pytest.skip("Live SQL Server dry-run integration fixture is not enabled.")
    preparation = _manual_preparation(
        tsql=(
            "SELECT TOP (@p0) [c].[Name] AS [dimension_0], SUM([d].[LineTotal]) AS [metric_value] "
            "FROM [SalesLT].[SalesOrderDetail] AS [d] "
            "INNER JOIN [SalesLT].[Product] AS [p] ON [d].[ProductID] = [p].[ProductID] "
            "INNER JOIN [SalesLT].[ProductCategory] AS [c] ON [p].[ProductCategoryID] = [c].[ProductCategoryID] "
            "GROUP BY [c].[Name] "
            "ORDER BY [metric_value] DESC, [dimension_0] ASC"
        ),
        params_declaration="@p0 int",
        bindings=[_binding("@p0", 0, "int", logical_type="integer", source="limit", operator="top")],
        shape="grouped",
        metric_value_type="currency",
    )

    report = _run_live_adapter(preparation)

    assert report.status in {"passed", "passed_with_warnings"}
    assert [row.name for row in report.normalized_metadata_rows] == ["dimension_0", "metric_value"]


def test_optional_live_adventureworks_view_source_metadata() -> None:
    if not _live_integration_enabled():
        pytest.skip("Live SQL Server dry-run integration fixture is not enabled.")
    preparation = _manual_preparation(
        tsql=(
            "SELECT [ProductCategoryName] AS [dimension_0], COUNT_BIG(*) AS [metric_value] "
            "FROM [SalesLT].[vGetAllCategories] "
            "GROUP BY [ProductCategoryName]"
        ),
        params_declaration="",
        bindings=[],
        shape="grouped",
    )

    report = _run_live_adapter(preparation)

    assert report.status in {"passed", "passed_with_warnings"}
    assert [row.name for row in report.normalized_metadata_rows] == ["dimension_0", "metric_value"]


def _run_adapter(
    preparation: ControlledDryRunPreparationReport,
    fake_pyodbc,
    *,
    connection: ConnectionMetadata | None = None,
    credentials: DatabaseCredentials | None = None,
    policy: SqlServerDryRunConnectionPolicy | None = None,
):
    return asyncio.run(
        run_sqlserver_metadata_dry_run(
            preparation,
            connection or _connection(),
            credentials or DatabaseCredentials(password="FixtureOnlyPassword"),
            audit_context=_audit_context(),
            timeout_config=SqlServerDryRunTimeoutConfig(connection_timeout_ms=15_000, metadata_timeout_ms=30_000),
            connection_policy=policy or SqlServerDryRunConnectionPolicy(),
            pyodbc_module=fake_pyodbc,
        )
    )


def _run_live_adapter(preparation: ControlledDryRunPreparationReport):
    connection = _live_connection()
    credentials = DatabaseCredentials(password=_live_required("PASSWORD"))
    policy = SqlServerDryRunConnectionPolicy(
        require_tls=_live_bool("REQUIRE_TLS", _live_bool("TLS_REQUIRED", True)),
        allow_trust_server_certificate=_live_bool("ALLOW_TRUST_SERVER_CERTIFICATE", _live_bool("TRUST_SERVER_CERTIFICATE", False)),
    )
    return asyncio.run(
        run_sqlserver_metadata_dry_run(
            preparation,
            connection,
            credentials,
            audit_context=_audit_context(),
            timeout_config=SqlServerDryRunTimeoutConfig(
                connection_timeout_ms=_live_int("CONNECTION_TIMEOUT_MS", 15_000),
                metadata_timeout_ms=_live_int("METADATA_TIMEOUT_MS", 30_000),
            ),
            connection_policy=policy,
        )
    )


def _live_integration_enabled() -> bool:
    if os.getenv("ATLANTE_SQLSERVER_DRY_RUN_INTEGRATION") != "1" and os.getenv("ADVENTUREWORKSLT_DRY_RUN_INTEGRATION") != "1":
        return False
    return _live_prefix() is not None


def _live_prefix() -> str | None:
    for prefix in _LIVE_ENV_PREFIXES:
        if all(os.getenv(f"{prefix}_{key}") for key in ("HOST", "USERNAME", "PASSWORD")):
            if os.getenv(f"{prefix}_DATABASE") or prefix == "ADVENTUREWORKSLT":
                return prefix
    return None


def _live_required(key: str) -> str:
    prefix = _live_prefix()
    if prefix is None:
        raise RuntimeError("Live SQL Server integration environment is not configured.")
    if key == "DATABASE" and prefix == "ADVENTUREWORKSLT":
        return os.getenv(f"{prefix}_DATABASE") or "AdventureWorksLT"
    value = os.getenv(f"{prefix}_{key}")
    if value is None or value == "":
        raise RuntimeError(f"Live SQL Server integration is missing {prefix}_{key}.")
    return value


def _live_optional(key: str, default: str | None = None) -> str | None:
    prefix = _live_prefix()
    if prefix is None:
        return default
    return os.getenv(f"{prefix}_{key}") or default


def _live_bool(key: str, default: bool) -> bool:
    value = _live_optional(key)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def _live_int(key: str, default: int) -> int:
    value = _live_optional(key)
    if value is None:
        return default
    return int(value)


def _live_connection() -> ConnectionMetadata:
    return ConnectionMetadata(
        tenant_id=TENANT_ID,
        connection_id=CONNECTION_ID,
        name="SQL Server dry-run live integration",
        engine=Engine.sqlserver,
        network_mode=_live_optional("NETWORK_MODE", "public_allowlist") or "public_allowlist",
        host=_live_required("HOST"),
        port=_live_int("PORT", 1433),
        database_name=_live_required("DATABASE"),
        username=_live_required("USERNAME"),
        secret_ref="integration-env",
        tls_required=_live_bool("TLS_REQUIRED", _live_bool("TLS", True)),
        trust_server_certificate=_live_bool("TRUST_SERVER_CERTIFICATE", False),
        tls_server_name=_live_optional("TLS_SERVER_NAME"),
    )


def _scalar_preparation():
    graph, layer, intent, schema_snapshot, preflight, compiled, validation = _scalar_artifacts()
    return _prepare(intent, preflight, compiled, validation, layer, graph, schema_snapshot)


def _manual_preparation(
    *,
    params_declaration: str,
    bindings: list[DryRunParameterBinding],
    shape: str = "scalar",
    tsql: str = "SELECT COUNT_BIG(*) AS [metric_value]",
    metric_value_type: str = "count",
) -> ControlledDryRunPreparationReport:
    columns = [QueryResultColumnExpectation(alias="metric_value", value_type=metric_value_type, nullable=False)]
    if shape == "grouped":
        columns = [
            QueryResultColumnExpectation(alias="dimension_0", value_type="text", nullable=True),
            QueryResultColumnExpectation(alias="metric_value", value_type=metric_value_type, nullable=False),
        ]
    request = DryRunMetadataRequest(
        sqlserver_validation_method="sp_describe_first_result_set",
        statement_template=METADATA_COMMAND,
        tsql=tsql,
        params_declaration=params_declaration,
        browse_information_mode=0,
        compiled_sql_hash=HASH_A,
        validator_report_hash=HASH_B,
        parameter_bindings=bindings,
    )
    return ControlledDryRunPreparationReport(
        status="ready",
        decision_category="safe",
        errors=[],
        warnings=[],
        infos=[],
        blocking_codes=[],
        summary=DryRunSummary(
            stage_count=0,
            passed_stage_count=0,
            warning_stage_count=0,
            blocked_stage_count=0,
            error_count=0,
            warning_count=0,
            info_count=0,
        ),
        stage_results=[],
        metadata_request=request,
        result_contract=QueryResultContract(shape=shape, columns=columns, disclosures=[]),
        compiled_sql_hash=HASH_A,
        validator_report_hash=HASH_B,
    )


def _binding(
    name: str,
    ordinal: int,
    sql_type: str,
    *,
    logical_type: str = "string",
    source: str = "filter",
    operator: str = "eq",
    value_fingerprint: str = "value-fingerprint",
) -> DryRunParameterBinding:
    return DryRunParameterBinding(
        name=name,
        ordinal=ordinal,
        sql_type=sql_type,
        logical_type=logical_type,
        source=source,
        operator=operator,
        context="test",
        value_fingerprint=value_fingerprint,
        nullable=False,
    )


def _connection(
    *,
    tls_required: bool = True,
    trust_server_certificate: bool = False,
    database_name: str = "AnalyticsDb",
) -> ConnectionMetadata:
    return ConnectionMetadata(
        tenant_id=TENANT_ID,
        connection_id=CONNECTION_ID,
        name="SQL Server dry-run",
        engine=Engine.sqlserver,
        network_mode="public",
        host="sql.example.com",
        port=1433,
        database_name=database_name,
        username="dryrun_reader",
        secret_ref="gcp-secret-manager://projects/demo/secrets/sqlserver",
        tls_required=tls_required,
        trust_server_certificate=trust_server_certificate,
        tls_server_name="sql.example.com",
    )


def _audit_context() -> SqlServerDryRunAuditContext:
    return SqlServerDryRunAuditContext(
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        connection_id=CONNECTION_ID,
        correlation_id="correlation-1",
    )


def _stub_endpoint(monkeypatch) -> None:
    async def fake_resolve_database_endpoint(connection, timeout_ms):
        return SimpleNamespace(address="203.0.113.10", certificate_name=connection.tls_server_name)

    monkeypatch.setattr(adapter, "resolve_database_endpoint", fake_resolve_database_endpoint)


def _metadata_rows(*rows):
    return [
        {
            "column_ordinal": ordinal,
            "name": name,
            "is_nullable": nullable,
            "system_type_id": 56,
            "system_type_name": sql_type,
            "max_length": 8,
            "precision": 18,
            "scale": 2,
            "collation_name": "Latin1_General_CS_AS",
            "is_case_sensitive": True,
            "source_schema": source_schema,
            "source_table": source_table,
            "source_column": source_column,
        }
        for name, ordinal, sql_type, nullable, *source in rows
        for source_schema, source_table, source_column in [_source_parts(source)]
    ]


def _source_parts(source):
    if not source:
        return (None, None, None)
    return (source + [None, None, None])[:3]


def _fake_pyodbc(rows, *, execute_error: Exception | None = None, connect_error: Exception | None = None):
    connection = FakeConnection(rows=rows, execute_error=execute_error)

    class FakePyodbc:
        Error = FakePyodbcError

        def __init__(self):
            self.connection = connection
            self.connection_string = None
            self.connection_timeout = None

        def connect(self, connection_string: str, autocommit: bool, timeout: int):
            self.connection_string = connection_string
            self.connection_timeout = timeout
            assert autocommit is True
            if connect_error is not None:
                raise connect_error
            return connection

    return FakePyodbc()


class FakePyodbcError(Exception):
    pass


class FakeConnection:
    def __init__(self, *, rows, execute_error: Exception | None):
        self.cursor_obj = FakeCursor(rows=rows, execute_error=execute_error)
        self.closed = False
        self.timeout = None

    def cursor(self):
        return self.cursor_obj

    def close(self) -> None:
        self.closed = True


class FakeCursor:
    def __init__(self, *, rows, execute_error: Exception | None):
        self.rows = rows
        self.execute_error = execute_error
        self.executions = []
        self.closed = False
        self.timeout = None
        self.description = [
            ("column_ordinal",),
            ("name",),
            ("is_nullable",),
            ("system_type_id",),
            ("system_type_name",),
            ("max_length",),
            ("precision",),
            ("scale",),
            ("collation_name",),
            ("is_case_sensitive",),
            ("source_schema",),
            ("source_table",),
            ("source_column",),
        ]

    def execute(self, command: str, *params):
        self.executions.append((command, params))
        if self.execute_error is not None:
            raise self.execute_error

    def fetchall(self):
        return [
            (
                row["column_ordinal"],
                row["name"],
                row["is_nullable"],
                row["system_type_id"],
                row["system_type_name"],
                row["max_length"],
                row["precision"],
                row["scale"],
                row["collation_name"],
                row["is_case_sensitive"],
                row["source_schema"],
                row["source_table"],
                row["source_column"],
            )
            for row in self.rows
        ]

    def close(self) -> None:
        self.closed = True


def _fake_error(sqlstate: str, number: int, message: str) -> FakePyodbcError:
    return FakePyodbcError(sqlstate, f"[SQL Server] {message} ({number})")


def _adapter_codes(report) -> list[str]:
    return [issue.code for issue in report.errors]
