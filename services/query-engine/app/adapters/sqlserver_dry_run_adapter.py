from __future__ import annotations

import asyncio
import re
from dataclasses import asdict, dataclass
from time import monotonic
from typing import Any, Literal

from app.controlled_dry_run import (
    ControlledDryRunPreparationReport,
    ControlledDryRunReport,
    DryRunDecisionCategory,
    SqlServerMetadataColumn,
    validate_controlled_dry_run_metadata,
)
from app.drivers.base import ConnectionMetadata, DatabaseCredentials
from app.drivers.sqlserver import _connect_sync, _connection_string_parts
from app.network import resolve_database_endpoint


METADATA_COMMAND = "EXEC sys.sp_describe_first_result_set @tsql = ?, @params = ?, @browse_information_mode = ?"
_SUPPORTED_PARAMETER_DECLARATION_RE = re.compile(
    r"^(?:int|bigint|decimal\(38,10\)|date|datetime|datetime2|bit|nvarchar\(4000\)|varchar\([1-9][0-9]{0,3}\)|uniqueidentifier)$",
    re.IGNORECASE,
)


AdapterStatus = Literal["passed", "passed_with_warnings", "blocked", "engine_error"]
AdapterSeverity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class SqlServerDryRunTimeoutConfig:
    connection_timeout_ms: int = 15_000
    metadata_timeout_ms: int = 30_000


@dataclass(frozen=True)
class SqlServerDryRunConnectionPolicy:
    require_tls: bool = True
    allow_trust_server_certificate: bool = False


@dataclass(frozen=True)
class SqlServerDryRunAuditContext:
    tenant_id: str
    user_id: str
    connection_id: str
    correlation_id: str | None = None


@dataclass(frozen=True)
class SqlServerDryRunAdapterIssue:
    stage: str
    code: str
    severity: AdapterSeverity
    message: str
    decision_category: DryRunDecisionCategory
    safe_detail: str = ""
    suggested_action: str = ""


@dataclass(frozen=True)
class SqlServerDryRunAdapterSummary:
    status: AdapterStatus
    error_count: int
    warning_count: int
    metadata_column_count: int
    duration_ms: int


@dataclass(frozen=True)
class SqlServerDryRunNormalizedColumn:
    ordinal: int
    name: str | None
    nullable: bool | None
    sql_type: str
    system_type_id: int | None = None
    precision: int | None = None
    scale: int | None = None
    max_length: int | None = None
    collation_name: str | None = None
    is_case_sensitive: bool | None = None
    source_schema: str | None = None
    source_table: str | None = None
    source_column: str | None = None


@dataclass(frozen=True)
class SqlServerDryRunAdapterReport:
    status: AdapterStatus
    decision_category: DryRunDecisionCategory
    metadata_method: str
    browse_information_mode: int | None
    normalized_metadata_rows: list[SqlServerDryRunNormalizedColumn]
    validation_report: ControlledDryRunReport | None
    errors: list[SqlServerDryRunAdapterIssue]
    warnings: list[SqlServerDryRunAdapterIssue]
    infos: list[SqlServerDryRunAdapterIssue]
    summary: SqlServerDryRunAdapterSummary
    duration_ms: int
    tenant_id: str
    user_id: str
    connection_id: str
    correlation_id: str | None
    compiled_sql_hash: str | None
    validator_report_hash: str | None
    dry_run_report_hash: str | None
    executed_command: str | None

    def to_debug_dict(self) -> dict[str, object]:
        return asdict(self)


