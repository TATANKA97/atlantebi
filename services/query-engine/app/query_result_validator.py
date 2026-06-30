from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.models import (
    QueryIntentResult,
    QueryabilityGraphArtifact,
    SemanticFilter,
    SemanticLayer,
    SemanticMetric,
)
from app.query_compiler import (
    CompiledSqlParameter,
    CompiledSqlReference,
    QueryCompilerResult,
    QueryCompilerTrace,
)
from app.query_compiler_preflight import QueryCompilerPreflightReport


ResultValidationStatus = Literal["valid", "valid_with_warnings", "blocked"]
ResultValidationStageStatus = Literal["pass", "warning", "blocked"]
ResultValidationSeverity = Literal["error", "warning", "info"]
ResultValidationDecisionCategory = Literal[
    "safe",
    "safe_with_disclosure",
    "invalid_compilation",
    "unsafe_sql",
    "parameter_mismatch",
    "trace_mismatch",
    "unsupported",
    "stale",
]

_STAGES: tuple[str, ...] = (
    "compiler_result_integrity",
    "context_binding",
    "canonical_sql_validation",
    "sql_shape_guardrails",
    "parameter_validation",
    "trace_consistency",
    "identifier_reference_validation",
    "join_contract_validation",
    "filter_contract_validation",
    "aggregation_contract_validation",
    "result_contract_validation",
    "final_decision",
)
_CATEGORY_PRECEDENCE: tuple[ResultValidationDecisionCategory, ...] = (
    "stale",
    "unsafe_sql",
    "unsupported",
    "invalid_compilation",
    "parameter_mismatch",
    "trace_mismatch",
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
_SUPPORTED_FILTER_OPERATORS = {
    "eq",
    "neq",
    "in",
    "not_in",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "is_null",
    "is_not_null",
}
_RAW_SQL_KEYS = {
    "sql",
    "raw_sql",
    "native_sql",
    "ref_sql",
    "query",
    "transform_sql",
}
_GROUPED_LIMIT_DEFAULT = 500
_GROUPED_LIMIT_MAX = 1000


@dataclass(frozen=True)
class QueryResultValidationIssue:
    stage: str
    code: str
    severity: ResultValidationSeverity
    message: str
    metric_key: str | None = None
    table_key: str | None = None
    column_key: str | None = None
    edge_key: str | None = None
    filter_key: str | None = None
    physical_label: str | None = None
    decision_category: ResultValidationDecisionCategory = "invalid_compilation"
    downstream_impact: str = ""
    suggested_action: str = ""


@dataclass(frozen=True)
class QueryResultValidationStageResult:
    stage: str
    status: ResultValidationStageStatus
    issues: list[QueryResultValidationIssue]
    selected_references: list[str]


@dataclass(frozen=True)
class QueryResultColumnExpectation:
    alias: str
    value_type: str
    nullable: bool | None = None
    source_column_key: str | None = None
    source_table_key: str | None = None


@dataclass(frozen=True)
class QueryResultContract:
    shape: Literal["scalar", "grouped"]
    columns: list[QueryResultColumnExpectation]
    disclosures: list[str]
    limit: int | None = None
    date_range: dict[str, str] | None = None


@dataclass(frozen=True)
class QueryResultValidationSummary:
    stage_count: int
    passed_stage_count: int
    warning_stage_count: int
    blocked_stage_count: int
    error_count: int
    warning_count: int
    info_count: int
    selected_reference_count: int


@dataclass(frozen=True)
class QueryResultValidationReport:
    status: ResultValidationStatus
    decision_category: ResultValidationDecisionCategory
    errors: list[QueryResultValidationIssue]
    warnings: list[QueryResultValidationIssue]
    infos: list[QueryResultValidationIssue]
    blocking_codes: list[str]
    summary: QueryResultValidationSummary
    stage_results: list[QueryResultValidationStageResult]
    result_contract: QueryResultContract | None

    def to_debug_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _SqlClauses:
    select: str
    from_clause: str
    joins: list[str]
    where: str | None
    group_by: str | None
    order_by: str | None


@dataclass(frozen=True)
class _ExpectedSql:
    sql: str
    clauses: _SqlClauses
    parameters: list[CompiledSqlParameter]
    trace: QueryCompilerTrace
    result_contract: QueryResultContract


@dataclass
class _ValidationContext:
    compiler_result: QueryCompilerResult
    query_intent_result: QueryIntentResult
    preflight_report: QueryCompilerPreflightReport
    semantic_layer: SemanticLayer
    queryability_graph: QueryabilityGraphArtifact
    schema_snapshot: Any
    metric: SemanticMetric
    nodes_by_key: dict[str, Any]
    columns_by_key: dict[str, tuple[Any, Any]]
    edges_by_key: dict[str, Any]
    snapshot_objects: dict[tuple[str, str], Any]
    snapshot_columns: dict[tuple[str, str, str], Any]
    snapshot_fks: dict[str, Any]

    @property
    def plan(self) -> Any:
        return self.query_intent_result.plan


@dataclass
class _SqlBuildState:
    context: _ValidationContext
    aliases: dict[str, str] = field(default_factory=dict)
    table_refs: dict[str, CompiledSqlReference] = field(default_factory=dict)
    column_refs: dict[str, CompiledSqlReference] = field(default_factory=dict)
    edge_refs: dict[str, CompiledSqlReference] = field(default_factory=dict)
    parameters: list[CompiledSqlParameter] = field(default_factory=list)
    where_clauses: list[str] = field(default_factory=list)
    where_structured: list[dict[str, object]] = field(default_factory=list)
    group_by_structured: list[dict[str, object]] = field(default_factory=list)
    order_by_structured: list[dict[str, object]] | None = None
    joins: list[str] = field(default_factory=list)
    limit: int | None = None


def validate_compiled_query_result_contract(
    compiler_result: QueryCompilerResult | None,
    query_intent_result: QueryIntentResult,
    preflight_report: QueryCompilerPreflightReport,
    semantic_layer: SemanticLayer,
    queryability_graph: QueryabilityGraphArtifact,
    schema_snapshot: Any,
    *,
    dialect: str = "sqlserver",
) -> QueryResultValidationReport:
    stage_results: list[QueryResultValidationStageResult] = []
    result_contract: QueryResultContract | None = None

    integrity_issues = _validate_integrity(compiler_result, query_intent_result, schema_snapshot, dialect)
    stage_results.append(_stage_result("compiler_result_integrity", integrity_issues, _initial_refs(compiler_result)))
    if _core_unavailable(compiler_result, query_intent_result, schema_snapshot, dialect):
        return _report(stage_results, result_contract)

    context_result = _build_context(
        compiler_result=compiler_result,
        query_intent_result=query_intent_result,
        preflight_report=preflight_report,
        semantic_layer=semantic_layer,
        queryability_graph=queryability_graph,
        schema_snapshot=schema_snapshot,
    )
    if isinstance(context_result, list):
        stage_results.append(_stage_result("context_binding", context_result, []))
        return _report(_append_skipped_stages(stage_results, after="context_binding"), result_contract)
    context = context_result

    expected_result = _build_expected_sql(context)
    if isinstance(expected_result, list):
        stage_results.append(_stage_result("context_binding", _validate_context_binding(context), _context_refs(context)))
        stage_results.append(_stage_result("canonical_sql_validation", expected_result, _context_refs(context)))
        return _report(_append_skipped_stages(stage_results, after="canonical_sql_validation"), result_contract)
    expected = expected_result
    result_contract = expected.result_contract

    stage_results.append(_stage_result("context_binding", _validate_context_binding(context), _context_refs(context)))
    stage_results.append(_stage_result("canonical_sql_validation", _validate_canonical_sql(context, expected), _context_refs(context)))
    stage_results.append(_stage_result("sql_shape_guardrails", _validate_sql_guardrails(context), []))
    stage_results.append(_stage_result("parameter_validation", _validate_parameters(context, expected), [param.name for param in compiler_result.parameters]))
    stage_results.append(_stage_result("trace_consistency", _validate_trace_consistency(context, expected), _context_refs(context)))
    stage_results.append(_stage_result("identifier_reference_validation", _validate_identifiers(context, expected), _context_refs(context)))
    stage_results.append(_stage_result("join_contract_validation", _validate_join_contract(context, expected), list(context.plan.required_edge_path_keys)))
    stage_results.append(_stage_result("filter_contract_validation", _validate_filter_contract(context, expected), [item.column_key for item in context.plan.filters]))
    stage_results.append(_stage_result("aggregation_contract_validation", _validate_aggregation_contract(context, expected), [str(context.metric.metric_key)]))
    stage_results.append(_stage_result("result_contract_validation", _validate_result_contract(context, expected), [column.alias for column in expected.result_contract.columns]))

    return _report(stage_results, result_contract)


def _validate_integrity(
    compiler_result: QueryCompilerResult | None,
    query_intent_result: QueryIntentResult,
    schema_snapshot: Any,
    dialect: str,
) -> list[QueryResultValidationIssue]:
    issues: list[QueryResultValidationIssue] = []
    if compiler_result is None:
        issues.append(_issue("compiler_result_integrity", "COMPILER_RESULT_MISSING", "error", "Compiler result is required."))
        return issues
    if dialect != "sqlserver":
        issues.append(
            _issue(
                "compiler_result_integrity",
                "UNKNOWN_DIALECT",
                "error",
                "Only SQL Server compiled SQL is supported by Result Validator V1.",
                decision_category="unsupported",
            )
        )
    if compiler_result.status != "compiled":
        issues.append(_issue("compiler_result_integrity", "COMPILER_NOT_COMPILED", "error", "Compiler result status must be compiled."))
    if not compiler_result.sql or not compiler_result.sql.strip():
        issues.append(_issue("compiler_result_integrity", "COMPILED_SQL_MISSING", "error", "Compiled SQL is missing."))
    if compiler_result.trace is None:
        issues.append(_issue("compiler_result_integrity", "COMPILER_TRACE_MISSING", "error", "Compiler trace is missing."))
    if compiler_result.errors:
        issues.append(_issue("compiler_result_integrity", "COMPILER_ERRORS_PRESENT", "error", "Compiled result contains compiler errors."))
    if query_intent_result.status != "ready" or query_intent_result.plan is None:
        issues.append(_issue("compiler_result_integrity", "VALIDATION_CONTEXT_MISMATCH", "error", "Validator requires a ready query intent plan.", decision_category="trace_mismatch"))
    if schema_snapshot is None:
        issues.append(_issue("compiler_result_integrity", "SNAPSHOT_HASH_MISMATCH", "error", "Validator requires the schema snapshot.", decision_category="stale"))
    return issues


def _core_unavailable(
    compiler_result: QueryCompilerResult | None,
    query_intent_result: QueryIntentResult,
    schema_snapshot: Any,
    dialect: str,
) -> bool:
    return (
        compiler_result is None
        or dialect != "sqlserver"
        or compiler_result.trace is None
        or not compiler_result.sql
        or compiler_result.status != "compiled"
        or query_intent_result.status != "ready"
        or query_intent_result.plan is None
        or schema_snapshot is None
    )


def _build_context(
    *,
    compiler_result: QueryCompilerResult,
    query_intent_result: QueryIntentResult,
    preflight_report: QueryCompilerPreflightReport,
    semantic_layer: SemanticLayer,
    queryability_graph: QueryabilityGraphArtifact,
    schema_snapshot: Any,
) -> _ValidationContext | list[QueryResultValidationIssue]:
    plan = query_intent_result.plan
    metrics_by_key = {str(metric.metric_key): metric for metric in semantic_layer.metrics}
    metric = metrics_by_key.get(str(plan.primary_metric_key))
    if metric is None:
        return [
            _issue(
                "context_binding",
                "VALIDATION_CONTEXT_MISMATCH",
                "error",
                "Selected metric is missing from the semantic layer.",
                metric_key=str(plan.primary_metric_key),
                decision_category="trace_mismatch",
            )
        ]
    nodes_by_key = {node.node_key: node for node in queryability_graph.nodes}
    columns_by_key = {
        column.column_key: (node, column)
        for node in queryability_graph.nodes
        for column in node.columns
    }
    edges_by_key = {edge.edge_key: edge for edge in queryability_graph.edges}
    snapshot_objects = {
        (item.table_schema, item.name): item
        for item in getattr(schema_snapshot, "tables", [])
    }
    snapshot_columns = {
        (item.table_schema, item.name, column.name): column
        for item in getattr(schema_snapshot, "tables", [])
        for column in getattr(item, "columns", [])
    }
    snapshot_fks = {fk.constraint_name: fk for fk in getattr(schema_snapshot, "foreign_keys", [])}
    return _ValidationContext(
        compiler_result=compiler_result,
        query_intent_result=query_intent_result,
        preflight_report=preflight_report,
        semantic_layer=semantic_layer,
        queryability_graph=queryability_graph,
        schema_snapshot=schema_snapshot,
        metric=metric,
        nodes_by_key=nodes_by_key,
        columns_by_key=columns_by_key,
        edges_by_key=edges_by_key,
        snapshot_objects=snapshot_objects,
        snapshot_columns=snapshot_columns,
        snapshot_fks=snapshot_fks,
    )


def _validate_context_binding(context: _ValidationContext) -> list[QueryResultValidationIssue]:
    plan = context.plan
    compiler_trace = context.compiler_result.trace
    preflight_trace = context.preflight_report.plan_trace
    issues: list[QueryResultValidationIssue] = []

    if compiler_trace.metric_key != str(plan.primary_metric_key) or preflight_trace.selected_metric_key != str(plan.primary_metric_key):
        issues.append(_context_issue("Selected metric differs across intent, preflight, and compiler trace.", metric_key=str(plan.primary_metric_key)))
    if compiler_trace.source_table_key != context.metric.source_table_key:
        issues.append(_context_issue("Selected source table differs from semantic metric.", table_key=context.metric.source_table_key))
    if compiler_trace.date_column_key != plan.effective_date_column_key or preflight_trace.selected_date_column != plan.effective_date_column_key:
        issues.append(_context_issue("Selected date column differs across artifacts.", column_key=plan.effective_date_column_key))
    plan_dimensions = [item.column_key for item in plan.group_by_dimensions]
    preflight_dimensions = [str(item.get("column_key")) for item in preflight_trace.selected_dimensions]
    if compiler_trace.dimension_keys != plan_dimensions or preflight_dimensions != plan_dimensions:
        issues.append(_context_issue("Selected dimensions differ across artifacts."))
    plan_filters = [item.column_key for item in plan.filters]
    preflight_filters = [str(item.get("column_key")) for item in preflight_trace.selected_filters]
    if compiler_trace.filter_keys != plan_filters or preflight_filters != plan_filters:
        issues.append(_context_issue("Selected filters differ across artifacts."))
    plan_paths = _selected_plan_edge_keys(plan)
    preflight_paths = list(preflight_trace.selected_graph_paths)
    if sorted(compiler_trace.join_paths) != sorted(plan_paths) or sorted(preflight_paths) != sorted(plan_paths):
        issues.append(_context_issue("Selected graph paths differ across artifacts."))
    cache = preflight_trace.cache_key_inputs_preview
    if compiler_trace.semantic_hash != context.semantic_layer.semantic_hash or cache.get("semantic_hash") != context.semantic_layer.semantic_hash:
        issues.append(_issue("context_binding", "SEMANTIC_HASH_MISMATCH", "error", "Semantic hash does not match validation context.", decision_category="stale"))
    if compiler_trace.graph_hash != context.queryability_graph.graph_hash or cache.get("graph_hash") != context.queryability_graph.graph_hash:
        issues.append(_issue("context_binding", "GRAPH_HASH_MISMATCH", "error", "Graph hash does not match validation context.", decision_category="stale"))
    snapshot_hash = getattr(context.schema_snapshot, "snapshot_hash", None)
    if compiler_trace.snapshot_hash != snapshot_hash or cache.get("snapshot_hash") != snapshot_hash:
        issues.append(_issue("context_binding", "SNAPSHOT_HASH_MISMATCH", "error", "Snapshot hash does not match validation context.", decision_category="stale"))
    if _contains_raw_sql_payload(context.query_intent_result) or _contains_raw_sql_payload(context.semantic_layer):
        issues.append(_issue("context_binding", "RAW_SQL_LEAK", "error", "Raw SQL-shaped payload is present in structured artifacts.", decision_category="unsafe_sql"))
    return issues


def _build_expected_sql(context: _ValidationContext) -> _ExpectedSql | list[QueryResultValidationIssue]:
    state = _SqlBuildState(context=context)
    issues: list[QueryResultValidationIssue] = []

    if context.metric.source_table_key not in context.nodes_by_key:
        issues.append(_context_issue("Metric source table is missing from graph.", table_key=context.metric.source_table_key))
        return issues
    state.aliases[context.metric.source_table_key] = "t0"
    _record_table_ref(state, context.metric.source_table_key)

    join_issues = _assign_expected_aliases_and_joins(state)
    issues.extend(join_issues)
    metric_expr = _expected_metric_expression(state)
    if isinstance(metric_expr, QueryResultValidationIssue):
        issues.append(metric_expr)
    dimension_expr: str | None = None
    if context.plan.group_by_dimensions:
        dimension_result = _expected_dimension_expression(state)
        if isinstance(dimension_result, QueryResultValidationIssue):
            issues.append(dimension_result)
        else:
            dimension_expr = dimension_result

    if issues:
        return issues

    if dimension_expr is not None:
        state.limit = min(_GROUPED_LIMIT_DEFAULT, _GROUPED_LIMIT_MAX)
        limit_param = _add_expected_param(state, value=state.limit, logical_type="integer", source="limit", operator="top", param_context="grouped_result_limit")
        select_clause = (
            f"SELECT TOP ({limit_param.name})\n"
            f"  {dimension_expr} AS [dimension_0],\n"
            f"  {metric_expr} AS [metric_value]"
        )
        state.group_by_structured = [{"expression": dimension_expr, "alias": "dimension_0"}]
        state.order_by_structured = [
            {"expression": "[metric_value]", "direction": "DESC"},
            {"expression": "[dimension_0]", "direction": "ASC"},
        ]
    else:
        select_clause = f"SELECT\n  {metric_expr} AS [metric_value]"

    issues.extend(_expected_date_range(state))
    issues.extend(_expected_filters(state))
    if issues:
        return issues

    source_sql = _table_sql(context, context.metric.source_table_key)
    from_clause = f"FROM {source_sql} AS [{state.aliases[context.metric.source_table_key]}]"
    where_clause = "WHERE " + "\n  AND ".join(state.where_clauses) if state.where_clauses else None
    group_by_clause = f"GROUP BY {dimension_expr}" if dimension_expr is not None else None
    order_by_clause = "ORDER BY [metric_value] DESC, [dimension_0] ASC" if dimension_expr is not None else None
    sql_lines = [select_clause, from_clause, *state.joins]
    if where_clause:
        sql_lines.append(where_clause)
    if group_by_clause:
        sql_lines.append(group_by_clause)
    if order_by_clause:
        sql_lines.append(order_by_clause)

    contract = _expected_result_contract(context, state)
    expected_trace = QueryCompilerTrace(
        metric_key=str(context.metric.metric_key),
        source_table_key=context.metric.source_table_key,
        measure_column_key=context.metric.measure_column_key,
        date_column_key=context.plan.effective_date_column_key,
        dimension_keys=[item.column_key for item in context.plan.group_by_dimensions],
        filter_keys=[item.column_key for item in context.plan.filters],
        join_paths=_selected_plan_edge_keys(context.plan),
        selected_tables=list(state.table_refs.values()),
        selected_columns=list(state.column_refs.values()),
        aliases=dict(sorted(state.aliases.items(), key=lambda item: item[1])),
        where_clauses_structured=list(state.where_structured),
        group_by_structured=list(state.group_by_structured),
        order_by_structured=state.order_by_structured,
        limit=state.limit,
        preflight_status=context.preflight_report.status,
        preflight_decision_category=context.preflight_report.decision_category,
        semantic_hash=context.semantic_layer.semantic_hash,
        graph_hash=context.queryability_graph.graph_hash,
        snapshot_hash=getattr(context.schema_snapshot, "snapshot_hash", None),
    )
    return _ExpectedSql(
        sql="\n".join(sql_lines),
        clauses=_SqlClauses(
            select=select_clause,
            from_clause=from_clause,
            joins=list(state.joins),
            where=where_clause,
            group_by=group_by_clause,
            order_by=order_by_clause,
        ),
        parameters=list(state.parameters),
        trace=expected_trace,
        result_contract=contract,
    )


def _validate_canonical_sql(context: _ValidationContext, expected: _ExpectedSql) -> list[QueryResultValidationIssue]:
    actual_clauses = _extract_clauses(context.compiler_result.sql or "")
    issues: list[QueryResultValidationIssue] = []
    if _normalize_sql(context.compiler_result.sql or "") == _normalize_sql(expected.sql):
        return issues
    if _normalize_sql(actual_clauses.select) != _normalize_sql(expected.clauses.select):
        issues.append(_canonical_issue("CANONICAL_SELECT_MISMATCH", "SELECT clause differs from canonical compiler contract."))
    if _normalize_sql(actual_clauses.from_clause) != _normalize_sql(expected.clauses.from_clause):
        issues.append(_canonical_issue("CANONICAL_FROM_MISMATCH", "FROM clause differs from canonical compiler contract."))
    if [_normalize_sql(item) for item in actual_clauses.joins] != [_normalize_sql(item) for item in expected.clauses.joins]:
        issues.append(_canonical_issue("CANONICAL_JOIN_MISMATCH", "JOIN clauses differ from canonical compiler contract."))
    if _normalize_optional(actual_clauses.where) != _normalize_optional(expected.clauses.where):
        issues.append(_canonical_issue("CANONICAL_WHERE_MISMATCH", "WHERE clause differs from canonical compiler contract."))
    if _normalize_optional(actual_clauses.group_by) != _normalize_optional(expected.clauses.group_by):
        issues.append(_canonical_issue("CANONICAL_GROUP_BY_MISMATCH", "GROUP BY clause differs from canonical compiler contract."))
    if _normalize_optional(actual_clauses.order_by) != _normalize_optional(expected.clauses.order_by):
        issues.append(_canonical_issue("CANONICAL_ORDER_BY_MISMATCH", "ORDER BY clause differs from canonical compiler contract."))
    return issues


def _validate_sql_guardrails(context: _ValidationContext) -> list[QueryResultValidationIssue]:
    sql = context.compiler_result.sql or ""
    issues: list[QueryResultValidationIssue] = []
    scrubbed = _strip_bracket_identifiers(sql)
    if not _normalize_sql(scrubbed).upper().startswith("SELECT "):
        issues.append(_issue("sql_shape_guardrails", "SQL_NOT_SELECT_ONLY", "error", "Compiled SQL must be SELECT-only.", decision_category="unsafe_sql"))
    if ";" in scrubbed:
        issues.append(_issue("sql_shape_guardrails", "SQL_MULTIPLE_STATEMENTS", "error", "Compiled SQL must not contain statement separators.", decision_category="unsafe_sql"))
    if "--" in scrubbed or "/*" in scrubbed or "*/" in scrubbed:
        issues.append(_issue("sql_shape_guardrails", "SQL_COMMENT_PAYLOAD_FORBIDDEN", "error", "Compiled SQL must not contain comments.", decision_category="unsafe_sql"))
    for keyword in _FORBIDDEN_SQL_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", scrubbed, flags=re.IGNORECASE):
            code = "SQL_EXEC_FORBIDDEN" if keyword in {"EXEC", "EXECUTE"} else "SQL_DDL_DML_FORBIDDEN"
            issues.append(_issue("sql_shape_guardrails", code, "error", f"Forbidden SQL keyword detected: {keyword}.", decision_category="unsafe_sql"))
    if re.search(r"\bWITH\b|\bOVER\s*\(|\bSELECT\b.+\bSELECT\b", scrubbed, flags=re.IGNORECASE | re.DOTALL):
        issues.append(_issue("sql_shape_guardrails", "SQL_UNSUPPORTED_SHAPE", "error", "Compiled SQL shape is outside Result Validator V1 scope.", decision_category="unsupported"))
    return issues


def _validate_parameters(context: _ValidationContext, expected: _ExpectedSql) -> list[QueryResultValidationIssue]:
    issues: list[QueryResultValidationIssue] = []
    actual = list(context.compiler_result.parameters)
    sql_param_names = re.findall(r"@p\d+", context.compiler_result.sql or "")
    expected_names = [param.name for param in expected.parameters]
    actual_names = [param.name for param in actual]

    if len(actual_names) != len(set(actual_names)):
        issues.append(_issue("parameter_validation", "PARAMETER_DUPLICATE", "error", "Duplicate compiled parameter names.", decision_category="parameter_mismatch"))
    if actual_names != [f"@p{index}" for index in range(len(actual_names))]:
        issues.append(_issue("parameter_validation", "PARAMETER_ORDER_INVALID", "error", "Compiled parameters are not ordered as @p0..@pN.", decision_category="parameter_mismatch"))
    for name in sorted(set(sql_param_names)):
        if actual_names.count(name) != 1:
            issues.append(_issue("parameter_validation", "PARAMETER_MISSING", "error", "SQL parameter has no exactly matching parameter object.", decision_category="parameter_mismatch"))
    for name in actual_names:
        if name not in sql_param_names:
            issues.append(_issue("parameter_validation", "PARAMETER_UNUSED", "error", "Compiled parameter object is not used in SQL.", decision_category="parameter_mismatch"))
    if actual_names != expected_names:
        issues.append(_canonical_issue("CANONICAL_PARAMETER_MISMATCH", "Compiled parameter names differ from canonical contract.", stage="parameter_validation", category="parameter_mismatch"))
    if [asdict(param) for param in actual] != [asdict(param) for param in expected.parameters]:
        issues.append(_canonical_issue("CANONICAL_PARAMETER_MISMATCH", "Compiled parameter objects differ from canonical contract.", stage="parameter_validation", category="parameter_mismatch"))
    if context.plan.time_range is not None and not any(param.source == "date_range" for param in actual):
        issues.append(_issue("parameter_validation", "DATE_PARAMETER_MISSING", "error", "Date range parameters are missing.", decision_category="parameter_mismatch"))
    if context.plan.group_by_dimensions and not any(param.source == "limit" for param in actual):
        issues.append(_issue("parameter_validation", "LIMIT_PARAMETER_MISSING", "error", "Grouped result limit parameter is missing.", decision_category="parameter_mismatch"))
    for filter_item in context.plan.filters:
        if filter_item.operator in {"eq", "neq", "gt", "gte", "lt", "lte"} and filter_item.value is not None:
            if str(filter_item.value) in (context.compiler_result.sql or ""):
                issues.append(_issue("parameter_validation", "FILTER_VALUE_INTERPOLATED", "error", "Filter literal appears directly in SQL.", filter_key=filter_item.column_key, decision_category="unsafe_sql"))
    return issues


def _validate_trace_consistency(context: _ValidationContext, expected: _ExpectedSql) -> list[QueryResultValidationIssue]:
    actual = context.compiler_result.trace
    expected_trace = expected.trace
    issues: list[QueryResultValidationIssue] = []
    checks = (
        ("metric_key", actual.metric_key, expected_trace.metric_key),
        ("source_table_key", actual.source_table_key, expected_trace.source_table_key),
        ("measure_column_key", actual.measure_column_key, expected_trace.measure_column_key),
        ("date_column_key", actual.date_column_key, expected_trace.date_column_key),
        ("dimension_keys", actual.dimension_keys, expected_trace.dimension_keys),
        ("filter_keys", actual.filter_keys, expected_trace.filter_keys),
        ("join_paths", sorted(actual.join_paths), sorted(expected_trace.join_paths)),
        ("aliases", actual.aliases, expected_trace.aliases),
        ("where_clauses_structured", actual.where_clauses_structured, expected_trace.where_clauses_structured),
        ("group_by_structured", actual.group_by_structured, expected_trace.group_by_structured),
        ("order_by_structured", actual.order_by_structured, expected_trace.order_by_structured),
        ("limit", actual.limit, expected_trace.limit),
    )
    for field_name, actual_value, expected_value in checks:
        if actual_value != expected_value:
            issues.append(_issue("trace_consistency", "COMPILER_TRACE_MISMATCH", "error", f"Compiler trace field differs from canonical contract: {field_name}.", decision_category="trace_mismatch"))
    if actual.selected_tables != expected_trace.selected_tables:
        issues.append(_issue("trace_consistency", "TRACE_TABLE_MISMATCH", "error", "Compiler trace selected tables differ from canonical contract.", decision_category="trace_mismatch"))
    if actual.selected_columns != expected_trace.selected_columns:
        issues.append(_issue("trace_consistency", "TRACE_COLUMN_MISMATCH", "error", "Compiler trace selected columns differ from canonical contract.", decision_category="trace_mismatch"))
    if actual.join_paths != expected_trace.join_paths:
        issues.append(_issue("trace_consistency", "TRACE_JOIN_MISMATCH", "error", "Compiler trace joins differ from canonical contract.", decision_category="trace_mismatch"))
    return issues


def _validate_identifiers(context: _ValidationContext, expected: _ExpectedSql) -> list[QueryResultValidationIssue]:
    issues: list[QueryResultValidationIssue] = []
    if not _brackets_balanced(context.compiler_result.sql or ""):
        issues.append(_issue("identifier_reference_validation", "IDENTIFIER_ESCAPING_INVALID", "error", "SQL Server bracket escaping is invalid.", decision_category="unsafe_sql"))
    for ref in expected.trace.selected_tables:
        node = context.nodes_by_key.get(ref.key)
        if node is None or _snapshot_object(context, node) is None:
            issues.append(_issue("identifier_reference_validation", "TABLE_REFERENCE_INVALID", "error", "Selected table cannot be resolved in graph and snapshot.", table_key=ref.key, decision_category="trace_mismatch"))
    for ref in expected.trace.selected_columns:
        node_column = context.columns_by_key.get(ref.key)
        if node_column is None:
            issues.append(_issue("identifier_reference_validation", "COLUMN_REFERENCE_INVALID", "error", "Selected column cannot be resolved in graph.", column_key=ref.key, decision_category="trace_mismatch"))
            continue
        node, column = node_column
        if _snapshot_column(context, node, column) is None:
            issues.append(_issue("identifier_reference_validation", "COLUMN_REFERENCE_INVALID", "error", "Selected column cannot be resolved in snapshot.", column_key=ref.key, decision_category="trace_mismatch"))
    actual_aliases = set(re.findall(r"\[t\d+\]", context.compiler_result.sql or ""))
    expected_aliases = {f"[{alias}]" for alias in expected.trace.aliases.values()}
    if not actual_aliases.issubset(expected_aliases):
        issues.append(_issue("identifier_reference_validation", "ALIAS_REFERENCE_INVALID", "error", "SQL contains an alias outside compiler trace.", decision_category="trace_mismatch"))
    return issues


def _validate_join_contract(context: _ValidationContext, expected: _ExpectedSql) -> list[QueryResultValidationIssue]:
    issues: list[QueryResultValidationIssue] = []
    actual_join_keys = set(context.compiler_result.trace.join_paths)
    expected_join_keys = set(expected.trace.join_paths)
    if actual_join_keys != expected_join_keys:
        issues.append(_issue("join_contract_validation", "JOIN_NOT_IN_TRACE", "error", "Compiled joins do not match trace join paths.", decision_category="trace_mismatch"))
    for edge_key in expected.trace.join_paths:
        edge = context.edges_by_key.get(edge_key)
        if edge is None:
            issues.append(_issue("join_contract_validation", "JOIN_EDGE_NOT_FOUND", "error", "Join edge is missing from graph.", edge_key=edge_key, decision_category="trace_mismatch"))
            continue
        if getattr(edge, "edge_type", None) != "fk_join":
            issues.append(_issue("join_contract_validation", "JOIN_USES_LINEAGE", "error", "Join edge is not an FK edge.", edge_key=edge_key, decision_category="unsafe_sql"))
            continue
        if _node(context, edge.from_node_key).bridge_candidate or _node(context, edge.to_node_key).bridge_candidate:
            issues.append(_issue("join_contract_validation", "JOIN_BRIDGE_M2M_FORBIDDEN", "error", "Bridge or many-to-many join path is forbidden in V1.", edge_key=edge_key, decision_category="unsafe_sql"))
        if not _edge_is_compiler_safe(edge):
            issues.append(_issue("join_contract_validation", "JOIN_FK_UNTRUSTED", "error", "Join FK is not trusted/enabled/verified.", edge_key=edge_key, decision_category="unsafe_sql"))
        fk = context.snapshot_fks.get(edge.constraint_name)
        if fk is None:
            issues.append(_issue("join_contract_validation", "JOIN_FK_NOT_IN_SNAPSHOT", "error", "Join FK is missing from snapshot.", edge_key=edge_key, decision_category="trace_mismatch"))
            continue
        if not _snapshot_fk_matches(context, edge, fk):
            issues.append(_issue("join_contract_validation", "JOIN_PAIR_ORDER_INVALID", "error", "Join FK pair order or physical metadata differs from snapshot.", edge_key=edge_key, decision_category="trace_mismatch"))
    if expected.clauses.joins and not all(" = " in join for join in expected.clauses.joins):
        issues.append(_issue("join_contract_validation", "JOIN_NAME_INFERRED_FORBIDDEN", "error", "Join predicate must be FK column-pair based.", decision_category="unsafe_sql"))
    return issues


def _validate_filter_contract(context: _ValidationContext, expected: _ExpectedSql) -> list[QueryResultValidationIssue]:
    issues: list[QueryResultValidationIssue] = []
    actual_filters = list(context.compiler_result.trace.where_clauses_structured)
    expected_filters = list(expected.trace.where_clauses_structured)
    if actual_filters != expected_filters:
        issues.append(_issue("filter_contract_validation", "FILTER_NOT_IN_TRACE", "error", "Compiled filters differ from canonical trace.", decision_category="trace_mismatch"))
    first_plan_filter_index = 2 if context.plan.time_range is not None else 0
    expected_plan_filters = expected_filters[first_plan_filter_index:]
    if len(expected_plan_filters) != len(context.plan.filters):
        issues.append(_issue("filter_contract_validation", "FILTER_NOT_IN_TRACE", "error", "Compiled filter count differs from query intent.", decision_category="trace_mismatch"))
    for index, filter_item in enumerate(context.plan.filters):
        expected_item = expected_plan_filters[index] if index < len(expected_plan_filters) else None
        if expected_item is None:
            issues.append(_issue("filter_contract_validation", "FILTER_NOT_IN_TRACE", "error", "Plan filter is missing from compiled trace.", filter_key=filter_item.column_key, decision_category="trace_mismatch"))
            continue
        if expected_item.get("column_key") != filter_item.column_key:
            issues.append(_issue("filter_contract_validation", "FILTER_NOT_IN_TRACE", "error", "Compiled filter column differs from query intent.", filter_key=filter_item.column_key, decision_category="trace_mismatch"))
        if expected_item.get("operator") != filter_item.operator:
            issues.append(_issue("filter_contract_validation", "FILTER_OPERATOR_MISMATCH", "error", "Filter operator differs from plan.", filter_key=filter_item.column_key, decision_category="trace_mismatch"))
        if filter_item.operator in {"eq", "neq"} and filter_item.value is None:
            issues.append(_issue("filter_contract_validation", "FILTER_NULL_OPERATOR_INVALID", "error", "Null eq/neq filters are forbidden.", filter_key=filter_item.column_key, decision_category="unsafe_sql"))
        if filter_item.operator == "between" and len(expected_item.get("parameters", [])) != 2:
            issues.append(_issue("filter_contract_validation", "FILTER_BETWEEN_ARITY_INVALID", "error", "BETWEEN filter must have two parameters.", filter_key=filter_item.column_key, decision_category="parameter_mismatch"))
        if filter_item.operator in {"in", "not_in"} and not expected_item.get("parameters"):
            issues.append(_issue("filter_contract_validation", "FILTER_IN_EMPTY", "error", "IN filters must have one or more parameters.", filter_key=filter_item.column_key, decision_category="parameter_mismatch"))
        node_column = context.columns_by_key.get(filter_item.column_key)
        if node_column:
            _, column = node_column
            if getattr(column, "sensitivity", None) == "pii":
                issues.append(_issue("filter_contract_validation", "FILTER_PII_NOT_APPROVED", "error", "PII filters are not approved by Result Validator V1.", filter_key=filter_item.column_key, decision_category="unsafe_sql"))
    return issues


def _validate_aggregation_contract(context: _ValidationContext, expected: _ExpectedSql) -> list[QueryResultValidationIssue]:
    metric = context.metric
    issues: list[QueryResultValidationIssue] = []
    select = _normalize_sql(expected.clauses.select).upper()
    if metric.aggregation == "count" and metric.measure_column_key is None:
        if "COUNT_BIG(*)" not in select or metric.format.value_type != "count" or metric.aggregation_level not in {"row", "entity"}:
            issues.append(_issue("aggregation_contract_validation", "COUNT_BIG_NOT_ALLOWED", "error", "COUNT_BIG(*) is not allowed for this metric.", metric_key=str(metric.metric_key), decision_category="trace_mismatch"))
    elif metric.aggregation == "count":
        if metric.measure_column_key is None or "COUNT(" not in select:
            issues.append(_issue("aggregation_contract_validation", "COUNT_COLUMN_NOT_ALLOWED", "error", "COUNT(column) requires explicit count column.", metric_key=str(metric.metric_key), decision_category="trace_mismatch"))
    elif metric.aggregation == "count_distinct":
        if "COUNT(DISTINCT " not in select:
            issues.append(_issue("aggregation_contract_validation", "COUNT_DISTINCT_MISMATCH", "error", "COUNT_DISTINCT aggregation mismatch.", metric_key=str(metric.metric_key), decision_category="trace_mismatch"))
    elif metric.aggregation in {"sum", "avg", "min", "max"}:
        if metric.measure_column_key is None:
            issues.append(_issue("aggregation_contract_validation", "MEASURE_COLUMN_MISSING", "error", "Aggregation requires measure column.", metric_key=str(metric.metric_key), decision_category="trace_mismatch"))
        if f"{metric.aggregation.upper()}(" not in select:
            issues.append(_issue("aggregation_contract_validation", "AGGREGATION_MISMATCH", "error", "Aggregation function differs from metric definition.", metric_key=str(metric.metric_key), decision_category="trace_mismatch"))
    if len(getattr(context.semantic_layer, "metrics", [])) > 1 and str(context.plan.primary_metric_key) != str(metric.metric_key):
        issues.append(_issue("aggregation_contract_validation", "MULTI_METRIC_FORBIDDEN", "error", "Compiled query must target one primary metric.", decision_category="unsupported"))
    return issues


def _validate_result_contract(context: _ValidationContext, expected: _ExpectedSql) -> list[QueryResultValidationIssue]:
    contract = expected.result_contract
    issues: list[QueryResultValidationIssue] = []
    expected_aliases = ["dimension_0", "metric_value"] if context.plan.group_by_dimensions else ["metric_value"]
    actual_aliases = [column.alias for column in contract.columns]
    if actual_aliases != expected_aliases:
        issues.append(_issue("result_contract_validation", "RESULT_COLUMN_MISMATCH", "error", "Result contract columns do not match SQL aliases.", decision_category="trace_mismatch"))
    if context.metric.format.value_type not in {"currency", "number", "percentage", "count", "duration"}:
        issues.append(_issue("result_contract_validation", "RESULT_METRIC_TYPE_INVALID", "error", "Metric result type is invalid.", metric_key=str(context.metric.metric_key), decision_category="trace_mismatch"))
    if context.plan.group_by_dimensions and len(contract.columns) != 2:
        issues.append(_issue("result_contract_validation", "RESULT_DIMENSION_TYPE_INVALID", "error", "Grouped contract must contain dimension and metric columns.", decision_category="trace_mismatch"))
    required_disclosures = _active_disclosures(context)
    if required_disclosures and sorted(contract.disclosures) != sorted(required_disclosures):
        issues.append(_issue("result_contract_validation", "DISCLOSURE_NOT_PROPAGATED", "error", "Preflight/query disclosures are not propagated to result contract.", decision_category="trace_mismatch"))
    elif required_disclosures:
        issues.append(
            _issue(
                "result_contract_validation",
                "DISCLOSURE_PROPAGATED",
                "warning",
                "Preflight/query disclosures are propagated to the result contract.",
                decision_category="safe_with_disclosure",
                downstream_impact="Future consumers must surface these disclosures with the result contract.",
                suggested_action="Keep disclosures attached to any dry-run or execution preview.",
            )
        )
    if context.plan.group_by_dimensions and contract.limit is None:
        issues.append(_issue("result_contract_validation", "LIMIT_CONTRACT_MISSING", "error", "Grouped result contract must record limit.", decision_category="trace_mismatch"))
    if context.plan.time_range is not None and contract.date_range is None:
        issues.append(_issue("result_contract_validation", "DATE_RANGE_CONTRACT_MISSING", "error", "Result contract must record date range.", decision_category="trace_mismatch"))
    return issues


def _expected_result_contract(context: _ValidationContext, state: _SqlBuildState) -> QueryResultContract:
    disclosures = _active_disclosures(context)
    columns: list[QueryResultColumnExpectation] = []
    if context.plan.group_by_dimensions:
        dimension_key = context.plan.group_by_dimensions[0].column_key
        node, column = context.columns_by_key[dimension_key]
        columns.append(
            QueryResultColumnExpectation(
                alias="dimension_0",
                value_type=str(column.technical_role),
                nullable=column.nullable,
                source_column_key=dimension_key,
                source_table_key=node.node_key,
            )
        )
    columns.append(
        QueryResultColumnExpectation(
            alias="metric_value",
            value_type=context.metric.format.value_type,
            nullable=False,
            source_column_key=context.metric.measure_column_key,
            source_table_key=context.metric.source_table_key,
        )
    )
    date_range = None
    if context.plan.time_range is not None:
        date_range = {
            "start_date": context.plan.time_range.start_date,
            "end_date": context.plan.time_range.end_date,
            "date_column_key": context.plan.effective_date_column_key or "",
        }
    return QueryResultContract(
        shape="grouped" if context.plan.group_by_dimensions else "scalar",
        columns=columns,
        disclosures=disclosures,
        limit=state.limit,
        date_range=date_range,
    )


def _assign_expected_aliases_and_joins(state: _SqlBuildState) -> list[QueryResultValidationIssue]:
    context = state.context
    alias_index = 1
    issues: list[QueryResultValidationIssue] = []
    for edge_key in _selected_plan_edge_keys(context.plan):
        edge = context.edges_by_key.get(edge_key)
        if edge is None:
            issues.append(_issue("canonical_sql_validation", "JOIN_EDGE_NOT_FOUND", "error", "Selected edge is missing from graph.", edge_key=edge_key, decision_category="trace_mismatch"))
            continue
        if getattr(edge, "edge_type", None) != "fk_join":
            issues.append(_issue("canonical_sql_validation", "JOIN_USES_LINEAGE", "error", "Selected edge is not an FK join.", edge_key=edge_key, decision_category="unsafe_sql"))
            continue
        from_alias = state.aliases.get(edge.from_node_key)
        to_alias = state.aliases.get(edge.to_node_key)
        if from_alias is None and to_alias is None:
            issues.append(_issue("canonical_sql_validation", "JOIN_NOT_IN_TRACE", "error", "Selected edge is not connected to source table.", edge_key=edge_key, decision_category="trace_mismatch"))
            continue
        if from_alias is not None and to_alias is not None:
            _record_edge_ref(state, edge)
            continue
        if from_alias is not None:
            state.aliases[edge.to_node_key] = f"t{alias_index}"
            alias_index += 1
            join_node_key = edge.to_node_key
        else:
            state.aliases[edge.from_node_key] = f"t{alias_index}"
            alias_index += 1
            join_node_key = edge.from_node_key
        _record_table_ref(state, join_node_key)
        _record_edge_ref(state, edge)
        state.joins.append(_join_sql(state, edge, join_node_key))
    return issues


def _expected_metric_expression(state: _SqlBuildState) -> str | QueryResultValidationIssue:
    context = state.context
    metric = context.metric
    source_alias = state.aliases[metric.source_table_key]
    if metric.aggregation == "count" and metric.measure_column_key is None:
        if metric.format.value_type == "count" and metric.aggregation_level in {"row", "entity"}:
            return "COUNT_BIG(*)"
        return _issue("canonical_sql_validation", "COUNT_BIG_NOT_ALLOWED", "error", "COUNT metric lacks explicit row/entity semantics.", metric_key=str(metric.metric_key), decision_category="trace_mismatch")
    if metric.measure_column_key is None:
        return _issue("canonical_sql_validation", "MEASURE_COLUMN_MISSING", "error", "Metric requires an explicit measure column.", metric_key=str(metric.metric_key), decision_category="trace_mismatch")
    node_column = context.columns_by_key.get(metric.measure_column_key)
    if node_column is None:
        return _issue("canonical_sql_validation", "MEASURE_COLUMN_MISSING", "error", "Measure column is missing from graph.", column_key=metric.measure_column_key, decision_category="trace_mismatch")
    node, column = node_column
    alias = state.aliases.get(node.node_key)
    if alias is None:
        return _issue("canonical_sql_validation", "TRACE_TABLE_MISMATCH", "error", "Measure table is not selected by expected paths.", column_key=metric.measure_column_key, decision_category="trace_mismatch")
    expr = _column_expr(alias or source_alias, column.name)
    _record_column_ref(state, node, column, alias or source_alias)
    if metric.aggregation == "count_distinct":
        return f"COUNT(DISTINCT {expr})"
    if metric.aggregation == "count":
        snap_col = _snapshot_column(context, node, column)
        if column.nullable or getattr(snap_col, "is_nullable", True):
            return _issue("canonical_sql_validation", "COUNT_COLUMN_NOT_ALLOWED", "error", "COUNT column must be non-null.", column_key=metric.measure_column_key, decision_category="trace_mismatch")
        return f"COUNT({expr})"
    return f"{metric.aggregation.upper()}({expr})"


def _expected_dimension_expression(state: _SqlBuildState) -> str | QueryResultValidationIssue:
    context = state.context
    dimension = context.plan.group_by_dimensions[0]
    node_column = context.columns_by_key.get(dimension.column_key)
    if node_column is None:
        return _issue("canonical_sql_validation", "RESULT_DIMENSION_TYPE_INVALID", "error", "Dimension column is missing from graph.", column_key=dimension.column_key, decision_category="trace_mismatch")
    node, column = node_column
    alias = state.aliases.get(node.node_key)
    if alias is None:
        return _issue("canonical_sql_validation", "FILTER_CROSS_TABLE_PATH_MISSING", "error", "Dimension table is not selected by expected paths.", column_key=dimension.column_key, decision_category="trace_mismatch")
    _record_column_ref(state, node, column, alias)
    return _column_expr(alias, column.name)


def _expected_date_range(state: _SqlBuildState) -> list[QueryResultValidationIssue]:
    context = state.context
    plan = context.plan
    if plan.time_range is None:
        return []
    if plan.effective_date_column_key is None:
        return [_issue("canonical_sql_validation", "DATE_RANGE_CONTRACT_MISSING", "error", "Time range requires date column.", decision_category="trace_mismatch")]
    node_column = context.columns_by_key.get(plan.effective_date_column_key)
    if node_column is None:
        return [_issue("canonical_sql_validation", "COLUMN_REFERENCE_INVALID", "error", "Date column is missing from graph.", column_key=plan.effective_date_column_key, decision_category="trace_mismatch")]
    node, column = node_column
    alias = state.aliases.get(node.node_key)
    if alias is None:
        return [_issue("canonical_sql_validation", "FILTER_CROSS_TABLE_PATH_MISSING", "error", "Date table is not selected by expected paths.", column_key=plan.effective_date_column_key, decision_category="trace_mismatch")]
    _record_column_ref(state, node, column, alias)
    start = _add_expected_param(state, value=plan.time_range.start_date, logical_type="date", source="date_range", operator="gte", param_context=plan.effective_date_column_key)
    end = _add_expected_param(state, value=plan.time_range.end_date, logical_type="date", source="date_range", operator="lt", param_context=plan.effective_date_column_key)
    expr = _column_expr(alias, column.name)
    state.where_clauses.append(f"{expr} >= {start.name}")
    state.where_clauses.append(f"{expr} < {end.name}")
    state.where_structured.extend(
        [
            {"column_key": plan.effective_date_column_key, "operator": "gte", "parameter": start.name},
            {"column_key": plan.effective_date_column_key, "operator": "lt", "parameter": end.name},
        ]
    )
    return []


def _expected_filters(state: _SqlBuildState) -> list[QueryResultValidationIssue]:
    issues: list[QueryResultValidationIssue] = []
    for filter_item in state.context.plan.filters:
        if filter_item.operator not in _SUPPORTED_FILTER_OPERATORS:
            issues.append(_issue("filter_contract_validation", "FILTER_OPERATOR_MISMATCH", "error", "Filter operator is unsupported.", filter_key=filter_item.column_key, decision_category="unsupported"))
            continue
        node_column = state.context.columns_by_key.get(filter_item.column_key)
        if node_column is None:
            issues.append(_issue("filter_contract_validation", "FILTER_NOT_IN_TRACE", "error", "Filter column is missing from graph.", filter_key=filter_item.column_key, decision_category="trace_mismatch"))
            continue
        node, column = node_column
        alias = state.aliases.get(node.node_key)
        if alias is None:
            issues.append(_issue("filter_contract_validation", "FILTER_CROSS_TABLE_PATH_MISSING", "error", "Filter path is not selected.", filter_key=filter_item.column_key, decision_category="trace_mismatch"))
            continue
        _record_column_ref(state, node, column, alias)
        clause = _expected_filter_clause(state, filter_item, alias, column.name)
        if isinstance(clause, QueryResultValidationIssue):
            issues.append(clause)
        else:
            state.where_clauses.append(clause)
    return issues


def _expected_filter_clause(state: _SqlBuildState, filter_item: SemanticFilter, alias: str, column_name: str) -> str | QueryResultValidationIssue:
    expr = _column_expr(alias, column_name)
    op = filter_item.operator
    value = filter_item.value
    if op in {"eq", "neq"} and value is None:
        return _issue("filter_contract_validation", "FILTER_NULL_OPERATOR_INVALID", "error", "Null eq/neq filters are invalid.", filter_key=filter_item.column_key, decision_category="unsafe_sql")
    if op in {"is_null", "is_not_null"}:
        if value is not None:
            return _issue("filter_contract_validation", "FILTER_OPERATOR_MISMATCH", "error", "Null-check filters must not have values.", filter_key=filter_item.column_key, decision_category="trace_mismatch")
        state.where_structured.append({"column_key": filter_item.column_key, "operator": op})
        return f"{expr} IS {'NOT ' if op == 'is_not_null' else ''}NULL"
    if op in {"in", "not_in"}:
        if not isinstance(value, list) or not value:
            return _issue("filter_contract_validation", "FILTER_IN_EMPTY", "error", "IN filters require values.", filter_key=filter_item.column_key, decision_category="parameter_mismatch")
        params = [
            _add_expected_param(state, value=item, logical_type=filter_item.value_type, source="filter", operator=op, param_context=filter_item.column_key)
            for item in value
        ]
        state.where_structured.append({"column_key": filter_item.column_key, "operator": op, "parameters": [param.name for param in params]})
        return f"{expr} {'IN' if op == 'in' else 'NOT IN'} ({', '.join(param.name for param in params)})"
    if op == "between":
        if not isinstance(value, list) or len(value) != 2:
            return _issue("filter_contract_validation", "FILTER_BETWEEN_ARITY_INVALID", "error", "BETWEEN requires two values.", filter_key=filter_item.column_key, decision_category="parameter_mismatch")
        low = _add_expected_param(state, value=value[0], logical_type=filter_item.value_type, source="filter", operator="between_start", param_context=filter_item.column_key)
        high = _add_expected_param(state, value=value[1], logical_type=filter_item.value_type, source="filter", operator="between_end", param_context=filter_item.column_key)
        state.where_structured.append({"column_key": filter_item.column_key, "operator": op, "parameters": [low.name, high.name]})
        return f"{expr} BETWEEN {low.name} AND {high.name}"
    sql_op = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
    param = _add_expected_param(state, value=value, logical_type=filter_item.value_type, source="filter", operator=op, param_context=filter_item.column_key)
    state.where_structured.append({"column_key": filter_item.column_key, "operator": op, "parameter": param.name})
    return f"{expr} {sql_op} {param.name}"


def _join_sql(state: _SqlBuildState, edge: Any, join_node_key: str) -> str:
    join_node = _node(state.context, join_node_key)
    join_alias = state.aliases[join_node_key]
    from_alias = state.aliases[edge.from_node_key]
    to_alias = state.aliases[edge.to_node_key]
    predicates = [
        f"{_column_expr(from_alias, pair.from_column)} = {_column_expr(to_alias, pair.to_column)}"
        for pair in sorted(edge.column_pairs, key=lambda item: item.ordinal_position)
    ]
    return f"JOIN {_table_sql(state.context, join_node_key)} AS [{join_alias}] ON " + " AND ".join(predicates)


def _extract_clauses(sql: str) -> _SqlClauses:
    lines = [line.strip() for line in sql.splitlines() if line.strip()]
    select_lines: list[str] = []
    joins: list[str] = []
    where_lines: list[str] = []
    from_clause = ""
    group_by = None
    order_by = None
    mode = "select"
    for line in lines:
        upper = line.upper()
        if upper.startswith("FROM "):
            from_clause = line
            mode = "from"
        elif upper.startswith("JOIN "):
            joins.append(line)
            mode = "join"
        elif upper.startswith("WHERE "):
            where_lines.append(line)
            mode = "where"
        elif upper.startswith("AND ") and mode == "where":
            where_lines.append(line)
        elif upper.startswith("GROUP BY "):
            group_by = line
            mode = "group"
        elif upper.startswith("ORDER BY "):
            order_by = line
            mode = "order"
        elif mode == "select":
            select_lines.append(line)
    return _SqlClauses(
        select="\n".join(select_lines),
        from_clause=from_clause,
        joins=joins,
        where="\n".join(where_lines) if where_lines else None,
        group_by=group_by,
        order_by=order_by,
    )


def _stage_result(stage: str, issues: list[QueryResultValidationIssue], selected_references: list[str]) -> QueryResultValidationStageResult:
    if any(issue.severity == "error" for issue in issues):
        status: ResultValidationStageStatus = "blocked"
    elif any(issue.severity == "warning" for issue in issues):
        status = "warning"
    else:
        status = "pass"
    return QueryResultValidationStageResult(stage=stage, status=status, issues=issues, selected_references=selected_references)


def _append_skipped_stages(stage_results: list[QueryResultValidationStageResult], *, after: str) -> list[QueryResultValidationStageResult]:
    completed = {stage.stage for stage in stage_results}
    for stage in _STAGES:
        if stage not in completed:
            stage_results.append(
                QueryResultValidationStageResult(
                    stage=stage,
                    status="blocked",
                    issues=[
                        _issue(
                            stage,
                            "VALIDATION_STAGE_SKIPPED",
                            "warning",
                            f"Stage skipped because {after} could not produce required core metadata.",
                        )
                    ],
                    selected_references=[],
                )
            )
    return stage_results


def _report(
    stage_results: list[QueryResultValidationStageResult],
    result_contract: QueryResultContract | None,
) -> QueryResultValidationReport:
    if not any(stage.stage == "final_decision" for stage in stage_results):
        stage_results.append(_stage_result("final_decision", [], []))
    all_issues = [issue for stage in stage_results for issue in stage.issues]
    errors = [issue for issue in all_issues if issue.severity == "error"]
    warnings = [issue for issue in all_issues if issue.severity == "warning"]
    infos = [issue for issue in all_issues if issue.severity == "info"]
    if errors:
        status: ResultValidationStatus = "blocked"
    elif warnings:
        status = "valid_with_warnings"
    else:
        status = "valid"
    decision_category = _decision_category(errors, warnings)
    blocking_codes = sorted({issue.code for issue in errors})
    summary = QueryResultValidationSummary(
        stage_count=len(stage_results),
        passed_stage_count=sum(1 for stage in stage_results if stage.status == "pass"),
        warning_stage_count=sum(1 for stage in stage_results if stage.status == "warning"),
        blocked_stage_count=sum(1 for stage in stage_results if stage.status == "blocked"),
        error_count=len(errors),
        warning_count=len(warnings),
        info_count=len(infos),
        selected_reference_count=sum(len(stage.selected_references) for stage in stage_results),
    )
    return QueryResultValidationReport(
        status=status,
        decision_category=decision_category,
        errors=errors,
        warnings=warnings,
        infos=infos,
        blocking_codes=blocking_codes,
        summary=summary,
        stage_results=stage_results,
        result_contract=result_contract,
    )


def _decision_category(
    errors: list[QueryResultValidationIssue],
    warnings: list[QueryResultValidationIssue],
) -> ResultValidationDecisionCategory:
    if errors:
        categories = {issue.decision_category for issue in errors}
        for category in _CATEGORY_PRECEDENCE:
            if category in categories:
                return category
        return "invalid_compilation"
    if warnings:
        return "safe_with_disclosure"
    return "safe"


def _issue(
    stage: str,
    code: str,
    severity: ResultValidationSeverity,
    message: str,
    *,
    metric_key: str | None = None,
    table_key: str | None = None,
    column_key: str | None = None,
    edge_key: str | None = None,
    filter_key: str | None = None,
    physical_label: str | None = None,
    decision_category: ResultValidationDecisionCategory = "invalid_compilation",
    downstream_impact: str = "",
    suggested_action: str = "",
) -> QueryResultValidationIssue:
    return QueryResultValidationIssue(
        stage=stage,
        code=code,
        severity=severity,
        message=message,
        metric_key=metric_key,
        table_key=table_key,
        column_key=column_key,
        edge_key=edge_key,
        filter_key=filter_key,
        physical_label=physical_label,
        decision_category=decision_category,
        downstream_impact=downstream_impact or "A future dry-run or execution could validate a query different from the approved structured plan.",
        suggested_action=suggested_action or "Regenerate preflight and compiler output from the current artifacts.",
    )


def _canonical_issue(
    code: str,
    message: str,
    *,
    stage: str = "canonical_sql_validation",
    category: ResultValidationDecisionCategory = "trace_mismatch",
) -> QueryResultValidationIssue:
    return _issue(stage, code, "error", message, decision_category=category)


def _context_issue(message: str, *, metric_key: str | None = None, table_key: str | None = None, column_key: str | None = None) -> QueryResultValidationIssue:
    return _issue(
        "context_binding",
        "VALIDATION_CONTEXT_MISMATCH",
        "error",
        message,
        metric_key=metric_key,
        table_key=table_key,
        column_key=column_key,
        decision_category="trace_mismatch",
    )


def _initial_refs(compiler_result: QueryCompilerResult | None) -> list[str]:
    if compiler_result is None or compiler_result.trace is None:
        return []
    refs = [compiler_result.trace.metric_key or ""]
    refs.extend(compiler_result.trace.dimension_keys)
    refs.extend(compiler_result.trace.filter_keys)
    refs.extend(compiler_result.trace.join_paths)
    return [ref for ref in refs if ref]


def _context_refs(context: _ValidationContext) -> list[str]:
    refs = [str(context.metric.metric_key), context.metric.source_table_key]
    refs.extend(_selected_plan_edge_keys(context.plan))
    refs.extend(column.column_key for _, column in context.columns_by_key.values() if column.column_key in context.compiler_result.trace.filter_keys)
    return refs


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split())


