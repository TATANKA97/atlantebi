import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

from app.models import (
    QueryIntentAuditEvent,
    QueryIntentClarification,
    QueryIntentClarificationOption,
    QueryIntentGroupByDimension,
    QueryIntentPlan,
    QueryIntentRejectedAlternative,
    QueryIntentRequest,
    QueryIntentResult,
    QueryIntentTimeRange,
    QueryIntentUnsupportedReason,
    QueryabilityForeignKeyEdge,
    QueryabilityGraphArtifact,
    SemanticFilter,
    SemanticMetric,
)


_YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")
_MONTHS = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
}
_MONTH_PATTERN = "|".join(_MONTHS)
_DATE_RANGE_PATTERN = re.compile(
    rf"\bda(?:l)?\s+(\d{{1,2}})\s+({_MONTH_PATTERN})\s+(19\d{{2}}|20\d{{2}})"
    rf"\s+a(?:l)?\s+(\d{{1,2}})\s+({_MONTH_PATTERN})\s+(19\d{{2}}|20\d{{2}})\b"
)
_MONTH_YEAR_PATTERN = re.compile(rf"\b({_MONTH_PATTERN})\s+(19\d{{2}}|20\d{{2}})\b")
_RELATIVE_TIME_TERMS = (
    "mese scorso",
    "scorso mese",
    "ultimo mese",
    "ultimi",
    "scorsa settimana",
    "settimana scorsa",
    "anno scorso",
    "trimestre scorso",
)
_COMPARISON_TERMS = (
    " vs ",
    " versus ",
    "confronta",
    "confronto",
    "rispetto a",
    "anno su anno",
    "mese su mese",
    "yoy",
    "mom",
)
_CALCULATED_TERMS = (
    "%",
    "calcol",
    "conversione",
    "incidenza",
    "margine",
    "percentuale",
    "profitto",
    "quota",
    "ratio",
    "tasso",
)
_DESTRUCTIVE_TERMS = (
    "aggiorna",
    "cancella",
    "crea record",
    "delete",
    "drop",
    "elimina",
    "insert",
    "inserisci",
    "modifica",
    "rimuovi",
    "truncate",
    "update",
)
_REVENUE_TERMS = ("fatturato", "ricavi", "vendite", "revenue")
_REVENUE_LINE_DETAIL_TERMS = (
    "fatturato righe",
    "fatturato linee",
    "fatturato dettaglio",
    "line revenue",
    "line item revenue",
)
_GENERIC_LINE_DETAIL_TERMS = ("righe", "linee", "dettaglio", "line item")
_QUANTITY_TERMS = ("quantita", "pezzi", "unita vendute")
_CUSTOMER_TERMS = ("clienti", "customer")
_ORDER_CUSTOMER_TERMS = (
    "clienti che hanno ordinato",
    "clienti ordinanti",
    "clienti con ordini",
    "hanno ordinato",
    "hanno fatto ordini",
    "hanno comprato",
    "acquirenti",
    "order customers",
)
_CUSTOMER_MASTER_TERMS = (
    "clienti in anagrafica",
    "anagrafica clienti",
    "clienti censiti",
    "clienti registrati",
    "customer master",
    "registered customers",
    "totale clienti registrati",
)
_DOCUMENT_TOTAL_TERMS = ("totale documento", "totaldue", "total amount due")
_NET_REVENUE_TERMS = ("fatturato netto", "net revenue")
_ORDER_TERMS = ("ordini", "ordine", "documenti vendita", "sales orders", "orders")
_CATEGORY_TERMS = ("categoria prodotto", "categorie prodotto", "categoria")
_PRODUCT_TERMS = ("prodotto", "prodotti", "product")
_EMAIL_TERMS = ("email", "e-mail", "mail")
_ONLINE_TERMS = ("e commerce", "e-commerce", "ecommerce", "online", "ordini online", "web")
_OFFLINE_TERMS = (
    "offline",
    "rappresentante",
    "sales rep",
    "staff",
    "venditore",
)
_BLACK_COLOR_TERMS = (
    "color black",
    "color nero",
    "colore black",
    "colore nero",
    "prodotti neri",
    "prodotto nero",
)