async def run_sqlserver_metadata_dry_run(
    preparation_report: ControlledDryRunPreparationReport,
    connection: ConnectionMetadata,
    credentials: DatabaseCredentials,
    *,
    audit_context: SqlServerDryRunAuditContext,
    timeout_config: SqlServerDryRunTimeoutConfig | None = None,
    connection_policy: SqlServerDryRunConnectionPolicy | None = None,
    pyodbc_module: Any | None = None,
) -> SqlServerDryRunAdapterReport:
    started = monotonic()
    timeouts = timeout_config or SqlServerDryRunTimeoutConfig()
    policy = connection_policy or SqlServerDryRunConnectionPolicy()
    issues = [
        *_validate_preparation(preparation_report),
        *_validate_connection_context(
            connection=connection,
            audit_context=audit_context,
            policy=policy,
        ),
    ]

    if issues:
        return _adapter_report(
            preparation_report=preparation_report,
            audit_context=audit_context,
            started=started,
            status="blocked",
            issues=issues,
            normalized_metadata_rows=[],
            validation_report=None,
            executed_command=None,
        )

    metadata_request = preparation_report.metadata_request
    assert metadata_request is not None
    params_argument = metadata_request.params_declaration if metadata_request.parameter_bindings else None

    try:
        if pyodbc_module is None:
            import pyodbc as pyodbc_module
    except ImportError:
        validation_report = validate_controlled_dry_run_metadata(
            preparation_report,
            None,
            duration_ms=_duration_ms(started),
            audit_ref=audit_context.correlation_id,
            engine_error_category="driver_error",
            engine_error_message="SQL Server ODBC driver is not installed.",
        )
        return _adapter_report(
            preparation_report=preparation_report,
            audit_context=audit_context,
            started=started,
            status="engine_error",
            issues=[
                _issue(
                    "driver_gate",
                    "SQLSERVER_DRIVER_MISSING",
                    "SQL Server ODBC driver is not installed.",
                    "driver_error",
                )
            ],
            normalized_metadata_rows=[],
            validation_report=validation_report,
            executed_command=None,
        )

    try:
        endpoint = await resolve_database_endpoint(connection, timeouts.connection_timeout_ms)
        connection_parts = _connection_string_parts(
            connection,
            credentials,
            _timeout_seconds(timeouts.connection_timeout_ms),
            server_host=endpoint.address,
            certificate_name=endpoint.certificate_name,
        )
        if not any(part.lower().startswith("usefmtonly=") for part in connection_parts):
            connection_parts.append("UseFMTONLY=No")

        raw_rows = await asyncio.wait_for(
            asyncio.to_thread(
                _execute_metadata_sync,
                pyodbc_module,
                connection_parts,
                _timeout_seconds(timeouts.connection_timeout_ms),
                _timeout_seconds(timeouts.metadata_timeout_ms),
                metadata_request.tsql,
                params_argument,
            ),
            timeout=(timeouts.connection_timeout_ms + timeouts.metadata_timeout_ms) / 1000 + 1,
        )
    except TimeoutError:
        return _engine_error_report(
            preparation_report=preparation_report,
            audit_context=audit_context,
            started=started,
            category="timeout",
            code="SQLSERVER_METADATA_TIMEOUT",
            message="SQL Server metadata call timed out.",
        )
    except Exception as exc:
        category, code, message = _map_driver_error(exc)
        return _engine_error_report(
            preparation_report=preparation_report,
            audit_context=audit_context,
            started=started,
            category=category,
            code=code,
            message=message,
        )

    normalized_rows = [_normalize_metadata_row(row) for row in raw_rows]
    core_columns = [
        SqlServerMetadataColumn(
            name=row.name or "",
            ordinal=row.ordinal,
            sql_type=row.sql_type,
            nullable=row.nullable,
        )
        for row in normalized_rows
    ]
    validation_report = validate_controlled_dry_run_metadata(
        preparation_report,
        core_columns,
        duration_ms=_duration_ms(started),
        audit_ref=audit_context.correlation_id,
    )
    return _adapter_report(
        preparation_report=preparation_report,
        audit_context=audit_context,
        started=started,
        status=validation_report.status,
        issues=[],
        normalized_metadata_rows=normalized_rows,
        validation_report=validation_report,
        executed_command=METADATA_COMMAND,
    )


