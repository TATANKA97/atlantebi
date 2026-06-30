import asyncio
from types import SimpleNamespace

from app.models import (
    AISemanticBusinessConceptProposal,
    AISemanticDraftProposal,
    AISemanticMetricFormatHint,
    AISemanticMetricProposal,
    QueryabilityViewDependencyEdge,
)
from app.semantic import build_semantic_seed
from app.semantic_discovery import (
    SemanticDiscoveryError,
    compile_semantic_proposal,
    generate_semantic_layer,
)
from app.semantic_invariants import validate_semantic_layer_invariants
from tests.test_queryability_builder import (
    build,
    column,
    foreign_key,
    snapshot,
    table,
)
from tests.test_semantic_builder import (
    GRAPH_VERSION_ID,
    SEMANTIC_VERSION_ID,
    adventureworks_graph,
    adventureworks_quality_policy,
    column_key,
    edge_key,
    semantic_draft,
    semantic_policy,
)


class FailingGateway:
    provider = "openai"
    model_version = "fixture-model"
    thinking_config = {"type": "openai_reasoning", "effort": "medium"}

    async def generate(self, discovery_input):
        del discovery_input
        raise SemanticDiscoveryError("offline fixture failure")


def test_semantic_invariant_report_shape_and_valid_metric() -> None:
    graph = adventureworks_graph()
    layer = semantic_draft(graph)
    metric = _metric_by_variant(layer, "line_quantity").model_copy(
        update={
            "compiler_eligibility": "eligible_with_disclosure",
            "eligibility_reasons": ["ORDER_STATUS_SCOPE_DEFAULT_ALL_STATUSES"],
            "default_date_column_key": column_key("SalesOrderHeader", "OrderDate"),
            "required_join_edge_keys": [
                edge_key("FK_Detail_Header"),
                edge_key("FK_Detail_Product"),
                edge_key("FK_Product_ProductCategory"),
            ],
        }
    )

    report = _validate(_layer_with_metrics(layer, [metric]), graph)

    assert report.status == "valid"
    assert report.to_debug_dict()["summary"]["metric_count"] == 1
    assert report.blocking_codes == []


def test_missing_and_sensitive_source_columns_are_compiler_errors() -> None:
    graph = adventureworks_graph()
    layer = semantic_draft(graph)
    missing = _eligible(_metric_by_variant(layer, "line_quantity")).model_copy(
        update={"measure_column_key": "f" * 64}
    )
    sensitive = _eligible(_metric_by_variant(layer, "header_count")).model_copy(
        update={
            "measure_column_key": column_key(
                "SalesOrderHeader",
                "CreditCardApprovalCode",
            ),
            "aggregation": "count_distinct",
            "eligibility_reasons": ["ORDER_STATUS_SCOPE_DEFAULT_ALL_STATUSES"],
        }
    )

    report = _validate(_layer_with_metrics(layer, [missing, sensitive]), graph)

    assert _codes(report) >= {
        "AI_INVENTED_KEY_ACCEPTED",
        "AI_SENSITIVE_SOURCE_ACCEPTED",
    }


def test_untrusted_and_lineage_edges_are_not_compiler_safe() -> None:
    graph = adventureworks_graph()
    layer = semantic_draft(graph)
    untrusted_edges = [
        edge.model_copy(
            update={
                "validation_status": "untrusted",
                "automatic_join_allowed": False,
            }
        )
        if edge.edge_key == edge_key("FK_Detail_Product")
        else edge
        for edge in graph.edges
    ]
    untrusted_graph = graph.model_copy(update={"edges": untrusted_edges})
    lineage_key = "9" * 64
    lineage_graph = graph.model_copy(
        update={
            "edges": [
                *graph.edges,
                QueryabilityViewDependencyEdge(
                    edge_key=lineage_key,
                    edge_type="view_depends_on",
                    from_node_key=_node_key_by_name(graph, "vGetAllCategories"),
                    to_node_key=_node_key_by_name(graph, "ProductCategory"),
                    source="dm_sql_referenced_entities",
                    resolution_status="resolved",
                    automatic_join_allowed=False,
                    reason_codes=[],
                ),
            ]
        }
    )
    untrusted_metric = _eligible(_metric_by_variant(layer, "line_quantity"))
    lineage_metric = untrusted_metric.model_copy(
        update={"required_join_edge_keys": [lineage_key]}
    )

    untrusted_report = _validate(
        _layer_with_metrics(layer, [untrusted_metric]),
        untrusted_graph,
    )
    lineage_report = _validate(_layer_with_metrics(layer, [lineage_metric]), lineage_graph)

    assert "SEMANTIC_PATH_USES_UNTRUSTED_EDGE" in _codes(untrusted_report)
    assert "SEMANTIC_PATH_USES_LINEAGE_EDGE" in _codes(lineage_report)


