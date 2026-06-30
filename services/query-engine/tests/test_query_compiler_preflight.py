from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from app.drivers.base import (
    SchemaColumnMetadata,
    SchemaForeignKeyMetadata,
    SchemaIntrospectionResult,
    SchemaPrimaryKeyMetadata,
    SchemaTableMetadata,
)
from app.models import (
    Engine,
    QueryIntentGroupByDimension,
    QueryIntentPlan,
    QueryIntentResult,
    QueryIntentTimeRange,
    SemanticBusinessConcept,
    SemanticDimensionCompatibility,
    SemanticFilter,
    SemanticLayer,
    SemanticMetric,
    SemanticMetricFormat,
)
from app.query_compiler_preflight import validate_query_compiler_preflight
from app.semantic import (
    compute_metric_definition_hash,
    compute_semantic_hash,
    validate_semantic_layer,
)
from tests.test_query_intent import (
    active_adventureworks_layer,
    metric_by_variant,
    request_for,
)
from app.query_intent import resolve_query_intent
from tests.test_queryability_builder import (
    build,
    column,
    foreign_key,
    snapshot,
    table,
)
from tests.test_semantic_builder import (
    VALIDATED_AT,
    adventureworks_graph,
    column_key,
    edge_key,
    semantic_draft,
)


def test_stage_results_missing_snapshot_cap_and_plan_trace_are_deterministic() -> None:
    graph = adventureworks_graph()
    layer = _active_layer(validate_semantic_layer(layer=semantic_draft(graph), graph=graph, validated_at=VALIDATED_AT))
    metric = _eligible(metric_by_variant(layer, "customer_master"))
    layer = _layer_with_metrics(layer, [metric])
    result = _intent(metric)

    report = validate_query_compiler_preflight(
        result,
        layer,
        graph,
        _graph_report(),
        _semantic_invariant_report(),
    )

    assert [stage.stage for stage in report.stage_results] == [
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
    ]
    assert report.status == "ready_with_warnings"
    assert report.decision_category == "safe_with_disclosure"
    assert "SCHEMA_SNAPSHOT_MISSING" in _codes(report)
    assert report.plan_trace.selected_metric_key == str(metric.metric_key)
    assert report.plan_trace.cache_key_inputs_preview["metric_key"] == str(metric.metric_key)
    assert "selected_segments" in report.to_debug_dict()["plan_trace"]
    assert "expanded_segment_filters" in report.to_debug_dict()["plan_trace"]
    assert "segment_policy_sources" in report.to_debug_dict()["plan_trace"]
    assert "select " not in json.dumps(report.plan_trace.to_debug_dict() if hasattr(report.plan_trace, "to_debug_dict") else report.to_debug_dict()["plan_trace"]).lower()


def test_metadata_prefetch_blocks_missing_metric_before_downstream_checks() -> None:
    graph = adventureworks_graph()
    layer = _active_layer(validate_semantic_layer(layer=semantic_draft(graph), graph=graph, validated_at=VALIDATED_AT))
    metric = _eligible(metric_by_variant(layer, "customer_master"))
    missing_result = _intent(metric).model_copy(
        update={
            "plan": _intent(metric).plan.model_copy(
                update={"primary_metric_key": UUID("99999999-9999-4999-8999-999999999999")}
            )
        }
    )

    report = validate_query_compiler_preflight(
        missing_result,
        layer,
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )

    assert report.status == "blocked"
    assert report.decision_category == "invalid_artifact"
    assert "METRIC_NOT_FOUND" in report.blocking_codes
    prefetch = _stage(report, "metadata_prefetch")
    assert prefetch.status == "blocked"


def test_not_eligible_metric_is_unsupported_for_preflight() -> None:
    graph = adventureworks_graph()
    layer = _active_layer(validate_semantic_layer(layer=semantic_draft(graph), graph=graph, validated_at=VALIDATED_AT))
    metric = metric_by_variant(layer, "customer_master").model_copy(
        update={"compiler_eligibility": "not_eligible"}
    )

    report = validate_query_compiler_preflight(
        _intent(metric),
        _layer_with_metrics(layer, [metric]),
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )

    assert "METRIC_NOT_COMPILER_ELIGIBLE" in report.blocking_codes
    assert report.decision_category == "unsupported"