def _validate_preparation(preparation_report: ControlledDryRunPreparationReport) -> list[SqlServerDryRunAdapterIssue]:
    issues: list[SqlServerDryRunAdapterIssue] = []
    request = preparation_report.metadata_request
    if preparation_report.status != "ready" or request is None:
        return [
            _issue(
                "descriptor_gate",
                "DRY_RUN_PREPARATION_NOT_READY",
                "SQL Server metadata adapter requires a ready dry-run preparation report.",
                "context_mismatch",
            )
        ]
    if request.sqlserver_validation_method != "sp_describe_first_result_set":
        issues.append(
            _issue(
                "descriptor_gate",
                "SQLSERVER_VALIDATION_METHOD_UNSUPPORTED",
                "SQL Server dry-run adapter supports only sp_describe_first_result_set.",
                "unsupported_sql_shape",
            )
        )
    if request.browse_information_mode != 0:
        issues.append(
            _issue(
                "descriptor_gate",
                "BROWSE_INFORMATION_MODE_UNSUPPORTED",
                "SQL Server dry-run adapter supports only browse_information_mode 0.",
                "unsupported_sql_shape",
            )
        )
    if request.statement_template != METADATA_COMMAND:
        issues.append(
            _issue(
                "descriptor_gate",
                "METADATA_COMMAND_MISMATCH",
                "Dry-run metadata request must use the approved metadata command.",
                "unsupported_sql_shape",
            )
        )
    if request.compiled_sql_hash != preparation_report.compiled_sql_hash:
        issues.append(
            _issue(
                "descriptor_gate",
                "COMPILED_SQL_HASH_MISMATCH",
                "Dry-run request compiled SQL hash does not match the preparation report.",
                "context_mismatch",
            )
        )
    if request.validator_report_hash != preparation_report.validator_report_hash:
        issues.append(
            _issue(
                "descriptor_gate",
                "VALIDATOR_REPORT_HASH_MISMATCH",
                "Dry-run request validator report hash does not match the preparation report.",
                "context_mismatch",
            )
        )
    issues.extend(_validate_parameter_declaration_shape(request.params_declaration, [binding.name for binding in request.parameter_bindings]))
    return issues


def _validate_connection_context(
    *,
    connection: ConnectionMetadata,
    audit_context: SqlServerDryRunAuditContext,
    policy: SqlServerDryRunConnectionPolicy,
) -> list[SqlServerDryRunAdapterIssue]:
    issues: list[SqlServerDryRunAdapterIssue] = []
    if not connection.database_name:
        issues.append(
            _issue(
                "connection_policy",
                "DATABASE_NAME_REQUIRED",
                "SQL Server metadata dry-run requires an explicit database name.",
                "connection_error",
            )
        )
    if connection.tenant_id != audit_context.tenant_id or connection.connection_id != audit_context.connection_id:
        issues.append(
            _issue(
                "connection_policy",
                "CONNECTION_CONTEXT_MISMATCH",
                "Connection metadata does not match the dry-run audit context.",
                "context_mismatch",
            )
        )
    if policy.require_tls and not connection.tls_required:
        issues.append(
            _issue(
                "connection_policy",
                "TLS_REQUIRED",
                "SQL Server metadata dry-run requires TLS unless policy explicitly disables the requirement.",
                "tls_error",
            )
        )
    if connection.trust_server_certificate and not policy.allow_trust_server_certificate:
        issues.append(
            _issue(
                "connection_policy",
                "TRUST_SERVER_CERTIFICATE_NOT_ALLOWED",
                "TrustServerCertificate is allowed only with explicit tenant policy.",
                "tls_error",
            )
        )
    return issues


