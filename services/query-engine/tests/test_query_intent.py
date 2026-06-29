import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.models import QueryIntentAICandidate, QueryIntentRequest, SemanticLayer
from app.query_intent import resolve_query_intent
from tests.test_semantic_builder import (
    CONNECTION_ID,
    GRAPH_VERSION_ID,
    SEMANTIC_VERSION_ID,
    TENANT_ID,
    adventureworks_graph,
    column_key,
)
from tests.test_semantic_discovery import (
    GENERATED_AT,
    FakeGateway,
    generate_semantic_layer,
    proposal_from_fixture,
    semantic_seed,
)

USER_ID = "11111111-1111-4111-8111-111111111111"
AUTH_HEADERS = {"x-atlante-query-engine-token": "semantic-token"}


def active_adventureworks_layer() -> SemanticLayer:
    graph = adventureworks_graph()
    result = asyncio.run(
        generate_semantic_layer(
            graph=graph,
            seed=semantic_seed(),
            gateway=FakeGateway(proposal_from_fixture()),
            generated_at=GENERATED_AT,
        )
    )
    layer = result.semantic_layer.model_copy(update={"status": "active"})
    assert layer.validation_report.status == "valid_with_warnings"
    return layer


def request_for(
    question: str,
    *,
    layer: SemanticLayer | None = None,
    ai_candidate: QueryIntentAICandidate | None = None,
) -> QueryIntentRequest:
    graph = adventureworks_graph()
    return QueryIntentRequest(
        tenant_id=TENANT_ID,
        connection_id=CONNECTION_ID,
        user_id=USER_ID,
        question=question,
        semantic_layer=layer or active_adventureworks_layer(),
        graph=graph,
        ai_enabled=ai_candidate is not None,
        ai_candidate=ai_candidate,
    )


def metric_by_variant(layer: SemanticLayer, variant: str):
    return next(metric for metric in layer.metrics if metric.metric_variant == variant)


def fk_edge_key_between(from_object: str, to_object: str) -> str:
    graph = adventureworks_graph()
    nodes = {node.object_name: node.node_key for node in graph.nodes}
    for edge in graph.edges:
        if (
            edge.edge_type == "fk_join"
            and edge.from_node_key == nodes[from_object]
            and edge.to_node_key == nodes[to_object]
        ):
            return edge.edge_key
    raise AssertionError(f"FK edge {from_object} -> {to_object} not found")


def test_revenue_year_resolves_without_ai() -> None:
    layer = active_adventureworks_layer()

    result = resolve_query_intent(request_for("fatturato 2008", layer=layer))

    assert result.status == "ready"
    assert result.plan is not None
    assert result.plan.selected_variant == "net_header"
    assert result.plan.primary_metric_key == metric_by_variant(
        layer, "net_header"
    ).metric_key
    assert result.plan.effective_date_column_key == column_key(
        "SalesOrderHeader",
        "OrderDate",
    )
    assert result.plan.time_range is not None
    assert result.plan.time_range.start_date == "2008-01-01"
    assert result.plan.time_range.end_date == "2009-01-01"
    assert "Order status scope defaults to all statuses in V1." in (
        result.plan.disclosures
    )


def test_line_revenue_year_resolves_to_detail_metric() -> None:
    layer = active_adventureworks_layer()

    result = resolve_query_intent(request_for("fatturato righe 2008", layer=layer))

    assert result.status == "ready"
    assert result.plan is not None
    assert result.plan.requested_concept_ref == "revenue"
    assert result.plan.selected_variant == "line_detail"
    selected_metric = metric_by_variant(layer, "line_detail")
    assert result.plan.primary_metric_key == selected_metric.metric_key
    assert selected_metric.measure_column_key == column_key(
        "SalesOrderDetail",
        "LineTotal",
    )
    assert result.plan.effective_date_column_key == column_key(
        "SalesOrderHeader",
        "OrderDate",
    )
    assert fk_edge_key_between("SalesOrderDetail", "SalesOrderHeader") in (
        result.plan.required_edge_path_keys
    )
    assert result.plan.time_range is not None
    assert result.plan.time_range.start_date == "2008-01-01"
    assert result.plan.time_range.end_date == "2009-01-01"


def test_orders_year_resolves_to_header_count() -> None:
    layer = active_adventureworks_layer()

    result = resolve_query_intent(request_for("ordini 2008", layer=layer))

    assert result.status == "ready"
    assert result.plan is not None
    assert result.plan.requested_concept_ref == "orders"
    assert result.plan.selected_variant == "header_count"
    selected_metric = metric_by_variant(layer, "header_count")
    assert result.plan.primary_metric_key == selected_metric.metric_key
    assert selected_metric.aggregation == "count"
    assert selected_metric.measure_column_key == column_key(
        "SalesOrderHeader",
        "SalesOrderID",
    )
    assert result.plan.effective_date_column_key == column_key(
        "SalesOrderHeader",
        "OrderDate",
    )
    assert "Order status scope defaults to all statuses in V1." in (
        result.plan.disclosures
    )


def test_revenue_by_product_category_uses_line_detail() -> None:
    layer = active_adventureworks_layer()

    result = resolve_query_intent(
        request_for("fatturato per categoria prodotto", layer=layer)
    )

    assert result.status == "ready"
    assert result.plan is not None
    assert result.plan.selected_variant == "line_detail"
    assert result.plan.group_by_dimensions[0].column_key == column_key(
        "ProductCategory",
        "ProductCategoryID",
    )
    assert result.plan.group_by_dimensions[0].safety == "safe"
    assert result.plan.required_edge_path_keys


