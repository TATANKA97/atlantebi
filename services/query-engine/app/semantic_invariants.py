from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from app.models import (
    QueryabilityForeignKeyEdge,
    QueryabilityGraphArtifact,
    SemanticAmbiguity,
    SemanticLayer,
    SemanticMetric,
    SemanticPolicySnapshot,
)


SemanticInvariantSeverity = Literal["error", "warning", "info"]
SemanticInvariantStatus = Literal["valid", "valid_with_warnings", "invalid"]

_COMPILER_ELIGIBLE = {"eligible", "eligible_with_disclosure"}
_MEASURE_REQUIRED_AGGREGATIONS = {"sum", "avg", "min", "max", "count_distinct"}
_SUPPORTED_AGGREGATIONS = {"count", "count_distinct", "sum", "avg", "min", "max"}
_AUDIT_DATE_TOKENS = (
    "modified",
    "updated",
    "created",
    "rowversion",
    "lastchanged",
    "lastupdated",
)
_BUSINESS_DATE_TOKENS = (
    "order",
    "invoice",
    "document",
    "posting",
    "shipment",
    "ship",
    "due",
    "payment",
    "data",
    "fattura",
    "documento",
    "registrazione",
)
_AMOUNT_TOKENS = (
    "amount",
    "total",
    "subtotal",
    "due",
    "imponibile",
    "totale",
    "iva",
    "sconto",
    "trasporto",
    "freight",
    "tax",
    "discount",
)


@dataclass(frozen=True)
class SemanticLayerInvariantIssue:
    code: str
    severity: SemanticInvariantSeverity
    message: str
    metric_key: str | None = None
    concept_key: str | None = None
    column_key: str | None = None
    edge_key: str | None = None
    physical_label: str | None = None
    downstream_impact: str = ""
    suggested_action: str = ""


@dataclass(frozen=True)
class SemanticLayerInvariantSummary:
    metric_count: int
    compiler_candidate_metric_count: int
    eligible_metric_count: int
    eligible_with_disclosure_metric_count: int
    ambiguity_count: int
    profile_synthesized_metric_count: int


@dataclass(frozen=True)
class SemanticLayerInvariantReport:
    status: SemanticInvariantStatus
    errors: list[SemanticLayerInvariantIssue]
    warnings: list[SemanticLayerInvariantIssue]
    info: list[SemanticLayerInvariantIssue]
    summary: SemanticLayerInvariantSummary
    blocking_codes: list[str]

    @property
    def issues(self) -> list[SemanticLayerInvariantIssue]:
        return [*self.errors, *self.warnings, *self.info]

    def to_debug_dict(self) -> dict[str, object]:
        return asdict(self)


def validate_semantic_layer_invariants(
    layer: SemanticLayer,
    graph: QueryabilityGraphArtifact,
    graph_validation_report,
    policy: SemanticPolicySnapshot,
) -> SemanticLayerInvariantReport:
    nodes_by_key = {node.node_key: node for node in graph.nodes}
    columns_by_key = {
        column.column_key: (node, column)
        for node in graph.nodes
        for column in node.columns
    }
    edges_by_key = {edge.edge_key: edge for edge in graph.edges}
    concepts_by_key = {
        str(concept.business_concept_key): concept
        for concept in layer.business_concepts
    }
    issues: list[SemanticLayerInvariantIssue] = []

    issues.extend(_layer_issues(layer, graph, graph_validation_report, policy))

    for metric in _compiler_candidate_metrics(layer):
        concept = concepts_by_key.get(str(metric.business_concept_key))
        issues.extend(
            _metric_source_issues(
                metric=metric,
                nodes_by_key=nodes_by_key,
                columns_by_key=columns_by_key,
            )
        )
        issues.extend(
            _metric_date_issues(
                metric=metric,
                layer=layer,
                policy=policy,
                columns_by_key=columns_by_key,
                edges_by_key=edges_by_key,
            )
        )
        issues.extend(
            _metric_path_issues(
                metric=metric,
                edges_by_key=edges_by_key,
                nodes_by_key=nodes_by_key,
                columns_by_key=columns_by_key,
            )
        )
        issues.extend(
            _metric_ambiguity_issues(
                metric=metric,
                concept_name=concept.canonical_name if concept else None,
                layer=layer,
                graph=graph,
                columns_by_key=columns_by_key,
                policy=policy,
            )
        )
        issues.extend(_metric_provenance_issues(metric))
        issues.extend(_metric_raw_sql_issues(metric))

    issues.extend(_duplicate_metric_signature_issues(layer, concepts_by_key))
    return _report(layer=layer, issues=issues)