@dataclass(frozen=True)
class _SemanticIndexes:
    metrics_by_key: dict[str, SemanticMetric]
    metrics_by_concept_variant: dict[tuple[str, str], SemanticMetric]
    columns_by_key: set[str]
    safe_filter_columns_by_object_name: dict[tuple[str, str], str]
    sensitive_email_column_available: bool
    concept_aliases: dict[str, set[str]]
    metric_aliases: dict[tuple[str, str], set[str]]


@dataclass(frozen=True)
class _DimensionSelection:
    kind: str
    column_key: str
    label: str


@dataclass(frozen=True)
class _MetricSelection:
    concept_ref: str
    variant: str
    disclosure: str | None = None


@dataclass(frozen=True)
class _DimensionCompatibility:
    safety: str
    edge_path: list[str]


def resolve_query_intent(request: QueryIntentRequest) -> QueryIntentResult:
    indexes = _build_indexes(request)
    audit_trail = _audit_ai_candidate(request, indexes)
    readiness = _validate_semantic_readiness(request)
    if readiness is not None:
        return readiness.model_copy(update={"audit_trail": audit_trail})

    normalized = _normalize(request.question)
    unsupported = _detect_out_of_scope(normalized)
    if unsupported is not None:
        return _blocked(
            unsupported,
            _blocked_message(unsupported),
            audit_trail=audit_trail,
        )

    sensitive_block = _detect_sensitive_dimension_or_filter(normalized, indexes)
    if sensitive_block is not None:
        return _blocked(
            "sensitive_filter_not_allowed",
            sensitive_block,
            audit_trail=audit_trail,
        )

    time_range = _parse_time_range(normalized)
    dimension = _select_dimension(normalized, request.graph)
    filters = _select_filters(normalized, indexes)

    metric_selection = _select_metric(normalized, dimension, indexes)
    if metric_selection is None:
        return _blocked(
            "metric_not_eligible",
            "The request does not map to an eligible semantic metric in V1.",
            audit_trail=audit_trail,
        )
    if metric_selection == "customers_clarification":
        return _customers_clarification(indexes, audit_trail)

    metric = _metric_for_selection(indexes, metric_selection)
    if metric is None:
        return _blocked(
            "metric_not_eligible",
            "The selected semantic metric is not available in the active layer.",
            audit_trail=audit_trail,
        )

    if request.policy.order_status_scope == "clarification_required" and (
        metric_selection.concept_ref in {"revenue", "orders"}
    ):
        return _order_status_clarification(metric, metric_selection, audit_trail)

    if metric.compiler_eligibility == "not_eligible":
        return _blocked(
            "metric_not_eligible",
            "The selected semantic metric is not compiler eligible.",
            audit_trail=audit_trail,
        )
    if metric.compiler_eligibility == "clarification_required":
        return _blocked(
            "metric_not_eligible",
            "The selected semantic metric needs clarification outside this V1 request.",
            audit_trail=audit_trail,
        )

    dimension_plan: list[QueryIntentGroupByDimension] = []
    required_edges: list[str] = list(metric.required_join_edge_keys)
    rejected: list[QueryIntentRejectedAlternative] = []
    disclosures: list[str] = []
    if metric_selection.disclosure:
        disclosures.append(metric_selection.disclosure)
    if metric_selection.concept_ref in {"revenue", "orders"}:
        disclosures.append("Order status scope defaults to all statuses in V1.")

    if dimension is not None:
        compatibility = _dimension_compatibility(
            metric,
            dimension.column_key,
            request.graph,
        )
        if compatibility is None:
            return _blocked(
                "unsafe_dimension_for_metric",
                "The requested grouping dimension is not safe for the selected metric.",
                audit_trail=audit_trail,
                rejected=[
                    QueryIntentRejectedAlternative(
                        reason="unsafe_dimension_for_metric",
                        metric_key=metric.metric_key,
                        dimension_column_key=dimension.column_key,
                        message=(
                            "No grain-safe path exists between the metric and "
                            f"{dimension.label}."
                        ),
                    )
                ],
            )
        if compatibility.safety == "forbidden":
            return _blocked(
                "unsafe_dimension_for_metric",
                "The requested grouping dimension would violate metric grain safety.",
                audit_trail=audit_trail,
                rejected=[
                    QueryIntentRejectedAlternative(
                        reason="unsafe_dimension_for_metric",
                        metric_key=metric.metric_key,
                        dimension_column_key=dimension.column_key,
                        message=(
                            "Header-grain metrics cannot be grouped by lower-grain "
                            f"{dimension.label} dimensions in V1."
                        ),
                    )
                ],
            )
        dimension_plan.append(
            QueryIntentGroupByDimension(
                column_key=dimension.column_key,
                edge_path=list(compatibility.edge_path),
                safety="safe",
            )
        )
        required_edges = _merge_edges(required_edges, compatibility.edge_path)

    if metric_selection.concept_ref == "revenue" and dimension is not None:
        if (
            dimension.kind in {"product", "category"}
            and metric.metric_variant == "line_detail"
        ):
            disclosures.append(
                "Product-grain revenue uses line revenue because header revenue "
                "cannot be allocated to product dimensions in V1."
            )

    audit_trail = [
        *audit_trail,
        *_audit_ai_candidate_decision(
            request=request,
            indexes=indexes,
            metric=metric,
            dimension_plan=dimension_plan,
            filters=filters,
        ),
    ]
    plan = QueryIntentPlan(
        primary_metric_key=metric.metric_key,
        requested_concept_ref=metric_selection.concept_ref,
        selected_variant=metric.metric_variant,
        effective_date_column_key=metric.default_date_column_key,
        time_range=time_range,
        group_by_dimensions=dimension_plan,
        required_edge_path_keys=required_edges,
        grain_safety_decision="safe",
        filters=filters,
        rejected_alternatives=rejected,
        disclosures=_dedupe(disclosures),
        audit_trail=audit_trail,
    )
    return QueryIntentResult(
        status="ready",
        plan=plan,
        audit_trail=audit_trail,
        message="Query intent resolved without SQL generation.",
    )


