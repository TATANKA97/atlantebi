from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from app.models import QueryIntentResult, QueryabilityGraphArtifact, SemanticLayer
from app.query_compiler import CompiledSqlParameter, QueryCompilerResult
from app.query_compiler_preflight import QueryCompilerPreflightReport
from app.query_result_validator import QueryResultContract, QueryResultValidationReport


DryRunPreparationStatus = Literal["ready", "blocked"]
DryRunStatus = Literal["passed", "passed_with_warnings", "blocked", "engine_error"]
DryRunStageStatus = Literal["pass", "warning", "blocked"]
DryRunSeverity = Literal["error", "warning", "info"]
DryRunDecisionCategory = Literal[
    "safe",
    "safe_with_disclosure",
    "policy_blocked",
    "context_mismatch",
    "connection_error",
    "tls_error",
    "authentication_error",
    "permission_error",
    "object_not_found",
    "column_not_found",
    "parameter_binding_error",
    "syntax_error",
    "unsupported_sql_shape",
    "metadata_shape_mismatch",
    "timeout",
    "cancelled",
    "driver_error",
    "sqlserver_metadata_error",
    "engine_error",
]

_ACCEPTED_PREFLIGHT = {
    ("ready", "safe"),
    ("ready_with_warnings", "safe_with_disclosure"),
}
_ACCEPTED_VALIDATOR_STATUSES = {"valid", "valid_with_warnings"}
_VALIDATION_METHOD = "sp_describe_first_result_set"
_BROWSE_INFORMATION_MODE = 0
_METADATA_STATEMENT_TEMPLATE = (
    "EXEC sys.sp_describe_first_result_set "
    "@tsql = ?, @params = ?, @browse_information_mode = ?"
)
_FORBIDDEN_SQL_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "EXEC",
    "EXECUTE",
    "DECLARE",
    "SET",
    "USE",
    "GRANT",
    "REVOKE",
    "BACKUP",
    "RESTORE",
)
_NUMERIC_SQL_TYPES = {
    "bigint",
    "int",
    "smallint",
    "tinyint",
    "decimal",
    "numeric",
    "money",
    "smallmoney",
    "float",
    "real",
}
_TEXT_SQL_TYPES = {"char", "varchar", "nchar", "nvarchar", "text", "ntext"}
_BLOCKED_LOGICAL_TYPES = {
    "binary",
    "image",
    "sql_variant",
    "xml",
    "json",
    "geography",
    "geometry",
    "hierarchyid",
    "udt",
    "table",
    "tvp",
}


@dataclass(frozen=True)
class DryRunIssue:
    stage: str
    code: str
    severity: DryRunSeverity
    message: str
    decision_category: DryRunDecisionCategory
    downstream_impact: str = ""
    suggested_action: str = ""


@dataclass(frozen=True)
class DryRunStageResult:
    stage: str
    status: DryRunStageStatus
    issues: list[DryRunIssue]
    selected_references: list[str]


@dataclass(frozen=True)
class DryRunParameterBinding:
    name: str
    ordinal: int
    sql_type: str
    logical_type: str
    source: str
    operator: str
    context: str
    value_fingerprint: str
    nullable: bool


@dataclass(frozen=True)
class DryRunMetadataRequest:
    sqlserver_validation_method: Literal["sp_describe_first_result_set"]
    statement_template: str
    tsql: str
    params_declaration: str
    browse_information_mode: Literal[0]
    compiled_sql_hash: str
    validator_report_hash: str
    parameter_bindings: list[DryRunParameterBinding]


@dataclass(frozen=True)
class DryRunResultColumn:
    name: str
    ordinal: int
    sql_type: str
    nullable: bool | None
    expected_role: Literal["metric_value", "dimension_0"] | None
    matches_result_contract: bool


@dataclass(frozen=True)
class SqlServerMetadataColumn:
    name: str
    ordinal: int
    sql_type: str
    nullable: bool | None


@dataclass(frozen=True)
class DryRunSummary:
    stage_count: int
    passed_stage_count: int
    warning_stage_count: int
    blocked_stage_count: int
    error_count: int
    warning_count: int
    info_count: int