def _layer_issues(
    layer: SemanticLayer,
    graph: QueryabilityGraphArtifact,
    graph_validation_report,
    policy: SemanticPolicySnapshot,
) -> list[SemanticLayerInvariantIssue]:
    issues: list[SemanticLayerInvariantIssue] = []
    if layer.freshness != "fresh" or layer.base_graph_hash != graph.graph_hash:
        issues.append(
            _issue(
                code="SEMANTIC_LAYER_GRAPH_STALE_FOR_COMPILER",
                severity="error",
                message="Semantic layer is stale relative to the supplied Queryability Graph.",
                downstream_impact="A compiler could resolve metrics against outdated tables, columns, or paths.",
                suggested_action="Regenerate or rebase the semantic layer on the current graph.",
            )
        )
    if layer.base_policy_hash != policy.policy_hash:
        issues.append(
            _issue(
                code="SEMANTIC_LAYER_POLICY_STALE_FOR_COMPILER",
                severity="error",
                message="Semantic layer base policy hash differs from the supplied policy.",
                downstream_impact="A compiler could apply stale currency, activation, or concept policy.",
                suggested_action="Regenerate or revalidate with the current semantic policy.",
            )
        )
    if getattr(graph_validation_report, "status", None) == "invalid":
        issues.append(
            _issue(
                code="QUERYABILITY_GRAPH_INVALID_FOR_COMPILER",
                severity="error",
                message="Queryability Graph validation is invalid.",
                downstream_impact="Compiler joins and column exposure cannot be trusted.",
                suggested_action="Fix Queryability Graph invariant errors before compiling.",
            )
        )
    if layer.quality_report.status == "blocked":
        issues.append(
            _issue(
                code="SEMANTIC_QUALITY_GATE_BLOCKED_FOR_COMPILER",
                severity="error",
                message="Semantic quality gate is blocked.",
                downstream_impact="Required semantic policy guarantees are not satisfied.",
                suggested_action="Resolve quality gate blockers before compilation.",
            )
        )
    if layer.validation_report.status == "blocked":
        issues.append(
            _issue(
                code="SEMANTIC_VALIDATION_BLOCKED_FOR_COMPILER",
                severity="error",
                message="Semantic validation report is blocked.",
                downstream_impact="Current semantic artifact is not compiler-safe.",
                suggested_action="Resolve semantic validation blockers before compilation.",
            )
        )
    return issues