def _normalize_optional(sql: str | None) -> str | None:
    return _normalize_sql(sql) if sql is not None else None


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


def _brackets_balanced(sql: str) -> bool:
    index = 0
    while index < len(sql):
        char = sql[index]
        if char == "[":
            index += 1
            closed = False
            while index < len(sql):
                if sql[index] == "]":
                    if index + 1 < len(sql) and sql[index + 1] == "]":
                        index += 2
                        continue
                    closed = True
                    index += 1
                    break
                index += 1
            if not closed:
                return False
            continue
        if char == "]":
            return False
        index += 1
    return True


def _contains_raw_sql_payload(value: Any) -> bool:
    if hasattr(value, "model_dump"):
        return _filter_raw_value(value.model_dump(mode="json"))
    if hasattr(value, "__dataclass_fields__"):
        return _filter_raw_value(asdict(value))
    return _filter_raw_value(value)


def _filter_raw_value(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _RAW_SQL_KEYS and item not in (None, "", []):
                return True
            if _filter_raw_value(item):
                return True
    elif isinstance(value, list):
        return any(_filter_raw_value(item) for item in value)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(token in lowered for token in (";select ", "; select ", "--", "/*")):
            return True
    return False


def _selected_plan_edge_keys(plan: Any) -> list[str]:
    keys: list[str] = []
    for edge_key in plan.required_edge_path_keys:
        if edge_key not in keys:
            keys.append(edge_key)
    for dimension in plan.group_by_dimensions:
        for edge_key in dimension.edge_path:
            if edge_key not in keys:
                keys.append(edge_key)
    return keys


def _filter_value_fingerprint(filter_item: Any) -> str:
    payload = {
        "column_key": getattr(filter_item, "column_key", None),
        "operator": getattr(filter_item, "operator", None),
        "value_type": getattr(filter_item, "value_type", None),
        "value": getattr(filter_item, "value", None),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _active_disclosures(context: _ValidationContext) -> list[str]:
    disclosures: list[str] = []
    for item in context.plan.disclosures:
        if item not in disclosures:
            disclosures.append(item)
    for item in context.preflight_report.plan_trace.active_disclosures:
        if item not in disclosures:
            disclosures.append(item)
    return disclosures


def _snapshot_object(context: _ValidationContext, node: Any) -> Any | None:
    return context.snapshot_objects.get((node.schema_name, node.object_name))


def _snapshot_column(context: _ValidationContext, node: Any, column: Any) -> Any | None:
    return context.snapshot_columns.get((node.schema_name, node.object_name, column.name))


def _snapshot_fk_matches(context: _ValidationContext, edge: Any, fk: Any) -> bool:
    from_node = _node(context, edge.from_node_key)
    to_node = _node(context, edge.to_node_key)
    expected_from = [pair.from_column for pair in sorted(edge.column_pairs, key=lambda item: item.ordinal_position)]
    expected_to = [pair.to_column for pair in sorted(edge.column_pairs, key=lambda item: item.ordinal_position)]
    return (
        fk.from_schema == from_node.schema_name
        and fk.from_table == from_node.object_name
        and fk.to_schema == to_node.schema_name
        and fk.to_table == to_node.object_name
        and list(fk.from_columns) == expected_from
        and list(fk.to_columns) == expected_to
        and not getattr(fk, "is_disabled", False)
        and not getattr(fk, "is_not_trusted", False)
        and getattr(fk, "verified_by_db", True)
    )


def _edge_is_compiler_safe(edge: Any) -> bool:
    return (
        getattr(edge, "edge_type", None) == "fk_join"
        and getattr(edge, "automatic_join_allowed", False)
        and getattr(edge, "verified_by_db", False)
        and getattr(edge, "enforcement_status", None) == "enabled"
        and getattr(edge, "validation_status", None) == "trusted"
    )


def _node(context: _ValidationContext, node_key: str) -> Any:
    return context.nodes_by_key[node_key]


def _table_sql(context: _ValidationContext, node_key: str) -> str:
    node = context.nodes_by_key[node_key]
    return f"{_quote_identifier(node.schema_name)}.{_quote_identifier(node.object_name)}"


def _column_expr(alias: str, column_name: str) -> str:
    return f"[{alias}].{_quote_identifier(column_name)}"


def _quote_identifier(value: str) -> str:
    if not _identifier_valid(value):
        raise ValueError("invalid SQL Server identifier")
    return "[" + value.replace("]", "]]") + "]"


def _identifier_valid(value: str) -> bool:
    return bool(value) and "\x00" not in value


def _add_expected_param(
    state: _SqlBuildState,
    *,
    value: object,
    logical_type: str,
    source: Literal["date_range", "filter", "limit"],
    operator: str,
    param_context: str,
) -> CompiledSqlParameter:
    param = CompiledSqlParameter(
        name=f"@p{len(state.parameters)}",
        value=value,
        logical_type=logical_type,
        source=source,
        operator=operator,
        context=param_context,
    )
    state.parameters.append(param)
    return param


def _record_table_ref(state: _SqlBuildState, table_key: str) -> None:
    if table_key in state.table_refs:
        return
    node = state.context.nodes_by_key[table_key]
    state.table_refs[table_key] = CompiledSqlReference(
        ref_type="table",
        key=table_key,
        physical_label=f"{node.schema_name}.{node.object_name}",
        alias=state.aliases.get(table_key),
    )


def _record_column_ref(state: _SqlBuildState, node: Any, column: Any, alias: str) -> None:
    if column.column_key in state.column_refs:
        return
    state.column_refs[column.column_key] = CompiledSqlReference(
        ref_type="column",
        key=column.column_key,
        physical_label=f"{node.schema_name}.{node.object_name}.{column.name}",
        alias=alias,
    )


def _record_edge_ref(state: _SqlBuildState, edge: Any) -> None:
    if edge.edge_key in state.edge_refs:
        return
    state.edge_refs[edge.edge_key] = CompiledSqlReference(
        ref_type="edge",
        key=edge.edge_key,
        physical_label=edge.constraint_name,
    )