def test_mixed_blocking_categories_use_deterministic_precedence() -> None:
    graph = adventureworks_graph()
    layer = _active_layer(validate_semantic_layer(layer=semantic_draft(graph), graph=graph, validated_at=VALIDATED_AT))
    metric = _eligible(metric_by_variant(layer, "customer_master"))
    result = QueryIntentResult(
        status="blocked",
        unsupported_reason="multi_metric_not_supported",
        message="blocked",
    )
    invalid_artifact_report = validate_query_compiler_preflight(
        result,
        _layer_with_metrics(layer, [metric]),
        graph,
        _graph_report(status="invalid"),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )
    stale_layer = layer.model_copy(update={"freshness": "stale"})
    stale_report = validate_query_compiler_preflight(
        result,
        _layer_with_metrics(stale_layer, [metric]),
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )

    assert invalid_artifact_report.decision_category == "invalid_artifact"
    assert {"QUERYABILITY_GRAPH_INVALID", "QUERY_INTENT_MULTI_METRIC_NOT_SUPPORTED"} <= _codes(invalid_artifact_report)
    assert stale_report.decision_category == "stale"
    assert {"SEMANTIC_LAYER_STALE", "QUERY_INTENT_MULTI_METRIC_NOT_SUPPORTED"} <= _codes(stale_report)


def test_stale_untrusted_path_and_missing_policy_emit_all_codes_with_stale_precedence() -> None:
    graph = _header_detail_graph(with_fk=True, disabled=True)
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)).model_copy(update={"freshness": "stale"}),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "revenue",
    )
    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="revenue",
        variant="generic_revenue",
        table_name="DORIG",
        measure_column="IMPORTO",
        grain_columns=["IDRIG"],
        date_column=("DOTES", "DATA_DOC"),
        required_edges=["FK_DORIG_DOTES"],
        value_type="currency",
        eligibility="eligible",
    )

    report = validate_query_compiler_preflight(
        _intent(metric, concept_ref="revenue", date_column=_column_key(graph, "DOTES", "DATA_DOC")),
        _layer_with_metrics(layer, [metric]),
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )

    assert {
        "SEMANTIC_LAYER_STALE",
        "GRAPH_PATH_USES_UNTRUSTED_EDGE",
        "STATUS_SCOPE_REQUIRES_POLICY",
    } <= _codes(report)
    assert report.decision_category == "stale"


def test_adventureworks_status_disclosure_policy_source_and_no_resolver_mutation() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    result = resolve_query_intent(request_for("fatturato 2008", layer=layer))
    before = result.model_dump(mode="json")

    report = validate_query_compiler_preflight(
        result,
        layer,
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )

    assert result.model_dump(mode="json") == before
    assert "STATUS_SCOPE_DEFAULT_ALL_STATUSES_DISCLOSURE" in _codes(report)
    status_issue = next(
        issue
        for issue in report.warnings
        if issue.code == "STATUS_SCOPE_DEFAULT_ALL_STATUSES_DISCLOSURE"
    )
    assert status_issue.stage == "policy_permission_check"
    assert status_issue.policy_source == "semantic_layer"


def test_ugly_pmi_without_evidence_fails_and_with_explicit_evidence_passes() -> None:
    graph = _ugly_pmi_graph()
    empty_layer = _active_layer(_empty_layer_for(graph))
    missing_metric = QueryIntentResult(
        status="blocked",
        unsupported_reason="metric_not_eligible",
        message="No metric evidence.",
    )

    no_evidence = validate_query_compiler_preflight(
        missing_metric,
        empty_layer,
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )

    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="quantity_sold",
        variant="line_quantity",
        table_name="DORIG",
        measure_column="QTA",
        grain_columns=["ID"],
        dimension_column=("CATART", "CAT"),
        dimension_edges=["FK_DORIG_ARTICO", "FK_ARTICO_CATART"],
        value_type="number",
    )
    evidence_layer = _layer_with_metrics(
        _layer_with_concept(empty_layer, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "quantity_sold"),
        [metric],
    )
    passed = validate_query_compiler_preflight(
        _intent(
            metric,
            concept_ref="quantity_sold",
            group_by=[
                QueryIntentGroupByDimension(
                    column_key=_column_key(graph, "CATART", "CAT"),
                    edge_path=[_edge_key(graph, "FK_DORIG_ARTICO"), _edge_key(graph, "FK_ARTICO_CATART")],
                    safety="safe",
                )
            ],
            required_edges=[_edge_key(graph, "FK_DORIG_ARTICO"), _edge_key(graph, "FK_ARTICO_CATART")],
        ),
        evidence_layer,
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        schema_snapshot=_ugly_pmi_snapshot(),
    )

    assert no_evidence.status == "blocked"
    assert no_evidence.decision_category == "unsupported"
    assert passed.status == "ready"
    assert passed.decision_category == "safe"