def _metric_source_issues(
    *,
    metric: SemanticMetric,
    nodes_by_key: dict[str, object],
    columns_by_key: dict[str, tuple[object, object]],
) -> list[SemanticLayerInvariantIssue]:
    issues: list[SemanticLayerInvariantIssue] = []
    source_node = nodes_by_key.get(metric.source_table_key)
    if source_node is None:
        issues.append(
            _metric_issue(
                metric,
                _missing_key_code(metric),
                "error",
                "Metric source table key is missing from the graph.",
                downstream_impact="Compiler cannot resolve the metric source table.",
                suggested_action="Drop or regenerate the metric from the current graph.",
            )
        )
    if metric.aggregation not in _SUPPORTED_AGGREGATIONS:
        issues.append(
            _metric_issue(
                metric,
                "UNSUPPORTED_METRIC_AGGREGATION",
                "error",
                "Metric aggregation is not supported by the V1 compiler contract.",
                downstream_impact="Compiler cannot translate this metric deterministically.",
                suggested_action="Use a supported aggregation or keep the metric out of compiler scope.",
            )
        )
    if (
        metric.aggregation in _MEASURE_REQUIRED_AGGREGATIONS
        and metric.measure_column_key is None
    ):
        issues.append(
            _metric_issue(
                metric,
                "SEMANTIC_METRIC_MEASURE_COLUMN_MISSING",
                "error",
                "Metric aggregation requires a measure column.",
                downstream_impact="Compiler cannot build an aggregate expression.",
                suggested_action="Regenerate the metric with an explicit source column.",
            )
        )
    if metric.measure_column_key is not None:
        issues.extend(
            _column_usage_issues(
                metric=metric,
                column_key=metric.measure_column_key,
                columns_by_key=columns_by_key,
                code_prefix="SEMANTIC_METRIC_SOURCE",
                purpose="source/measure",
            )
        )

    grain_node = nodes_by_key.get(metric.grain_table_key)
    if grain_node is None:
        issues.append(
            _metric_issue(
                metric,
                "SEMANTIC_METRIC_GRAIN_TABLE_MISSING",
                "error",
                "Metric grain table key is missing from the graph.",
                downstream_impact="Compiler cannot reason about metric grain.",
                suggested_action="Regenerate the metric with a valid grain table.",
            )
        )
    for grain_key in metric.grain_column_keys:
        issues.extend(
            _column_usage_issues(
                metric=metric,
                column_key=grain_key,
                columns_by_key=columns_by_key,
                code_prefix="SEMANTIC_METRIC_GRAIN",
                purpose="grain",
            )
        )
    if grain_node is not None and not _grain_matches_candidate_key(
        grain_node, metric.grain_column_keys
    ):
        issues.append(
            _metric_issue(
                metric,
                "SEMANTIC_GRAIN_NOT_CANDIDATE_KEY",
                "error",
                "Metric grain columns do not match a graph candidate key.",
                physical_label=_node_label(grain_node),
                downstream_impact="Compiler aggregation can duplicate or collapse rows unpredictably.",
                suggested_action="Use an eligible candidate key or add explicit semantic grain policy.",
            )
        )
    if metric.format.value_type == "currency" and metric.format.currency is None:
        issues.append(
            _metric_issue(
                metric,
                "CURRENCY_NOT_RESOLVED_FOR_COMPILER",
                "error",
                "Currency metric has no resolved currency.",
                downstream_impact="Compiler output would omit required monetary context.",
                suggested_action="Resolve currency via tenant/connection policy or require clarification.",
            )
        )
    return issues


def _metric_date_issues(
    *,
    metric: SemanticMetric,
    layer: SemanticLayer,
    policy: SemanticPolicySnapshot,
    columns_by_key: dict[str, tuple[object, object]],
    edges_by_key: dict[str, object],
) -> list[SemanticLayerInvariantIssue]:
    issues: list[SemanticLayerInvariantIssue] = []
    if metric.default_date_column_key is None:
        return issues
    issues.extend(
        _column_usage_issues(
            metric=metric,
            column_key=metric.default_date_column_key,
            columns_by_key=columns_by_key,
            code_prefix="SEMANTIC_METRIC_DATE",
            purpose="default date",
        )
    )
    date_ref = columns_by_key.get(metric.default_date_column_key)
    source_ref = columns_by_key.get(metric.grain_column_keys[0])
    if date_ref is None or source_ref is None:
        return issues
    date_node, date_column = date_ref
    source_node = source_ref[0]
    if date_column.technical_role != "date":
        issues.append(
            _metric_issue(
                metric,
                "DEFAULT_DATE_COLUMN_NOT_DATE",
                "error",
                "Default date column is not typed as a date.",
                column_key=metric.default_date_column_key,
                physical_label=_column_label(date_node, date_column),
                downstream_impact="Compiler time filters would be applied to a non-date column.",
                suggested_action="Select a graph date column or remove the default date.",
            )
        )
    if date_node.node_key != metric.source_table_key and not _has_direct_fk_path(
        metric=metric,
        target_node_key=date_node.node_key,
        edges_by_key=edges_by_key,
    ):
        issues.append(
            _metric_issue(
                metric,
                "DETAIL_METRIC_MISSING_PARENT_DATE_PATH",
                "error",
                "Metric uses a date on a different table without a trusted date path.",
                column_key=metric.default_date_column_key,
                physical_label=_column_label(date_node, date_column),
                downstream_impact="Compiler cannot safely join to the business date table.",
                suggested_action="Add a trusted FK path or require date clarification.",
            )
        )
    source_date_node = date_node if date_node.node_key != source_node.node_key else source_node
    business_dates = _business_date_columns(source_date_node)
    if _is_audit_date(date_column.name) and business_dates:
        issues.append(
            _metric_issue(
                metric,
                "AUDIT_DATE_USED_AS_BUSINESS_DEFAULT",
                "warning",
                "Metric uses an audit date as its default business date.",
                column_key=metric.default_date_column_key,
                physical_label=_column_label(date_node, date_column),
                downstream_impact="Compiler time filters may answer modified/created timing instead of business activity.",
                suggested_action="Select a business event date or disclose the audit-date semantics.",
            )
        )
    if len(business_dates) > 1 and not _has_metric_signal(
        layer,
        metric,
        tokens=("DATE", "TIME", "DOCUMENT", "POSTING", "INVOICE"),
    ) and not _date_resolved_by_policy(
        metric,
        policy,
    ):
        issues.append(
            _metric_issue(
                metric,
                "MULTIPLE_BUSINESS_DATE_CANDIDATES",
                "error",
                "Metric has multiple plausible business date candidates without ambiguity/disclosure.",
                physical_label=_node_label(source_date_node),
                downstream_impact="Compiler could filter on the wrong business date.",
                suggested_action="Record a semantic ambiguity/disclosure or configure date policy.",
            )
        )
    return issues


