from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.models import (
    QueryIntentResult,
    QueryabilityForeignKeyEdge,
    QueryabilityGraphArtifact,
    SemanticLayer,
    SemanticMetric,
)


PreflightStatus = Literal["ready", "ready_with_warnings", "blocked"]
PreflightStageStatus = Literal["pass", "warning", "blocked"]
PreflightSeverity = Literal["error", "warning", "info"]
PreflightDecisionCategory = Literal[
    "safe",
    "safe_with_disclosure",
    "needs_policy",
    "insufficient_metadata",
    "unsafe",
    "unsupported",
    "stale",
    "invalid_artifact",
]
PreflightPolicySource = Literal[
    "semantic_layer",
    "queryability_graph",
    "semantic_invariant_report",
    "query_intent",
    "tenant_policy",
    "manual_override",
    "missing",
]

_STAGES: tuple[str, ...] = (
    "normalize_intent",
    "artifact_freshness",
    "metadata_prefetch",
    "metric_resolution",
    "date_resolution",
    "dimension_resolution",
    "filter_resolution",
    "path_resolution",
    "policy_permission_check",
    "final_decision",
)
_CATEGORY_PRECEDENCE: tuple[PreflightDecisionCategory, ...] = (
    "invalid_artifact",
    "stale",
    "unsafe",
    "unsupported",
    "insufficient_metadata",
    "needs_policy",
)
_COMPILER_ELIGIBLE = {"eligible", "eligible_with_disclosure"}
_REVENUE_OR_ORDER_CONCEPTS = {"revenue", "orders"}
_SQL_TOKENS = (
    "select ",
    "insert ",
    "update ",
    "delete ",
    "drop ",
    "truncate ",
    "merge ",
    "exec ",
    "execute ",
    " from ",
    " join ",
    "--",
    "/*",
)
_STATUS_TOKENS = (
    "status",
    "state",
    "stato",
    "annull",
    "cancel",
    "void",
    "closed",
    "chiuso",
    "draft",
    "bozza",
    "type",
    "tipo",
    "causal",
)
_AMOUNT_TOKENS = (
    "amount",
    "total",
    "subtotal",
    "gross",
    "net",
    "tax",
    "vat",
    "freight",
    "discount",
    "impon",
    "totale",
    "iva",
    "sconto",
    "trasporto",
)
_CURRENCY_TOKENS = ("currency", "valuta", "divisa", "exchange", "cambio")
_BUSINESS_DATE_TOKENS = (
    "order",
    "invoice",
    "doc",
    "document",
    "posting",
    "shipment",
    "payment",
    "data",
    "fattura",
    "documento",
    "registrazione",
)
_AUDIT_DATE_TOKENS = (
    "modified",
    "updated",
    "created",
    "rowversion",
    "lastchanged",
    "lastupdated",
    "modifica",
)
_PII_TOKENS = (
    "email",
    "mail",
    "phone",
    "telefono",
    "fiscal",
    "codicefiscale",
    "codice_fiscale",
    "piva",
    "partitaiva",
    "partita_iva",
    "iban",
    "pec",
)
_UNSUPPORTED_RAW_SQL_KEYS = {
    "sql",
    "raw_sql",
    "native_sql",
    "ref_sql",
    "query",
    "transform_sql",
}


@dataclass(frozen=True)
class QueryCompilerPreflightIssue:
    stage: str
    code: str
    severity: PreflightSeverity
    message: str
    metric_key: str | None = None
    concept_ref: str | None = None
    variant: str | None = None
    table_key: str | None = None
    column_key: str | None = None
    edge_key: str | None = None
    filter_key: str | None = None
    physical_label: str | None = None
    policy_source: PreflightPolicySource = "missing"
    downstream_impact: str = ""
    suggested_action: str = ""


@dataclass(frozen=True)
class QueryCompilerPreflightStageResult:
    stage: str
    status: PreflightStageStatus
    issues: list[QueryCompilerPreflightIssue]
    selected_references: list[str]


@dataclass(frozen=True)
class QueryCompilerPreflightSummary:
    stage_count: int
    passed_stage_count: int
    warning_stage_count: int
    blocked_stage_count: int
    error_count: int
    warning_count: int
    info_count: int
    selected_reference_count: int


@dataclass(frozen=True)
class QueryCompilerPreflightPlanTrace:
    selected_metric_key: str | None = None
    concept_ref: str | None = None
    variant: str | None = None
    selected_grain: list[str] = field(default_factory=list)
    selected_date_column: str | None = None
    selected_dimensions: list[dict[str, object]] = field(default_factory=list)
    selected_filters: list[dict[str, object]] = field(default_factory=list)
    selected_graph_paths: list[str] = field(default_factory=list)
    required_policies: list[str] = field(default_factory=list)
    active_disclosures: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    compiler_input_preview: dict[str, object] = field(default_factory=dict)
    selected_segments: list[dict[str, object]] = field(default_factory=list)
    expanded_segment_filters: list[dict[str, object]] = field(default_factory=list)
    segment_policy_sources: list[str] = field(default_factory=list)
    cache_key_inputs_preview: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class QueryCompilerPreflightReport:
    status: PreflightStatus
    decision_category: PreflightDecisionCategory
    errors: list[QueryCompilerPreflightIssue]
    warnings: list[QueryCompilerPreflightIssue]
    infos: list[QueryCompilerPreflightIssue]
    summary: QueryCompilerPreflightSummary
    blocking_codes: list[str]
    plan_trace: QueryCompilerPreflightPlanTrace
    stage_results: list[QueryCompilerPreflightStageResult]

    def to_debug_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class _PrefetchedMetadata:
    selected_metric: SemanticMetric | None = None
    selected_source_node: Any | None = None
    selected_measure_column: tuple[Any, Any] | None = None
    selected_grain_columns: list[tuple[Any, Any]] = field(default_factory=list)
    selected_date_column: tuple[Any, Any] | None = None
    selected_dimensions: list[tuple[Any, Any, Any]] = field(default_factory=list)
    selected_filters: list[tuple[Any, Any, Any]] = field(default_factory=list)
    selected_edges: list[Any] = field(default_factory=list)


@dataclass
class _PreflightContext:
    query_intent_result: QueryIntentResult
    semantic_layer: SemanticLayer
    queryability_graph: QueryabilityGraphArtifact
    graph_validation_report: Any
    semantic_invariant_report: Any
    schema_snapshot: Any | None
    policy: Any | None
    snapshot_checks_applicable: bool
    metrics_by_key: dict[str, SemanticMetric]
    concepts_by_key: dict[str, Any]
    nodes_by_key: dict[str, Any]
    columns_by_key: dict[str, tuple[Any, Any]]
    edges_by_key: dict[str, Any]
    snapshot_objects_by_key: dict[tuple[str, str], Any]
    snapshot_columns_by_key: dict[tuple[str, str, str], Any]
    snapshot_fks_by_key: dict[str, Any]
    prefetched: _PrefetchedMetadata = field(default_factory=_PrefetchedMetadata)

    @property
    def selected_metric(self) -> SemanticMetric | None:
        return self.prefetched.selected_metric

    @property
    def plan(self):
        return self.query_intent_result.plan


def validate_query_compiler_preflight(
    query_intent_result: QueryIntentResult,
    semantic_layer: SemanticLayer,
    queryability_graph: QueryabilityGraphArtifact,
    graph_validation_report,
    semantic_invariant_report,
    schema_snapshot=None,
    policy=None,
    *,
    snapshot_checks_applicable: bool = True,
) -> QueryCompilerPreflightReport:
    context = _context(
        query_intent_result=query_intent_result,
        semantic_layer=semantic_layer,
        queryability_graph=queryability_graph,
        graph_validation_report=graph_validation_report,
        semantic_invariant_report=semantic_invariant_report,
        schema_snapshot=schema_snapshot,
        policy=policy,
        snapshot_checks_applicable=snapshot_checks_applicable,
    )
    stage_results = [
        _run_stage("normalize_intent", _stage_normalize_intent, context),
        _run_stage("artifact_freshness", _stage_artifact_freshness, context),
        _run_stage("metadata_prefetch", _stage_metadata_prefetch, context),
        _run_stage("metric_resolution", _stage_metric_resolution, context),
        _run_stage("date_resolution", _stage_date_resolution, context),
        _run_stage("dimension_resolution", _stage_dimension_resolution, context),
        _run_stage("filter_resolution", _stage_filter_resolution, context),
        _run_stage("path_resolution", _stage_path_resolution, context),
        _run_stage("policy_permission_check", _stage_policy_permission_check, context),
    ]
    stage_results.append(_final_decision_stage(stage_results, context))
    return _report(stage_results, context)