def test_missing_and_disabled_fk_fail_closed_without_name_inference() -> None:
    graph = _header_detail_graph(with_fk=False)
    layer = _active_layer(_empty_layer_for(graph))
    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="revenue",
        variant="line_detail",
        table_name="DORIG",
        measure_column="IMPORTO",
        grain_columns=["IDRIG"],
        date_column=("DOTES", "DATA_DOC"),
        required_edges=[edge_key("FK_DORIG_DOTES")],
        value_type="currency",
        eligibility="eligible_with_disclosure",
    )
    layer = _layer_with_metrics(
        _layer_with_concept(layer, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "revenue"),
        [metric],
    )
    missing_fk = validate_query_compiler_preflight(
        _intent(metric, concept_ref="revenue", date_column=_column_key(graph, "DOTES", "DATA_DOC"), required_edges=[edge_key("FK_DORIG_DOTES")]),
        layer,
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )
    disabled_graph = _header_detail_graph(with_fk=True, disabled=True)
    disabled_metric = metric.model_copy(
        update={"required_join_edge_keys": [_edge_key(disabled_graph, "FK_DORIG_DOTES")]}
    )
    disabled_layer = _layer_with_metrics(
        _layer_with_concept(_active_layer(_empty_layer_for(disabled_graph)), "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "revenue"),
        [disabled_metric],
    )
    disabled = validate_query_compiler_preflight(
        _intent(disabled_metric, concept_ref="revenue", date_column=_column_key(disabled_graph, "DOTES", "DATA_DOC"), required_edges=[_edge_key(disabled_graph, "FK_DORIG_DOTES")]),
        disabled_layer,
        disabled_graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )

    assert "GRAPH_PATH_INVALID" in missing_fk.blocking_codes
    assert missing_fk.decision_category == "insufficient_metadata"
    assert "GRAPH_PATH_USES_UNTRUSTED_EDGE" in disabled.blocking_codes
    assert disabled.decision_category == "unsafe"


def test_snapshot_selected_metadata_gap_blocks_contextually() -> None:
    graph = _header_detail_graph(with_fk=True)
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "revenue",
    )
    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="revenue",
        variant="line_detail",
        table_name="DORIG",
        measure_column="IMPORTO",
        grain_columns=["IDRIG"],
        date_column=("DOTES", "DATA_DOC"),
        required_edges=["FK_DORIG_DOTES"],
        value_type="currency",
        eligibility="eligible_with_disclosure",
    )

    report = validate_query_compiler_preflight(
        _intent(metric, concept_ref="revenue", date_column=_column_key(graph, "DOTES", "DATA_DOC")),
        _layer_with_metrics(layer, [metric]),
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        schema_snapshot=snapshot(
            tables=[
                table("DOTES", [column("ID", 1), column("DATA_DOC", 2, role="date", native_type="datetime")], primary_key=["ID"]),
                table("DORIG", [column("IDRIG", 1), column("IDTES", 2), column("IMPORTO", 3, role="money_candidate", native_type="money"), column("STATO", 4, role="text", native_type="nvarchar")], primary_key=["IDRIG"]),
            ],
            foreign_keys=[],
        ),
    )

    assert "SCHEMA_FK_NOT_FOUND" in report.blocking_codes
    assert report.decision_category == "insufficient_metadata"