def test_header_metric_safe_detail_dimension_requires_allocation() -> None:
    graph = adventureworks_graph()
    layer = semantic_draft(graph)
    metric = _eligible(_metric_by_variant(layer, "net_header"))
    compatibility = next(
        item
        for item in metric.common_dimension_compatibility
        if item.dimension_column_key == column_key(
            "ProductCategory",
            "ProductCategoryID",
        )
    ).model_copy(update={"safety": "safe"})
    metric = metric.model_copy(update={"common_dimension_compatibility": [compatibility]})

    report = _validate(_layer_with_metrics(layer, [metric]), graph)

    assert "HEADER_METRIC_DETAIL_DIMENSION_REQUIRES_ALLOCATION" in _codes(report)


def test_audit_date_and_multiple_business_dates_are_diagnostics() -> None:
    graph = adventureworks_graph()
    customer = next(node for node in graph.nodes if node.object_name == "Customer")
    customer = customer.model_copy(
        update={
            "columns": [
                *customer.columns,
                customer.columns[0].model_copy(
                    update={
                        "column_key": column_key("Customer", "OrderDate"),
                        "name": "OrderDate",
                        "ordinal_position": 99,
                        "technical_role": "date",
                        "native_type": "datetime",
                        "normalized_type": "datetime",
                    }
                ),
            ]
        }
    )
    graph = graph.model_copy(
        update={
            "nodes": [
                customer if node.object_name == "Customer" else node
                for node in graph.nodes
            ]
        }
    )
    layer = semantic_draft(graph)
    metric = _eligible(_metric_by_variant(layer, "customer_master")).model_copy(
        update={"default_date_column_key": column_key("Customer", "ModifiedDate")}
    )

    report = _validate(_layer_with_metrics(layer, [metric]), graph)

    assert "AUDIT_DATE_USED_AS_BUSINESS_DEFAULT" in _codes(report)


def test_profile_synthesis_must_be_auditable() -> None:
    graph = adventureworks_graph()
    layer = semantic_draft(graph)
    metric = _eligible(_metric_by_variant(layer, "line_quantity")).model_copy(
        update={
            "provenance": "system",
            "provenance_detail": "quality_profile",
            "source_spec_key": None,
        }
    )

    report = _validate(_layer_with_metrics(layer, [metric]), graph)

    assert "PROFILE_SYNTHESIS_NOT_AUDITABLE" in _codes(report)


def test_status_scope_is_warning_with_disclosure_and_error_when_silent() -> None:
    graph = adventureworks_graph()
    layer = semantic_draft(graph)
    disclosed = _metric_by_variant(layer, "header_count").model_copy(
        update={"compiler_eligibility": "eligible_with_disclosure"}
    )
    silent = _metric_by_variant(layer, "header_count").model_copy(
        update={"compiler_eligibility": "eligible"}
    )

    disclosed_report = _validate(_layer_with_metrics(layer, [disclosed]), graph)
    silent_report = _validate(_layer_with_metrics(layer, [silent]), graph)

    assert "STATUS_SCOPE_AMBIGUITY_NOT_RECORDED" in {
        issue.code for issue in disclosed_report.warnings
    }
    assert "STATUS_SCOPE_AMBIGUITY_NOT_RECORDED" in {
        issue.code for issue in silent_report.errors
    }