def _context(
    *,
    query_intent_result: QueryIntentResult,
    semantic_layer: SemanticLayer,
    queryability_graph: QueryabilityGraphArtifact,
    graph_validation_report,
    semantic_invariant_report,
    schema_snapshot,
    policy,
    snapshot_checks_applicable: bool,
) -> _PreflightContext:
    return _PreflightContext(
        query_intent_result=query_intent_result,
        semantic_layer=semantic_layer,
        queryability_graph=queryability_graph,
        graph_validation_report=graph_validation_report,
        semantic_invariant_report=semantic_invariant_report,
        schema_snapshot=schema_snapshot,
        policy=policy,
        snapshot_checks_applicable=snapshot_checks_applicable,
        metrics_by_key={str(metric.metric_key): metric for metric in semantic_layer.metrics},
        concepts_by_key={
            str(concept.business_concept_key): concept
            for concept in semantic_layer.business_concepts
        },
        nodes_by_key={node.node_key: node for node in queryability_graph.nodes},
        columns_by_key={
            column.column_key: (node, column)
            for node in queryability_graph.nodes
            for column in node.columns
        },
        edges_by_key={edge.edge_key: edge for edge in queryability_graph.edges},
        snapshot_objects_by_key=_snapshot_objects(schema_snapshot),
        snapshot_columns_by_key=_snapshot_columns(schema_snapshot),
        snapshot_fks_by_key=_snapshot_fks(schema_snapshot),
    )


def _stage_normalize_intent(
    context: _PreflightContext,
) -> tuple[list[QueryCompilerPreflightIssue], list[str]]:
    result = context.query_intent_result
    refs: list[str] = []
    issues: list[QueryCompilerPreflightIssue] = []
    if result.status != "ready":
        issues.append(
            _issue(
                stage="normalize_intent",
                code=_query_intent_scope_code(result),
                severity="error",
                message="Query Intent result is not ready for compilation.",
                policy_source="query_intent",
                downstream_impact="Compiler would receive an unsupported or unresolved intent.",
                suggested_action="Resolve or block the intent before compiler preflight.",
            )
        )
        return issues, refs
    if result.plan is None:
        issues.append(
            _issue(
                stage="normalize_intent",
                code="QUERY_INTENT_NOT_READY",
                severity="error",
                message="Ready Query Intent result does not contain a plan.",
                policy_source="query_intent",
                downstream_impact="Compiler cannot build a deterministic input.",
                suggested_action="Reject malformed intent artifacts.",
            )
        )
        return issues, refs
    refs.append(f"metric:{result.plan.primary_metric_key}")
    refs.append(f"concept:{result.plan.requested_concept_ref}")
    refs.append(f"variant:{result.plan.selected_variant}")
    if _contains_sql_payload(result.model_dump(mode="json")):
        issues.append(
            _issue(
                stage="normalize_intent",
                code="SQL_PAYLOAD_NOT_ALLOWED",
                severity="error",
                message="Query Intent artifact contains raw SQL-like payload.",
                metric_key=str(result.plan.primary_metric_key),
                concept_ref=result.plan.requested_concept_ref,
                variant=result.plan.selected_variant,
                policy_source="query_intent",
                downstream_impact="Preflight must validate structured intent, not SQL supplied by AI or users.",
                suggested_action="Strip SQL payloads and keep this request out of compiler scope.",
            )
        )
    return issues, refs


def _stage_artifact_freshness(
    context: _PreflightContext,
) -> tuple[list[QueryCompilerPreflightIssue], list[str]]:
    issues: list[QueryCompilerPreflightIssue] = []
    refs = [
        f"semantic_hash:{context.semantic_layer.semantic_hash}",
        f"graph_hash:{context.queryability_graph.graph_hash}",
        f"policy_hash:{context.semantic_layer.base_policy_hash}",
    ]
    graph_status = getattr(context.graph_validation_report, "status", None)
    if graph_status == "invalid":
        issues.append(
            _issue(
                stage="artifact_freshness",
                code="QUERYABILITY_GRAPH_INVALID",
                severity="error",
                message="Queryability Graph validation report is invalid.",
                policy_source="queryability_graph",
                downstream_impact="Compiler path and column references cannot be trusted.",
                suggested_action="Fix graph invariant errors before compiler preflight.",
            )
        )
    if context.semantic_layer.base_graph_hash != context.queryability_graph.graph_hash:
        issues.append(
            _issue(
                stage="artifact_freshness",
                code="QUERYABILITY_GRAPH_STALE",
                severity="error",
                message="Semantic layer base graph hash does not match the supplied graph.",
                policy_source="semantic_layer",
                downstream_impact="Compiler could resolve metrics against stale graph metadata.",
                suggested_action="Regenerate or rebase the semantic layer on the current graph.",
            )
        )
    policy_hash = getattr(context.policy, "policy_hash", None)
    if policy_hash is not None and context.semantic_layer.base_policy_hash != policy_hash:
        issues.append(
            _issue(
                stage="artifact_freshness",
                code="SEMANTIC_LAYER_STALE",
                severity="error",
                message="Semantic layer base policy hash does not match supplied policy.",
                policy_source="tenant_policy",
                downstream_impact="Compiler could apply stale policy semantics.",
                suggested_action="Revalidate semantic layer against the current policy.",
            )
        )
    if context.semantic_layer.status != "active":
        issues.append(
            _issue(
                stage="artifact_freshness",
                code="SEMANTIC_LAYER_NOT_ACTIVE",
                severity="error",
                message="Semantic layer is not active.",
                policy_source="semantic_layer",
                downstream_impact="Compiler must not use draft/proposed/archived semantic artifacts.",
                suggested_action="Activate a validated semantic layer before compilation.",
            )
        )
    if context.semantic_layer.freshness != "fresh":
        issues.append(
            _issue(
                stage="artifact_freshness",
                code="SEMANTIC_LAYER_STALE",
                severity="error",
                message="Semantic layer freshness is stale.",
                policy_source="semantic_layer",
                downstream_impact="Compiler could use outdated metric definitions.",
                suggested_action="Regenerate or revalidate the semantic layer.",
            )
        )
    if context.semantic_layer.validation_report.status == "blocked":
        issues.append(
            _issue(
                stage="artifact_freshness",
                code="SEMANTIC_VALIDATION_BLOCKED",
                severity="error",
                message="Semantic validation report is blocked.",
                policy_source="semantic_layer",
                downstream_impact="Compiler would consume a known-invalid semantic layer.",
                suggested_action="Resolve semantic validation blockers first.",
            )
        )
    if context.semantic_layer.quality_report.status != "passed":
        issues.append(
            _issue(
                stage="artifact_freshness",
                code="SEMANTIC_QUALITY_GATE_NOT_PASSED",
                severity="error",
                message="Semantic quality gate has not passed.",
                policy_source="semantic_layer",
                downstream_impact="Compiler readiness depends on quality-gated semantic artifacts.",
                suggested_action="Pass quality gate before compiler preflight.",
            )
        )
    invariant_errors = list(getattr(context.semantic_invariant_report, "errors", []))
    for invariant in invariant_errors:
        issues.append(
            _issue(
                stage="artifact_freshness",
                code="SEMANTIC_INVARIANT_ERROR",
                severity="error",
                message=f"Semantic invariant error: {getattr(invariant, 'code', 'UNKNOWN')}.",
                metric_key=getattr(invariant, "metric_key", None),
                column_key=getattr(invariant, "column_key", None),
                edge_key=getattr(invariant, "edge_key", None),
                physical_label=getattr(invariant, "physical_label", None),
                policy_source="semantic_invariant_report",
                downstream_impact=getattr(invariant, "downstream_impact", "")
                or "Compiler readiness invariant failed.",
                suggested_action=getattr(invariant, "suggested_action", "")
                or "Resolve semantic invariant errors before compiling.",
            )
        )
    if context.schema_snapshot is None and context.snapshot_checks_applicable:
        issues.append(
            _issue(
                stage="artifact_freshness",
                code="SCHEMA_SNAPSHOT_MISSING",
                severity="warning",
                message="Technical Snapshot was not supplied to preflight.",
                policy_source="missing",
                downstream_impact="Snapshot-specific object/FK/type checks cannot be independently verified.",
                suggested_action="Supply the matching Technical Snapshot for clean compiler readiness.",
            )
        )
        return issues, refs
    if context.schema_snapshot is None:
        return issues, refs
    coverage_status = str(getattr(context.schema_snapshot, "coverage_status", "ok"))
    if coverage_status == "blocked":
        issues.append(
            _issue(
                stage="artifact_freshness",
                code="SCHEMA_SNAPSHOT_BLOCKED",
                severity="error",
                message="Technical Snapshot coverage status is blocked.",
                policy_source="queryability_graph",
                downstream_impact="Compiler cannot trust incomplete base metadata.",
                suggested_action="Fix snapshot introspection coverage before compiling.",
            )
        )
    elif coverage_status in {"partial", "warning"}:
        issues.append(
            _issue(
                stage="artifact_freshness",
                code="SCHEMA_COVERAGE_PARTIAL",
                severity="warning",
                message="Technical Snapshot coverage is partial.",
                policy_source="queryability_graph",
                downstream_impact="Compilation is safe only if selected metadata is unaffected.",
                suggested_action="Review selected metadata and coverage warnings.",
            )
        )
    if getattr(context.schema_snapshot, "snapshot_hash", None) not in {
        None,
        context.queryability_graph.snapshot_hash,
    }:
        issues.append(
            _issue(
                stage="artifact_freshness",
                code="SCHEMA_SNAPSHOT_STALE",
                severity="error",
                message="Technical Snapshot hash differs from graph snapshot hash.",
                policy_source="queryability_graph",
                downstream_impact="Compiler could combine a graph with the wrong snapshot.",
                suggested_action="Use the snapshot that produced the supplied graph.",
            )
        )
    return issues, refs