def test_view_source_is_allowed_but_lineage_join_and_raw_sql_semantic_object_block() -> None:
    graph = _view_graph()
    base_layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "orders",
    )
    view_metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="orders",
        variant="view_count",
        table_name="VW_DOC",
        measure_column="ID",
        grain_columns=["ID"],
        value_type="count",
    )
    ok = validate_query_compiler_preflight(
        _intent(view_metric, concept_ref="orders"),
        _layer_with_metrics(base_layer, [view_metric]),
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
        policy={"status_scope": "include_all_with_disclosure"},
    )
    lineage_metric = view_metric.model_copy(
        update={"required_join_edge_keys": [next(edge.edge_key for edge in graph.edges)]}
    )
    lineage = validate_query_compiler_preflight(
        _intent(lineage_metric, concept_ref="orders", required_edges=[next(edge.edge_key for edge in graph.edges)]),
        _layer_with_metrics(base_layer, [lineage_metric]),
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )
    raw = validate_query_compiler_preflight(
        _intent(view_metric.model_copy(update={"reasoning_summary": "select * from source"}), concept_ref="orders"),
        _layer_with_metrics(base_layer, [view_metric.model_copy(update={"reasoning_summary": "select * from source"})]),
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )

    assert ok.status in {"ready", "ready_with_warnings"}
    assert "GRAPH_PATH_USES_LINEAGE" in lineage.blocking_codes
    assert "RAW_SQL_NOT_ALLOWED" in raw.blocking_codes


def test_generic_ambiguity_detectors_block_silent_amount_date_status_currency_and_pii() -> None:
    graph = _ambiguous_business_graph()
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "revenue",
    )
    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="revenue",
        variant="generic_revenue",
        table_name="DOC_HEAD",
        measure_column="TOTAL_AMOUNT",
        grain_columns=["ID"],
        date_column=("DOC_HEAD", "UPDATED_AT"),
        value_type="currency",
        currency=None,
        eligibility="eligible",
    )
    filter_item = SemanticFilter(
        column_key=_column_key(graph, "DOC_HEAD", "CUSTOMER_EMAIL"),
        operator="eq",
        value="redacted@example.com",
        value_type="string",
    )
    result = _intent(
        metric,
        concept_ref="revenue",
        date_column=_column_key(graph, "DOC_HEAD", "UPDATED_AT"),
        filters=[filter_item],
    )

    report = validate_query_compiler_preflight(
        result,
        _layer_with_metrics(layer, [metric]),
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )

    assert {
        "AMOUNT_SEMANTIC_AMBIGUITY_NOT_RECORDED",
        "AUDIT_DATE_USED_AS_BUSINESS_DEFAULT",
        "MULTIPLE_DATE_CANDIDATES_REQUIRE_CLARIFICATION",
        "STATUS_SCOPE_REQUIRES_POLICY",
        "CURRENCY_MISSING",
        "FILTER_PII_REQUIRES_POLICY",
    } <= _codes(report)
    assert report.decision_category == "needs_policy"


def test_table_without_pk_bridge_and_semantic_invariant_errors_block() -> None:
    no_pk_graph = build(
        snapshot(
            tables=[
                table("FACT_ROWS", [column("AMOUNT", 1, role="money_candidate", native_type="money")])
            ]
        )
    )
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(no_pk_graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "revenue",
    )
    metric = _semantic_metric(
        no_pk_graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="revenue",
        variant="generic_revenue",
        table_name="FACT_ROWS",
        measure_column="AMOUNT",
        grain_columns=["AMOUNT"],
        value_type="currency",
        eligibility="eligible_with_disclosure",
    )
    invariant_error = SimpleNamespace(
        status="invalid",
        errors=[
            SimpleNamespace(
                code="SEMANTIC_PATH_USES_UNTRUSTED_EDGE",
                metric_key=str(metric.metric_key),
                column_key=None,
                edge_key=None,
                physical_label=None,
                downstream_impact="bad path",
                suggested_action="fix path",
            )
        ],
        warnings=[],
        info=[],
        blocking_codes=["SEMANTIC_PATH_USES_UNTRUSTED_EDGE"],
    )

    report = validate_query_compiler_preflight(
        _intent(metric, concept_ref="revenue"),
        _layer_with_metrics(layer, [metric]),
        no_pk_graph,
        _graph_report(),
        invariant_error,
        snapshot_checks_applicable=False,
    )

    assert "TABLE_WITHOUT_PK_UNSAFE_FOR_GRAIN" in _codes(report)
    assert "SEMANTIC_INVARIANT_ERROR" in report.blocking_codes