def _build_indexes(request: QueryIntentRequest) -> _SemanticIndexes:
    concept_lookup = {
        concept.business_concept_key: concept
        for concept in request.semantic_layer.business_concepts
    }
    concept_aliases = {
        concept.canonical_name: _aliases(
            concept.canonical_name,
            concept.display_name,
            *concept.synonyms,
        )
        for concept in request.semantic_layer.business_concepts
    }
    metrics_by_key = {
        str(metric.metric_key): metric for metric in request.semantic_layer.metrics
    }
    metrics_by_concept_variant: dict[tuple[str, str], SemanticMetric] = {}
    metric_aliases: dict[tuple[str, str], set[str]] = {}
    for metric in request.semantic_layer.metrics:
        concept = concept_lookup.get(metric.business_concept_key)
        if concept is not None:
            key = (concept.canonical_name, metric.metric_variant)
            metrics_by_concept_variant[key] = metric
            metric_aliases[key] = _aliases(
                metric.canonical_name,
                metric.metric_variant,
                metric.name,
            )
    columns_by_key = {column.column_key for column in request.semantic_layer.columns}
    semantic_columns_by_key = {
        column.column_key: column for column in request.semantic_layer.columns
    }
    safe_filter_columns_by_object_name = {}
    for node in request.graph.nodes:
        for graph_column in node.columns:
            semantic_column = semantic_columns_by_key.get(graph_column.column_key)
            if (
                semantic_column is not None
                and semantic_column.included
                and semantic_column.queryability_status == "queryable"
                and semantic_column.sensitivity == "none"
            ):
                safe_filter_columns_by_object_name[
                    (node.object_name, graph_column.name)
                ] = graph_column.column_key
    sensitive_email_column_available = any(
        "email" in _normalize(column.physical_name) and column.sensitivity != "none"
        for column in request.semantic_layer.columns
    )
    return _SemanticIndexes(
        metrics_by_key=metrics_by_key,
        metrics_by_concept_variant=metrics_by_concept_variant,
        columns_by_key=columns_by_key,
        safe_filter_columns_by_object_name=safe_filter_columns_by_object_name,
        sensitive_email_column_available=sensitive_email_column_available,
        concept_aliases=concept_aliases,
        metric_aliases=metric_aliases,
    )