@dataclass(frozen=True)
class ControlledDryRunPreparationReport:
    status: DryRunPreparationStatus
    decision_category: DryRunDecisionCategory
    errors: list[DryRunIssue]
    warnings: list[DryRunIssue]
    infos: list[DryRunIssue]
    blocking_codes: list[str]
    summary: DryRunSummary
    stage_results: list[DryRunStageResult]
    metadata_request: DryRunMetadataRequest | None
    result_contract: QueryResultContract | None
    compiled_sql_hash: str | None
    validator_report_hash: str | None

    def to_debug_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ControlledDryRunReport:
    status: DryRunStatus
    decision_category: DryRunDecisionCategory
    sqlserver_validation_method: str | None
    result_columns: list[DryRunResultColumn]
    parameter_bindings: list[DryRunParameterBinding]
    errors: list[DryRunIssue]
    warnings: list[DryRunIssue]
    infos: list[DryRunIssue]
    blocking_codes: list[str]
    summary: DryRunSummary
    stage_results: list[DryRunStageResult]
    duration_ms: int
    audit_ref: str | None
    compiled_sql_hash: str | None
    validator_report_hash: str | None
    dry_run_report_hash: str | None = None

    def to_debug_dict(self) -> dict[str, object]:
        return asdict(self)


def prepare_controlled_dry_run(
    query_intent_result: QueryIntentResult,
    preflight_report: QueryCompilerPreflightReport,
    compiler_result: QueryCompilerResult,
    query_result_validation_report: QueryResultValidationReport,
    semantic_layer: SemanticLayer,
    queryability_graph: QueryabilityGraphArtifact,
    schema_snapshot: Any,
    *,
    tenant_id: str,
    user_id: str,
    connection_id: str,
    sqlserver_validation_method: str = _VALIDATION_METHOD,
    browse_information_mode: int = _BROWSE_INFORMATION_MODE,
    expected_compiled_sql_hash: str | None = None,
    expected_validator_report_hash: str | None = None,
) -> ControlledDryRunPreparationReport:
    stage_results: list[DryRunStageResult] = []
    stage_results.append(
        _stage_result(
            "input_artifact_gate",
            _validate_input_artifacts(
                query_intent_result=query_intent_result,
                preflight_report=preflight_report,
                compiler_result=compiler_result,
                validation_report=query_result_validation_report,
                semantic_layer=semantic_layer,
                queryability_graph=queryability_graph,
                schema_snapshot=schema_snapshot,
            ),
            _artifact_refs(compiler_result),
        )
    )
    stage_results.append(
        _stage_result(
            "tenant_connection_gate",
            _validate_tenant_context(tenant_id=tenant_id, user_id=user_id, connection_id=connection_id),
            [tenant_id, user_id, connection_id],
        )
    )
    stage_results.append(
        _stage_result(
            "sqlserver_method_gate",
            _validate_sqlserver_method(
                sqlserver_validation_method=sqlserver_validation_method,
                browse_information_mode=browse_information_mode,
            ),
            [sqlserver_validation_method, str(browse_information_mode)],
        )
    )
    stage_results.append(_stage_result("sql_shape_gate", _validate_sql_shape(compiler_result), []))
    stage_results.append(
        _stage_result(
            "join_predicate_gate",
            _validate_join_predicates(compiler_result),
            list(getattr(compiler_result.trace, "join_paths", [])) if compiler_result.trace else [],
        )
    )

    request: DryRunMetadataRequest | None = None
    parameter_issues, parameter_bindings, params_declaration = _build_parameter_bindings(compiler_result.parameters)
    stage_results.append(
        _stage_result(
            "parameter_declaration_gate",
            parameter_issues,
            [binding.name for binding in parameter_bindings],
        )
    )

    result_contract = query_result_validation_report.result_contract
    compiled_sql_hash = _hash_string(compiler_result.sql or "")
    validator_report_hash = _hash_payload(query_result_validation_report.to_debug_dict())
    stage_results.append(
        _stage_result(
            "hash_replay_gate",
            _validate_replay_hashes(
                compiled_sql_hash=compiled_sql_hash,
                validator_report_hash=validator_report_hash,
                expected_compiled_sql_hash=expected_compiled_sql_hash,
                expected_validator_report_hash=expected_validator_report_hash,
            ),
            [compiled_sql_hash, validator_report_hash],
        )
    )

    if not _has_errors(stage_results):
        request = DryRunMetadataRequest(
            sqlserver_validation_method="sp_describe_first_result_set",
            statement_template=_METADATA_STATEMENT_TEMPLATE,
            tsql=compiler_result.sql or "",
            params_declaration=params_declaration,
            browse_information_mode=0,
            compiled_sql_hash=compiled_sql_hash,
            validator_report_hash=validator_report_hash,
            parameter_bindings=parameter_bindings,
        )

    return _preparation_report(
        stage_results=stage_results,
        metadata_request=request,
        result_contract=result_contract,
        compiled_sql_hash=compiled_sql_hash,
        validator_report_hash=validator_report_hash,
    )