def test_generic_customers_needs_clarification() -> None:
    result = resolve_query_intent(request_for("clienti"))

    assert result.status == "needs_clarification"
    assert result.clarification is not None
    assert result.clarification.reason_code == "CUSTOMER_POPULATION_AMBIGUOUS"
    assert {option.value for option in result.clarification.options} == {
        "order_customers",
        "customer_master",
    }


def test_specific_customer_populations_are_ready() -> None:
    order_customers = resolve_query_intent(request_for("clienti che hanno ordinato"))
    order_customers_question = resolve_query_intent(
        request_for("quanti clienti hanno ordinato")
    )
    order_customers_ordered = resolve_query_intent(
        request_for("clienti che hanno fatto ordini")
    )
    customer_master = resolve_query_intent(request_for("clienti in anagrafica"))

    assert order_customers.status == "ready"
    assert order_customers.plan is not None
    assert order_customers.plan.selected_variant == "order_customers"
    assert order_customers_question.status == "ready"
    assert order_customers_question.plan is not None
    assert order_customers_question.plan.selected_variant == "order_customers"
    assert order_customers_ordered.status == "ready"
    assert order_customers_ordered.plan is not None
    assert order_customers_ordered.plan.selected_variant == "order_customers"
    assert customer_master.status == "ready"
    assert customer_master.plan is not None
    assert customer_master.plan.selected_variant == "customer_master"


def test_document_total_by_category_is_blocked_as_unsafe() -> None:
    result = resolve_query_intent(request_for("totale documento per categoria prodotto"))

    assert result.status == "blocked"
    assert result.unsupported_reason == "unsafe_dimension_for_metric"
    assert any(
        event.code == "FORBIDDEN_ALTERNATIVE_RECORDED"
        for event in result.audit_trail
    )


def test_net_revenue_by_product_never_uses_header_subtotal() -> None:
    layer = active_adventureworks_layer()

    result = resolve_query_intent(request_for("fatturato netto per prodotto", layer=layer))

    assert result.status == "ready"
    assert result.plan is not None
    assert result.plan.selected_variant == "line_detail"
    selected_metric = metric_by_variant(layer, result.plan.selected_variant)
    assert selected_metric.measure_column_key == column_key(
        "SalesOrderDetail",
        "LineTotal",
    )
    assert selected_metric.measure_column_key != column_key(
        "SalesOrderHeader",
        "SubTotal",
    )


def test_multi_metric_request_is_blocked() -> None:
    result = resolve_query_intent(request_for("fatturato e quantita per categoria"))

    assert result.status == "blocked"
    assert result.unsupported_reason == "multi_metric_not_supported"


def test_generic_line_detail_terms_do_not_select_revenue_without_revenue_intent() -> None:
    result = resolve_query_intent(request_for("righe 2008"))

    assert result.status == "blocked"
    assert result.unsupported_reason == "metric_not_eligible"


def test_relative_time_expression_is_blocked() -> None:
    result = resolve_query_intent(request_for("fatturato mese scorso"))

    assert result.status == "blocked"
    assert result.unsupported_reason == "unsupported_time_expression"


def test_sensitive_dimension_or_filter_is_blocked() -> None:
    result = resolve_query_intent(request_for("fatturato per email cliente"))

    assert result.status == "blocked"
    assert result.unsupported_reason == "sensitive_filter_not_allowed"


def test_stale_semantic_layer_is_blocked() -> None:
    layer = active_adventureworks_layer().model_copy(update={"freshness": "stale"})

    result = resolve_query_intent(request_for("fatturato 2008", layer=layer))

    assert result.status == "blocked"
    assert result.unsupported_reason == "semantic_layer_stale"


def test_not_eligible_metric_is_blocked() -> None:
    layer = active_adventureworks_layer()
    metrics = [
        metric.model_copy(update={"compiler_eligibility": "not_eligible"})
        if metric.metric_variant == "net_header"
        else metric
        for metric in layer.metrics
    ]
    layer = layer.model_copy(update={"metrics": metrics})

    result = resolve_query_intent(request_for("fatturato 2008", layer=layer))

    assert result.status == "blocked"
    assert result.unsupported_reason == "metric_not_eligible"


def test_invented_ai_stable_key_is_audited_but_not_used() -> None:
    result = resolve_query_intent(
        request_for(
            "fatturato 2008",
            ai_candidate=QueryIntentAICandidate(
                primary_metric_key="99999999-9999-4999-8999-999999999999",
                dimension_column_key="f" * 64,
                filter_column_keys=["e" * 64],
            ),
        )
    )

    assert result.status == "ready"
    assert result.plan is not None
    assert result.plan.selected_variant == "net_header"
    assert {
        event.code for event in result.audit_trail
    } >= {
        "AI_METRIC_KEY_REJECTED",
        "AI_DIMENSION_KEY_REJECTED",
        "AI_FILTER_KEY_REJECTED",
    }


def test_query_intent_endpoint_returns_plan(monkeypatch) -> None:
    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "semantic-token")
    request = request_for("fatturato 2008")

    response = TestClient(app).post(
        "/query/intent/resolve",
        headers=AUTH_HEADERS,
        json=request.model_dump(mode="json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["plan"]["selected_variant"] == "net_header"
    assert "sql" not in payload


def test_contract_constants_match_fixture_scope() -> None:
    assert GRAPH_VERSION_ID
    assert SEMANTIC_VERSION_ID