def _metric_path_issues(
    *,
    metric: SemanticMetric,
    edges_by_key: dict[str, object],
    nodes_by_key: dict[str, object],
    columns_by_key: dict[str, tuple[object, object]],
) -> list[SemanticLayerInvariantIssue]:
    issues: list[SemanticLayerInvariantIssue] = []
    for edge_key in metric.required_join_edge_keys:
        issues.extend(
            _edge_path_issues(
                metric=metric,
                edge_key=edge_key,
                edges_by_key=edges_by_key,
                nodes_by_key=nodes_by_key,
            )
        )
    for compatibility in metric.common_dimension_compatibility:
        if compatibility.safety != "safe":
            continue
        dimension_ref = columns_by_key.get(compatibility.dimension_column_key)
        if dimension_ref is not None:
            dimension_node, dimension_column = dimension_ref
            if (
                dimension_column.queryability_status != "queryable"
                or dimension_column.sensitivity != "none"
            ):
                issues.append(
                    _metric_issue(
                        metric,
                        "SEMANTIC_DIMENSION_COLUMN_NOT_COMPILER_SAFE",
                        "error",
                        "Safe dimension compatibility references a non-safe column.",
                        column_key=dimension_column.column_key,
                        physical_label=_column_label(dimension_node, dimension_column),
                        downstream_impact="Compiler could expose or group by excluded/sensitive data.",
                        suggested_action="Mark the dimension forbidden or require explicit privacy policy.",
                    )
                )
        for edge_key in compatibility.edge_path:
            issues.extend(
                _edge_path_issues(
                    metric=metric,
                    edge_key=edge_key,
                    edges_by_key=edges_by_key,
                    nodes_by_key=nodes_by_key,
                )
            )
        if _is_parent_to_child_compatibility(
            metric=metric,
            edge_path=compatibility.edge_path,
            edges_by_key=edges_by_key,
        ):
            issues.append(
                _metric_issue(
                    metric,
                    "HEADER_METRIC_DETAIL_DIMENSION_REQUIRES_ALLOCATION",
                    "error",
                    "Header-grain metric is marked safe for a child/detail dimension.",
                    column_key=compatibility.dimension_column_key,
                    downstream_impact="SQL compiler would duplicate header amount across detail rows.",
                    suggested_action="Mark the dimension forbidden or define an explicit allocation strategy.",
                )
            )
    return issues