def validate_controlled_dry_run_metadata(
    preparation_report: ControlledDryRunPreparationReport,
    metadata_columns: list[SqlServerMetadataColumn] | None,
    *,
    duration_ms: int,
    audit_ref: str | None,
    engine_error_category: DryRunDecisionCategory | None = None,
    engine_error_message: str | None = None,
) -> ControlledDryRunReport:
    stage_results: list[DryRunStageResult] = []
    if preparation_report.status != "ready" or preparation_report.metadata_request is None:
        stage_results.append(
            _stage_result(
                "preparation_gate",
                [
                    _issue(
                        "preparation_gate",
                        "DRY_RUN_PREPARATION_NOT_READY",
                        "error",
                        "Dry-run metadata validation requires a ready preparation report.",
                        "context_mismatch",
                        downstream_impact="SQL Server metadata validation would run without accepted pre-runtime gates.",
                        suggested_action="Prepare dry-run again with accepted artifacts and connection context.",
                    )
                ],
                [],
            )
        )
        return _dry_run_report(
            stage_results=stage_results,
            preparation_report=preparation_report,
            result_columns=[],
            duration_ms=duration_ms,
            audit_ref=audit_ref,
            forced_status="blocked",
        )

    if engine_error_category is not None or engine_error_message is not None:
        stage_results.append(
            _stage_result(
                "sqlserver_metadata_gate",
                [
                    _issue(
                        "sqlserver_metadata_gate",
                        "SQLSERVER_METADATA_ERROR",
                        "error",
                        engine_error_message or "SQL Server metadata validation failed.",
                        engine_error_category or "sqlserver_metadata_error",
                        downstream_impact="Dry-run could not confirm SQL Server metadata compatibility.",
                        suggested_action="Inspect SQL Server metadata permissions, parameter declarations, and snapshot drift.",
                    )
                ],
                [],
            )
        )
        return _dry_run_report(
            stage_results=stage_results,
            preparation_report=preparation_report,
            result_columns=[],
            duration_ms=duration_ms,
            audit_ref=audit_ref,
            forced_status="engine_error",
        )

    if metadata_columns is None:
        stage_results.append(
            _stage_result(
                "sqlserver_metadata_gate",
                [
                    _issue(
                        "sqlserver_metadata_gate",
                        "SQLSERVER_METADATA_MISSING",
                        "error",
                        "SQL Server metadata columns are required to complete dry-run validation.",
                        "sqlserver_metadata_error",
                        downstream_impact="Dry-run cannot compare engine metadata to the Result Validator contract.",
                        suggested_action="Call the approved metadata method and pass its result columns to validation.",
                    )
                ],
                [],
            )
        )
        return _dry_run_report(
            stage_results=stage_results,
            preparation_report=preparation_report,
            result_columns=[],
            duration_ms=duration_ms,
            audit_ref=audit_ref,
            forced_status="engine_error",
        )

    result_columns, metadata_issues = _validate_metadata_columns(
        metadata_columns,
        preparation_report.result_contract,
    )
    stage_results.append(
        _stage_result(
            "metadata_contract_validation",
            metadata_issues,
            [column.name for column in metadata_columns],
        )
    )
    stage_results.append(
        _stage_result(
            "disclosure_propagation",
            _validate_disclosures(preparation_report.result_contract),
            [],
        )
    )
    return _dry_run_report(
        stage_results=stage_results,
        preparation_report=preparation_report,
        result_columns=result_columns,
        duration_ms=duration_ms,
        audit_ref=audit_ref,
    )