def test_bridge_many_to_many_path_requires_policy() -> None:
    graph = _bridge_graph()
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "orders",
    )
    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="orders",
        variant="bridge_count",
        table_name="CUSTOMER_PRODUCT",
        measure_column="CUSTOMER_ID",
        grain_columns=["CUSTOMER_ID", "PRODUCT_ID"],
        dimension_column=("PRODUCT", "PRODUCT_ID"),
        dimension_edges=["FK_BRIDGE_PRODUCT"],
        value_type="count",
    )

    report = validate_query_compiler_preflight(
        _intent(
            metric,
            concept_ref="orders",
            group_by=[
                QueryIntentGroupByDimension(
                    column_key=_column_key(graph, "PRODUCT", "PRODUCT_ID"),
                    edge_path=[_edge_key(graph, "FK_BRIDGE_PRODUCT")],
                    safety="safe",
                )
            ],
            required_edges=[_edge_key(graph, "FK_BRIDGE_PRODUCT")],
        ),
        _layer_with_metrics(layer, [metric]),
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )

    assert "GRAPH_PATH_REQUIRES_BRIDGE_POLICY" in report.blocking_codes
    assert report.decision_category == "needs_policy"


def test_composite_multischema_trusted_path_can_pass() -> None:
    graph = _composite_multischema_graph()
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "quantity_sold",
    )
    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="quantity_sold",
        variant="line_quantity",
        table_name="DOC_LINE",
        measure_column="QTY",
        grain_columns=["COMPANY_ID", "DOC_ID", "LINE_NO"],
        date_column=("DOC_HEAD", "DOC_DATE"),
        required_edges=["FK_LINE_HEAD"],
        value_type="number",
    )

    report = validate_query_compiler_preflight(
        _intent(metric, concept_ref="quantity_sold", date_column=_column_key(graph, "DOC_HEAD", "DOC_DATE")),
        _layer_with_metrics(layer, [metric]),
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        snapshot_checks_applicable=False,
    )

    assert report.status == "ready"
    assert report.decision_category == "safe"


def test_preflight_module_has_no_demo_or_fixture_literals() -> None:
    source = Path("app/query_compiler_preflight.py").read_text(encoding="utf-8")

    assert "SalesOrder" not in source
    assert "ProductCategory" not in source
    assert "DOTES" not in source
    assert "DORIG" not in source
    assert "ANACLI" not in source
    assert "ARTICO" not in source
    assert "CATART" not in source


def _graph_report(status: str = "valid"):
    return SimpleNamespace(status=status, errors=[], warnings=[], info=[], blocking_codes=[])


def _semantic_invariant_report():
    return SimpleNamespace(status="valid", errors=[], warnings=[], info=[], blocking_codes=[])


def _codes(report) -> set[str]:
    return {issue.code for issue in [*report.errors, *report.warnings, *report.infos]}


def _stage(report, stage: str):
    return next(item for item in report.stage_results if item.stage == stage)


def _active_layer(layer: SemanticLayer) -> SemanticLayer:
    return layer.model_copy(
        update={
            "status": "active",
            "freshness": "fresh",
            "validation_report": layer.validation_report.model_copy(update={"status": "valid"}),
            "quality_report": layer.quality_report.model_copy(update={"status": "passed"}),
        }
    )


def _layer_with_metrics(layer: SemanticLayer, metrics: list[SemanticMetric]) -> SemanticLayer:
    updated = layer.model_copy(update={"metrics": metrics})
    return updated.model_copy(update={"semantic_hash": compute_semantic_hash(updated)})


def _layer_with_concept(layer: SemanticLayer, concept_key: str, concept_ref: str) -> SemanticLayer:
    concept = SemanticBusinessConcept(
        business_concept_key=concept_key,
        canonical_name=concept_ref,
        display_name=concept_ref.replace("_", " ").title(),
        status="human_verified",
        provenance="human",
    )
    updated = layer.model_copy(update={"business_concepts": [concept]})
    return updated.model_copy(update={"semantic_hash": compute_semantic_hash(updated)})