def _audit_ai_candidate(
    request: QueryIntentRequest,
    indexes: _SemanticIndexes,
) -> list[QueryIntentAuditEvent]:
    candidate = request.ai_candidate
    if not request.ai_enabled or candidate is None:
        return []
    events: list[QueryIntentAuditEvent] = []
    if (
        candidate.primary_metric_key is not None
        and str(candidate.primary_metric_key) not in indexes.metrics_by_key
    ):
        events.append(
            QueryIntentAuditEvent(
                code="AI_METRIC_KEY_REJECTED",
                message="AI candidate referenced a metric key outside the semantic layer.",
                metadata={"metric_key": str(candidate.primary_metric_key)},
            )
        )
    if (
        candidate.dimension_column_key is not None
        and candidate.dimension_column_key not in indexes.columns_by_key
    ):
        events.append(
            QueryIntentAuditEvent(
                code="AI_DIMENSION_KEY_REJECTED",
                message="AI candidate referenced a column key outside the semantic layer.",
                metadata={"column_key": candidate.dimension_column_key},
            )
        )
    for column_key in candidate.filter_column_keys:
        if column_key not in indexes.columns_by_key:
            events.append(
                QueryIntentAuditEvent(
                    code="AI_FILTER_KEY_REJECTED",
                    message="AI candidate referenced a filter key outside the semantic layer.",
                    metadata={"column_key": column_key},
                )
            )
    return events


def _audit_ai_candidate_decision(
    *,
    request: QueryIntentRequest,
    indexes: _SemanticIndexes,
    metric: SemanticMetric,
    dimension_plan: list[QueryIntentGroupByDimension],
    filters: list[SemanticFilter],
) -> list[QueryIntentAuditEvent]:
    candidate = request.ai_candidate
    if not request.ai_enabled or candidate is None:
        return []
    events: list[QueryIntentAuditEvent] = []
    if (
        candidate.primary_metric_key is not None
        and str(candidate.primary_metric_key) in indexes.metrics_by_key
    ):
        accepted = candidate.primary_metric_key == metric.metric_key
        events.append(
            QueryIntentAuditEvent(
                code=(
                    "AI_METRIC_CANDIDATE_ACCEPTED"
                    if accepted
                    else "AI_METRIC_CANDIDATE_IGNORED"
                ),
                message=(
                    "AI metric candidate matched the deterministic selection."
                    if accepted
                    else "AI metric candidate was valid but ignored by the deterministic canonicalizer."
                ),
                metadata={
                    "metric_key": str(candidate.primary_metric_key),
                    "selected_metric_key": str(metric.metric_key),
                },
            )
        )
    if (
        candidate.dimension_column_key is not None
        and candidate.dimension_column_key in indexes.columns_by_key
    ):
        selected_dimensions = {item.column_key for item in dimension_plan}
        accepted = candidate.dimension_column_key in selected_dimensions
        events.append(
            QueryIntentAuditEvent(
                code=(
                    "AI_DIMENSION_CANDIDATE_ACCEPTED"
                    if accepted
                    else "AI_DIMENSION_CANDIDATE_IGNORED"
                ),
                message=(
                    "AI dimension candidate matched the deterministic selection."
                    if accepted
                    else "AI dimension candidate was valid but ignored by the deterministic canonicalizer."
                ),
                metadata={
                    "column_key": candidate.dimension_column_key,
                },
            )
        )
    selected_filter_keys = {item.column_key for item in filters}
    for column_key in candidate.filter_column_keys:
        if column_key not in indexes.columns_by_key:
            continue
        accepted = column_key in selected_filter_keys
        events.append(
            QueryIntentAuditEvent(
                code=(
                    "AI_FILTER_CANDIDATE_ACCEPTED"
                    if accepted
                    else "AI_FILTER_CANDIDATE_IGNORED"
                ),
                message=(
                    "AI filter candidate matched the deterministic selection."
                    if accepted
                    else "AI filter candidate was valid but ignored by the deterministic canonicalizer."
                ),
                metadata={"column_key": column_key},
            )
        )
    return events