def _validate_input_artifacts(
    *,
    query_intent_result: QueryIntentResult,
    preflight_report: QueryCompilerPreflightReport,
    compiler_result: QueryCompilerResult,
    validation_report: QueryResultValidationReport,
    semantic_layer: SemanticLayer,
    queryability_graph: QueryabilityGraphArtifact,
    schema_snapshot: Any,
) -> list[DryRunIssue]:
    issues: list[DryRunIssue] = []
    if query_intent_result.status != "ready" or query_intent_result.plan is None:
        issues.append(_gate_issue("QUERY_INTENT_NOT_READY", "Query intent must be ready for dry-run."))
    if (preflight_report.status, preflight_report.decision_category) not in _ACCEPTED_PREFLIGHT:
        issues.append(_gate_issue("PREFLIGHT_NOT_ACCEPTED", "Preflight report is not accepted for dry-run."))
    if compiler_result.status != "compiled" or not compiler_result.sql:
        issues.append(_gate_issue("COMPILER_NOT_COMPILED", "Compiler result must be compiled for dry-run."))
    if validation_report.status not in _ACCEPTED_VALIDATOR_STATUSES:
        issues.append(_gate_issue("RESULT_VALIDATOR_NOT_ACCEPTED", "Result Validator report must be valid or valid_with_warnings."))
    if validation_report.result_contract is None:
        issues.append(_gate_issue("RESULT_CONTRACT_MISSING", "Result Validator contract is required for dry-run."))
    if semantic_layer.status != "active" or semantic_layer.freshness != "fresh":
        issues.append(_gate_issue("SEMANTIC_LAYER_NOT_FRESH", "Semantic Layer must be active and fresh.", category="context_mismatch"))
    if schema_snapshot is None:
        issues.append(_gate_issue("SCHEMA_SNAPSHOT_MISSING", "Technical Snapshot is required for dry-run.", category="context_mismatch"))
        return issues
    if compiler_result.trace.semantic_hash != semantic_layer.semantic_hash:
        issues.append(_gate_issue("SEMANTIC_HASH_MISMATCH", "Compiler trace semantic hash does not match supplied Semantic Layer.", category="context_mismatch"))
    if compiler_result.trace.graph_hash != queryability_graph.graph_hash:
        issues.append(_gate_issue("GRAPH_HASH_MISMATCH", "Compiler trace graph hash does not match supplied Queryability Graph.", category="context_mismatch"))
    if compiler_result.trace.snapshot_hash != getattr(schema_snapshot, "snapshot_hash", None):
        issues.append(_gate_issue("SNAPSHOT_HASH_MISMATCH", "Compiler trace snapshot hash does not match supplied Technical Snapshot.", category="context_mismatch"))
    if semantic_layer.base_graph_hash != queryability_graph.graph_hash:
        issues.append(_gate_issue("SEMANTIC_GRAPH_HASH_MISMATCH", "Semantic Layer base graph hash does not match supplied graph.", category="context_mismatch"))
    if getattr(schema_snapshot, "snapshot_hash", None) != queryability_graph.snapshot_hash:
        issues.append(_gate_issue("GRAPH_SNAPSHOT_HASH_MISMATCH", "Graph snapshot hash does not match supplied Technical Snapshot.", category="context_mismatch"))
    return issues


def _validate_tenant_context(*, tenant_id: str, user_id: str, connection_id: str) -> list[DryRunIssue]:
    issues: list[DryRunIssue] = []
    if not tenant_id:
        issues.append(_gate_issue("TENANT_ID_MISSING", "Tenant id is required.", category="policy_blocked"))
    if not user_id:
        issues.append(_gate_issue("USER_ID_MISSING", "User id is required.", category="policy_blocked"))
    if not connection_id:
        issues.append(_gate_issue("CONNECTION_ID_MISSING", "Connection id is required.", category="policy_blocked"))
    return issues