def test_profile_enabled_and_disabled_outputs_are_not_silently_equivalent() -> None:
    graph = adventureworks_graph()
    enabled_policy = adventureworks_quality_policy()
    enabled_seed = build_semantic_seed(
        graph=graph,
        semantic_version_id=SEMANTIC_VERSION_ID,
        queryability_graph_version_id=GRAPH_VERSION_ID,
        version=1,
        semantic_policy=enabled_policy,
    )
    enabled = asyncio.run(
        generate_semantic_layer(
            graph=graph,
            seed=enabled_seed,
            gateway=FailingGateway(),
        )
    ).semantic_layer
    disabled_policy = semantic_policy()
    disabled_seed = build_semantic_seed(
        graph=graph,
        semantic_version_id=SEMANTIC_VERSION_ID,
        queryability_graph_version_id=GRAPH_VERSION_ID,
        version=1,
        semantic_policy=disabled_policy,
    )
    disabled = compile_semantic_proposal(
        graph=graph,
        seed=disabled_seed,
        proposal=_empty_proposal(),
        model_version="fixture-model",
        semantic_policy=disabled_policy,
    )

    enabled_profile_metrics = [
        metric
        for metric in enabled.metrics
        if metric.provenance_detail == "quality_profile"
    ]

    assert enabled.quality_report.required_specs_count == 7
    assert enabled.quality_report.satisfied_specs_count == 7
    assert len(enabled_profile_metrics) == 7
    assert len(disabled.metrics) == 0
    assert disabled.quality_report.required_specs_count == 0
    assert enabled.quality_report.satisfied_specs_count != (
        disabled.quality_report.satisfied_specs_count
    )


def test_ugly_pmi_schema_needs_evidence_but_accepts_valid_evidence() -> None:
    graph = _ugly_pmi_graph()
    policy = semantic_policy()
    seed = build_semantic_seed(
        graph=graph,
        semantic_version_id=SEMANTIC_VERSION_ID,
        queryability_graph_version_id=GRAPH_VERSION_ID,
        version=1,
        semantic_policy=policy,
    )
    no_evidence = compile_semantic_proposal(
        graph=graph,
        seed=seed,
        proposal=_empty_proposal(),
        model_version="fixture-model",
        semantic_policy=policy,
    )
    proposal = AISemanticDraftProposal(
        contract_version="semantic_ai_draft.v1",
        tables=[],
        columns=[],
        business_concepts=[
                AISemanticBusinessConceptProposal(
                    concept_ref="quantity_sold",
                    display_name="Quantita venduta",
                    description="Explicit fake evidence for quantity.",
                synonyms=[],
            )
        ],
        metrics=[
            AISemanticMetricProposal(
                canonical_name="quantita_venduta",
                business_concept_ref="quantity_sold",
                    metric_variant="line_quantity",
                    name="Quantita venduta",
                    description="Explicit fake evidence maps DORIG.QTA to quantity.",
                source_table_key=_node_key_by_name(graph, "DORIG"),
                aggregation="sum",
                measure_column_key=_column_key_by_name(graph, "DORIG", "QTA"),
                default_date_column_key=None,
                format_hint=AISemanticMetricFormatHint(
                    value_type="number",
                    decimals=0,
                ),
                synonyms=[],
                reasoning_summary="Explicit fake evidence maps DORIG.QTA to quantity.",
            )
        ],
        ambiguities=[],
    )
    with_evidence = compile_semantic_proposal(
        graph=graph,
        seed=seed,
        proposal=proposal,
        model_version="fixture-model",
        semantic_policy=policy,
    )

    assert no_evidence.metrics == []
    assert len(with_evidence.metrics) == 1
    report = _validate(
        _layer_with_metrics(
            with_evidence,
            [_eligible(with_evidence.metrics[0])],
        ),
        graph,
        policy=policy,
    )
    assert report.status == "valid"