def _validate_parameter_declaration_shape(params_declaration: str, parameter_names: list[str]) -> list[SqlServerDryRunAdapterIssue]:
    if not parameter_names:
        if params_declaration.strip():
            return [
                _issue(
                    "parameter_declaration_gate",
                    "PARAMETER_DECLARATION_UNEXPECTED",
                    "Parameter declaration must be empty when compiled SQL has no parameters.",
                    "parameter_binding_error",
                )
            ]
        return []

    issues: list[SqlServerDryRunAdapterIssue] = []
    if not params_declaration.strip():
        issues.append(
            _issue(
                "parameter_declaration_gate",
                "PARAMETER_DECLARATION_MISSING",
                "Parameter declaration is required when compiled SQL has parameters.",
                "parameter_binding_error",
            )
        )
        return issues

    expected = [f"@p{index}" for index in range(len(parameter_names))]
    if parameter_names != expected:
        issues.append(
            _issue(
                "parameter_declaration_gate",
                "PARAMETER_ORDER_INVALID",
                "Compiled parameter names must be deterministic and gap-free.",
                "parameter_binding_error",
            )
        )
    declared_names = re.findall(r"@p\d+", params_declaration)
    if declared_names != expected:
        issues.append(
            _issue(
                "parameter_declaration_gate",
                "PARAMETER_DECLARATION_MISMATCH",
                "Parameter declaration must match compiled parameter names in order.",
                "parameter_binding_error",
            )
        )
    for declaration in _split_parameter_declarations(params_declaration):
        parts = declaration.strip().split(maxsplit=1)
        if len(parts) != 2 or not _SUPPORTED_PARAMETER_DECLARATION_RE.fullmatch(parts[1].strip()):
            issues.append(
                _issue(
                    "parameter_declaration_gate",
                    "PARAMETER_DECLARATION_TYPE_UNSUPPORTED",
                    "Parameter declaration contains a SQL Server type outside Dry-Run V1 support.",
                    "parameter_binding_error",
                )
            )
            break
    return issues


def _split_parameter_declarations(params_declaration: str) -> list[str]:
    declarations: list[str] = []
    current: list[str] = []
    paren_depth = 0
    for char in params_declaration:
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth = max(0, paren_depth - 1)
        if char == "," and paren_depth == 0:
            declarations.append("".join(current))
            current = []
            continue
        current.append(char)
    if current:
        declarations.append("".join(current))
    return declarations


def _execute_metadata_sync(
    pyodbc_module,
    connection_parts: list[str],
    connection_timeout_seconds: int,
    metadata_timeout_seconds: int,
    tsql: str,
    params_declaration: str | None,
) -> list[dict[str, object]]:
    sql_connection = None
    cursor = None
    deadline = monotonic() + metadata_timeout_seconds
    try:
        sql_connection = _connect_sync(pyodbc_module, connection_parts, connection_timeout_seconds)
        sql_connection.timeout = _remaining_timeout_seconds(deadline)
        cursor = sql_connection.cursor()
        if hasattr(cursor, "timeout"):
            cursor.timeout = _remaining_timeout_seconds(deadline)
        cursor.execute(METADATA_COMMAND, tsql, params_declaration, 0)
        rows = cursor.fetchall()
        columns = [item[0] for item in getattr(cursor, "description", [])]
        return [_row_to_dict(row, columns) for row in rows]
    finally:
        if cursor is not None:
            cursor.close()
        if sql_connection is not None:
            sql_connection.close()


def _row_to_dict(row, columns: list[str]) -> dict[str, object]:
    if isinstance(row, dict):
        return row
    if hasattr(row, "cursor_description"):
        columns = [item[0] for item in row.cursor_description]
    if not columns and hasattr(row, "_fields"):
        columns = list(row._fields)
    return {column: row[index] for index, column in enumerate(columns)}


def _normalize_metadata_row(row: dict[str, object]) -> SqlServerDryRunNormalizedColumn:
    return SqlServerDryRunNormalizedColumn(
        ordinal=_required_int(row.get("column_ordinal")),
        name=_optional_str(row.get("name")),
        nullable=_optional_bool(row.get("is_nullable")),
        sql_type=_optional_str(row.get("system_type_name")) or "unknown",
        system_type_id=_optional_int(row.get("system_type_id")),
        precision=_optional_int(row.get("precision")),
        scale=_optional_int(row.get("scale")),
        max_length=_optional_int(row.get("max_length")),
        collation_name=_optional_str(row.get("collation_name")),
        is_case_sensitive=_optional_bool(row.get("is_case_sensitive")),
        source_schema=_optional_str(row.get("source_schema")),
        source_table=_optional_str(row.get("source_table")),
        source_column=_optional_str(row.get("source_column")),
    )