def _stage_metadata_prefetch(
    context: _PreflightContext,
) -> tuple[list[QueryCompilerPreflightIssue], list[str]]:
    refs: list[str] = []
    issues: list[QueryCompilerPreflightIssue] = []
    plan = context.plan
    if plan is None:
        return issues, refs
    metric_key = str(plan.primary_metric_key)
    metric = context.metrics_by_key.get(metric_key)
    if metric is None:
        issues.append(
            _issue(
                stage="metadata_prefetch",
                code="METRIC_NOT_FOUND",
                severity="error",
                message="Selected metric key is not present in the Semantic Layer.",
                metric_key=metric_key,
                concept_ref=plan.requested_concept_ref,
                variant=plan.selected_variant,
                policy_source="semantic_layer",
                downstream_impact="Compiler cannot resolve selected metric metadata.",
                suggested_action="Resolve the intent against the active semantic layer.",
            )
        )
        return issues, refs
    context.prefetched.selected_metric = metric
    refs.append(f"metric:{metric_key}")
    source_node = context.nodes_by_key.get(metric.source_table_key)
    if source_node is None:
        issues.append(_missing_graph_ref("metadata_prefetch", "source table", metric, table_key=metric.source_table_key))
    else:
        context.prefetched.selected_source_node = source_node
        refs.append(f"table:{metric.source_table_key}")
    if metric.measure_column_key is not None:
        measure_ref = context.columns_by_key.get(metric.measure_column_key)
        if measure_ref is None:
            issues.append(_missing_graph_ref("metadata_prefetch", "measure column", metric, column_key=metric.measure_column_key))
        else:
            context.prefetched.selected_measure_column = measure_ref
            refs.append(f"column:{metric.measure_column_key}")
    for grain_key in metric.grain_column_keys:
        grain_ref = context.columns_by_key.get(grain_key)
        if grain_ref is None:
            issues.append(_missing_graph_ref("metadata_prefetch", "grain column", metric, column_key=grain_key))
        else:
            context.prefetched.selected_grain_columns.append(grain_ref)
            refs.append(f"grain_column:{grain_key}")
    if plan.effective_date_column_key:
        date_ref = context.columns_by_key.get(plan.effective_date_column_key)
        if date_ref is None:
            issues.append(
                _issue(
                    stage="metadata_prefetch",
                    code="DATE_COLUMN_NOT_FOUND",
                    severity="error",
                    message="Selected date column key is missing from the graph.",
                    metric_key=metric_key,
                    concept_ref=plan.requested_concept_ref,
                    variant=plan.selected_variant,
                    column_key=plan.effective_date_column_key,
                    policy_source="queryability_graph",
                    downstream_impact="Compiler cannot apply time range filters safely.",
                    suggested_action="Resolve intent against a semantic layer with a valid date column.",
                )
            )
        else:
            context.prefetched.selected_date_column = date_ref
            refs.append(f"date_column:{plan.effective_date_column_key}")
    for dimension in plan.group_by_dimensions:
        dim_ref = context.columns_by_key.get(dimension.column_key)
        if dim_ref is None:
            issues.append(
                _issue(
                    stage="metadata_prefetch",
                    code="DIMENSION_NOT_FOUND",
                    severity="error",
                    message="Selected dimension column key is missing from the graph.",
                    metric_key=metric_key,
                    concept_ref=plan.requested_concept_ref,
                    variant=plan.selected_variant,
                    column_key=dimension.column_key,
                    policy_source="queryability_graph",
                    downstream_impact="Compiler cannot group by an unknown dimension.",
                    suggested_action="Resolve the intent with a valid graph dimension.",
                )
            )
        else:
            context.prefetched.selected_dimensions.append((*dim_ref, dimension))
            refs.append(f"dimension:{dimension.column_key}")
    for filter_item in plan.filters:
        filter_ref = context.columns_by_key.get(filter_item.column_key)
        if filter_ref is None:
            issues.append(
                _issue(
                    stage="metadata_prefetch",
                    code="FILTER_COLUMN_NOT_FOUND",
                    severity="error",
                    message="Selected filter column key is missing from the graph.",
                    metric_key=metric_key,
                    concept_ref=plan.requested_concept_ref,
                    variant=plan.selected_variant,
                    column_key=filter_item.column_key,
                    filter_key=filter_item.column_key,
                    policy_source="queryability_graph",
                    downstream_impact="Compiler cannot filter on an unknown column.",
                    suggested_action="Resolve the intent with a valid filter column.",
                )
            )
        else:
            context.prefetched.selected_filters.append((*filter_ref, filter_item))
            refs.append(f"filter:{filter_item.column_key}")
    for edge_key in _selected_edge_keys(context):
        edge = context.edges_by_key.get(edge_key)
        if edge is None:
            issues.append(
                _issue(
                    stage="metadata_prefetch",
                    code="GRAPH_PATH_INVALID",
                    severity="error",
                    message="Selected path edge key is missing from the graph.",
                    metric_key=metric_key,
                    concept_ref=plan.requested_concept_ref,
                    variant=plan.selected_variant,
                    edge_key=edge_key,
                    policy_source="queryability_graph",
                    downstream_impact="Compiler cannot materialize a selected path.",
                    suggested_action="Regenerate semantic paths from the current graph.",
                )
            )
        else:
            context.prefetched.selected_edges.append(edge)
            refs.append(f"edge:{edge_key}")
    if context.schema_snapshot is not None:
        issues.extend(_selected_snapshot_issues(context))
    return issues, refs