def _empty_layer_for(graph) -> SemanticLayer:
    return semantic_draft(adventureworks_graph()).model_copy(
        update={
            "tenant_id": graph.tenant_id,
            "connection_id": graph.connection_id,
            "base_graph_hash": graph.graph_hash,
            "tables": [],
            "columns": [],
            "relationships": [],
            "business_concepts": [],
            "ambiguities": [],
            "metrics": [],
        }
    )


def _eligible(metric: SemanticMetric) -> SemanticMetric:
    return metric.model_copy(
        update={
            "compiler_eligibility": "eligible_with_disclosure",
            "eligibility_reasons": ["ORDER_STATUS_SCOPE_DEFAULT_ALL_STATUSES"],
            "confidence_score": 0.95,
            "confidence_label": "high",
        }
    )


def _intent(
    metric: SemanticMetric,
    *,
    concept_ref: str | None = None,
    date_column: str | None = None,
    group_by: list[QueryIntentGroupByDimension] | None = None,
    filters: list[SemanticFilter] | None = None,
    required_edges: list[str] | None = None,
) -> QueryIntentResult:
    return QueryIntentResult(
        status="ready",
        plan=QueryIntentPlan(
            primary_metric_key=metric.metric_key,
            requested_concept_ref=concept_ref or "customers",
            selected_variant=metric.metric_variant,
            effective_date_column_key=date_column or metric.default_date_column_key,
            time_range=(
                QueryIntentTimeRange(
                    kind="year",
                    start_date="2024-01-01",
                    end_date="2025-01-01",
                    label="2024",
                )
                if date_column or metric.default_date_column_key
                else None
            ),
            group_by_dimensions=group_by or [],
            required_edge_path_keys=required_edges or list(metric.required_join_edge_keys),
            grain_safety_decision="safe",
            filters=filters or [],
            disclosures=list(metric.eligibility_reasons),
            audit_trail=[],
        ),
        message="ready",
    )


def _semantic_metric(
    graph,
    *,
    concept_key: str,
    concept_ref: str,
    variant: str,
    table_name: str,
    measure_column: str,
    grain_columns: list[str],
    date_column: tuple[str, str] | None = None,
    dimension_column: tuple[str, str] | None = None,
    dimension_edges: list[str] | None = None,
    required_edges: list[str] | None = None,
    value_type: str = "number",
    currency: str | None = "EUR",
    eligibility: str = "eligible",
) -> SemanticMetric:
    compatibilities = []
    if dimension_column:
        compatibilities.append(
            SemanticDimensionCompatibility(
                dimension_column_key=_column_key(graph, *dimension_column),
                edge_path=[_edge_key(graph, edge) for edge in dimension_edges or []],
                safety="safe",
                reason_code="TRUSTED_PARENT_PATH",
            )
        )
    metric = SemanticMetric(
        metric_key="30000000-0000-4000-8000-000000000001",
        canonical_name=f"{concept_ref}_{variant}",
        metric_definition_hash="0" * 64,
        business_concept_key=concept_key,
        metric_variant=variant,
        name=f"{concept_ref} {variant}",
        status="human_verified",
        source_table_key=_node_key(graph, table_name),
        aggregation="sum" if value_type == "currency" else "count" if value_type == "count" else "sum",
        measure_column_key=_column_key(graph, table_name, measure_column),
        grain_table_key=_node_key(graph, table_name),
        grain_column_keys=[_column_key(graph, table_name, column_name) for column_name in grain_columns],
        aggregation_level="entity",
        additivity="additive",
        default_date_column_key=_column_key(graph, *date_column) if date_column else None,
        required_join_edge_keys=[_edge_key(graph, edge) if not _looks_like_sha(edge) else edge for edge in required_edges or []],
        common_dimension_compatibility=compatibilities,
        dimension_policy={
            "same_grain": "safe",
            "parent_many_to_one": "safe",
            "child_one_to_many": "forbidden",
            "bridge_or_many_to_many": "forbidden",
            "self_reference": "conditional",
        },
        preferred_for_grains=[],
        preferred_for_dimensions=[],
        filters=[],
        format=SemanticMetricFormat(
            value_type=value_type,
            currency=currency if value_type == "currency" else None,
            decimals=2,
        ),
        synonyms=[],
        confidence_score=0.95,
        confidence_label="high",
        compiler_eligibility=eligibility,
        eligibility_reasons=[],
        validation_warnings=[],
        provenance="human",
        provenance_detail="human_override",
        enabled=True,
    )
    return metric.model_copy(update={"metric_definition_hash": compute_metric_definition_hash(metric)})