def _validate_sqlserver_method(*, sqlserver_validation_method: str, browse_information_mode: int) -> list[DryRunIssue]:
    issues: list[DryRunIssue] = []
    if sqlserver_validation_method != _VALIDATION_METHOD:
        issues.append(
            _gate_issue(
                "SQLSERVER_VALIDATION_METHOD_UNSUPPORTED",
                "Dry-Run V1 supports only sp_describe_first_result_set as the default metadata gate.",
                category="unsupported_sql_shape",
            )
        )
    if browse_information_mode != _BROWSE_INFORMATION_MODE:
        issues.append(
            _gate_issue(
                "BROWSE_INFORMATION_MODE_UNSUPPORTED",
                "Dry-Run V1 uses browse_information_mode=0 to validate exposed result metadata.",
                category="unsupported_sql_shape",
            )
        )
    return issues


def _validate_replay_hashes(
    *,
    compiled_sql_hash: str,
    validator_report_hash: str,
    expected_compiled_sql_hash: str | None,
    expected_validator_report_hash: str | None,
) -> list[DryRunIssue]:
    issues: list[DryRunIssue] = []
    if expected_compiled_sql_hash is not None and expected_compiled_sql_hash != compiled_sql_hash:
        issues.append(
            _gate_issue(
                "COMPILED_SQL_HASH_MISMATCH",
                "Compiled SQL hash does not match the expected dry-run input hash.",
                category="context_mismatch",
            )
        )
    if expected_validator_report_hash is not None and expected_validator_report_hash != validator_report_hash:
        issues.append(
            _gate_issue(
                "VALIDATOR_REPORT_HASH_MISMATCH",
                "Result Validator report hash does not match the expected dry-run input hash.",
                category="context_mismatch",
            )
        )
    return issues


def _validate_sql_shape(compiler_result: QueryCompilerResult) -> list[DryRunIssue]:
    sql = compiler_result.sql or ""
    issues: list[DryRunIssue] = []
    normalized = _strip_bracket_identifiers(sql).upper()
    if re.search(r"^\s*SELECT\b", normalized) is None:
        issues.append(_gate_issue("SQL_NOT_SELECT_ONLY", "Dry-run accepts only compiled SELECT SQL.", category="unsupported_sql_shape"))
    if ";" in sql:
        issues.append(_gate_issue("SQL_MULTIPLE_STATEMENTS", "Dry-run rejects semicolon-separated SQL.", category="unsupported_sql_shape"))
    if "--" in sql or "/*" in sql or "*/" in sql:
        issues.append(_gate_issue("SQL_COMMENT_PAYLOAD_FORBIDDEN", "Dry-run rejects SQL comments.", category="unsupported_sql_shape"))
    for keyword in _FORBIDDEN_SQL_KEYWORDS:
        if re.search(rf"\b{keyword}\b", normalized):
            issues.append(_gate_issue("SQL_FORBIDDEN_KEYWORD", f"Dry-run rejects forbidden SQL keyword {keyword}.", category="unsupported_sql_shape"))
            break
    if _contains_cross_database_reference(sql):
        issues.append(_gate_issue("SQL_CROSS_DATABASE_REFERENCE_FORBIDDEN", "Dry-run V1 rejects cross-database references.", category="unsupported_sql_shape"))
    return issues


def _validate_join_predicates(compiler_result: QueryCompilerResult) -> list[DryRunIssue]:
    sql = compiler_result.sql or ""
    has_join = re.search(r"\bJOIN\b", _strip_bracket_identifiers(sql), flags=re.IGNORECASE) is not None
    predicates = list(getattr(compiler_result.trace, "join_predicates", []) or [])
    if has_join and not predicates:
        return [
            _gate_issue(
                "JOIN_PREDICATE_TRACE_MISSING",
                "Dry-run requires materialized join_predicates for every compiled SQL JOIN.",
                category="context_mismatch",
            )
        ]
    if predicates and len(predicates) != len(re.findall(r"\bJOIN\b", _strip_bracket_identifiers(sql), flags=re.IGNORECASE)):
        return [
            _gate_issue(
                "JOIN_PREDICATE_COUNT_MISMATCH",
                "Dry-run join predicate trace count must match compiled SQL JOIN count.",
                category="context_mismatch",
            )
        ]
    return []