def _stage_metric_resolution(
    context: _PreflightContext,
) -> tuple[list[QueryCompilerPreflightIssue], list[str]]:
    metric = context.selected_metric
    if metric is None:
        return [], []
    concept = context.concepts_by_key.get(str(metric.business_concept_key))
    refs = [f"metric:{metric.metric_key}"]
    issues: list[QueryCompilerPreflightIssue] = []
    if metric.compiler_eligibility not in _COMPILER_ELIGIBLE:
        issues.append(
            _metric_issue(
                "metric_resolution",
                "METRIC_NOT_COMPILER_ELIGIBLE",
                "error",
                "Selected metric is not compiler eligible.",
                metric,
                concept_ref=getattr(concept, "canonical_name", None),
                policy_source="semantic_layer",
                downstream_impact="Compiler must not use metrics marked not eligible or clarification required.",
                suggested_action="Choose an eligible metric or resolve the semantic ambiguity first.",
            )
        )
    if metric.enabled is False:
        issues.append(
            _metric_issue(
                "metric_resolution",
                "METRIC_NOT_COMPILER_ELIGIBLE",
                "error",
                "Selected metric is disabled.",
                metric,
                concept_ref=getattr(concept, "canonical_name", None),
                policy_source="semantic_layer",
                downstream_impact="Compiler must not use disabled metrics.",
                suggested_action="Use an enabled metric.",
            )
        )
    for ref in [context.prefetched.selected_measure_column, *context.prefetched.selected_grain_columns]:
        if ref is None:
            continue
        node, column = ref
        issues.extend(
            _column_safety_issues(
                stage="metric_resolution",
                code_prefix="METRIC_SOURCE",
                metric=metric,
                node=node,
                column=column,
                purpose="metric source/grain",
                pii_requires_policy=False,
            )
        )
    source_node = context.prefetched.selected_source_node
    if source_node is not None:
        if not source_node.candidate_keys:
            issues.append(
                _metric_issue(
                    "metric_resolution",
                    "TABLE_WITHOUT_PK_UNSAFE_FOR_GRAIN",
                    "error",
                    "Selected metric source table has no candidate key for deterministic grain.",
                    metric,
                    policy_source="queryability_graph",
                    downstream_impact="Compiler cannot prove aggregate grain or row identity.",
                    suggested_action="Add a candidate key or explicit grain policy before compiling.",
                )
            )
        elif not _grain_matches_candidate_key(source_node, metric.grain_column_keys):
            issues.append(
                _metric_issue(
                    "metric_resolution",
                    "METRIC_GRAIN_INVALID",
                    "error",
                    "Selected metric grain does not match a graph candidate key.",
                    metric,
                    policy_source="semantic_layer",
                    downstream_impact="Compiler aggregation could duplicate or collapse rows.",
                    suggested_action="Use candidate-key grain columns or explicit grain policy.",
                )
            )
        concept = context.concepts_by_key.get(str(metric.business_concept_key))
        if (
            getattr(concept, "canonical_name", None) == "revenue"
            and len(_amount_like_columns(source_node)) > 1
            and _amount_ambiguity_is_silent(metric)
            and not _has_disclosure(context, "amount")
            and not _policy_value(context.policy, "amount_overrides")
        ):
            issues.append(
                _metric_issue(
                    "metric_resolution",
                    "AMOUNT_SEMANTIC_AMBIGUITY_NOT_RECORDED",
                    "error",
                    "Multiple amount-like columns exist without explicit revenue amount policy or disclosure.",
                    metric,
                    policy_source="missing",
                    downstream_impact="Compiler could silently use gross, net, tax, freight, or discount as revenue.",
                    suggested_action="Resolve amount semantics through policy or semantic disclosure.",
                )
            )
    if metric.aggregation in {"sum", "avg", "min", "max", "count_distinct"} and metric.measure_column_key is None:
        issues.append(
            _metric_issue(
                "metric_resolution",
                "GRAPH_REFERENCE_INVALID",
                "error",
                "Selected metric aggregation requires a measure column.",
                metric,
                policy_source="semantic_layer",
                downstream_impact="Compiler cannot form a structured aggregate input.",
                suggested_action="Use a metric with an explicit source column.",
            )
        )
    if _contains_sql_payload(metric.model_dump(mode="json")):
        issues.append(
            _metric_issue(
                "metric_resolution",
                "RAW_SQL_NOT_ALLOWED",
                "error",
                "Selected metric contains raw SQL-like semantic payload.",
                metric,
                policy_source="semantic_layer",
                downstream_impact="Compiler readiness requires structured semantic objects.",
                suggested_action="Reject raw SQL semantic objects until a dedicated validator exists.",
            )
        )
    if metric.format.value_type == "currency":
        if metric.format.currency:
            issues.append(
                _metric_issue(
                    "metric_resolution",
                    "CURRENCY_POLICY_DERIVED",
                    "info",
                    "Currency context is available for the selected metric.",
                    metric,
                    policy_source="semantic_layer",
                    downstream_impact="Compiler can preserve monetary context in result metadata.",
                    suggested_action="Keep currency explicit or policy-derived.",
                )
            )
        elif _policy_value(context.policy, "single_currency") or context.semantic_layer.semantic_policy_snapshot.default_currency:
            issues.append(
                _metric_issue(
                    "metric_resolution",
                    "CURRENCY_POLICY_DERIVED",
                    "warning",
                    "Currency is derived from policy rather than the metric itself.",
                    metric,
                    policy_source="tenant_policy",
                    downstream_impact="Compiler output depends on tenant-level currency policy.",
                    suggested_action="Disclose policy-derived currency in compiled results.",
                )
            )
        else:
            issues.append(
                _metric_issue(
                    "metric_resolution",
                    "CURRENCY_MISSING",
                    "error",
                    "Currency metric has no explicit or policy-derived currency.",
                    metric,
                    policy_source="missing",
                    downstream_impact="Compiler output would omit required monetary context.",
                    suggested_action="Add currency policy or require clarification.",
                )
            )
    if metric.compiler_eligibility == "eligible_with_disclosure":
        issues.append(
            _metric_issue(
                "metric_resolution",
                "METRIC_ELIGIBLE_WITH_DISCLOSURE",
                "warning",
                "Selected metric is eligible with disclosure.",
                metric,
                concept_ref=getattr(concept, "canonical_name", None),
                policy_source="semantic_layer",
                downstream_impact="Compiler result must carry semantic disclosure.",
                suggested_action="Include active disclosures in the compiler input metadata.",
            )
        )
    return issues, refs


def _stage_date_resolution(
    context: _PreflightContext,
) -> tuple[list[QueryCompilerPreflightIssue], list[str]]:
    metric = context.selected_metric
    plan = context.plan
    if metric is None or plan is None:
        return [], []
    refs: list[str] = []
    issues: list[QueryCompilerPreflightIssue] = []
    if plan.time_range is None and plan.effective_date_column_key is None:
        return issues, refs
    if context.prefetched.selected_date_column is None:
        issues.append(
            _metric_issue(
                "date_resolution",
                "DATE_COLUMN_NOT_FOUND",
                "error",
                "Time-filtered intent has no resolvable date column.",
                metric,
                column_key=plan.effective_date_column_key,
                policy_source="queryability_graph",
                downstream_impact="Compiler cannot apply time filters safely.",
                suggested_action="Resolve a valid business date before compiling.",
            )
        )
        return issues, refs
    node, column = context.prefetched.selected_date_column
    refs.append(f"date_column:{column.column_key}")
    issues.extend(
        _column_safety_issues(
            stage="date_resolution",
            code_prefix="DATE",
            metric=metric,
            node=node,
            column=column,
            purpose="date",
            pii_requires_policy=False,
        )
    )
    if column.technical_role != "date":
        issues.append(
            _metric_issue(
                "date_resolution",
                "DATE_COLUMN_NOT_QUERYABLE",
                "error",
                "Selected date column is not tagged as a date.",
                metric,
                column_key=column.column_key,
                physical_label=_column_label(node, column),
                policy_source="queryability_graph",
                downstream_impact="Compiler time filters could be applied to non-date data.",
                suggested_action="Select a queryable date column.",
            )
        )
    date_edges = [
        edge
        for edge in context.prefetched.selected_edges
        if node.node_key in {getattr(edge, "from_node_key", None), getattr(edge, "to_node_key", None)}
    ]
    if node.node_key != metric.source_table_key and not date_edges:
        issues.append(
            _metric_issue(
                "date_resolution",
                "DATE_PATH_INVALID",
                "error",
                "Selected date column is on another table without a selected trusted path.",
                metric,
                column_key=column.column_key,
                physical_label=_column_label(node, column),
                policy_source="queryability_graph",
                downstream_impact="Compiler cannot safely join to the date table.",
                suggested_action="Add a trusted date path or require clarification.",
            )
        )
    source_node = context.nodes_by_key.get(metric.source_table_key)
    business_dates = _date_columns(source_node, audit=False) if source_node else []
    if _is_audit_date(column.name) and business_dates:
        severity = "warning" if _has_disclosure(context, "date") else "error"
        issues.append(
            _metric_issue(
                "date_resolution",
                "AUDIT_DATE_USED_AS_BUSINESS_DEFAULT",
                severity,
                "Selected business date looks like an audit/technical date.",
                metric,
                column_key=column.column_key,
                physical_label=_column_label(node, column),
                policy_source="semantic_layer" if severity == "warning" else "missing",
                downstream_impact="Compiler time filters could answer modification timing instead of business timing.",
                suggested_action="Select a business date or disclose the audit-date semantics.",
            )
        )
    if source_node is not None and len(business_dates) > 1 and not _has_disclosure(context, "date") and not _policy_value(context.policy, "business_date_overrides"):
        issues.append(
            _metric_issue(
                "date_resolution",
                "MULTIPLE_DATE_CANDIDATES_REQUIRE_CLARIFICATION",
                "error",
                "Multiple plausible business date columns exist without policy/disclosure.",
                metric,
                policy_source="missing",
                downstream_impact="Compiler could apply filters to the wrong date semantics.",
                suggested_action="Add semantic ambiguity, disclosure, or business-date policy.",
            )
        )
    return issues, refs


def _stage_dimension_resolution(
    context: _PreflightContext,
) -> tuple[list[QueryCompilerPreflightIssue], list[str]]:
    metric = context.selected_metric
    if metric is None:
        return [], []
    refs: list[str] = []
    issues: list[QueryCompilerPreflightIssue] = []
    for node, column, dimension in context.prefetched.selected_dimensions:
        refs.append(f"dimension:{column.column_key}")
        issues.extend(
            _column_safety_issues(
                stage="dimension_resolution",
                code_prefix="DIMENSION",
                metric=metric,
                node=node,
                column=column,
                purpose="dimension",
                pii_requires_policy=True,
            )
        )
        compatibility = _dimension_compatibility(metric, column.column_key)
        edge_path = list(getattr(dimension, "edge_path", [])) or list(getattr(compatibility, "edge_path", []))
        if compatibility is None:
            issues.append(
                _metric_issue(
                    "dimension_resolution",
                    "DIMENSION_PATH_INVALID",
                    "error",
                    "Selected dimension is not declared compatible with the selected metric.",
                    metric,
                    column_key=column.column_key,
                    physical_label=_column_label(node, column),
                    policy_source="semantic_layer",
                    downstream_impact="Compiler could group at an unsafe grain.",
                    suggested_action="Use a semantic-compatible dimension or define explicit policy.",
                )
            )
        elif compatibility.safety != "safe":
            issues.append(
                _metric_issue(
                    "dimension_resolution",
                    "UNSAFE_FANOUT_DIMENSION",
                    "error",
                    "Selected dimension is forbidden for the selected metric.",
                    metric,
                    column_key=column.column_key,
                    physical_label=_column_label(node, column),
                    policy_source="semantic_layer",
                    downstream_impact="Compiler would produce unsafe grouped results.",
                    suggested_action="Use a compatible metric or dimension.",
                )
            )
        if _path_has_parent_to_child(metric, edge_path, context):
            issues.append(
                _metric_issue(
                    "dimension_resolution",
                    "HEADER_METRIC_DETAIL_DIMENSION_REQUIRES_ALLOCATION",
                    "error",
                    "Metric grain would fan out through the selected dimension path.",
                    metric,
                    column_key=column.column_key,
                    policy_source="semantic_layer",
                    downstream_impact="Compiler could duplicate header-grain amounts across child rows.",
                    suggested_action="Use a detail-grain metric or define explicit allocation policy.",
                )
            )
    return issues, refs