def _map_driver_error(exc: Exception) -> tuple[DryRunDecisionCategory, str, str]:
    sqlstate = _sqlstate(exc)
    error_number = _sqlserver_error_number(exc)
    message = _error_message(exc).lower()

    if sqlstate == "HY008" or "cancel" in message:
        return "cancelled", "SQLSERVER_METADATA_CANCELLED", "SQL Server metadata call was cancelled."
    if sqlstate == "HYT00" or sqlstate == "HYT01" or "timeout" in message:
        return "timeout", "SQLSERVER_METADATA_TIMEOUT", "SQL Server metadata call timed out."
    if error_number == 18456 or sqlstate == "28000" or "login failed" in message:
        return "authentication_error", "SQLSERVER_AUTHENTICATION_FAILED", "SQL Server authentication failed."
    if "certificate" in message or "ssl" in message or "tls" in message:
        return "tls_error", "SQLSERVER_TLS_ERROR", "SQL Server TLS/certificate validation failed."
    if sqlstate and sqlstate.startswith("08"):
        return "connection_error", "SQLSERVER_CONNECTION_ERROR", "SQL Server connection failed."
    if "destination" in message or "resolve" in message or "connection failed" in message:
        return "connection_error", "SQLSERVER_CONNECTION_ERROR", "SQL Server connection failed."
    if error_number in {229, 230, 297} or "permission" in message or "denied" in message:
        return "permission_error", "SQLSERVER_PERMISSION_DENIED", "SQL Server metadata permissions are insufficient."
    if error_number == 208 or "invalid object name" in message or "object" in message and "not found" in message:
        return "object_not_found", "SQLSERVER_OBJECT_NOT_FOUND", "SQL Server object is missing or not visible."
    if error_number == 207 or "invalid column name" in message:
        return "column_not_found", "SQLSERVER_COLUMN_NOT_FOUND", "SQL Server column is missing or not visible."
    if error_number in {102, 105, 156} or "syntax" in message or "incorrect syntax" in message:
        return "syntax_error", "SQLSERVER_SYNTAX_ERROR", "SQL Server rejected the compiled SQL syntax."
    if "parameter" in message or "declare" in message or "declared more than one" in message:
        return "parameter_binding_error", "SQLSERVER_PARAMETER_DECLARATION_ERROR", "SQL Server rejected the parameter declaration."
    if "temporary table" in message or "permanent table" in message:
        return "unsupported_sql_shape", "SQLSERVER_METADATA_UNSUPPORTED_SQL_SHAPE", "SQL Server cannot describe this SQL shape in V1 dry-run."
    if "metadata" in message or error_number is not None and 11500 <= error_number <= 11599:
        return "sqlserver_metadata_error", "SQLSERVER_METADATA_STATIC_ANALYSIS_FAILED", "SQL Server could not statically determine result metadata."
    return "driver_error", "SQLSERVER_DRIVER_ERROR", "SQL Server driver raised an unexpected metadata error."


def _engine_error_report(
    *,
    preparation_report: ControlledDryRunPreparationReport,
    audit_context: SqlServerDryRunAuditContext,
    started: float,
    category: DryRunDecisionCategory,
    code: str,
    message: str,
) -> SqlServerDryRunAdapterReport:
    validation_report = validate_controlled_dry_run_metadata(
        preparation_report,
        None,
        duration_ms=_duration_ms(started),
        audit_ref=audit_context.correlation_id,
        engine_error_category=category,
        engine_error_message=message,
    )
    return _adapter_report(
        preparation_report=preparation_report,
        audit_context=audit_context,
        started=started,
        status="engine_error",
        issues=[_issue("sqlserver_metadata_call", code, message, category)],
        normalized_metadata_rows=[],
        validation_report=validation_report,
        executed_command=METADATA_COMMAND,
    )