def _node_key(graph, table_name: str) -> str:
    return next(node.node_key for node in graph.nodes if node.object_name == table_name)


def _column_key(graph, table_name: str, column_name: str) -> str:
    node = next(node for node in graph.nodes if node.object_name == table_name)
    return next(column.column_key for column in node.columns if column.name == column_name)


def _edge_key(graph, constraint_name: str) -> str:
    return next(edge.edge_key for edge in graph.edges if getattr(edge, "constraint_name", None) == constraint_name)


def _looks_like_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _ugly_pmi_snapshot():
    return snapshot(
        tables=[
            table("DOTES", [column("ID", 1), column("DATDOC", 2, role="date", native_type="datetime"), column("CODCLI", 3)], primary_key=["ID"]),
            table("DORIG", [column("ID", 1), column("IDTES", 2), column("CODART", 3), column("QTA", 4, role="quantity_candidate", native_type="decimal")], primary_key=["ID"]),
            table("ANACLI", [column("CODCLI", 1)], primary_key=["CODCLI"]),
            table("ARTICO", [column("CODART", 1), column("CAT", 2)], primary_key=["CODART"]),
            table("CATART", [column("CAT", 1)], primary_key=["CAT"]),
        ],
        foreign_keys=[
            foreign_key("FK_DORIG_DOTES", "DORIG", ["IDTES"], "DOTES", ["ID"]),
            foreign_key("FK_DOTES_ANACLI", "DOTES", ["CODCLI"], "ANACLI", ["CODCLI"]),
            foreign_key("FK_DORIG_ARTICO", "DORIG", ["CODART"], "ARTICO", ["CODART"]),
            foreign_key("FK_ARTICO_CATART", "ARTICO", ["CAT"], "CATART", ["CAT"]),
        ],
    )


def _ugly_pmi_graph():
    return build(_ugly_pmi_snapshot())


def _header_detail_graph(*, with_fk: bool, disabled: bool = False):
    fks = [
        foreign_key("FK_DORIG_DOTES", "DORIG", ["IDTES"], "DOTES", ["ID"], disabled=disabled)
    ] if with_fk else []
    return build(
        snapshot(
            tables=[
                table("DOTES", [column("ID", 1), column("DATA_DOC", 2, role="date", native_type="datetime"), column("TOTALE", 3, role="money_candidate", native_type="money")], primary_key=["ID"]),
                table("DORIG", [column("IDRIG", 1), column("IDTES", 2), column("IMPORTO", 3, role="money_candidate", native_type="money"), column("STATO", 4, role="text", native_type="nvarchar")], primary_key=["IDRIG"]),
            ],
            foreign_keys=fks,
        )
    )


def _view_graph():
    from dataclasses import replace
    from app.drivers.base import SchemaViewLineageDependency

    source = table("DOC", [column("ID", 1)], primary_key=["ID"])
    view = replace(
        table("VW_DOC", [column("ID", 1)], primary_key=["ID"], table_type="view"),
        view_lineage=[
            SchemaViewLineageDependency(
                source="dm_sql_referenced_entities",
                referencing_column="ID",
                referenced_schema_name="SalesLT",
                referenced_entity_name="DOC",
                referenced_column_name="ID",
                referenced_class="OBJECT_OR_COLUMN",
            )
        ],
    )
    return build(snapshot(tables=[source, view]))