def _metric_ambiguity_issues(
    *,
    metric: SemanticMetric,
    concept_name: str | None,
    layer: SemanticLayer,
    graph: QueryabilityGraphArtifact,
    columns_by_key: dict[str, tuple[object, object]],
    policy: SemanticPolicySnapshot,
) -> list[SemanticLayerInvariantIssue]:
    issues: list[SemanticLayerInvariantIssue] = []
    if concept_name in {"revenue", "orders"}:
        severity = "warning" if _has_status_scope_signal(
            layer,
            metric,
            policy,
        ) else "error"
        issues.append(
            _metric_issue(
                metric,
                "STATUS_SCOPE_AMBIGUITY_NOT_RECORDED",
                severity,
                "Order/status scope is not explicit enough for compiler readiness.",
                downstream_impact="Compiler output may silently include cancelled/voided/order-status variants.",
                suggested_action="Add policy, disclosure, ambiguity, clarification, or compiler-readiness warning.",
            )
        )
    if concept_name == "customers" and metric.metric_variant not in {
        "order_customers",
        "customer_master",
    } and not _has_metric_signal(layer, metric, tokens=("CUSTOMER", "POPULATION")):
        issues.append(
            _metric_issue(
                metric,
                "CUSTOMER_POPULATION_AMBIGUITY_NOT_RECORDED",
                "error",
                "Generic customer metric lacks population ambiguity or specific variant.",
                downstream_impact="Compiler could count order customers or customer-master rows incorrectly.",
                suggested_action="Use a specific customer variant or record a customer population ambiguity.",
            )
        )
    if concept_name == "revenue" and not _amount_ambiguity_resolved(
        metric,
        layer,
        graph,
        columns_by_key,
        policy,
    ):
        issues.append(
            _metric_issue(
                metric,
                "AMOUNT_SEMANTIC_AMBIGUITY_NOT_RECORDED",
                "error",
                "Revenue metric is sourced from a table with multiple amount-like columns without policy/disclosure.",
                downstream_impact="Compiler could use subtotal, gross total, tax, freight, or discount as revenue silently.",
                suggested_action="Resolve the amount variant by policy/spec or record a material ambiguity/disclosure.",
            )
        )
    return issues


def _metric_provenance_issues(
    metric: SemanticMetric,
) -> list[SemanticLayerInvariantIssue]:
    if metric.provenance_detail != "quality_profile":
        return []
    if metric.provenance == "system" and metric.source_spec_key:
        return []
    return [
        _metric_issue(
            metric,
            "PROFILE_SYNTHESIS_NOT_AUDITABLE",
            "error",
            "Quality-profile synthesized metric lacks auditable provenance.",
            downstream_impact="Compiler output could depend on an untraceable synthetic metric.",
            suggested_action="Require system provenance, quality_profile detail, and source_spec_key.",
        )
    ]


def _metric_raw_sql_issues(metric: SemanticMetric) -> list[SemanticLayerInvariantIssue]:
    payload = metric.model_dump(mode="json")
    if any(key in payload for key in ("sql", "raw_sql", "query")):
        return [
            _metric_issue(
                metric,
                "AI_RAW_SQL_ACCEPTED",
                "error",
                "Metric carries raw SQL payload.",
                downstream_impact="Compiler readiness must be based on structured semantics, not AI SQL.",
                suggested_action="Reject the candidate and rebuild metric from stable graph keys.",
            )
        ]
    return []


def _duplicate_metric_signature_issues(
    layer: SemanticLayer,
    concepts_by_key: dict[str, object],
) -> list[SemanticLayerInvariantIssue]:
    seen: dict[tuple[str, str, str, str | None], SemanticMetric] = {}
    issues: list[SemanticLayerInvariantIssue] = []
    for metric in layer.metrics:
        concept = concepts_by_key.get(str(metric.business_concept_key))
        signature = (
            getattr(concept, "canonical_name", str(metric.business_concept_key)),
            metric.metric_variant,
            metric.source_table_key,
            metric.measure_column_key,
        )
        previous = seen.get(signature)
        if previous is None:
            seen[signature] = metric
            continue
        issues.append(
            _metric_issue(
                metric,
                "DUPLICATE_CONCEPT_VARIANT_SOURCE",
                "warning",
                "Duplicate semantic metric signature exists.",
                downstream_impact="Compiler metric selection may be ambiguous.",
                suggested_action="Deduplicate concept/variant/source metrics before compiler use.",
            )
        )
    return issues