def _validate_semantic_readiness(
    request: QueryIntentRequest,
) -> QueryIntentResult | None:
    layer = request.semantic_layer
    stale = (
        layer.status != "active"
        or layer.freshness != "fresh"
        or layer.base_graph_hash != request.graph.graph_hash
        or layer.base_policy_hash != layer.semantic_policy_snapshot.policy_hash
        or layer.validation_report.status not in {"valid", "valid_with_warnings"}
        or bool(layer.validation_report.blocking_errors)
        or layer.validation_report.validated_revision != layer.revision
        or layer.validation_report.validated_at is None
        or layer.validation_report.validator_version != layer.validator_version
    )
    if stale:
        return _blocked(
            "semantic_layer_stale",
            "The semantic layer is not active, fresh, and validated.",
        )
    return None


def _detect_out_of_scope(normalized: str) -> QueryIntentUnsupportedReason | None:
    if any(term in normalized for term in _DESTRUCTIVE_TERMS):
        return "destructive_request_not_allowed"
    if any(term in normalized for term in _COMPARISON_TERMS):
        return "unsupported_comparison"
    if any(term in normalized for term in _RELATIVE_TIME_TERMS):
        return "unsupported_time_expression"
    if any(term in normalized for term in _CALCULATED_TERMS):
        return "unsupported_calculated_metric"
    if _is_multi_metric_request(normalized):
        return "multi_metric_not_supported"
    return None


def _detect_sensitive_dimension_or_filter(
    normalized: str,
    indexes: _SemanticIndexes,
) -> str | None:
    if not any(term in normalized for term in _EMAIL_TERMS):
        return None
    if indexes.sensitive_email_column_available:
        return "The requested filter or dimension targets a sensitive customer email column."
    return "Email-like customer fields are not allowed as V1 filters or dimensions."


def _parse_time_range(normalized: str) -> QueryIntentTimeRange | None:
    range_match = _DATE_RANGE_PATTERN.search(normalized)
    if range_match is not None:
        start = _date_from_parts(
            day=range_match.group(1),
            month_name=range_match.group(2),
            year=range_match.group(3),
        )
        inclusive_end = _date_from_parts(
            day=range_match.group(4),
            month_name=range_match.group(5),
            year=range_match.group(6),
        )
        if start is not None and inclusive_end is not None and start <= inclusive_end:
            end = inclusive_end + timedelta(days=1)
            return QueryIntentTimeRange(
                kind="custom",
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                label=f"{start.isoformat()} - {inclusive_end.isoformat()}",
            )

    month_match = _MONTH_YEAR_PATTERN.search(normalized)
    if month_match is not None:
        month = _MONTHS[month_match.group(1)]
        year = int(month_match.group(2))
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        return QueryIntentTimeRange(
            kind="month",
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            label=f"{month_match.group(1)} {year}",
        )

    match = _YEAR_PATTERN.search(normalized)
    if match is None:
        return None
    year = match.group(1)
    return QueryIntentTimeRange(
        kind="year",
        start_date=f"{year}-01-01",
        end_date=f"{int(year) + 1}-01-01",
        label=year,
    )


def _date_from_parts(*, day: str, month_name: str, year: str) -> date | None:
    try:
        return date(int(year), _MONTHS[month_name], int(day))
    except ValueError:
        return None


def _select_dimension(
    normalized: str,
    graph: QueryabilityGraphArtifact,
) -> _DimensionSelection | None:
    if any(term in normalized for term in _CATEGORY_TERMS):
        column_key = _graph_column_key(graph, "ProductCategory", "ProductCategoryID")
        if column_key is not None:
            return _DimensionSelection(
                kind="category",
                column_key=column_key,
                label="ProductCategory",
            )
    if any(term in normalized for term in _PRODUCT_TERMS):
        column_key = _graph_column_key(graph, "Product", "ProductID")
        if column_key is not None:
            return _DimensionSelection(
                kind="product",
                column_key=column_key,
                label="Product",
            )
    return None