def _stage_filter_resolution(
    context: _PreflightContext,
) -> tuple[list[QueryCompilerPreflightIssue], list[str]]:
    metric = context.selected_metric
    if metric is None:
        return [], []
    refs: list[str] = []
    issues: list[QueryCompilerPreflightIssue] = []
    for node, column, filter_item in context.prefetched.selected_filters:
        refs.append(f"filter:{column.column_key}")
        issues.extend(
            _column_safety_issues(
                stage="filter_resolution",
                code_prefix="FILTER",
                metric=metric,
                node=node,
                column=column,
                purpose="filter",
                pii_requires_policy=True,
                filter_key=column.column_key,
            )
        )
        if filter_item.value_type in {"string", "integer", "decimal", "boolean", "date", "datetime"} and filter_item.operator in {"is_null", "is_not_null"}:
            continue
        if filter_item.value is None:
            issues.append(
                _metric_issue(
                    "filter_resolution",
                    "FILTER_VALUE_UNSTRUCTURED",
                    "error",
                    "Selected filter lacks a structured value.",
                    metric,
                    column_key=column.column_key,
                    filter_key=column.column_key,
                    policy_source="query_intent",
                    downstream_impact="Compiler cannot safely parameterize this filter.",
                    suggested_action="Use structured filter values only.",
                )
            )
        if _contains_sql_payload({"value": filter_item.value}):
            issues.append(
                _metric_issue(
                    "filter_resolution",
                    "SQL_PAYLOAD_NOT_ALLOWED",
                    "error",
                    "Filter value contains SQL-like text.",
                    metric,
                    column_key=column.column_key,
                    filter_key=column.column_key,
                    policy_source="query_intent",
                    downstream_impact="Compiler must never consume raw SQL filter payloads.",
                    suggested_action="Reject SQL-like filter values.",
                )
            )
    return issues, refs


def _stage_path_resolution(
    context: _PreflightContext,
) -> tuple[list[QueryCompilerPreflightIssue], list[str]]:
    metric = context.selected_metric
    if metric is None:
        return [], []
    refs: list[str] = []
    issues: list[QueryCompilerPreflightIssue] = []
    for edge in context.prefetched.selected_edges:
        edge_key = getattr(edge, "edge_key", None)
        if edge_key:
            refs.append(f"edge:{edge_key}")
        if not isinstance(edge, QueryabilityForeignKeyEdge):
            issues.append(
                _metric_issue(
                    "path_resolution",
                    "GRAPH_PATH_USES_LINEAGE",
                    "error",
                    "Selected path uses lineage/provenance instead of a FK join.",
                    metric,
                    edge_key=edge_key,
                    policy_source="queryability_graph",
                    downstream_impact="Compiler could join through provenance evidence.",
                    suggested_action="Use only trusted FK graph paths for joins.",
                )
            )
            continue
        if (
            not edge.automatic_join_allowed
            or not edge.verified_by_db
            or edge.enforcement_status != "enabled"
            or edge.validation_status != "trusted"
        ):
            issues.append(
                _metric_issue(
                    "path_resolution",
                    "GRAPH_PATH_USES_UNTRUSTED_EDGE",
                    "error",
                    "Selected path uses an edge that is not trusted/enabled/verified.",
                    metric,
                    edge_key=edge.edge_key,
                    physical_label=edge.constraint_name,
                    policy_source="queryability_graph",
                    downstream_impact="Compiler could generate unsafe joins.",
                    suggested_action="Use enabled, trusted, DB-verified FK paths only.",
                )
            )
        from_node = context.nodes_by_key.get(edge.from_node_key)
        to_node = context.nodes_by_key.get(edge.to_node_key)
        if getattr(from_node, "bridge_candidate", False) or getattr(to_node, "bridge_candidate", False):
            allowed = bool(_policy_value(context.policy, "allow_bridge_paths"))
            issues.append(
                _metric_issue(
                    "path_resolution",
                    "GRAPH_PATH_REQUIRES_BRIDGE_POLICY",
                    "warning" if allowed else "error",
                    "Selected path traverses a bridge/many-to-many candidate.",
                    metric,
                    edge_key=edge.edge_key,
                    physical_label=edge.constraint_name,
                    policy_source="manual_override" if allowed else "missing",
                    downstream_impact="Many-to-many joins can multiply rows unless policy defines semantics.",
                    suggested_action="Add explicit bridge/allocation policy or block the path.",
                )
            )
    if "AMBIGUOUS_PATH" in _reason_codes(context.selected_metric):
        issues.append(
            _metric_issue(
                "path_resolution",
                "GRAPH_PATH_AMBIGUOUS",
                "error",
                "Selected semantic metric records ambiguous path evidence.",
                context.selected_metric,
                policy_source="semantic_layer",
                downstream_impact="Compiler must not silently choose among equivalent paths.",
                suggested_action="Resolve path ambiguity before compilation.",
            )
        )
    return issues, refs


def _stage_policy_permission_check(
    context: _PreflightContext,
) -> tuple[list[QueryCompilerPreflightIssue], list[str]]:
    metric = context.selected_metric
    if metric is None:
        return [], []
    refs = [f"policy:{key}" for key in sorted(_policy_keys(context.policy))]
    issues: list[QueryCompilerPreflightIssue] = []
    concept = context.concepts_by_key.get(str(metric.business_concept_key))
    concept_name = getattr(concept, "canonical_name", None)
    if _policy_value(context.policy, "allow_native_sql") is True:
        issues.append(
            _metric_issue(
                "policy_permission_check",
                "SQL_PAYLOAD_NOT_ALLOWED",
                "error",
                "Native/raw SQL policy is not supported by this preflight gate.",
                metric,
                concept_ref=concept_name,
                policy_source="tenant_policy",
                downstream_impact="Atlante compiler scope is structured intent only.",
                suggested_action="Do not enable native SQL in V1 preflight.",
            )
        )
    if _policy_value(context.policy, "deny_metric_keys") and str(metric.metric_key) in set(_policy_value(context.policy, "deny_metric_keys")):
        issues.append(
            _metric_issue(
                "policy_permission_check",
                "METRIC_ACCESS_DENIED",
                "error",
                "Internal policy denies access to the selected metric.",
                metric,
                concept_ref=concept_name,
                policy_source="tenant_policy",
                downstream_impact="Compiler must not compile metrics hidden by policy.",
                suggested_action="Choose an allowed metric or update policy.",
            )
        )
    if concept_name in _REVENUE_OR_ORDER_CONCEPTS:
        source_node = context.prefetched.selected_source_node
        status_like = _status_like_columns(source_node) if source_node else []
        has_policy = bool(_policy_value(context.policy, "status_scope"))
        has_disclosure = _has_disclosure(context, "status")
        if status_like and not (has_policy or has_disclosure or metric.compiler_eligibility == "eligible_with_disclosure"):
            issues.append(
                _metric_issue(
                    "policy_permission_check",
                    "STATUS_SCOPE_REQUIRES_POLICY",
                    "error",
                    "Revenue/order metric uses a table with status-like fields but no policy or disclosure.",
                    metric,
                    concept_ref=concept_name,
                    policy_source="missing",
                    downstream_impact="Compiler could silently include cancelled, voided, draft, or status-specific rows.",
                    suggested_action="Add status scope policy or semantic disclosure.",
                )
            )
        elif has_policy or has_disclosure or metric.compiler_eligibility == "eligible_with_disclosure":
            issues.append(
                _metric_issue(
                    "policy_permission_check",
                    "STATUS_SCOPE_DEFAULT_ALL_STATUSES_DISCLOSURE",
                    "warning",
                    "Status scope is explicit as policy, disclosure, or eligible-with-disclosure.",
                    metric,
                    concept_ref=concept_name,
                    policy_source="tenant_policy" if has_policy else "semantic_layer",
                    downstream_impact="Compiler output must carry status-scope disclosure.",
                    suggested_action="Propagate status-scope disclosure into compiled result metadata.",
                )
            )
    source_node = context.prefetched.selected_source_node
    if metric.format.value_type == "currency" and source_node is not None and _currency_like_columns(source_node) and not (_policy_value(context.policy, "single_currency") or metric.format.currency):
        issues.append(
            _metric_issue(
                "policy_permission_check",
                "CURRENCY_MISSING",
                "error",
                "Currency-like fields exist but the selected metric has no currency strategy.",
                metric,
                concept_ref=concept_name,
                policy_source="missing",
                downstream_impact="Compiler could aggregate mixed currencies.",
                suggested_action="Add currency policy or explicit metric currency.",
            )
        )
    return issues, refs