def _column_usage_issues(
    *,
    metric: SemanticMetric,
    column_key: str,
    columns_by_key: dict[str, tuple[object, object]],
    code_prefix: str,
    purpose: str,
) -> list[SemanticLayerInvariantIssue]:
    ref = columns_by_key.get(column_key)
    if ref is None:
        return [
            _metric_issue(
                metric,
                _missing_key_code(metric),
                "error",
                f"Metric {purpose} column key is missing from the graph.",
                column_key=column_key,
                downstream_impact="Compiler cannot resolve a required column.",
                suggested_action="Regenerate or drop the metric for the current graph.",
            )
        ]
    node, column = ref
    issues: list[SemanticLayerInvariantIssue] = []
    if column.queryability_status != "queryable":
        issues.append(
            _metric_issue(
                metric,
                f"{code_prefix}_COLUMN_EXCLUDED",
                "error",
                f"Metric {purpose} column is excluded from queryability.",
                column_key=column_key,
                physical_label=_column_label(node, column),
                downstream_impact="Compiler would depend on a non-queryable column.",
                suggested_action="Use a queryable source column or keep the metric out of compiler scope.",
            )
        )
    if column.sensitivity != "none":
        code = "AI_SENSITIVE_SOURCE_ACCEPTED" if code_prefix == "SEMANTIC_METRIC_SOURCE" else f"{code_prefix}_COLUMN_SENSITIVE"
        issues.append(
            _metric_issue(
                metric,
                code,
                "error",
                f"Metric {purpose} column is sensitive or PII.",
                column_key=column_key,
                physical_label=_column_label(node, column),
                downstream_impact="Compiler could expose sensitive data through metric computation.",
                suggested_action="Reject the metric or require explicit privacy-aware compiler policy.",
            )
        )
    return issues


def _edge_path_issues(
    *,
    metric: SemanticMetric,
    edge_key: str,
    edges_by_key: dict[str, object],
    nodes_by_key: dict[str, object],
) -> list[SemanticLayerInvariantIssue]:
    edge = edges_by_key.get(edge_key)
    if edge is None:
        return [
            _metric_issue(
                metric,
                _missing_key_code(metric),
                "error",
                "Semantic path references an edge missing from the graph.",
                edge_key=edge_key,
                downstream_impact="Compiler cannot materialize the required join path.",
                suggested_action="Regenerate the metric paths from the current graph.",
            )
        ]
    if not isinstance(edge, QueryabilityForeignKeyEdge):
        return [
            _metric_issue(
                metric,
                "SEMANTIC_PATH_USES_LINEAGE_EDGE",
                "error",
                "Semantic path uses view lineage instead of a FK join.",
                edge_key=edge_key,
                downstream_impact="Compiler could join through provenance evidence.",
                suggested_action="Keep lineage as audit only and require trusted FK joins.",
            )
        ]
    issues: list[SemanticLayerInvariantIssue] = []
    if (
        not edge.automatic_join_allowed
        or not edge.verified_by_db
        or edge.enforcement_status != "enabled"
        or edge.validation_status != "trusted"
    ):
        issues.append(
            _metric_issue(
                metric,
                "SEMANTIC_PATH_USES_UNTRUSTED_EDGE",
                "error",
                "Semantic path uses an edge that is not compiler-safe.",
                edge_key=edge.edge_key,
                physical_label=edge.constraint_name,
                downstream_impact="Compiler could generate joins from unsafe relationship metadata.",
                suggested_action="Use only enabled, trusted, DB-verified FK joins.",
            )
        )
    from_node = nodes_by_key.get(edge.from_node_key)
    to_node = nodes_by_key.get(edge.to_node_key)
    if getattr(from_node, "bridge_candidate", False) or getattr(
        to_node,
        "bridge_candidate",
        False,
    ):
        issues.append(
            _metric_issue(
                metric,
                "SEMANTIC_PATH_REQUIRES_BRIDGE_POLICY",
                "error",
                "Semantic path traverses a bridge/many-to-many candidate.",
                edge_key=edge.edge_key,
                physical_label=edge.constraint_name,
                downstream_impact="Compiler joins can multiply rows through many-to-many paths.",
                suggested_action="Block this path until explicit bridge/allocation policy exists.",
            )
        )
    return issues


def _compiler_candidate_metrics(layer: SemanticLayer) -> list[SemanticMetric]:
    return [
        metric
        for metric in layer.metrics
        if metric.enabled and metric.compiler_eligibility in _COMPILER_ELIGIBLE
    ]


def _missing_key_code(metric: SemanticMetric) -> str:
    return (
        "AI_INVENTED_KEY_ACCEPTED"
        if metric.provenance == "ai"
        else "SEMANTIC_LAYER_KEY_MISSING_FROM_GRAPH"
    )