def _select_filters(
    normalized: str,
    indexes: _SemanticIndexes,
) -> list[SemanticFilter]:
    filters: list[SemanticFilter] = []
    online_flag = _safe_filter_column(indexes, "SalesOrderHeader", "OnlineOrderFlag")
    if online_flag is not None:
        if _contains_any(normalized, _ONLINE_TERMS):
            filters.append(
                SemanticFilter(
                    column_key=online_flag,
                    operator="eq",
                    value=True,
                    value_type="boolean",
                )
            )
        elif _contains_any(normalized, _OFFLINE_TERMS):
            filters.append(
                SemanticFilter(
                    column_key=online_flag,
                    operator="eq",
                    value=False,
                    value_type="boolean",
                )
            )

    color = _safe_filter_column(indexes, "Product", "Color")
    if color is not None and _contains_any(normalized, _BLACK_COLOR_TERMS):
        filters.append(
            SemanticFilter(
                column_key=color,
                operator="eq",
                value="black",
                value_type="string",
            )
        )

    return filters


def _safe_filter_column(
    indexes: _SemanticIndexes,
    object_name: str,
    column_name: str,
) -> str | None:
    return indexes.safe_filter_columns_by_object_name.get((object_name, column_name))


def _select_metric(
    normalized: str,
    dimension: _DimensionSelection | None,
    indexes: _SemanticIndexes,
) -> _MetricSelection | str | None:
    revenue_mentioned = _mentions_concept(normalized, indexes, "revenue", _REVENUE_TERMS)
    if _mentions_concept(normalized, indexes, "customers", _CUSTOMER_TERMS):
        if _mentions_variant(
            normalized,
            indexes,
            "customers",
            "order_customers",
            _ORDER_CUSTOMER_TERMS,
        ):
            return _MetricSelection("customers", "order_customers")
        if _mentions_variant(
            normalized,
            indexes,
            "customers",
            "customer_master",
            _CUSTOMER_MASTER_TERMS,
        ):
            return _MetricSelection("customers", "customer_master")
        if not (
            revenue_mentioned
            or _mentions_concept(
                normalized,
                indexes,
                "quantity_sold",
                _QUANTITY_TERMS,
            )
        ):
            return "customers_clarification"

    if _mentions_concept(normalized, indexes, "quantity_sold", _QUANTITY_TERMS):
        return _MetricSelection("quantity_sold", "line_quantity")

    if _mentions_variant(
        normalized,
        indexes,
        "revenue",
        "document_total",
        _DOCUMENT_TOTAL_TERMS,
    ):
        return _MetricSelection("revenue", "document_total")

    if revenue_mentioned:
        if _mentions_line_detail_revenue(normalized, indexes):
            return _MetricSelection("revenue", "line_detail")
        if dimension is not None and dimension.kind in {"product", "category"}:
            disclosure = None
            if _mentions_variant(
                normalized,
                indexes,
                "revenue",
                "net_header",
                _NET_REVENUE_TERMS,
            ):
                disclosure = (
                    "The request says net revenue, but product-level grouping uses "
                    "line revenue because header net revenue is unsafe by product in V1."
                )
            return _MetricSelection("revenue", "line_detail", disclosure)
        return _MetricSelection("revenue", "net_header")

    if _mentions_concept(normalized, indexes, "orders", _ORDER_TERMS):
        return _MetricSelection("orders", "header_count")

    return None


def _metric_for_selection(
    indexes: _SemanticIndexes,
    selection: _MetricSelection,
) -> SemanticMetric | None:
    return indexes.metrics_by_concept_variant.get(
        (selection.concept_ref, selection.variant)
    )


def _dimension_compatibility(
    metric: SemanticMetric,
    dimension_column_key: str,
    graph: QueryabilityGraphArtifact,
) -> _DimensionCompatibility | None:
    if dimension_column_key in metric.grain_column_keys:
        return _DimensionCompatibility(safety="safe", edge_path=[])
    declared = next(
        (
            item
            for item in metric.common_dimension_compatibility
            if item.dimension_column_key == dimension_column_key
        ),
        None,
    )
    if declared is not None:
        return _DimensionCompatibility(
            safety=declared.safety,
            edge_path=list(declared.edge_path),
        )
    safe_path = _safe_child_to_parent_path(
        graph,
        source_node_key=metric.source_table_key,
        target_column_key=dimension_column_key,
    )
    if safe_path is not None:
        return _DimensionCompatibility(safety="safe", edge_path=safe_path)
    return None


