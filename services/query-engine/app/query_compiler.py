from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.models import (
    QueryIntentResult,
    QueryabilityGraphArtifact,
    SemanticFilter,
    SemanticLayer,
    SemanticMetric,
)
from app.query_compiler_preflight import QueryCompilerPreflightReport


CompilerStatus = Literal["compiled", "blocked"]
CompilerSeverity = Literal["error", "warning", "info"]
CompiledParameterSource = Literal["date_range", "filter", "limit"]

_ACCEPTED_PREFLIGHT = {
    ("ready", "safe"),
    ("ready_with_warnings", "safe_with_disclosure"),
}
_SUPPORTED_DIALECTS = {"sqlserver"}
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
class QueryCompilerIssue:
    code: str
    severity: CompilerSeverity
    message: str
    metric_key: str | None = None
    table_key: str | None = None
    column_key: str | None = None
    edge_key: str | None = None
    filter_key: str | None = None
    physical_label: str | None = None
    downstream_impact: str = ""
    suggested_action: str = ""


@dataclass(frozen=True)
class CompiledSqlParameter:
    name: str
    value: object
    logical_type: str
    source: CompiledParameterSource
    operator: str
    context: str


@dataclass(frozen=True)
class CompiledSqlReference:
    ref_type: Literal["table", "column", "edge"]
    key: str
    physical_label: str
    alias: str | None = None


@dataclass(frozen=True)
class QueryCompilerTrace:
    metric_key: str | None = None
    source_table_key: str | None = None
    measure_column_key: str | None = None
    date_column_key: str | None = None
    dimension_keys: list[str] = field(default_factory=list)
    filter_keys: list[str] = field(default_factory=list)
    join_paths: list[str] = field(default_factory=list)
    selected_tables: list[CompiledSqlReference] = field(default_factory=list)
    selected_columns: list[CompiledSqlReference] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    where_clauses_structured: list[dict[str, object]] = field(default_factory=list)
    group_by_structured: list[dict[str, object]] = field(default_factory=list)
    order_by_structured: list[dict[str, object]] | None = None
    limit: int | None = None
    preflight_status: str | None = None
    preflight_decision_category: str | None = None
    semantic_hash: str | None = None
    graph_hash: str | None = None
    snapshot_hash: str | None = None

    def to_debug_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class QueryCompilerResult:
    status: CompilerStatus
    sql: str | None
    parameters: list[CompiledSqlParameter]
    trace: QueryCompilerTrace
    errors: list[QueryCompilerIssue]
    warnings: list[QueryCompilerIssue]

    def to_debug_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class _CompilerContext:
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

    @property
    def plan(self) -> Any:
        return self.query_intent_result.plan