def _report(
    *,
    layer: SemanticLayer,
    issues: list[SemanticLayerInvariantIssue],
) -> SemanticLayerInvariantReport:
    errors = sorted(
        [issue for issue in issues if issue.severity == "error"],
        key=_issue_sort_key,
    )
    warnings = sorted(
        [issue for issue in issues if issue.severity == "warning"],
        key=_issue_sort_key,
    )
    info = sorted(
        [issue for issue in issues if issue.severity == "info"],
        key=_issue_sort_key,
    )
    status: SemanticInvariantStatus = (
        "invalid" if errors else "valid_with_warnings" if warnings else "valid"
    )
    return SemanticLayerInvariantReport(
        status=status,
        errors=errors,
        warnings=warnings,
        info=info,
        summary=SemanticLayerInvariantSummary(
            metric_count=len(layer.metrics),
            compiler_candidate_metric_count=len(_compiler_candidate_metrics(layer)),
            eligible_metric_count=sum(
                metric.compiler_eligibility == "eligible"
                for metric in layer.metrics
            ),
            eligible_with_disclosure_metric_count=sum(
                metric.compiler_eligibility == "eligible_with_disclosure"
                for metric in layer.metrics
            ),
            ambiguity_count=len(layer.ambiguities),
            profile_synthesized_metric_count=sum(
                metric.provenance_detail == "quality_profile"
                for metric in layer.metrics
            ),
        ),
        blocking_codes=sorted({issue.code for issue in errors}),
    )


def _issue(
    *,
    code: str,
    severity: SemanticInvariantSeverity,
    message: str,
    metric_key: str | None = None,
    concept_key: str | None = None,
    column_key: str | None = None,
    edge_key: str | None = None,
    physical_label: str | None = None,
    downstream_impact: str = "",
    suggested_action: str = "",
) -> SemanticLayerInvariantIssue:
    return SemanticLayerInvariantIssue(
        code=code,
        severity=severity,
        message=message,
        metric_key=metric_key,
        concept_key=concept_key,
        column_key=column_key,
        edge_key=edge_key,
        physical_label=physical_label,
        downstream_impact=downstream_impact,
        suggested_action=suggested_action,
    )


def _metric_issue(
    metric: SemanticMetric,
    code: str,
    severity: SemanticInvariantSeverity,
    message: str,
    *,
    column_key: str | None = None,
    edge_key: str | None = None,
    physical_label: str | None = None,
    downstream_impact: str = "",
    suggested_action: str = "",
) -> SemanticLayerInvariantIssue:
    return _issue(
        code=code,
        severity=severity,
        message=message,
        metric_key=str(metric.metric_key),
        concept_key=str(metric.business_concept_key),
        column_key=column_key,
        edge_key=edge_key,
        physical_label=physical_label,
        downstream_impact=downstream_impact,
        suggested_action=suggested_action,
    )


def _issue_sort_key(issue: SemanticLayerInvariantIssue) -> tuple[str, str, str, str]:
    return (
        issue.code,
        issue.metric_key or "",
        issue.column_key or "",
        issue.edge_key or "",
    )


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


def _has_direct_fk_path(
    *,
    metric: SemanticMetric,
    target_node_key: str,
    edges_by_key: dict[str, object],
) -> bool:
    for edge_key in metric.required_join_edge_keys:
        edge = edges_by_key.get(edge_key)
        if not isinstance(edge, QueryabilityForeignKeyEdge):
            continue
        if (
            edge.from_node_key == metric.source_table_key
            and edge.to_node_key == target_node_key
            and edge.automatic_join_allowed
            and edge.verified_by_db
            and edge.enforcement_status == "enabled"
            and edge.validation_status == "trusted"
        ):
            return True
    return False


def _is_parent_to_child_compatibility(
    *,
    metric: SemanticMetric,
    edge_path: list[str],
    edges_by_key: dict[str, object],
) -> bool:
    for edge_key in edge_path:
        edge = edges_by_key.get(edge_key)
        if not isinstance(edge, QueryabilityForeignKeyEdge):
            continue
        if (
            edge.to_node_key == metric.grain_table_key
            and edge.parent_to_child == "zero_or_many"
        ):
            return True
    return False