def _safe_child_to_parent_path(
    graph: QueryabilityGraphArtifact,
    *,
    source_node_key: str,
    target_column_key: str,
) -> list[str] | None:
    target_nodes = {
        node.node_key
        for node in graph.nodes
        for column in node.columns
        if column.column_key == target_column_key
    }
    if not target_nodes:
        return None
    if source_node_key in target_nodes:
        return []
    fk_edges = [
        edge
        for edge in graph.edges
        if isinstance(edge, QueryabilityForeignKeyEdge)
        and edge.automatic_join_allowed
        and edge.enforcement_status == "enabled"
        and edge.validation_status == "trusted"
    ]
    queue: list[tuple[str, list[str]]] = [(source_node_key, [])]
    visited: set[str] = {source_node_key}
    while queue:
        current_node, path = queue.pop(0)
        if len(path) >= 4:
            continue
        for edge in fk_edges:
            if edge.from_node_key != current_node:
                continue
            next_path = [*path, edge.edge_key]
            if edge.to_node_key in target_nodes:
                return next_path
            if edge.to_node_key not in visited:
                visited.add(edge.to_node_key)
                queue.append((edge.to_node_key, next_path))
    return None


def _customers_clarification(
    indexes: _SemanticIndexes,
    audit_trail: list[QueryIntentAuditEvent],
) -> QueryIntentResult:
    order_customers = indexes.metrics_by_concept_variant.get(
        ("customers", "order_customers")
    )
    customer_master = indexes.metrics_by_concept_variant.get(
        ("customers", "customer_master")
    )
    options: list[QueryIntentClarificationOption] = []
    if order_customers is not None:
        options.append(
            QueryIntentClarificationOption(
                label="Clienti che hanno ordinato",
                value="order_customers",
                metric_key=order_customers.metric_key,
                business_concept_ref="customers",
                metric_variant="order_customers",
            )
        )
    if customer_master is not None:
        options.append(
            QueryIntentClarificationOption(
                label="Clienti in anagrafica",
                value="customer_master",
                metric_key=customer_master.metric_key,
                business_concept_ref="customers",
                metric_variant="customer_master",
            )
        )
    if not options:
        return _blocked(
            "metric_not_eligible",
            "No valid customer population metrics are available.",
            audit_trail=audit_trail,
        )
    return QueryIntentResult(
        status="needs_clarification",
        clarification=QueryIntentClarification(
            reason_code="CUSTOMER_POPULATION_AMBIGUOUS",
            question="Vuoi clienti in anagrafica o clienti che hanno ordinato?",
            options=options,
        ),
        audit_trail=audit_trail,
        message="The customer request maps to multiple valid populations.",
    )


def _order_status_clarification(
    metric: SemanticMetric,
    selection: _MetricSelection,
    audit_trail: list[QueryIntentAuditEvent],
) -> QueryIntentResult:
    return QueryIntentResult(
        status="needs_clarification",
        clarification=QueryIntentClarification(
            reason_code="ORDER_STATUS_SCOPE_REQUIRED",
            question="Quale stato ordine vuoi includere?",
            options=[
                QueryIntentClarificationOption(
                    label="Tutti gli stati",
                    value="all_statuses",
                    metric_key=metric.metric_key,
                    business_concept_ref=selection.concept_ref,
                    metric_variant=selection.variant,
                ),
                QueryIntentClarificationOption(
                    label="Solo ordini completati",
                    value="completed_only",
                    metric_key=metric.metric_key,
                    business_concept_ref=selection.concept_ref,
                    metric_variant=selection.variant,
                ),
            ],
        ),
        audit_trail=audit_trail,
        message="Order status scope requires user clarification by policy.",
    )