def compile_query_plan(
    query_intent_result: QueryIntentResult,
    preflight_report: QueryCompilerPreflightReport | None,
    semantic_layer: SemanticLayer,
    queryability_graph: QueryabilityGraphArtifact,
    schema_snapshot: Any | None = None,
    *,
    dialect: str = "sqlserver",
) -> QueryCompilerResult:
    errors: list[QueryCompilerIssue] = []
    warnings: list[QueryCompilerIssue] = []

    if dialect not in _SUPPORTED_DIALECTS:
        errors.append(
            _issue(
                "UNKNOWN_DIALECT",
                "error",
                f"Unsupported compiler dialect: {dialect}.",
                downstream_impact="Compiler cannot quote identifiers or render syntax safely.",
                suggested_action="Use the SQL Server compiler dialect.",
            )
        )
    if preflight_report is None:
        errors.append(
            _issue(
                "PREFLIGHT_MISSING",
                "error",
                "Compiler requires a preflight report.",
                downstream_impact="Compiler could receive an unchecked plan.",
                suggested_action="Run query compiler preflight before compilation.",
            )
        )
    elif (preflight_report.status, preflight_report.decision_category) not in _ACCEPTED_PREFLIGHT:
        errors.append(
            _issue(
                "PREFLIGHT_NOT_ACCEPTED",
                "error",
                "Preflight status/category is not compiler accepted.",
                downstream_impact="Compiler could produce SQL for a policy, safety, stale, or unsupported plan.",
                suggested_action="Compile only ready/safe or ready_with_warnings/safe_with_disclosure preflight outputs.",
            )
        )
    if query_intent_result.status != "ready" or query_intent_result.plan is None:
        errors.append(
            _issue(
                "QUERY_INTENT_NOT_READY",
                "error",
                "Compiler requires a ready query intent plan.",
                downstream_impact="Compiler cannot deterministically resolve selected metric references.",
                suggested_action="Resolve the query intent to ready status before compilation.",
            )
        )
    if schema_snapshot is None:
        errors.append(
            _issue(
                "SCHEMA_SNAPSHOT_MISSING",
                "error",
                "Compiler V1 requires the Technical Snapshot.",
                downstream_impact="Compiler cannot verify physical SQL Server identifiers.",
                suggested_action="Provide the matching schema snapshot used to build the graph.",
            )
        )
    if _contains_raw_sql_payload(query_intent_result):
        errors.append(
            _issue(
                "RAW_SQL_NOT_ALLOWED",
                "error",
                "Raw SQL payload is not allowed as compiler input.",
                downstream_impact="Compiler would no longer be deterministic over structured metadata.",
                suggested_action="Remove raw SQL payloads and compile from structured intent only.",
            )
        )

    trace = _initial_trace(
        query_intent_result=query_intent_result,
        preflight_report=preflight_report,
        semantic_layer=semantic_layer,
        queryability_graph=queryability_graph,
        schema_snapshot=schema_snapshot,
    )
    if errors or preflight_report is None or query_intent_result.plan is None or schema_snapshot is None:
        return _blocked(errors=errors, warnings=warnings, trace=trace)

    context_result = _build_context(
        query_intent_result=query_intent_result,
        preflight_report=preflight_report,
        semantic_layer=semantic_layer,
        queryability_graph=queryability_graph,
        schema_snapshot=schema_snapshot,
    )
    if isinstance(context_result, list):
        return _blocked(errors=[*errors, *context_result], warnings=warnings, trace=trace)
    context = context_result

    errors.extend(_validate_preflight_binding(context))
    errors.extend(_validate_artifact_binding(context))
    errors.extend(_validate_metric(context))
    errors.extend(_validate_selected_paths(context))
    errors.extend(_validate_selected_columns_against_snapshot(context))
    if errors:
        return _blocked(errors=errors, warnings=warnings, trace=_trace(context))

    errors.extend(_assign_aliases_and_joins(context))
    if errors:
        return _blocked(errors=errors, warnings=warnings, trace=_trace(context))

    metric_expr_result = _metric_expression(context)
    if isinstance(metric_expr_result, QueryCompilerIssue):
        errors.append(metric_expr_result)
        return _blocked(errors=errors, warnings=warnings, trace=_trace(context))
    metric_expr = metric_expr_result

    dimension_expr = None
    if context.plan.group_by_dimensions:
        dimension_expr_result = _dimension_expression(context)
        if isinstance(dimension_expr_result, QueryCompilerIssue):
            errors.append(dimension_expr_result)
            return _blocked(errors=errors, warnings=warnings, trace=_trace(context))
        dimension_expr = dimension_expr_result
        context.limit = min(_GROUPED_LIMIT_DEFAULT, _GROUPED_LIMIT_MAX)
        limit_param = _add_param(
            context,
            value=context.limit,
            logical_type="integer",
            source="limit",
            operator="top",
            param_context="grouped_result_limit",
        )
        select_clause = (
            f"SELECT TOP ({limit_param.name})\n"
            f"  {dimension_expr} AS [dimension_0],\n"
            f"  {metric_expr} AS [metric_value]"
        )
        context.group_by_structured = [{"expression": dimension_expr, "alias": "dimension_0"}]
        context.order_by_structured = [
            {"expression": "[metric_value]", "direction": "DESC"},
            {"expression": "[dimension_0]", "direction": "ASC"},
        ]
    else:
        select_clause = f"SELECT\n  {metric_expr} AS [metric_value]"

    errors.extend(_compile_date_range(context))
    errors.extend(_compile_filters(context))
    if errors:
        return _blocked(errors=errors, warnings=warnings, trace=_trace(context))

    source_sql = _table_sql(context, context.metric.source_table_key)
    sql_lines = [select_clause, f"FROM {source_sql} AS [{context.aliases[context.metric.source_table_key]}]"]
    sql_lines.extend(context.joins)
    if context.where_clauses:
        sql_lines.append("WHERE " + "\n  AND ".join(context.where_clauses))
    if dimension_expr is not None:
        sql_lines.append(f"GROUP BY {dimension_expr}")
        sql_lines.append("ORDER BY [metric_value] DESC, [dimension_0] ASC")

    return QueryCompilerResult(
        status="compiled",
        sql="\n".join(sql_lines),
        parameters=list(context.parameters),
        trace=_trace(context),
        errors=[],
        warnings=warnings,
    )