def _adapter_report(
    *,
    preparation_report: ControlledDryRunPreparationReport,
    audit_context: SqlServerDryRunAuditContext,
    started: float,
    status: AdapterStatus,
    issues: list[SqlServerDryRunAdapterIssue],
    normalized_metadata_rows: list[SqlServerDryRunNormalizedColumn],
    validation_report: ControlledDryRunReport | None,
    executed_command: str | None,
) -> SqlServerDryRunAdapterReport:
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    infos = [issue for issue in issues if issue.severity == "info"]
    decision_category: DryRunDecisionCategory
    if errors:
        decision_category = errors[0].decision_category
    elif validation_report is not None:
        decision_category = validation_report.decision_category
    else:
        decision_category = "safe"
    duration_ms = _duration_ms(started)
    return SqlServerDryRunAdapterReport(
        status=status,
        decision_category=decision_category,
        metadata_method="sp_describe_first_result_set",
        browse_information_mode=preparation_report.metadata_request.browse_information_mode if preparation_report.metadata_request else None,
        normalized_metadata_rows=normalized_metadata_rows,
        validation_report=validation_report,
        errors=errors,
        warnings=warnings,
        infos=infos,
        summary=SqlServerDryRunAdapterSummary(
            status=status,
            error_count=len(errors),
            warning_count=len(warnings),
            metadata_column_count=len(normalized_metadata_rows),
            duration_ms=duration_ms,
        ),
        duration_ms=duration_ms,
        tenant_id=audit_context.tenant_id,
        user_id=audit_context.user_id,
        connection_id=audit_context.connection_id,
        correlation_id=audit_context.correlation_id,
        compiled_sql_hash=preparation_report.compiled_sql_hash,
        validator_report_hash=preparation_report.validator_report_hash,
        dry_run_report_hash=validation_report.dry_run_report_hash if validation_report else None,
        executed_command=executed_command,
    )


def _issue(
    stage: str,
    code: str,
    message: str,
    category: DryRunDecisionCategory,
    *,
    severity: AdapterSeverity = "error",
) -> SqlServerDryRunAdapterIssue:
    return SqlServerDryRunAdapterIssue(
        stage=stage,
        code=code,
        severity=severity,
        message=message,
        decision_category=category,
    )


def _duration_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))


def _timeout_seconds(timeout_ms: int) -> int:
    return max(1, timeout_ms // 1000)


def _remaining_timeout_seconds(deadline: float) -> int:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("SQL Server metadata call deadline exceeded.")
    return max(1, int(remaining))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _required_int(value: object) -> int:
    if value is None:
        raise ValueError("SQL Server metadata row is missing column_ordinal.")
    return int(value)


def _sqlstate(exc: Exception) -> str | None:
    for arg in getattr(exc, "args", ()):
        if isinstance(arg, str) and re.fullmatch(r"[A-Z0-9]{5}", arg):
            return arg
        if isinstance(arg, (tuple, list)):
            for item in arg:
                if isinstance(item, str) and re.fullmatch(r"[A-Z0-9]{5}", item):
                    return item
    return None


def _sqlserver_error_number(exc: Exception) -> int | None:
    for arg in getattr(exc, "args", ()):
        if isinstance(arg, int):
            return arg
        if isinstance(arg, (tuple, list)):
            for item in arg:
                if isinstance(item, int):
                    return item
    matches = re.findall(r"\((\d{3,6})\)", _error_message(exc))
    if not matches:
        return None
    return int(matches[-1])


def _error_message(exc: Exception) -> str:
    return " ".join(str(arg) for arg in getattr(exc, "args", ()) if arg is not None)