def _blocked(
    reason: QueryIntentUnsupportedReason,
    message: str,
    *,
    audit_trail: list[QueryIntentAuditEvent] | None = None,
    rejected: list[QueryIntentRejectedAlternative] | None = None,
) -> QueryIntentResult:
    events = list(audit_trail or [])
    for alternative in rejected or []:
        events.append(
            QueryIntentAuditEvent(
                code="FORBIDDEN_ALTERNATIVE_RECORDED",
                message=alternative.message,
                metadata={
                    "reason": alternative.reason,
                    "metric_key": str(alternative.metric_key)
                    if alternative.metric_key
                    else "",
                    "dimension_column_key": alternative.dimension_column_key or "",
                },
            )
        )
    return QueryIntentResult(
        status="blocked",
        unsupported_reason=reason,
        audit_trail=events,
        message=message,
    )


def _blocked_message(reason: QueryIntentUnsupportedReason) -> str:
    return {
        "multi_metric_not_supported": (
            "Query Intent Resolver V1 supports one primary metric per request."
        ),
        "unsafe_dimension_for_metric": (
            "The requested dimension is not grain-safe for the selected metric."
        ),
        "semantic_layer_stale": "The semantic layer is stale or not validated.",
        "metric_not_eligible": "The selected metric is not compiler eligible.",
        "sensitive_filter_not_allowed": (
            "The requested filter or dimension uses a sensitive column."
        ),
        "unsupported_time_expression": (
            "Query Intent Resolver V1 supports explicit simple dates only."
        ),
        "unsupported_calculated_metric": (
            "Calculated metrics are outside Query Intent Resolver V1."
        ),
        "unsupported_comparison": "Comparisons are outside Query Intent Resolver V1.",
        "destructive_request_not_allowed": (
            "Destructive or data-changing operations are outside Query Intent Resolver V1."
        ),
    }[reason]


def _graph_column_key(
    graph: QueryabilityGraphArtifact,
    object_name: str,
    column_name: str,
) -> str | None:
    for node in graph.nodes:
        if node.object_name == object_name:
            for column in node.columns:
                if column.name == column_name:
                    return column.column_key
    return None


def _mentions_revenue(normalized: str) -> bool:
    return any(term in normalized for term in _REVENUE_TERMS)


def _is_multi_metric_request(normalized: str) -> bool:
    if " e " not in normalized and " and " not in normalized:
        return False
    mentioned = [
        _contains_any(normalized, (*_REVENUE_TERMS, "sales")),
        _contains_any(normalized, (*_QUANTITY_TERMS, "units")),
        _contains_any(normalized, _ORDER_TERMS),
        _contains_any(normalized, _CUSTOMER_TERMS),
    ]
    return sum(1 for item in mentioned if item) > 1


def _mentions_line_detail_revenue(
    normalized: str,
    indexes: _SemanticIndexes,
) -> bool:
    return (
        _contains_any(normalized, _REVENUE_LINE_DETAIL_TERMS)
        or _mentions_variant(
            normalized,
            indexes,
            "revenue",
            "line_detail",
            _GENERIC_LINE_DETAIL_TERMS,
        )
    )


def _mentions_quantity(normalized: str) -> bool:
    return any(term in normalized for term in _QUANTITY_TERMS)


def _mentions_concept(
    normalized: str,
    indexes: _SemanticIndexes,
    concept_ref: str,
    fallback_terms: tuple[str, ...],
) -> bool:
    return _contains_any(
        normalized,
        (*fallback_terms, *indexes.concept_aliases.get(concept_ref, set())),
    )


def _mentions_variant(
    normalized: str,
    indexes: _SemanticIndexes,
    concept_ref: str,
    metric_variant: str,
    fallback_terms: tuple[str, ...],
) -> bool:
    return _contains_any(
        normalized,
        (
            *fallback_terms,
            *indexes.metric_aliases.get((concept_ref, metric_variant), set()),
        ),
    )


def _contains_any(normalized: str, terms: tuple[str, ...] | set[str]) -> bool:
    return any(term and term in normalized for term in terms)


def _merge_edges(first: list[str], second: list[str]) -> list[str]:
    merged: list[str] = []
    for edge in [*first, *second]:
        if edge not in merged:
            merged.append(edge)
    return merged


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _normalize(value: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents.lower()).strip()


def _aliases(*values: str | None) -> set[str]:
    return {_normalize(value) for value in values if value}