def _build_parameter_bindings(parameters: list[CompiledSqlParameter]) -> tuple[list[DryRunIssue], list[DryRunParameterBinding], str]:
    issues: list[DryRunIssue] = []
    bindings: list[DryRunParameterBinding] = []
    declarations: list[str] = []
    for ordinal, parameter in enumerate(parameters):
        expected_name = f"@p{ordinal}"
        if parameter.name != expected_name:
            issues.append(
                _gate_issue(
                    "PARAMETER_ORDER_INVALID",
                    "Dry-run requires deterministic @p0..@pN parameter order.",
                    category="parameter_binding_error",
                )
            )
        sql_type = _sqlserver_type_for_parameter(parameter)
        if sql_type is None:
            issues.append(
                _gate_issue(
                    "PARAMETER_TYPE_UNSUPPORTED",
                    f"Dry-run V1 does not support parameter logical type {parameter.logical_type}.",
                    category="parameter_binding_error",
                )
            )
            continue
        nullable = parameter.value is None
        binding = DryRunParameterBinding(
            name=parameter.name,
            ordinal=ordinal,
            sql_type=sql_type,
            logical_type=parameter.logical_type,
            source=parameter.source,
            operator=parameter.operator,
            context=parameter.context,
            value_fingerprint=_hash_payload(
                {
                    "name": parameter.name,
                    "value": parameter.value,
                    "logical_type": parameter.logical_type,
                    "source": parameter.source,
                    "operator": parameter.operator,
                    "context": parameter.context,
                }
            ),
            nullable=nullable,
        )
        bindings.append(binding)
        declarations.append(f"{parameter.name} {sql_type}")
    return issues, bindings, ", ".join(declarations)


def _sqlserver_type_for_parameter(parameter: CompiledSqlParameter) -> str | None:
    logical_type = parameter.logical_type.lower()
    if logical_type in _BLOCKED_LOGICAL_TYPES:
        return None
    if logical_type in {"integer", "int", "smallint", "tinyint"}:
        return "int"
    if logical_type in {"bigint", "count"}:
        return "bigint"
    if logical_type in {"decimal", "numeric", "currency", "money", "number"}:
        return "decimal(38,10)"
    if logical_type in {"float", "real"}:
        return "float"
    if logical_type == "date":
        return "date"
    if logical_type in {"datetime", "datetime2", "timestamp"}:
        return "datetime2"
    if logical_type in {"boolean", "bool", "bit"}:
        return "bit"
    if logical_type in {"uuid", "uniqueidentifier"}:
        return "uniqueidentifier"
    if logical_type in {"string", "text", "nvarchar", "varchar"}:
        return "nvarchar(4000)"
    return None