def _build_context(
    *,
    query_intent_result: QueryIntentResult,
    preflight_report: QueryCompilerPreflightReport,
    semantic_layer: SemanticLayer,
    queryability_graph: QueryabilityGraphArtifact,
    schema_snapshot: Any,
) -> _CompilerContext | list[QueryCompilerIssue]:
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
    snapshot_fks = {
        fk.constraint_name: fk
        for fk in getattr(schema_snapshot, "foreign_keys", [])
    }
    metrics_by_key = {str(metric.metric_key): metric for metric in semantic_layer.metrics}
    plan = query_intent_result.plan
    metric = metrics_by_key.get(str(plan.primary_metric_key))
    if metric is None:
        return [
            _issue(
                "METRIC_NOT_FOUND",
                "error",
                "Selected metric does not exist in the semantic layer.",
                metric_key=str(plan.primary_metric_key),
                downstream_impact="Compiler cannot resolve metric source metadata.",
                suggested_action="Use a preflight report generated for the active semantic layer.",
            )
        ]
    return _CompilerContext(
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


def _validate_preflight_binding(context: _CompilerContext) -> list[QueryCompilerIssue]:
    plan = context.plan
    trace = context.preflight_report.plan_trace
    issues: list[QueryCompilerIssue] = []
    if trace.selected_metric_key != str(plan.primary_metric_key):
        issues.append(_context_mismatch("Selected metric key differs from preflight.", metric_key=str(plan.primary_metric_key)))
    if trace.selected_date_column != plan.effective_date_column_key:
        issues.append(_context_mismatch("Selected date column differs from preflight.", column_key=plan.effective_date_column_key))
    trace_dimensions = [str(item.get("column_key")) for item in trace.selected_dimensions]
    plan_dimensions = [item.column_key for item in plan.group_by_dimensions]
    if trace_dimensions != plan_dimensions:
        issues.append(_context_mismatch("Selected dimensions differ from preflight."))
    trace_filters = [
        (
            str(item.get("column_key")),
            str(item.get("operator")),
            str(item.get("value_type")),
            str(item.get("value_fingerprint")),
        )
        for item in trace.selected_filters
    ]
    plan_filters = [_filter_binding_signature(item) for item in plan.filters]
    if trace_filters != plan_filters:
        issues.append(_context_mismatch("Selected filters differ from preflight."))
    trace_paths = sorted(str(item) for item in trace.selected_graph_paths)
    plan_paths = sorted(_selected_plan_edge_keys(plan))
    if trace_paths != plan_paths:
        issues.append(_context_mismatch("Selected graph paths differ from preflight."))
    cache = trace.cache_key_inputs_preview
    if cache.get("semantic_hash") != context.semantic_layer.semantic_hash:
        issues.append(_context_mismatch("Semantic hash differs from preflight."))
    if cache.get("graph_hash") != context.queryability_graph.graph_hash:
        issues.append(_context_mismatch("Graph hash differs from preflight."))
    if cache.get("snapshot_hash") != getattr(context.schema_snapshot, "snapshot_hash", None):
        issues.append(_context_mismatch("Snapshot hash differs from preflight."))
    if (context.preflight_report.status, context.preflight_report.decision_category) not in _ACCEPTED_PREFLIGHT:
        issues.append(
            _issue(
                "PREFLIGHT_NOT_ACCEPTED",
                "error",
                "Preflight status/category is not compiler accepted.",
                downstream_impact="Compiler could produce SQL for an unsafe plan.",
                suggested_action="Use only accepted preflight reports.",
            )
        )
    return issues


def _validate_artifact_binding(context: _CompilerContext) -> list[QueryCompilerIssue]:
    issues: list[QueryCompilerIssue] = []
    if context.semantic_layer.status != "active" or context.semantic_layer.freshness != "fresh":
        issues.append(
            _issue(
                "SEMANTIC_LAYER_NOT_ACTIVE",
                "error",
                "Semantic Layer must be active and fresh.",
                downstream_impact="Compiler could use stale or draft metric definitions.",
                suggested_action="Compile only against the active fresh Semantic Layer.",
            )
        )
    if context.semantic_layer.base_graph_hash != context.queryability_graph.graph_hash:
        issues.append(
            _issue(
                "QUERYABILITY_GRAPH_STALE",
                "error",
                "Semantic Layer base graph hash does not match the supplied graph.",
                downstream_impact="Compiler could resolve stable keys against the wrong graph.",
                suggested_action="Regenerate or reload matching graph and semantic artifacts.",
            )
        )
    if context.queryability_graph.status == "blocked":
        issues.append(
            _issue(
                "QUERYABILITY_GRAPH_INVALID",
                "error",
                "Queryability Graph is blocked.",
                downstream_impact="Compiler cannot trust graph references.",
                suggested_action="Rebuild the graph before compilation.",
            )
        )
    if getattr(context.schema_snapshot, "snapshot_hash", None) != context.queryability_graph.snapshot_hash:
        issues.append(
            _issue(
                "SCHEMA_SNAPSHOT_STALE",
                "error",
                "Schema snapshot hash does not match the queryability graph.",
                downstream_impact="Compiler could quote or join physical objects from the wrong snapshot.",
                suggested_action="Provide the snapshot used to build the graph.",
            )
        )
    return issues


def _validate_metric(context: _CompilerContext) -> list[QueryCompilerIssue]:
    metric = context.metric
    issues: list[QueryCompilerIssue] = []
    if metric.compiler_eligibility not in {"eligible", "eligible_with_disclosure"}:
        issues.append(
            _issue(
                "METRIC_NOT_COMPILER_ELIGIBLE",
                "error",
                "Selected metric is not compiler eligible.",
                metric_key=str(metric.metric_key),
                downstream_impact="Compiler must not compile a metric requiring clarification or marked not eligible.",
                suggested_action="Select a compiler-eligible metric.",
            )
        )
    if not metric.enabled:
        issues.append(
            _issue(
                "METRIC_DISABLED",
                "error",
                "Selected metric is disabled.",
                metric_key=str(metric.metric_key),
                downstream_impact="Compiler could expose disabled semantic definitions.",
                suggested_action="Use an enabled metric.",
            )
        )
    if metric.aggregation not in {"count", "count_distinct", "sum", "avg", "min", "max"}:
        issues.append(
            _issue(
                "UNSUPPORTED_AGGREGATION",
                "error",
                "Metric aggregation is outside Query Compiler V1 scope.",
                metric_key=str(metric.metric_key),
                downstream_impact="Compiler cannot render this aggregation deterministically.",
                suggested_action="Keep unsupported aggregations out of compiler scope.",
            )
        )
    return issues


def _validate_selected_paths(context: _CompilerContext) -> list[QueryCompilerIssue]:
    issues: list[QueryCompilerIssue] = []
    for edge_key in _selected_plan_edge_keys(context.plan):
        edge = context.edges_by_key.get(edge_key)
        if edge is None:
            issues.append(
                _issue(
                    "GRAPH_PATH_INVALID",
                    "error",
                    "Selected edge key is missing from the graph.",
                    edge_key=edge_key,
                    downstream_impact="Compiler cannot materialize the selected join path.",
                    suggested_action="Re-run preflight with matching graph metadata.",
                )
            )
            continue
        if getattr(edge, "edge_type", None) != "fk_join":
            issues.append(
                _issue(
                    "GRAPH_PATH_USES_LINEAGE",
                    "error",
                    "Selected path uses a non-FK edge.",
                    edge_key=edge_key,
                    downstream_impact="Compiler would treat lineage or provenance as join evidence.",
                    suggested_action="Use only trusted FK join paths.",
                )
            )
            continue
        if not _edge_is_compiler_safe(edge):
            issues.append(
                _issue(
                    "GRAPH_PATH_USES_UNTRUSTED_EDGE",
                    "error",
                    "Selected FK edge is not trusted/enabled/verified.",
                    edge_key=edge_key,
                    downstream_impact="Compiler could generate unsafe joins.",
                    suggested_action="Use only automatic-join-allowed FK edges.",
                )
            )
        if _node(context, edge.from_node_key).bridge_candidate or _node(context, edge.to_node_key).bridge_candidate:
            issues.append(
                _issue(
                    "GRAPH_PATH_REQUIRES_BRIDGE_POLICY",
                    "error",
                    "Selected path traverses a bridge or many-to-many candidate.",
                    edge_key=edge_key,
                    downstream_impact="Compiler could multiply rows without explicit bridge policy.",
                    suggested_action="Keep bridge paths out of V1 compiler scope.",
                )
            )
        issues.extend(_validate_snapshot_fk(context, edge))
    return issues


def _validate_selected_columns_against_snapshot(context: _CompilerContext) -> list[QueryCompilerIssue]:
    metric = context.metric
    plan = context.plan
    column_keys = [*metric.grain_column_keys]
    if metric.measure_column_key:
        column_keys.append(metric.measure_column_key)
    if plan.effective_date_column_key:
        column_keys.append(plan.effective_date_column_key)
    column_keys.extend(item.column_key for item in plan.group_by_dimensions)
    column_keys.extend(item.column_key for item in plan.filters)
    table_keys = {metric.source_table_key, metric.grain_table_key}
    issues: list[QueryCompilerIssue] = []
    for column_key in column_keys:
        node_column = context.columns_by_key.get(column_key)
        if node_column is None:
            issues.append(
                _issue(
                    "GRAPH_COLUMN_NOT_FOUND",
                    "error",
                    "Selected column is missing from the graph.",
                    column_key=column_key,
                    downstream_impact="Compiler cannot resolve a stable column key.",
                    suggested_action="Use a plan generated from the supplied graph.",
                )
            )
            continue
        node, column = node_column
        table_keys.add(node.node_key)
        if _snapshot_column(context, node, column) is None:
            issues.append(
                _issue(
                    "SCHEMA_COLUMN_NOT_FOUND",
                    "error",
                    "Selected column is missing from the Technical Snapshot.",
                    column_key=column_key,
                    physical_label=f"{node.schema_name}.{node.object_name}.{column.name}",
                    downstream_impact="Compiler cannot safely quote the physical column.",
                    suggested_action="Provide a matching schema snapshot.",
                )
            )
        if not _identifier_valid(column.name):
            issues.append(
                _issue(
                    "UNSAFE_IDENTIFIER",
                    "error",
                    "Selected column has an unsafe physical identifier.",
                    column_key=column_key,
                    physical_label=f"{node.schema_name}.{node.object_name}.{column.name}",
                    downstream_impact="Compiler cannot safely quote this physical column.",
                    suggested_action="Refresh metadata or exclude the unsafe object.",
                )
            )
        if column.queryability_status != "queryable" or column.sensitivity in {"pii", "sensitive"}:
            issues.append(
                _issue(
                    "COLUMN_NOT_COMPILER_SAFE",
                    "error",
                    "Selected column is not compiler-safe.",
                    column_key=column_key,
                    physical_label=f"{node.schema_name}.{node.object_name}.{column.name}",
                    downstream_impact="Compiler could expose excluded, PII, or sensitive data.",
                    suggested_action="Use only preflight-approved non-sensitive queryable columns.",
                )
            )
    for table_key in table_keys:
        node = context.nodes_by_key.get(table_key)
        if node is None:
            issues.append(
                _issue(
                    "GRAPH_TABLE_NOT_FOUND",
                    "error",
                    "Selected table key is missing from the graph.",
                    table_key=table_key,
                    downstream_impact="Compiler cannot resolve source table metadata.",
                    suggested_action="Use matching graph and semantic artifacts.",
                )
            )
            continue
        if _snapshot_object(context, node) is None:
            issues.append(
                _issue(
                    "SCHEMA_OBJECT_NOT_FOUND",
                    "error",
                    "Selected object is missing from the Technical Snapshot.",
                    table_key=table_key,
                    physical_label=f"{node.schema_name}.{node.object_name}",
                    downstream_impact="Compiler cannot safely quote the physical object.",
                    suggested_action="Provide a matching schema snapshot.",
                )
            )
        if not _identifier_valid(node.schema_name) or not _identifier_valid(node.object_name):
            issues.append(
                _issue(
                    "UNSAFE_IDENTIFIER",
                    "error",
                    "Selected object has an unsafe physical identifier.",
                    table_key=table_key,
                    physical_label=f"{node.schema_name}.{node.object_name}",
                    downstream_impact="Compiler cannot safely quote this physical object.",
                    suggested_action="Refresh metadata or exclude the unsafe object.",
                )
            )
    return issues


def _assign_aliases_and_joins(context: _CompilerContext) -> list[QueryCompilerIssue]:
    context.aliases[context.metric.source_table_key] = "t0"
    _record_table_ref(context, context.metric.source_table_key)
    alias_index = 1
    issues: list[QueryCompilerIssue] = []
    for edge_key in _selected_plan_edge_keys(context.plan):
        edge = context.edges_by_key[edge_key]
        from_alias = context.aliases.get(edge.from_node_key)
        to_alias = context.aliases.get(edge.to_node_key)
        if from_alias is None and to_alias is None:
            issues.append(
                _issue(
                    "JOIN_PATH_NOT_CONNECTED",
                    "error",
                    "Selected edge is not connected to an already selected table.",
                    edge_key=edge_key,
                    downstream_impact="Compiler would need to choose a path, which is out of scope.",
                    suggested_action="Provide a preflight-approved connected edge order.",
                )
            )
            continue
        if from_alias is not None and to_alias is not None:
            _record_edge_ref(context, edge)
            continue
        if from_alias is not None:
            context.aliases[edge.to_node_key] = f"t{alias_index}"
            alias_index += 1
            join_node_key = edge.to_node_key
        else:
            context.aliases[edge.from_node_key] = f"t{alias_index}"
            alias_index += 1
            join_node_key = edge.from_node_key
        _record_table_ref(context, join_node_key)
        _record_edge_ref(context, edge)
        context.joins.append(_join_sql(context, edge, join_node_key))
    return issues


def _metric_expression(context: _CompilerContext) -> str | QueryCompilerIssue:
    metric = context.metric
    source_alias = context.aliases[metric.source_table_key]
    if metric.aggregation == "count" and metric.measure_column_key is None:
        if metric.format.value_type == "count" and metric.aggregation_level in {"row", "entity"}:
            return "COUNT_BIG(*)"
        return _issue(
            "COUNT_TARGET_NOT_DECLARED",
            "error",
            "COUNT metric without measure column is not explicitly row/entity count.",
            metric_key=str(metric.metric_key),
            downstream_impact="Compiler would have to guess count semantics.",
            suggested_action="Declare row/entity count semantics or a non-null count column.",
        )
    if metric.aggregation in {"sum", "avg", "min", "max", "count_distinct", "count"} and metric.measure_column_key is None:
        return _issue(
            "MEASURE_COLUMN_REQUIRED",
            "error",
            "Metric aggregation requires a measure column.",
            metric_key=str(metric.metric_key),
            downstream_impact="Compiler cannot render a safe aggregate expression.",
            suggested_action="Use a metric with an explicit measure column.",
        )
    if metric.measure_column_key is None:
        return _issue(
            "MEASURE_COLUMN_REQUIRED",
            "error",
            "Metric has no measure column.",
            metric_key=str(metric.metric_key),
            downstream_impact="Compiler cannot render this metric.",
            suggested_action="Use a metric with structured measure evidence.",
        )
    node, column = context.columns_by_key[metric.measure_column_key]
    alias = context.aliases.get(node.node_key)
    if alias is None:
        return _issue(
            "MEASURE_TABLE_NOT_SELECTED",
            "error",
            "Measure column table is not selected.",
            column_key=metric.measure_column_key,
            downstream_impact="Compiler would need to add a join not selected by preflight.",
            suggested_action="Use a preflight-approved plan containing the measure table.",
        )
    expr = _column_expr(alias, column.name)
    _record_column_ref(context, node, column, alias)
    if metric.aggregation == "count_distinct":
        return f"COUNT(DISTINCT {expr})"
    if metric.aggregation == "count":
        snap_col = _snapshot_column(context, node, column)
        if column.nullable or getattr(snap_col, "is_nullable", True):
            return _issue(
                "COUNT_COLUMN_NULLABLE",
                "error",
                "COUNT column must be explicitly non-null.",
                column_key=metric.measure_column_key,
                downstream_impact="Compiler could count non-null values instead of rows/entities.",
                suggested_action="Use COUNT_BIG row/entity count or a non-null count column.",
            )
        return f"COUNT({expr})"
    return f"{metric.aggregation.upper()}({expr})"


def _dimension_expression(context: _CompilerContext) -> str | QueryCompilerIssue:
    dimension = context.plan.group_by_dimensions[0]
    node_column = context.columns_by_key.get(dimension.column_key)
    if node_column is None:
        return _issue(
            "DIMENSION_NOT_FOUND",
            "error",
            "Selected dimension column is missing.",
            column_key=dimension.column_key,
            downstream_impact="Compiler cannot render GROUP BY.",
            suggested_action="Use a preflight-approved dimension.",
        )
    node, column = node_column
    alias = context.aliases.get(node.node_key)
    if alias is None:
        return _issue(
            "DIMENSION_PATH_NOT_SELECTED",
            "error",
            "Dimension table is not reachable through selected paths.",
            column_key=dimension.column_key,
            downstream_impact="Compiler would need to choose an unapproved join path.",
            suggested_action="Use only preflight-selected dimension paths.",
        )
    _record_column_ref(context, node, column, alias)
    return _column_expr(alias, column.name)


def _compile_date_range(context: _CompilerContext) -> list[QueryCompilerIssue]:
    plan = context.plan
    if plan.time_range is None:
        return []
    if plan.effective_date_column_key is None:
        return [
            _issue(
                "DATE_COLUMN_NOT_FOUND",
                "error",
                "Time range requires an effective date column.",
                downstream_impact="Compiler cannot apply a structured date range.",
                suggested_action="Use a preflight plan with a selected date column.",
            )
        ]
    node_column = context.columns_by_key.get(plan.effective_date_column_key)
    if node_column is None:
        return [
            _issue(
                "DATE_COLUMN_NOT_FOUND",
                "error",
                "Effective date column is missing from the graph.",
                column_key=plan.effective_date_column_key,
                downstream_impact="Compiler cannot apply a structured date range.",
                suggested_action="Use matching graph and intent artifacts.",
            )
        ]
    node, column = node_column
    alias = context.aliases.get(node.node_key)
    if alias is None:
        return [
            _issue(
                "DATE_PATH_NOT_SELECTED",
                "error",
                "Date column table is not reachable through selected paths.",
                column_key=plan.effective_date_column_key,
                downstream_impact="Compiler would need to add an unapproved join.",
                suggested_action="Use preflight-selected date paths only.",
            )
        ]
    _record_column_ref(context, node, column, alias)
    start = _add_param(
        context,
        value=plan.time_range.start_date,
        logical_type="date",
        source="date_range",
        operator="gte",
        param_context=plan.effective_date_column_key,
    )
    end = _add_param(
        context,
        value=plan.time_range.end_date,
        logical_type="date",
        source="date_range",
        operator="lt",
        param_context=plan.effective_date_column_key,
    )
    expr = _column_expr(alias, column.name)
    context.where_clauses.append(f"{expr} >= {start.name}")
    context.where_clauses.append(f"{expr} < {end.name}")
    context.where_structured.extend(
        [
            {"column_key": plan.effective_date_column_key, "operator": "gte", "parameter": start.name},
            {"column_key": plan.effective_date_column_key, "operator": "lt", "parameter": end.name},
        ]
    )
    return []


def _compile_filters(context: _CompilerContext) -> list[QueryCompilerIssue]:
    issues: list[QueryCompilerIssue] = []
    for filter_item in context.plan.filters:
        if filter_item.operator not in _SUPPORTED_FILTER_OPERATORS:
            issues.append(
                _issue(
                    "FILTER_OPERATOR_UNSUPPORTED",
                    "error",
                    "Filter operator is outside Query Compiler V1 scope.",
                    column_key=filter_item.column_key,
                    filter_key=filter_item.column_key,
                    downstream_impact="Compiler cannot render this filter safely.",
                    suggested_action="Use a supported structured filter operator.",
                )
            )
            continue
        node_column = context.columns_by_key.get(filter_item.column_key)
        if node_column is None:
            issues.append(
                _issue(
                    "FILTER_COLUMN_NOT_FOUND",
                    "error",
                    "Filter column is missing from the graph.",
                    column_key=filter_item.column_key,
                    filter_key=filter_item.column_key,
                    downstream_impact="Compiler cannot render this filter.",
                    suggested_action="Use matching graph and intent artifacts.",
                )
            )
            continue
        node, column = node_column
        alias = context.aliases.get(node.node_key)
        if alias is None:
            issues.append(
                _issue(
                    "FILTER_PATH_NOT_SELECTED",
                    "error",
                    "Cross-table filter path was not selected by preflight.",
                    column_key=filter_item.column_key,
                    filter_key=filter_item.column_key,
                    downstream_impact="Compiler would need to add an unapproved join.",
                    suggested_action="Include the filter path in preflight-selected paths.",
                )
            )
            continue
        _record_column_ref(context, node, column, alias)
        clause_result = _filter_clause(context, filter_item, alias, column.name)
        if isinstance(clause_result, QueryCompilerIssue):
            issues.append(clause_result)
            continue
        context.where_clauses.append(clause_result)
    return issues


def _filter_clause(context: _CompilerContext, filter_item: SemanticFilter, alias: str, column_name: str) -> str | QueryCompilerIssue:
    expr = _column_expr(alias, column_name)
    op = filter_item.operator
    value = filter_item.value
    if op in {"eq", "neq"} and value is None:
        return _issue(
            "FILTER_NULL_OPERATOR_INVALID",
            "error",
            "Null comparisons require explicit is_null or is_not_null.",
            column_key=filter_item.column_key,
            filter_key=filter_item.column_key,
            downstream_impact="Compiler could render incorrect SQL null semantics.",
            suggested_action="Use is_null or is_not_null for null checks.",
        )
    if op in {"is_null", "is_not_null"}:
        if value is not None:
            return _issue(
                "FILTER_VALUE_UNSTRUCTURED",
                "error",
                "Null-check filter operators must not include a value.",
                column_key=filter_item.column_key,
                filter_key=filter_item.column_key,
                downstream_impact="Compiler cannot interpret a value for null-check operators.",
                suggested_action="Remove the filter value.",
            )
        clause = f"{expr} IS {'NOT ' if op == 'is_not_null' else ''}NULL"
        context.where_structured.append({"column_key": filter_item.column_key, "operator": op})
        return clause
    if op in {"in", "not_in"}:
        if not isinstance(value, list) or not value:
            return _issue(
                "FILTER_VALUE_UNSTRUCTURED",
                "error",
                "IN and NOT IN filters require a non-empty value list.",
                column_key=filter_item.column_key,
                filter_key=filter_item.column_key,
                downstream_impact="Compiler cannot safely render a set filter.",
                suggested_action="Provide one or more structured filter values.",
            )
        params = [
            _add_param(
                context,
                value=item,
                logical_type=filter_item.value_type,
                source="filter",
                operator=op,
                param_context=filter_item.column_key,
            )
            for item in value
        ]
        sql_op = "IN" if op == "in" else "NOT IN"
        context.where_structured.append(
            {
                "column_key": filter_item.column_key,
                "operator": op,
                "parameters": [param.name for param in params],
            }
        )
        return f"{expr} {sql_op} ({', '.join(param.name for param in params)})"
    if op == "between":
        if not isinstance(value, list) or len(value) != 2:
            return _issue(
                "FILTER_VALUE_UNSTRUCTURED",
                "error",
                "BETWEEN filter requires exactly two values.",
                column_key=filter_item.column_key,
                filter_key=filter_item.column_key,
                downstream_impact="Compiler cannot safely render the range bounds.",
                suggested_action="Provide exactly two structured values.",
            )
        low = _add_param(context, value=value[0], logical_type=filter_item.value_type, source="filter", operator="between_start", param_context=filter_item.column_key)
        high = _add_param(context, value=value[1], logical_type=filter_item.value_type, source="filter", operator="between_end", param_context=filter_item.column_key)
        context.where_structured.append({"column_key": filter_item.column_key, "operator": op, "parameters": [low.name, high.name]})
        return f"{expr} BETWEEN {low.name} AND {high.name}"
    sql_op = {
        "eq": "=",
        "neq": "<>",
        "gt": ">",
        "gte": ">=",
        "lt": "<",
        "lte": "<=",
    }[op]
    param = _add_param(context, value=value, logical_type=filter_item.value_type, source="filter", operator=op, param_context=filter_item.column_key)
    context.where_structured.append({"column_key": filter_item.column_key, "operator": op, "parameter": param.name})
    return f"{expr} {sql_op} {param.name}"


def _join_sql(context: _CompilerContext, edge: Any, join_node_key: str) -> str:
    join_node = _node(context, join_node_key)
    join_alias = context.aliases[join_node_key]
    from_alias = context.aliases[edge.from_node_key]
    to_alias = context.aliases[edge.to_node_key]
    predicates = [
        f"{_column_expr(from_alias, pair.from_column)} = {_column_expr(to_alias, pair.to_column)}"
        for pair in sorted(edge.column_pairs, key=lambda item: item.ordinal_position)
    ]
    return f"JOIN {_table_sql(context, join_node_key)} AS [{join_alias}] ON " + " AND ".join(predicates)


def _filter_raw_value(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _RAW_SQL_KEYS and item not in (None, "", []):
                return True
            if _filter_raw_value(item):
                return True
    elif isinstance(value, list):
        return any(_filter_raw_value(item) for item in value)
    return False


def _contains_raw_sql_payload(value: Any) -> bool:
    if hasattr(value, "model_dump"):
        return _filter_raw_value(value.model_dump(mode="json"))
    return _filter_raw_value(value)


def _filter_binding_signature(filter_item: Any) -> tuple[str, str, str, str]:
    return (
        str(getattr(filter_item, "column_key", None)),
        str(getattr(filter_item, "operator", None)),
        str(getattr(filter_item, "value_type", None)),
        _filter_value_fingerprint(filter_item),
    )


def _filter_value_fingerprint(filter_item: Any) -> str:
    payload = {
        "column_key": getattr(filter_item, "column_key", None),
        "operator": getattr(filter_item, "operator", None),
        "value_type": getattr(filter_item, "value_type", None),
        "value": getattr(filter_item, "value", None),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_snapshot_fk(context: _CompilerContext, edge: Any) -> list[QueryCompilerIssue]:
    fk = context.snapshot_fks.get(edge.constraint_name)
    if fk is None:
        return [
            _issue(
                "SCHEMA_FK_NOT_FOUND",
                "error",
                "Selected FK is missing from the Technical Snapshot.",
                edge_key=edge.edge_key,
                physical_label=edge.constraint_name,
                downstream_impact="Compiler cannot verify the physical join predicate.",
                suggested_action="Provide a matching snapshot containing the FK.",
            )
        ]
    from_node = _node(context, edge.from_node_key)
    to_node = _node(context, edge.to_node_key)
    expected_from = [pair.from_column for pair in sorted(edge.column_pairs, key=lambda item: item.ordinal_position)]
    expected_to = [pair.to_column for pair in sorted(edge.column_pairs, key=lambda item: item.ordinal_position)]
    if (
        fk.from_schema != from_node.schema_name
        or fk.from_table != from_node.object_name
        or fk.to_schema != to_node.schema_name
        or fk.to_table != to_node.object_name
        or list(fk.from_columns) != expected_from
        or list(fk.to_columns) != expected_to
        or getattr(fk, "is_disabled", False)
        or getattr(fk, "is_not_trusted", False)
        or not getattr(fk, "verified_by_db", True)
    ):
        return [
            _issue(
                "SCHEMA_FK_MISMATCH",
                "error",
                "Selected FK metadata does not match the Technical Snapshot.",
                edge_key=edge.edge_key,
                physical_label=edge.constraint_name,
                downstream_impact="Compiler could produce an invalid or unsafe join.",
                suggested_action="Use matching graph and snapshot metadata.",
            )
        ]
    return []


def _edge_is_compiler_safe(edge: Any) -> bool:
    return (
        getattr(edge, "edge_type", None) == "fk_join"
        and getattr(edge, "automatic_join_allowed", False)
        and getattr(edge, "verified_by_db", False)
        and getattr(edge, "enforcement_status", None) == "enabled"
        and getattr(edge, "validation_status", None) == "trusted"
    )


def _snapshot_object(context: _CompilerContext, node: Any) -> Any | None:
    return context.snapshot_objects.get((node.schema_name, node.object_name))


def _snapshot_column(context: _CompilerContext, node: Any, column: Any) -> Any | None:
    return context.snapshot_columns.get((node.schema_name, node.object_name, column.name))


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


def _node(context: _CompilerContext, node_key: str) -> Any:
    return context.nodes_by_key[node_key]


def _table_sql(context: _CompilerContext, node_key: str) -> str:
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


def _add_param(
    compiler_context: _CompilerContext,
    *,
    value: object,
    logical_type: str,
    source: CompiledParameterSource,
    operator: str,
    param_context: str,
) -> CompiledSqlParameter:
    param = CompiledSqlParameter(
        name=f"@p{len(compiler_context.parameters)}",
        value=value,
        logical_type=logical_type,
        source=source,
        operator=operator,
        context=param_context,
    )
    compiler_context.parameters.append(param)
    return param


def _record_table_ref(context: _CompilerContext, table_key: str) -> None:
    if table_key in context.table_refs:
        return
    node = context.nodes_by_key[table_key]
    context.table_refs[table_key] = CompiledSqlReference(
        ref_type="table",
        key=table_key,
        physical_label=f"{node.schema_name}.{node.object_name}",
        alias=context.aliases.get(table_key),
    )


def _record_column_ref(context: _CompilerContext, node: Any, column: Any, alias: str) -> None:
    if column.column_key in context.column_refs:
        return
    context.column_refs[column.column_key] = CompiledSqlReference(
        ref_type="column",
        key=column.column_key,
        physical_label=f"{node.schema_name}.{node.object_name}.{column.name}",
        alias=alias,
    )


def _record_edge_ref(context: _CompilerContext, edge: Any) -> None:
    if edge.edge_key in context.edge_refs:
        return
    context.edge_refs[edge.edge_key] = CompiledSqlReference(
        ref_type="edge",
        key=edge.edge_key,
        physical_label=edge.constraint_name,
    )


def _initial_trace(
    *,
    query_intent_result: QueryIntentResult,
    preflight_report: QueryCompilerPreflightReport | None,
    semantic_layer: SemanticLayer,
    queryability_graph: QueryabilityGraphArtifact,
    schema_snapshot: Any | None,
) -> QueryCompilerTrace:
    plan = query_intent_result.plan
    return QueryCompilerTrace(
        metric_key=str(plan.primary_metric_key) if plan else None,
        date_column_key=plan.effective_date_column_key if plan else None,
        dimension_keys=[item.column_key for item in plan.group_by_dimensions] if plan else [],
        filter_keys=[item.column_key for item in plan.filters] if plan else [],
        join_paths=_selected_plan_edge_keys(plan) if plan else [],
        preflight_status=preflight_report.status if preflight_report else None,
        preflight_decision_category=preflight_report.decision_category if preflight_report else None,
        semantic_hash=semantic_layer.semantic_hash,
        graph_hash=queryability_graph.graph_hash,
        snapshot_hash=getattr(schema_snapshot, "snapshot_hash", None),
    )


def _trace(context: _CompilerContext) -> QueryCompilerTrace:
    metric = context.metric
    return QueryCompilerTrace(
        metric_key=str(metric.metric_key),
        source_table_key=metric.source_table_key,
        measure_column_key=metric.measure_column_key,
        date_column_key=context.plan.effective_date_column_key,
        dimension_keys=[item.column_key for item in context.plan.group_by_dimensions],
        filter_keys=[item.column_key for item in context.plan.filters],
        join_paths=_selected_plan_edge_keys(context.plan),
        selected_tables=list(context.table_refs.values()),
        selected_columns=list(context.column_refs.values()),
        aliases=dict(sorted(context.aliases.items(), key=lambda item: item[1])),
        where_clauses_structured=list(context.where_structured),
        group_by_structured=list(context.group_by_structured),
        order_by_structured=context.order_by_structured,
        limit=context.limit,
        preflight_status=context.preflight_report.status,
        preflight_decision_category=context.preflight_report.decision_category,
        semantic_hash=context.semantic_layer.semantic_hash,
        graph_hash=context.queryability_graph.graph_hash,
        snapshot_hash=getattr(context.schema_snapshot, "snapshot_hash", None),
    )


def _blocked(
    *,
    errors: list[QueryCompilerIssue],
    warnings: list[QueryCompilerIssue],
    trace: QueryCompilerTrace,
) -> QueryCompilerResult:
    return QueryCompilerResult(
        status="blocked",
        sql=None,
        parameters=[],
        trace=trace,
        errors=errors,
        warnings=warnings,
    )


def _context_mismatch(message: str, *, metric_key: str | None = None, column_key: str | None = None) -> QueryCompilerIssue:
    return _issue(
        "PREFLIGHT_CONTEXT_MISMATCH",
        "error",
        message,
        metric_key=metric_key,
        column_key=column_key,
        downstream_impact="Compiler could reuse a preflight approval for a different plan or artifact context.",
        suggested_action="Run preflight for the exact intent, semantic layer, graph, snapshot, and policy context.",
    )


def _issue(
    code: str,
    severity: CompilerSeverity,
    message: str,
    *,
    metric_key: str | None = None,
    table_key: str | None = None,
    column_key: str | None = None,
    edge_key: str | None = None,
    filter_key: str | None = None,
    physical_label: str | None = None,
    downstream_impact: str,
    suggested_action: str,
) -> QueryCompilerIssue:
    return QueryCompilerIssue(
        code=code,
        severity=severity,
        message=message,
        metric_key=metric_key,
        table_key=table_key,
        column_key=column_key,
        edge_key=edge_key,
        filter_key=filter_key,
        physical_label=physical_label,
        downstream_impact=downstream_impact,
        suggested_action=suggested_action,
    )