def _final_decision_stage(
    stage_results: list[QueryCompilerPreflightStageResult],
    context: _PreflightContext,
) -> QueryCompilerPreflightStageResult:
    errors = [
        issue
        for stage in stage_results
        for issue in stage.issues
        if issue.severity == "error"
    ]
    warnings = [
        issue
        for stage in stage_results
        for issue in stage.issues
        if issue.severity == "warning"
    ]
    issues: list[QueryCompilerPreflightIssue] = []
    if errors:
        issues.append(
            _issue(
                stage="final_decision",
                code="PREFLIGHT_BLOCKED",
                severity="info",
                message="Preflight is blocked by one or more compiler-readiness errors.",
                policy_source="missing",
                downstream_impact="Future compiler must not receive this plan.",
                suggested_action="Resolve blocking diagnostics before compilation.",
            )
        )
    elif warnings:
        issues.append(
            _issue(
                stage="final_decision",
                code="PREFLIGHT_READY_WITH_WARNINGS",
                severity="info",
                message="Preflight is ready with disclosures or missing optional evidence.",
                policy_source="semantic_layer",
                downstream_impact="Future compiler may proceed only with surfaced disclosures.",
                suggested_action="Propagate warnings into compiler metadata.",
            )
        )
    else:
        issues.append(
            _issue(
                stage="final_decision",
                code="PREFLIGHT_READY",
                severity="info",
                message="Preflight is clean-ready for the diagnostic scope.",
                policy_source="semantic_layer",
                downstream_impact="Future compiler can consume this structured plan.",
                suggested_action="Keep plan trace and artifact hashes with compiled output.",
            )
        )
    return _stage_result("final_decision", issues, _selected_refs(context))


def _report(
    stage_results: list[QueryCompilerPreflightStageResult],
    context: _PreflightContext,
) -> QueryCompilerPreflightReport:
    all_issues = [issue for stage in stage_results for issue in stage.issues]
    errors = sorted(
        [issue for issue in all_issues if issue.severity == "error"],
        key=_issue_sort_key,
    )
    warnings = sorted(
        [issue for issue in all_issues if issue.severity == "warning"],
        key=_issue_sort_key,
    )
    infos = sorted(
        [issue for issue in all_issues if issue.severity == "info"],
        key=_issue_sort_key,
    )
    status: PreflightStatus
    if errors:
        status = "blocked"
    elif warnings:
        status = "ready_with_warnings"
    else:
        status = "ready"
    decision_category = _decision_category(errors, warnings)
    return QueryCompilerPreflightReport(
        status=status,
        decision_category=decision_category,
        errors=errors,
        warnings=warnings,
        infos=infos,
        summary=QueryCompilerPreflightSummary(
            stage_count=len(stage_results),
            passed_stage_count=sum(stage.status == "pass" for stage in stage_results),
            warning_stage_count=sum(stage.status == "warning" for stage in stage_results),
            blocked_stage_count=sum(stage.status == "blocked" for stage in stage_results),
            error_count=len(errors),
            warning_count=len(warnings),
            info_count=len(infos),
            selected_reference_count=len(
                {ref for stage in stage_results for ref in stage.selected_references}
            ),
        ),
        blocking_codes=sorted({issue.code for issue in errors}),
        plan_trace=_plan_trace(context, errors, warnings),
        stage_results=stage_results,
    )


def _run_stage(
    stage: str,
    fn,
    context: _PreflightContext,
) -> QueryCompilerPreflightStageResult:
    issues, refs = fn(context)
    return _stage_result(stage, issues, refs)


def _stage_result(
    stage: str,
    issues: list[QueryCompilerPreflightIssue],
    refs: list[str],
) -> QueryCompilerPreflightStageResult:
    if any(issue.severity == "error" for issue in issues):
        status: PreflightStageStatus = "blocked"
    elif any(issue.severity == "warning" for issue in issues):
        status = "warning"
    else:
        status = "pass"
    return QueryCompilerPreflightStageResult(
        stage=stage,
        status=status,
        issues=issues,
        selected_references=sorted(set(refs)),
    )


def _decision_category(
    errors: list[QueryCompilerPreflightIssue],
    warnings: list[QueryCompilerPreflightIssue],
) -> PreflightDecisionCategory:
    if not errors:
        return "safe_with_disclosure" if warnings else "safe"
    categories = {_category_for_code(issue.code) for issue in errors}
    for category in _CATEGORY_PRECEDENCE:
        if category in categories:
            return category
    return "invalid_artifact"


def _category_for_code(code: str) -> PreflightDecisionCategory:
    if code in {
        "AMOUNT_SEMANTIC_AMBIGUITY_NOT_RECORDED",
        "CURRENCY_MISSING",
        "FILTER_PII_REQUIRES_POLICY",
        "GRAPH_PATH_AMBIGUOUS",
        "GRAPH_PATH_REQUIRES_BRIDGE_POLICY",
        "MULTIPLE_DATE_CANDIDATES_REQUIRE_CLARIFICATION",
        "STATUS_SCOPE_REQUIRES_POLICY",
    }:
        return "needs_policy"
    if code in {
        "QUERYABILITY_GRAPH_INVALID",
        "GRAPH_REFERENCE_INVALID",
        "METRIC_NOT_FOUND",
        "SEMANTIC_INVARIANT_ERROR",
        "PREFLIGHT_ARTIFACT_MALFORMED",
    }:
        return "invalid_artifact"
    if "STALE" in code or code in {"SEMANTIC_LAYER_NOT_ACTIVE"}:
        return "stale"
    if any(token in code for token in ("UNTRUSTED", "SENSITIVE", "LINEAGE", "FANOUT", "ALLOCATION", "SQL_PAYLOAD", "RAW_SQL", "DESTRUCTIVE")):
        return "unsafe"
    if code.startswith("QUERY_INTENT") or code in {"METRIC_NOT_COMPILER_ELIGIBLE", "RAW_SQL_NOT_ALLOWED"}:
        return "unsupported"
    if any(token in code for token in ("MISSING", "NOT_FOUND", "SNAPSHOT_BLOCKED", "DATE_PATH_INVALID", "GRAPH_PATH_INVALID")):
        return "insufficient_metadata"
    return "needs_policy"


def _plan_trace(
    context: _PreflightContext,
    errors: list[QueryCompilerPreflightIssue],
    warnings: list[QueryCompilerPreflightIssue],
) -> QueryCompilerPreflightPlanTrace:
    plan = context.plan
    metric = context.selected_metric
    selected_dimensions = [
        {
            "column_key": column.column_key,
            "edge_path": list(getattr(dimension, "edge_path", [])),
        }
        for _, column, dimension in context.prefetched.selected_dimensions
    ]
    selected_filters = [
        {
            "column_key": column.column_key,
            "operator": getattr(filter_item, "operator", None),
            "value_type": getattr(filter_item, "value_type", None),
            "value_fingerprint": _filter_value_fingerprint(filter_item),
        }
        for _, column, filter_item in context.prefetched.selected_filters
    ]
    metric_key = str(metric.metric_key) if metric else (str(plan.primary_metric_key) if plan else None)
    dimension_keys = [item["column_key"] for item in selected_dimensions]
    filter_keys = [item["column_key"] for item in selected_filters]
    date_range = None
    if plan and plan.time_range:
        date_range = {
            "kind": plan.time_range.kind,
            "start_date": plan.time_range.start_date,
            "end_date": plan.time_range.end_date,
        }
    disclosures = list(plan.disclosures) if plan else []
    required_policies = sorted(
        {
            _required_policy_for_issue(issue)
            for issue in [*errors, *warnings]
            if _required_policy_for_issue(issue)
        }
    )
    return QueryCompilerPreflightPlanTrace(
        selected_metric_key=metric_key,
        concept_ref=plan.requested_concept_ref if plan else None,
        variant=plan.selected_variant if plan else None,
        selected_grain=list(metric.grain_column_keys) if metric else [],
        selected_date_column=plan.effective_date_column_key if plan else None,
        selected_dimensions=selected_dimensions,
        selected_filters=selected_filters,
        selected_graph_paths=sorted(_selected_edge_keys(context)),
        required_policies=required_policies,
        active_disclosures=disclosures,
        blocked_reasons=sorted({issue.code for issue in errors}),
        compiler_input_preview={
            "metric_key": metric_key,
            "concept_ref": plan.requested_concept_ref if plan else None,
            "variant": plan.selected_variant if plan else None,
            "date_column_key": plan.effective_date_column_key if plan else None,
            "dimension_keys": dimension_keys,
            "filter_keys": filter_keys,
            "edge_path_keys": sorted(_selected_edge_keys(context)),
            "snapshot_hash": getattr(context.schema_snapshot, "snapshot_hash", None),
        },
        selected_segments=[],
        expanded_segment_filters=[],
        segment_policy_sources=[],
        cache_key_inputs_preview={
            "tenant_id": str(context.semantic_layer.tenant_id),
            "semantic_hash": context.semantic_layer.semantic_hash,
            "graph_hash": context.queryability_graph.graph_hash,
            "snapshot_hash": getattr(context.schema_snapshot, "snapshot_hash", None),
            "policy_hash": context.semantic_layer.base_policy_hash,
            "metric_key": metric_key,
            "dimension_keys": dimension_keys,
            "filter_keys": filter_keys,
            "date_range": date_range,
            "result_limit": None,
        },
    )