def _validate_metadata_columns(
    metadata_columns: list[SqlServerMetadataColumn],
    result_contract: QueryResultContract | None,
) -> tuple[list[DryRunResultColumn], list[DryRunIssue]]:
    if result_contract is None:
        return [], [
            _gate_issue(
                "RESULT_CONTRACT_MISSING",
                "Dry-run cannot validate SQL Server metadata without a Result Validator contract.",
                category="metadata_shape_mismatch",
            )
        ]
    expected = result_contract.columns
    result_columns: list[DryRunResultColumn] = []
    issues: list[DryRunIssue] = []
    if len(metadata_columns) != len(expected):
        issues.append(
            _gate_issue(
                "METADATA_COLUMN_COUNT_MISMATCH",
                "SQL Server metadata column count differs from Result Validator contract.",
                category="metadata_shape_mismatch",
            )
        )
    for index, actual in enumerate(metadata_columns):
        expected_column = expected[index] if index < len(expected) else None
        expected_role = expected_column.alias if expected_column and expected_column.alias in {"metric_value", "dimension_0"} else None
        matches = (
            expected_column is not None
            and actual.ordinal == index + 1
            and actual.name == expected_column.alias
            and _sql_type_compatible(actual.sql_type, expected_column.value_type, expected_column.alias)
        )
        result_columns.append(
            DryRunResultColumn(
                name=actual.name,
                ordinal=actual.ordinal,
                sql_type=actual.sql_type,
                nullable=actual.nullable,
                expected_role=expected_role,  # type: ignore[arg-type]
                matches_result_contract=matches,
            )
        )
        if not matches:
            issues.append(
                _gate_issue(
                    "METADATA_SHAPE_MISMATCH",
                    "SQL Server metadata column does not match Result Validator contract.",
                    category="metadata_shape_mismatch",
                )
            )
    return result_columns, issues


def _sql_type_compatible(sql_type: str, expected_value_type: str, alias: str) -> bool:
    normalized = sql_type.lower().split("(", 1)[0].strip()
    expected = expected_value_type.lower()
    if alias == "metric_value":
        if expected in {"currency", "number", "count"}:
            return normalized in _NUMERIC_SQL_TYPES
        return normalized not in {"image", "binary", "varbinary"}
    if alias == "dimension_0":
        return normalized not in {"image", "binary", "varbinary", "sql_variant"}
    return False


def _validate_disclosures(result_contract: QueryResultContract | None) -> list[DryRunIssue]:
    if result_contract is None:
        return []
    if result_contract.disclosures:
        return [
            _issue(
                "disclosure_propagation",
                "DISCLOSURE_PROPAGATED",
                "warning",
                "Result Validator disclosures are propagated into dry-run metadata validation.",
                "safe_with_disclosure",
                downstream_impact="Dry-run remains transparent about disclosed semantic assumptions.",
                suggested_action="Surface these disclosures with the dry-run result.",
            )
        ]
    return []


def _preparation_report(
    *,
    stage_results: list[DryRunStageResult],
    metadata_request: DryRunMetadataRequest | None,
    result_contract: QueryResultContract | None,
    compiled_sql_hash: str | None,
    validator_report_hash: str | None,
) -> ControlledDryRunPreparationReport:
    errors, warnings, infos = _collect_issues(stage_results)
    status: DryRunPreparationStatus = "blocked" if errors else "ready"
    return ControlledDryRunPreparationReport(
        status=status,
        decision_category=_decision_category(errors, warnings),
        errors=errors,
        warnings=warnings,
        infos=infos,
        blocking_codes=sorted({issue.code for issue in errors}),
        summary=_summary(stage_results, errors, warnings, infos),
        stage_results=stage_results,
        metadata_request=metadata_request,
        result_contract=result_contract,
        compiled_sql_hash=compiled_sql_hash,
        validator_report_hash=validator_report_hash,
    )


def _dry_run_report(
    *,
    stage_results: list[DryRunStageResult],
    preparation_report: ControlledDryRunPreparationReport,
    result_columns: list[DryRunResultColumn],
    duration_ms: int,
    audit_ref: str | None,
    forced_status: DryRunStatus | None = None,
) -> ControlledDryRunReport:
    errors, warnings, infos = _collect_issues(stage_results)
    if forced_status is not None:
        status = forced_status
    elif errors:
        status = "blocked"
    elif warnings:
        status = "passed_with_warnings"
    else:
        status = "passed"
    report = ControlledDryRunReport(
        status=status,
        decision_category=_decision_category(errors, warnings),
        sqlserver_validation_method=preparation_report.metadata_request.sqlserver_validation_method if preparation_report.metadata_request else None,
        result_columns=result_columns,
        parameter_bindings=preparation_report.metadata_request.parameter_bindings if preparation_report.metadata_request else [],
        errors=errors,
        warnings=warnings,
        infos=infos,
        blocking_codes=sorted({issue.code for issue in errors}),
        summary=_summary(stage_results, errors, warnings, infos),
        stage_results=stage_results,
        duration_ms=duration_ms,
        audit_ref=audit_ref,
        compiled_sql_hash=preparation_report.compiled_sql_hash,
        validator_report_hash=preparation_report.validator_report_hash,
    )
    return replace(report, dry_run_report_hash=_hash_payload(report.to_debug_dict()))