def _has_metric_signal(
    layer: SemanticLayer,
    metric: SemanticMetric,
    *,
    tokens: tuple[str, ...],
) -> bool:
    upper_tokens = tuple(token.upper() for token in tokens)
    metric_key = str(metric.metric_key)
    concept_key = str(metric.business_concept_key)
    for warning in metric.validation_warnings + metric.eligibility_reasons:
        if any(token in warning.upper() for token in upper_tokens):
            return True
    for ambiguity in layer.ambiguities:
        if ambiguity.target_key not in {metric_key, concept_key}:
            continue
        haystack = f"{ambiguity.code} {ambiguity.summary}".upper()
        if any(token in haystack for token in upper_tokens):
            return True
    for issue in [
        *layer.validation_report.blocking_errors,
        *layer.validation_report.warnings,
        *layer.validation_report.info,
    ]:
        if issue.target_key not in {metric_key, concept_key, str(layer.semantic_version_id)}:
            continue
        haystack = f"{issue.code} {issue.message}".upper()
        if any(token in haystack for token in upper_tokens):
            return True
    return False


def _has_status_scope_signal(
    layer: SemanticLayer,
    metric: SemanticMetric,
    policy: SemanticPolicySnapshot,
) -> bool:
    if _has_metric_signal(layer, metric, tokens=("STATUS", "CANCEL", "VOID", "SCOPE")):
        return True
    if metric.compiler_eligibility == "eligible_with_disclosure":
        return True
    if metric.compiler_eligibility == "clarification_required":
        return True
    for issue in policy.required_metric_specs:
        if issue.business_concept_ref in {"revenue", "orders"} and (
            "status" in " ".join(issue.synonyms).casefold()
        ):
            return True
    return False


def _amount_ambiguity_resolved(
    metric: SemanticMetric,
    layer: SemanticLayer,
    graph: QueryabilityGraphArtifact,
    columns_by_key: dict[str, tuple[object, object]],
    policy: SemanticPolicySnapshot,
) -> bool:
    source_node = next(
        (node for node in graph.nodes if node.node_key == metric.source_table_key),
        None,
    )
    if source_node is None:
        return True
    amount_columns = [
        column
        for column in source_node.columns
        if column.queryability_status == "queryable"
        and column.sensitivity == "none"
        and (
            column.technical_role == "money_candidate"
            or any(token in column.name.casefold() for token in _AMOUNT_TOKENS)
        )
    ]
    if len(amount_columns) <= 1:
        return True
    if _has_metric_signal(layer, metric, tokens=("AMOUNT", "REVENUE", "TOTAL", "TAX", "FREIGHT", "DISCOUNT")):
        return True
    for spec in policy.required_metric_specs:
        if (
            spec.business_concept_ref == "revenue"
            and spec.expected_variant == metric.metric_variant
            and spec.source_table_key == metric.source_table_key
            and spec.measure_column_key == metric.measure_column_key
        ):
            return True
    measure = columns_by_key.get(metric.measure_column_key) if metric.measure_column_key else None
    return measure is None


def _date_resolved_by_policy(
    metric: SemanticMetric,
    policy: SemanticPolicySnapshot,
) -> bool:
    for spec in policy.required_metric_specs:
        if (
            spec.expected_variant == metric.metric_variant
            and spec.source_table_key == metric.source_table_key
            and spec.default_date_column_key == metric.default_date_column_key
        ):
            return True
    return False


def _business_date_columns(node) -> list[object]:
    return [
        column
        for column in node.columns
        if column.queryability_status == "queryable"
        and column.technical_role == "date"
        and not _is_audit_date(column.name)
        and (
            any(token in column.name.casefold() for token in _BUSINESS_DATE_TOKENS)
            or column.name.casefold().startswith("data")
        )
    ]


def _is_audit_date(name: str) -> bool:
    normalized = "".join(ch for ch in name.casefold() if ch.isalnum())
    return any(token in normalized for token in _AUDIT_DATE_TOKENS)


def _node_label(node) -> str:
    return f"{node.schema_name}.{node.object_name}"


def _column_label(node, column) -> str:
    return f"{node.schema_name}.{node.object_name}.{column.name}"