def test_multiple_amounts_dates_and_missing_fk_fail_closed() -> None:
    graph = adventureworks_graph()
    layer = semantic_draft(graph)
    amount_metric = _eligible(_metric_by_variant(layer, "net_header"))
    amount_report = _validate(_layer_with_metrics(layer, [amount_metric]), graph)

    missing_fk_graph = graph.model_copy(
        update={
            "edges": [
                edge
                for edge in graph.edges
                if edge.edge_key != edge_key("FK_Detail_Header")
            ]
        }
    )
    detail_metric = _eligible(_metric_by_variant(layer, "line_quantity")).model_copy(
        update={
            "default_date_column_key": column_key("SalesOrderHeader", "OrderDate"),
            "required_join_edge_keys": [edge_key("FK_Detail_Header")],
        }
    )
    missing_fk_report = _validate(
        _layer_with_metrics(layer, [detail_metric]),
        missing_fk_graph,
    )

    assert "AMOUNT_SEMANTIC_AMBIGUITY_NOT_RECORDED" in _codes(amount_report)
    assert "DETAIL_METRIC_MISSING_PARENT_DATE_PATH" in _codes(missing_fk_report)
    assert "AI_INVENTED_KEY_ACCEPTED" in _codes(missing_fk_report)


def _validate(layer, graph, *, policy=None):
    return validate_semantic_layer_invariants(
        layer,
        graph,
        SimpleNamespace(status="valid"),
        policy or layer.semantic_policy_snapshot,
    )


def _codes(report) -> set[str]:
    return {issue.code for issue in report.issues}


def _metric_by_variant(layer, variant: str):
    return next(metric for metric in layer.metrics if metric.metric_variant == variant)


def _eligible(metric):
    return metric.model_copy(
        update={
            "compiler_eligibility": "eligible",
            "eligibility_reasons": [],
            "confidence_score": 0.95,
            "confidence_label": "high",
        }
    )


def _layer_with_metrics(layer, metrics):
    return layer.model_copy(update={"metrics": metrics})


def _empty_proposal() -> AISemanticDraftProposal:
    return AISemanticDraftProposal(
        contract_version="semantic_ai_draft.v1",
        tables=[],
        columns=[],
        business_concepts=[],
        metrics=[],
        ambiguities=[],
    )


def _node_key_by_name(graph, object_name: str) -> str:
    return next(node.node_key for node in graph.nodes if node.object_name == object_name)


def _column_key_by_name(graph, object_name: str, column_name: str) -> str:
    node = next(node for node in graph.nodes if node.object_name == object_name)
    return next(column.column_key for column in node.columns if column.name == column_name)


def _ugly_pmi_graph():
    return build(
        snapshot(
            tables=[
                table(
                    "DOTES",
                    [
                        column("ID", 1),
                        column("DATDOC", 2, role="date", native_type="datetime"),
                        column("CODCLI", 3),
                    ],
                    primary_key=["ID"],
                ),
                table(
                    "DORIG",
                    [
                        column("ID", 1),
                        column("IDTES", 2),
                        column("CODART", 3),
                        column("QTA", 4, role="quantity_candidate", native_type="decimal"),
                    ],
                    primary_key=["ID"],
                ),
                table(
                    "ANACLI",
                    [column("CODCLI", 1)],
                    primary_key=["CODCLI"],
                ),
                table(
                    "ARTICO",
                    [column("CODART", 1), column("CAT", 2)],
                    primary_key=["CODART"],
                ),
                table(
                    "CATART",
                    [column("CAT", 1)],
                    primary_key=["CAT"],
                ),
            ],
            foreign_keys=[
                foreign_key("FK_DORIG_DOTES", "DORIG", ["IDTES"], "DOTES", ["ID"]),
                foreign_key(
                    "FK_DOTES_ANACLI",
                    "DOTES",
                    ["CODCLI"],
                    "ANACLI",
                    ["CODCLI"],
                ),
                foreign_key(
                    "FK_DORIG_ARTICO",
                    "DORIG",
                    ["CODART"],
                    "ARTICO",
                    ["CODART"],
                ),
                foreign_key("FK_ARTICO_CATART", "ARTICO", ["CAT"], "CATART", ["CAT"]),
            ],
        )
    )