def _ambiguous_business_graph():
    return build(
        snapshot(
            tables=[
                table(
                    "DOC_HEAD",
                    [
                        column("ID", 1),
                        column("DOC_DATE", 2, role="date", native_type="datetime"),
                        column("INVOICE_DATE", 3, role="date", native_type="datetime"),
                        column("UPDATED_AT", 4, role="date", native_type="datetime"),
                        column("TOTAL_AMOUNT", 5, role="money_candidate", native_type="money"),
                        column("TAX_AMOUNT", 6, role="money_candidate", native_type="money"),
                        column("CURRENCY_CODE", 7, role="text", native_type="nvarchar"),
                        column("STATUS", 8, role="text", native_type="nvarchar"),
                        column("CANCELLED_FLAG", 9, role="boolean", native_type="bit"),
                        column("CUSTOMER_EMAIL", 10, role="text", native_type="nvarchar"),
                    ],
                    primary_key=["ID"],
                )
            ]
        )
    )


def _bridge_graph():
    return build(
        snapshot(
            tables=[
                table("CUSTOMER", [column("CUSTOMER_ID", 1)], primary_key=["CUSTOMER_ID"]),
                table("PRODUCT", [column("PRODUCT_ID", 1)], primary_key=["PRODUCT_ID"]),
                table(
                    "CUSTOMER_PRODUCT",
                    [column("CUSTOMER_ID", 1), column("PRODUCT_ID", 2)],
                    primary_key=["CUSTOMER_ID", "PRODUCT_ID"],
                ),
            ],
            foreign_keys=[
                foreign_key("FK_BRIDGE_CUSTOMER", "CUSTOMER_PRODUCT", ["CUSTOMER_ID"], "CUSTOMER", ["CUSTOMER_ID"]),
                foreign_key("FK_BRIDGE_PRODUCT", "CUSTOMER_PRODUCT", ["PRODUCT_ID"], "PRODUCT", ["PRODUCT_ID"]),
            ],
        )
    )


def _schema_column(name: str, ordinal: int, *, role: str = "identifier", native_type: str = "int") -> SchemaColumnMetadata:
    return SchemaColumnMetadata(
        name=name,
        data_type=native_type,
        native_type=native_type,
        normalized_type=native_type,
        technical_role=role,
        ordinal_position=ordinal,
        is_nullable=False,
    )


def _schema_table(
    schema_name: str,
    table_name: str,
    columns: list[SchemaColumnMetadata],
    primary_key: list[str],
) -> SchemaTableMetadata:
    return SchemaTableMetadata(
        table_schema=schema_name,
        name=table_name,
        table_type="base_table",
        columns=columns,
        primary_key=SchemaPrimaryKeyMetadata(
            name=f"PK_{table_name}",
            columns=primary_key,
        ),
    )


def _composite_multischema_graph():
    source = SchemaIntrospectionResult(
        engine=Engine.sqlserver,
        database_name="ERP",
        engine_version="16.0",
        schema_hash="a" * 64,
        snapshot_hash="b" * 64,
        coverage_status="ok",
        tables=[
            _schema_table(
                "azienda",
                "DOC_HEAD",
                [
                    _schema_column("COMPANY_ID", 1),
                    _schema_column("DOC_ID", 2),
                    _schema_column("DOC_DATE", 3, role="date", native_type="datetime"),
                ],
                ["COMPANY_ID", "DOC_ID"],
            ),
            _schema_table(
                "azienda",
                "DOC_LINE",
                [
                    _schema_column("COMPANY_ID", 1),
                    _schema_column("DOC_ID", 2),
                    _schema_column("LINE_NO", 3),
                    _schema_column("QTY", 4, role="quantity_candidate", native_type="decimal"),
                ],
                ["COMPANY_ID", "DOC_ID", "LINE_NO"],
            ),
        ],
        foreign_keys=[
            SchemaForeignKeyMetadata(
                constraint_name="FK_LINE_HEAD",
                from_schema="azienda",
                from_table="DOC_LINE",
                from_columns=["COMPANY_ID", "DOC_ID"],
                to_schema="azienda",
                to_table="DOC_HEAD",
                to_columns=["COMPANY_ID", "DOC_ID"],
                delete_rule="no_action",
                update_rule="no_action",
                verified_by_db=True,
            )
        ],
    )
    return build(source)