def _issue(
    *,
    stage: str,
    code: str,
    severity: PreflightSeverity,
    message: str,
    metric_key: str | None = None,
    concept_ref: str | None = None,
    variant: str | None = None,
    table_key: str | None = None,
    column_key: str | None = None,
    edge_key: str | None = None,
    filter_key: str | None = None,
    physical_label: str | None = None,
    policy_source: PreflightPolicySource,
    downstream_impact: str,
    suggested_action: str,
) -> QueryCompilerPreflightIssue:
    return QueryCompilerPreflightIssue(
        stage=stage,
        code=code,
        severity=severity,
        message=message,
        metric_key=metric_key,
        concept_ref=concept_ref,
        variant=variant,
        table_key=table_key,
        column_key=column_key,
        edge_key=edge_key,
        filter_key=filter_key,
        physical_label=physical_label,
        policy_source=policy_source,
        downstream_impact=downstream_impact,
        suggested_action=suggested_action,
    )


def _metric_issue(
    stage: str,
    code: str,
    severity: PreflightSeverity,
    message: str,
    metric: SemanticMetric,
    *,
    concept_ref: str | None = None,
    column_key: str | None = None,
    edge_key: str | None = None,
    filter_key: str | None = None,
    physical_label: str | None = None,
    policy_source: PreflightPolicySource,
    downstream_impact: str,
    suggested_action: str,
) -> QueryCompilerPreflightIssue:
    return _issue(
        stage=stage,
        code=code,
        severity=severity,
        message=message,
        metric_key=str(metric.metric_key),
        concept_ref=concept_ref,
        variant=metric.metric_variant,
        table_key=metric.source_table_key,
        column_key=column_key,
        edge_key=edge_key,
        filter_key=filter_key,
        physical_label=physical_label,
        policy_source=policy_source,
        downstream_impact=downstream_impact,
        suggested_action=suggested_action,
    )


def _missing_graph_ref(
    stage: str,
    label: str,
    metric: SemanticMetric,
    *,
    table_key: str | None = None,
    column_key: str | None = None,
) -> QueryCompilerPreflightIssue:
    return _issue(
        stage=stage,
        code="GRAPH_REFERENCE_INVALID",
        severity="error",
        message=f"Selected metric {label} reference is missing from the graph.",
        metric_key=str(metric.metric_key),
        variant=metric.metric_variant,
        table_key=table_key,
        column_key=column_key,
        policy_source="queryability_graph",
        downstream_impact="Compiler cannot resolve all selected metric references.",
        suggested_action="Regenerate semantic layer against the current graph.",
    )


def _column_safety_issues(
    *,
    stage: str,
    code_prefix: str,
    metric: SemanticMetric,
    node,
    column,
    purpose: str,
    pii_requires_policy: bool,
    filter_key: str | None = None,
) -> list[QueryCompilerPreflightIssue]:
    issues: list[QueryCompilerPreflightIssue] = []
    if column.queryability_status != "queryable":
        issues.append(
            _metric_issue(
                stage,
                f"{code_prefix}_NOT_QUERYABLE",
                "error",
                f"Selected {purpose} column is excluded from queryability.",
                metric,
                column_key=column.column_key,
                filter_key=filter_key,
                physical_label=_column_label(node, column),
                policy_source="queryability_graph",
                downstream_impact="Compiler would depend on a non-queryable column.",
                suggested_action="Use a queryable column or keep this plan out of compiler scope.",
            )
        )
    if column.sensitivity == "sensitive":
        issues.append(
            _metric_issue(
                stage,
                f"{code_prefix}_SENSITIVE",
                "error",
                f"Selected {purpose} column is sensitive.",
                metric,
                column_key=column.column_key,
                filter_key=filter_key,
                physical_label=_column_label(node, column),
                policy_source="queryability_graph",
                downstream_impact="Compiler could expose sensitive data.",
                suggested_action="Reject this plan or use non-sensitive semantic evidence.",
            )
        )
    if column.sensitivity == "pii" or _has_token(column.name, _PII_TOKENS):
        if pii_requires_policy:
            issues.append(
                _metric_issue(
                    stage,
                    f"{code_prefix}_PII_REQUIRES_POLICY",
                    "error",
                    f"Selected {purpose} column is PII-like and lacks explicit policy.",
                    metric,
                    column_key=column.column_key,
                    filter_key=filter_key,
                    physical_label=_column_label(node, column),
                    policy_source="missing",
                    downstream_impact="Compiler would use PII without explicit permission policy.",
                    suggested_action="Add explicit PII policy or remove the selected field.",
                )
            )
        else:
            issues.append(
                _metric_issue(
                    stage,
                    f"{code_prefix}_SENSITIVE",
                    "error",
                    f"Selected {purpose} column is PII-like.",
                    metric,
                    column_key=column.column_key,
                    filter_key=filter_key,
                    physical_label=_column_label(node, column),
                    policy_source="queryability_graph",
                    downstream_impact="Compiler could derive sensitive output from PII.",
                    suggested_action="Use non-PII source columns for compiler-ready metrics.",
                )
            )
    if column.technical_role in {"binary", "xml"}:
        issues.append(
            _metric_issue(
                stage,
                f"{code_prefix}_UNSUPPORTED_TYPE_USED",
                "error",
                f"Selected {purpose} column uses an unsupported technical type.",
                metric,
                column_key=column.column_key,
                filter_key=filter_key,
                physical_label=_column_label(node, column),
                policy_source="queryability_graph",
                downstream_impact="Compiler cannot safely parameterize or aggregate this type.",
                suggested_action="Exclude unsupported types from compiler scope.",
            )
        )
    return issues


def _selected_snapshot_issues(
    context: _PreflightContext,
) -> list[QueryCompilerPreflightIssue]:
    issues: list[QueryCompilerPreflightIssue] = []
    metric = context.selected_metric
    if metric is None:
        return issues
    selected_nodes = [
        node
        for node in [
            context.prefetched.selected_source_node,
            *(item[0] for item in context.prefetched.selected_grain_columns),
            *(item[0] for item in context.prefetched.selected_dimensions),
            *(item[0] for item in context.prefetched.selected_filters),
            context.prefetched.selected_date_column[0]
            if context.prefetched.selected_date_column
            else None,
        ]
        if node is not None
    ]
    for node in selected_nodes:
        key = (node.schema_name, node.object_name)
        if key not in context.snapshot_objects_by_key:
            issues.append(
                _metric_issue(
                    "metadata_prefetch",
                    "SCHEMA_OBJECT_NOT_FOUND",
                    "error",
                    "Selected graph node is missing from the supplied Technical Snapshot.",
                    metric,
                    physical_label=_node_label(node),
                    policy_source="queryability_graph",
                    downstream_impact="Compiler cannot independently verify selected object metadata.",
                    suggested_action="Supply the matching snapshot or regenerate graph.",
                )
            )
    selected_column_refs = [
        context.prefetched.selected_measure_column,
        *context.prefetched.selected_grain_columns,
        context.prefetched.selected_date_column,
        *((node, column) for node, column, _ in context.prefetched.selected_dimensions),
        *((node, column) for node, column, _ in context.prefetched.selected_filters),
    ]
    selected_columns = [
        (node, column)
        for item in selected_column_refs
        if item is not None
        for node, column in [item]
        if node is not None and column is not None
    ]
    for node, column in selected_columns:
        key = (node.schema_name, node.object_name, column.name)
        if key not in context.snapshot_columns_by_key:
            issues.append(
                _metric_issue(
                    "metadata_prefetch",
                    "SCHEMA_COLUMN_NOT_FOUND",
                    "error",
                    "Selected graph column is missing from the supplied Technical Snapshot.",
                    metric,
                    column_key=column.column_key,
                    physical_label=_column_label(node, column),
                    policy_source="queryability_graph",
                    downstream_impact="Compiler cannot independently verify selected column metadata.",
                    suggested_action="Supply the matching snapshot or regenerate graph.",
                )
            )
    for edge in context.prefetched.selected_edges:
        if not isinstance(edge, QueryabilityForeignKeyEdge):
            continue
        if edge.constraint_name not in context.snapshot_fks_by_key:
            issues.append(
                _metric_issue(
                    "metadata_prefetch",
                    "SCHEMA_FK_NOT_FOUND",
                    "error",
                    "Selected FK edge is missing from the supplied Technical Snapshot.",
                    metric,
                    edge_key=edge.edge_key,
                    physical_label=edge.constraint_name,
                    policy_source="queryability_graph",
                    downstream_impact="Compiler cannot independently verify required FK metadata.",
                    suggested_action="Supply the matching snapshot or regenerate graph.",
                )
            )
        fk = context.snapshot_fks_by_key.get(edge.constraint_name)
        if fk is not None and (fk.is_disabled or fk.is_not_trusted):
            issues.append(
                _metric_issue(
                    "metadata_prefetch",
                    "SCHEMA_FK_DISABLED_OR_UNTRUSTED",
                    "error",
                    "Selected FK is disabled or untrusted in the Technical Snapshot.",
                    metric,
                    edge_key=edge.edge_key,
                    physical_label=edge.constraint_name,
                    policy_source="queryability_graph",
                    downstream_impact="Compiler could join through unsafe database metadata.",
                    suggested_action="Use only enabled/trusted FK metadata.",
                )
            )
    return issues