def _stage_result(stage: str, issues: list[DryRunIssue], selected_references: list[str]) -> DryRunStageResult:
    if any(issue.severity == "error" for issue in issues):
        status: DryRunStageStatus = "blocked"
    elif any(issue.severity == "warning" for issue in issues):
        status = "warning"
    else:
        status = "pass"
    return DryRunStageResult(
        stage=stage,
        status=status,
        issues=issues,
        selected_references=[item for item in selected_references if item],
    )


def _collect_issues(stage_results: list[DryRunStageResult]) -> tuple[list[DryRunIssue], list[DryRunIssue], list[DryRunIssue]]:
    issues = [issue for stage in stage_results for issue in stage.issues]
    return (
        [issue for issue in issues if issue.severity == "error"],
        [issue for issue in issues if issue.severity == "warning"],
        [issue for issue in issues if issue.severity == "info"],
    )


def _has_errors(stage_results: list[DryRunStageResult]) -> bool:
    return any(issue.severity == "error" for stage in stage_results for issue in stage.issues)


def _summary(
    stage_results: list[DryRunStageResult],
    errors: list[DryRunIssue],
    warnings: list[DryRunIssue],
    infos: list[DryRunIssue],
) -> DryRunSummary:
    return DryRunSummary(
        stage_count=len(stage_results),
        passed_stage_count=sum(1 for stage in stage_results if stage.status == "pass"),
        warning_stage_count=sum(1 for stage in stage_results if stage.status == "warning"),
        blocked_stage_count=sum(1 for stage in stage_results if stage.status == "blocked"),
        error_count=len(errors),
        warning_count=len(warnings),
        info_count=len(infos),
    )


def _decision_category(errors: list[DryRunIssue], warnings: list[DryRunIssue]) -> DryRunDecisionCategory:
    if errors:
        return errors[0].decision_category
    if warnings:
        return "safe_with_disclosure"
    return "safe"


def _artifact_refs(compiler_result: QueryCompilerResult) -> list[str]:
    trace = compiler_result.trace
    refs = [trace.metric_key or "", trace.source_table_key or ""]
    refs.extend(trace.dimension_keys)
    refs.extend(trace.filter_keys)
    refs.extend(trace.join_paths)
    return [ref for ref in refs if ref]


def _contains_cross_database_reference(sql: str) -> bool:
    stripped = _strip_bracket_identifiers(sql)
    return re.search(r"\[\]\.\[\]\.\[\]", stripped) is not None


def _strip_bracket_identifiers(sql: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(sql):
        if sql[index] != "[":
            output.append(sql[index])
            index += 1
            continue
        output.append("[]")
        index += 1
        while index < len(sql):
            if sql[index] == "]":
                if index + 1 < len(sql) and sql[index + 1] == "]":
                    index += 2
                    continue
                index += 1
                break
            index += 1
    return "".join(output)


def _hash_string(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_payload(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _gate_issue(
    code: str,
    message: str,
    *,
    category: DryRunDecisionCategory = "context_mismatch",
) -> DryRunIssue:
    return _issue(
        "pre_runtime_gate",
        code,
        "error",
        message,
        category,
        downstream_impact="Dry-run could validate a query outside the approved deterministic pipeline.",
        suggested_action="Regenerate or rebind the pipeline artifacts before dry-run.",
    )


def _issue(
    stage: str,
    code: str,
    severity: DryRunSeverity,
    message: str,
    decision_category: DryRunDecisionCategory,
    *,
    downstream_impact: str,
    suggested_action: str,
) -> DryRunIssue:
    return DryRunIssue(
        stage=stage,
        code=code,
        severity=severity,
        message=message,
        decision_category=decision_category,
        downstream_impact=downstream_impact,
        suggested_action=suggested_action,
    )