def _selected_edge_keys(context: _PreflightContext) -> set[str]:
    plan = context.plan
    metric = context.selected_metric
    edge_keys: set[str] = set()
    if metric:
        edge_keys.update(metric.required_join_edge_keys)
    if plan:
        edge_keys.update(plan.required_edge_path_keys)
        for dimension in plan.group_by_dimensions:
            edge_keys.update(dimension.edge_path)
            if metric:
                compatibility = _dimension_compatibility(
                    metric,
                    dimension.column_key,
                )
                if compatibility is not None and compatibility.safety == "safe":
                    edge_keys.update(compatibility.edge_path)
    return edge_keys


def _dimension_compatibility(metric: SemanticMetric, column_key: str):
    return next(
        (
            compatibility
            for compatibility in metric.common_dimension_compatibility
            if compatibility.dimension_column_key == column_key
        ),
        None,
    )


def _path_has_parent_to_child(
    metric: SemanticMetric,
    edge_path: list[str],
    context: _PreflightContext,
) -> bool:
    current_node_key = metric.source_table_key
    for edge_key in edge_path:
        edge = context.edges_by_key.get(edge_key)
        if not isinstance(edge, QueryabilityForeignKeyEdge):
            continue
        if edge.to_node_key == current_node_key and edge.from_node_key != current_node_key:
            return True
        if edge.from_node_key == current_node_key:
            current_node_key = edge.to_node_key
        elif edge.to_node_key == current_node_key:
            current_node_key = edge.from_node_key
    return False


def _snapshot_objects(schema_snapshot) -> dict[tuple[str, str], Any]:
    if schema_snapshot is None:
        return {}
    return {
        (table.table_schema, table.name): table
        for table in getattr(schema_snapshot, "tables", [])
    }


def _snapshot_columns(schema_snapshot) -> dict[tuple[str, str, str], Any]:
    if schema_snapshot is None:
        return {}
    return {
        (table.table_schema, table.name, column.name): column
        for table in getattr(schema_snapshot, "tables", [])
        for column in table.columns
    }


def _snapshot_fks(schema_snapshot) -> dict[str, Any]:
    if schema_snapshot is None:
        return {}
    return {
        fk.constraint_name: fk for fk in getattr(schema_snapshot, "foreign_keys", [])
    }


def _query_intent_scope_code(result: QueryIntentResult) -> str:
    reason = result.unsupported_reason
    if reason == "multi_metric_not_supported":
        return "QUERY_INTENT_MULTI_METRIC_NOT_SUPPORTED"
    if reason == "unsupported_calculated_metric":
        return "QUERY_INTENT_CALCULATED_METRIC_NOT_SUPPORTED"
    if reason == "unsupported_comparison":
        return "QUERY_INTENT_COMPARISON_NOT_SUPPORTED"
    if reason == "destructive_request_not_allowed":
        return "QUERY_INTENT_DESTRUCTIVE_REQUEST"
    if result.status != "ready":
        return "QUERY_INTENT_NOT_READY"
    return "QUERY_INTENT_UNSUPPORTED_SCOPE"


def _contains_sql_payload(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in _UNSUPPORTED_RAW_SQL_KEYS:
                return True
            if _contains_sql_payload(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_sql_payload(item) for item in value)
    if isinstance(value, str):
        normalized = f" {value.lower()} "
        return any(token in normalized for token in _SQL_TOKENS)
    return False


def _policy_value(policy, key: str):
    if policy is None:
        return None
    if isinstance(policy, dict):
        return policy.get(key)
    return getattr(policy, key, None)


def _policy_keys(policy) -> set[str]:
    if policy is None:
        return set()
    if isinstance(policy, dict):
        return {str(key) for key in policy}
    return {
        key
        for key in dir(policy)
        if not key.startswith("_") and not callable(getattr(policy, key))
    }


def _has_disclosure(context: _PreflightContext, token: str) -> bool:
    plan = context.plan
    if plan is None:
        return False
    haystack = " ".join(
        [
            *plan.disclosures,
            *(metric_reason for metric_reason in (context.selected_metric.eligibility_reasons if context.selected_metric else [])),
            *(metric_warning for metric_warning in (context.selected_metric.validation_warnings if context.selected_metric else [])),
        ]
    ).lower()
    return token.lower() in haystack or "all_statuses" in haystack


def _reason_codes(metric: SemanticMetric | None) -> set[str]:
    if metric is None:
        return set()
    return {*metric.eligibility_reasons, *metric.validation_warnings}


def _date_columns(node, *, audit: bool) -> list[Any]:
    if node is None:
        return []
    return [
        column
        for column in node.columns
        if column.queryability_status == "queryable"
        and column.technical_role == "date"
        and (_is_audit_date(column.name) if audit else _is_business_date(column.name))
    ]


def _status_like_columns(node) -> list[Any]:
    if node is None:
        return []
    return [
        column
        for column in node.columns
        if column.queryability_status == "queryable"
        and (column.technical_role in {"text", "boolean", "identifier"} or column.normalized_type in {"bit", "nvarchar", "varchar", "int"})
        and _has_token(column.name, _STATUS_TOKENS)
    ]


def _currency_like_columns(node) -> list[Any]:
    if node is None:
        return []
    return [
        column
        for column in node.columns
        if column.queryability_status == "queryable" and _has_token(column.name, _CURRENCY_TOKENS)
    ]


def _amount_like_columns(node) -> list[Any]:
    if node is None:
        return []
    return [
        column
        for column in node.columns
        if column.queryability_status == "queryable"
        and (
            column.technical_role == "money_candidate"
            or _has_token(column.name, _AMOUNT_TOKENS)
        )
    ]


def _amount_ambiguity_is_silent(metric: SemanticMetric) -> bool:
    normalized_variant = _normalize_identifier(metric.metric_variant)
    normalized_name = _normalize_identifier(metric.canonical_name)
    if normalized_variant.startswith("generic") or normalized_variant in {
        "revenue",
        "amount",
        "sales",
        "default",
    }:
        return True
    return normalized_name in {"revenue", "sales", "amount"}


def _grain_matches_candidate_key(node, grain_column_keys: list[str]) -> bool:
    columns_by_name = {column.name: column.column_key for column in node.columns}
    grain = list(grain_column_keys)
    for candidate in node.candidate_keys:
        if not candidate.eligible_for_cardinality:
            continue
        candidate_keys = [
            columns_by_name[column_name]
            for column_name in candidate.columns
            if column_name in columns_by_name
        ]
        if candidate_keys == grain:
            return True
    return False


def _is_audit_date(name: str) -> bool:
    return _has_token(name, _AUDIT_DATE_TOKENS)


def _is_business_date(name: str) -> bool:
    return _has_token(name, _BUSINESS_DATE_TOKENS) and not _is_audit_date(name)


def _has_token(value: str | None, tokens: tuple[str, ...]) -> bool:
    normalized = _normalize_identifier(value or "")
    return any(token in normalized for token in tokens)


def _normalize_identifier(value: str) -> str:
    return (
        value.replace("_", "")
        .replace("-", "")
        .replace(" ", "")
        .lower()
    )


def _required_policy_for_issue(issue: QueryCompilerPreflightIssue) -> str | None:
    if issue.code.endswith("REQUIRES_POLICY"):
        return issue.code
    if issue.policy_source in {"missing", "manual_override", "tenant_policy"} and issue.severity in {"error", "warning"}:
        return issue.code
    return None


def _selected_refs(context: _PreflightContext) -> list[str]:
    refs = []
    if context.selected_metric:
        refs.append(f"metric:{context.selected_metric.metric_key}")
    refs.extend(f"edge:{edge.edge_key}" for edge in context.prefetched.selected_edges if getattr(edge, "edge_key", None))
    refs.extend(f"dimension:{column.column_key}" for _, column, _ in context.prefetched.selected_dimensions)
    refs.extend(f"filter:{column.column_key}" for _, column, _ in context.prefetched.selected_filters)
    if context.prefetched.selected_date_column:
        refs.append(f"date_column:{context.prefetched.selected_date_column[1].column_key}")
    return refs


def _node_label(node) -> str:
    return f"{node.schema_name}.{node.object_name}"


def _column_label(node, column) -> str:
    return f"{node.schema_name}.{node.object_name}.{column.name}"


def _issue_sort_key(issue: QueryCompilerPreflightIssue) -> tuple[str, str, str, str, str]:
    return (
        issue.stage,
        issue.code,
        issue.metric_key or "",
        issue.column_key or "",
        issue.edge_key or "",
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
