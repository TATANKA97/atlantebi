import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models import (
    AISemanticAmbiguity,
    AISemanticBusinessConceptProposal,
    AISemanticDraftProposal,
    AISemanticMetricFormatHint,
    AISemanticMetricProposal,
    AnthropicProviderConfig,
    AnthropicSemanticAnnotationsOutput,
    AnthropicSemanticBusinessConceptProposal,
    AnthropicSemanticMetricsOutput,
    SemanticDimensionCompatibility,
)
from app.semantic import (
    build_semantic_seed,
    compute_metric_definition_hash,
    compute_semantic_hash,
    validate_semantic_layer,
)
from app.semantic_discovery import (
    ANTHROPIC_ANNOTATION_OUTPUT_TOKENS,
    ANTHROPIC_METRIC_OUTPUT_TOKENS,
    ANTHROPIC_SEMANTIC_PHASE_TIMEOUT_SECONDS,
    ANTHROPIC_SEMANTIC_TOTAL_TIMEOUT_SECONDS,
    AnthropicSemanticDiscoveryGateway,
    OpenAISemanticDiscoveryGateway,
    SemanticDiscoveryError,
    SemanticDiscoveryInputTooLarge,
    SemanticDiscoveryProviderConfigurationError,
    SemanticDiscoveryRefused,
    SemanticProposalInvalid,
    _compile_anthropic_concepts,
    _compile_anthropic_metrics,
    _raise_anthropic_provider_error,
    build_semantic_discovery_input,
    compile_semantic_proposal,
    generate_semantic_layer,
)
from tests.test_semantic_builder import (
    GRAPH_VERSION_ID,
    SEMANTIC_VERSION_ID,
    adventureworks_graph,
    adventureworks_quality_policy,
    column_key,
    edge_key,
    node_key,
    semantic_policy,
)
from tests.shared_fixtures import contract_fixture_path


GENERATED_AT = datetime(2026, 6, 14, 10, 0, tzinfo=UTC)
SHARED_FIXTURE = contract_fixture_path("semantic-ai-draft-v1.json")


def proposal_from_fixture() -> AISemanticDraftProposal:
    def metric(
        *,
        canonical_name: str,
        concept_ref: str,
        variant: str,
        source_table: str,
        aggregation: str,
        measure_column: str,
        grain_columns: list[str],
        default_date: tuple[str, str] | None = None,
        common_dimensions: list[object] | None = None,
        required_edges: list[str] | None = None,
        value_type: str = "number",
        synonyms: list[str] | None = None,
    ) -> AISemanticMetricProposal:
        del grain_columns, common_dimensions, required_edges
        return AISemanticMetricProposal(
            canonical_name=canonical_name,
            business_concept_ref=concept_ref,
            metric_variant=variant,
            name=canonical_name.replace("_", " ").title(),
            description=f"Structured metric {canonical_name}.",
            source_table_key=node_key(source_table),
            aggregation=aggregation,
            measure_column_key=column_key(source_table, measure_column),
            default_date_column_key=(
                column_key(*default_date) if default_date else None
            ),
            format_hint=AISemanticMetricFormatHint(
                value_type=value_type,
                decimals=2 if value_type == "currency" else 0,
            ),
            synonyms=synonyms or [],
            reasoning_summary=(
                "Supported by the technical graph and declared metric grain."
            ),
        )

    return AISemanticDraftProposal(
        contract_version="semantic_ai_draft.v1",
        tables=[],
        columns=[],
        business_concepts=[
            AISemanticBusinessConceptProposal(
                concept_ref=concept_ref,
                display_name=display_name,
                description=f"Business concept {display_name}.",
                synonyms=synonyms,
            )
            for concept_ref, display_name, synonyms in [
                ("revenue", "Fatturato", ["vendite"]),
                ("quantity_sold", "Quantita venduta", ["quantita"]),
                ("orders", "Ordini", ["documenti vendita"]),
                ("customers", "Clienti", ["clienti"]),
            ]
        ],
        metrics=[
            metric(
                canonical_name="fatturato_netto",
                concept_ref="revenue",
                variant="net_header",
                source_table="SalesOrderHeader",
                aggregation="sum",
                measure_column="SubTotal",
                grain_columns=["SalesOrderID"],
                default_date=("SalesOrderHeader", "OrderDate"),
                value_type="currency",
                synonyms=["fatturato", "vendite"],
            ),
            metric(
                canonical_name="totale_documento",
                concept_ref="revenue",
                variant="document_total",
                source_table="SalesOrderHeader",
                aggregation="sum",
                measure_column="TotalDue",
                grain_columns=["SalesOrderID"],
                default_date=("SalesOrderHeader", "OrderDate"),
                value_type="currency",
            ),
            metric(
                canonical_name="fatturato_righe",
                concept_ref="revenue",
                variant="line_detail",
                source_table="SalesOrderDetail",
                aggregation="sum",
                measure_column="LineTotal",
                grain_columns=["SalesOrderID", "SalesOrderDetailID"],
                required_edges=[
                    "FK_Detail_Product",
                    "FK_Product_ProductCategory",
                ],
                value_type="currency",
            ),
            metric(
                canonical_name="quantita_venduta",
                concept_ref="quantity_sold",
                variant="line_quantity",
                source_table="SalesOrderDetail",
                aggregation="sum",
                measure_column="OrderQty",
                grain_columns=["SalesOrderID", "SalesOrderDetailID"],
                required_edges=[
                    "FK_Detail_Product",
                    "FK_Product_ProductCategory",
                ],
            ),
            metric(
                canonical_name="ordini",
                concept_ref="orders",
                variant="header_count",
                source_table="SalesOrderHeader",
                aggregation="count",
                measure_column="SalesOrderID",
                grain_columns=["SalesOrderID"],
                default_date=("SalesOrderHeader", "OrderDate"),
                value_type="count",
            ),
            metric(
                canonical_name="clienti_ordini",
                concept_ref="customers",
                variant="order_customers",
                source_table="SalesOrderHeader",
                aggregation="count_distinct",
                measure_column="CustomerID",
                grain_columns=["SalesOrderID"],
                default_date=("SalesOrderHeader", "OrderDate"),
                value_type="count",
                synonyms=["clienti"],
            ),
            metric(
                canonical_name="clienti_anagrafica",
                concept_ref="customers",
                variant="customer_master",
                source_table="Customer",
                aggregation="count",
                measure_column="CustomerID",
                grain_columns=["CustomerID"],
                value_type="count",
                synonyms=["clienti"],
            ),
        ],
        ambiguities=[
            AISemanticAmbiguity(
                code="CUSTOMER_POPULATION_AMBIGUOUS",
                target_type="business_concept",
                target_ref="customers",
                summary="Order customers and customer master are distinct populations.",
                clarification_question=(
                    "Should customers mean purchasers or all customer records?"
                ),
                severity="material_ambiguity",
            )
        ],
    )


def semantic_seed():
    return build_semantic_seed(
        graph=adventureworks_graph(),
        semantic_version_id=SEMANTIC_VERSION_ID,
        queryability_graph_version_id=GRAPH_VERSION_ID,
        version=1,
        semantic_policy=adventureworks_quality_policy(),
    )


def anthropic_metric_payload(
    metric: AISemanticMetricProposal,
    *,
    ambiguities: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "canonical_name": metric.canonical_name,
        "business_concept_ref": metric.business_concept_ref,
        "metric_variant": metric.metric_variant,
        "name": metric.name,
        "description": metric.description,
        "source_table_key": metric.source_table_key,
        "aggregation": metric.aggregation,
        "measure_column_key": metric.measure_column_key,
        "default_date_column_key": metric.default_date_column_key,
        "format_hint": metric.format_hint.model_dump(mode="json"),
        "synonyms": metric.synonyms,
        "reasoning_summary": metric.reasoning_summary,
        "ambiguities": ambiguities or [],
    }


class FakeGateway:
    provider = "openai"
    model_version = "fixture-model-v2"
    thinking_config = {"type": "openai_reasoning", "effort": "medium"}

    def __init__(self, proposal: AISemanticDraftProposal) -> None:
        self.proposal = proposal
        self.received = None

    async def generate(self, discovery_input):
        self.received = discovery_input
        return SimpleNamespace(
            response_id="resp_fixture",
            proposal=self.proposal,
        )


def test_discovery_input_is_allowlisted_and_omits_excluded_sensitive_metadata() -> None:
    discovery_input = build_semantic_discovery_input(
        adventureworks_graph(), semantic_policy()
    )

    assert len(discovery_input.tables) == 13
    assert len(discovery_input.columns) == 124
    assert len(discovery_input.relationships) == 12
    assert all(
        column.queryability_status == "queryable"
        and column.sensitivity != "sensitive"
        for column in discovery_input.columns
    )
    serialized = discovery_input.model_dump_json()
    assert "PasswordHash" not in serialized
    assert "PasswordSalt" not in serialized
    assert "CreditCardApprovalCode" not in serialized
    assert "view_definition" not in serialized
    assert "extended_properties" not in serialized
    assert all(
        len(column_key_value) == 64
        for table in discovery_input.tables
        for candidate in table.candidate_keys
        for column_key_value in candidate.column_keys
    )


def test_discovery_input_is_invariant_to_graph_collection_order() -> None:
    graph = adventureworks_graph()
    reordered_graph = graph.model_copy(
        update={
            "nodes": [
                node.model_copy(update={"columns": list(reversed(node.columns))})
                for node in reversed(graph.nodes)
            ],
            "edges": list(reversed(graph.edges)),
        }
    )

    assert build_semantic_discovery_input(
        graph, semantic_policy()
    ).model_dump(mode="json") == build_semantic_discovery_input(
        reordered_graph, semantic_policy()
    ).model_dump(mode="json")


def test_discovery_input_never_truncates_silently(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.semantic_discovery.MAX_SEMANTIC_DISCOVERY_INPUT_BYTES",
        100,
    )

    with pytest.raises(SemanticDiscoveryInputTooLarge):
        build_semantic_discovery_input(adventureworks_graph(), semantic_policy())


def test_blocked_graph_cannot_enter_semantic_discovery() -> None:
    graph = adventureworks_graph().model_copy(update={"status": "blocked"})

    with pytest.raises(
        SemanticProposalInvalid,
        match="blocked Queryability Graph",
    ):
        build_semantic_discovery_input(graph, semantic_policy())


def test_adventureworks_proposal_compiles_and_validates_with_expected_metrics() -> None:
    graph = adventureworks_graph()
    compiled = compile_semantic_proposal(
        graph=graph,
        seed=semantic_seed(),
        proposal=proposal_from_fixture(),
        model_version="fixture-model-v2",
    )
    result = asyncio.run(
        generate_semantic_layer(
            graph=graph,
            seed=semantic_seed(),
            gateway=FakeGateway(proposal_from_fixture()),
            generated_at=GENERATED_AT,
        )
    )

    assert compiled.ai_prompt_version == "semantic-discovery.v1"
    assert result.semantic_layer.validation_report.status == "valid_with_warnings"
    signatures = {
        (
            concept.canonical_name,
            metric.metric_variant,
            metric.aggregation,
            metric.measure_column_key,
        )
        for metric in result.semantic_layer.metrics
        for concept in result.semantic_layer.business_concepts
        if concept.business_concept_key == metric.business_concept_key
    }
    assert (
        "revenue",
        "net_header",
        "sum",
        column_key("SalesOrderHeader", "SubTotal"),
    ) in signatures
    assert (
        "revenue",
        "document_total",
        "sum",
        column_key("SalesOrderHeader", "TotalDue"),
    ) in signatures
    assert (
        "revenue",
        "line_detail",
        "sum",
        column_key("SalesOrderDetail", "LineTotal"),
    ) in signatures
    assert {
        (concept, variant)
        for concept, variant, _, _ in signatures
    } >= {
        ("quantity_sold", "line_quantity"),
        ("orders", "header_count"),
        ("customers", "order_customers"),
        ("customers", "customer_master"),
    }
    assert len(result.semantic_layer.metrics) == 7
    assert len(result.semantic_layer.ambiguities) == 1
    net_revenue = next(
        metric
        for metric in result.semantic_layer.metrics
        if metric.metric_variant == "net_header"
    )
    customer_metrics = [
        metric
        for metric in result.semantic_layer.metrics
        if metric.metric_variant in {"order_customers", "customer_master"}
    ]
    assert net_revenue.compiler_eligibility == "eligible_with_disclosure"
    assert net_revenue.format.currency == "EUR"
    assert net_revenue.grain_column_keys == [
        column_key("SalesOrderHeader", "SalesOrderID")
    ]
    assert net_revenue.default_date_column_key == column_key(
        "SalesOrderHeader", "OrderDate"
    )
    quantity = next(
        metric
        for metric in result.semantic_layer.metrics
        if metric.metric_variant == "line_quantity"
    )
    assert quantity.default_date_column_key == column_key(
        "SalesOrderHeader", "OrderDate"
    )
    assert quantity.required_join_edge_keys == [edge_key("FK_Detail_Header")]
    assert result.semantic_layer.quality_report.status == "passed"
    assert result.semantic_layer.quality_report.satisfied_specs_count == 7
    assert result.semantic_layer.quality_report.compiler_eligible_required_count == 4
    assert all(
        metric.compiler_eligibility == "clarification_required"
        for metric in customer_metrics
    )
    assert result.provenance.response_id == "resp_fixture"
    assert result.provenance.generated_at == "2026-06-14T10:00:00Z"


def test_declared_ambiguity_drives_clarification_without_synonym_collision() -> None:
    proposal = proposal_from_fixture()
    metrics = [
        metric.model_copy(
            update={
                "synonyms": (
                    ["clienti acquirenti"]
                    if metric.metric_variant == "order_customers"
                    else ["anagrafica clienti"]
                    if metric.metric_variant == "customer_master"
                    else metric.synonyms
                )
            }
        )
        for metric in proposal.metrics
    ]
    result = asyncio.run(
        generate_semantic_layer(
            graph=adventureworks_graph(),
            seed=semantic_seed(),
            gateway=FakeGateway(proposal.model_copy(update={"metrics": metrics})),
            generated_at=GENERATED_AT,
        )
    )
    customer_metrics = [
        metric
        for metric in result.semantic_layer.metrics
        if metric.metric_variant in {"order_customers", "customer_master"}
    ]

    assert all(
        metric.compiler_eligibility == "clarification_required"
        for metric in customer_metrics
    )
    assert all(
        "SEMANTIC_AMBIGUITY_DECLARED" in metric.validation_warnings
        for metric in customer_metrics
    )


def test_customer_quality_profile_synthesis_declares_system_ambiguity() -> None:
    proposal = proposal_from_fixture()
    metrics = [
        metric.model_copy(
            update={
                "synonyms": (
                    ["clienti acquirenti"]
                    if metric.metric_variant == "order_customers"
                    else ["anagrafica clienti"]
                    if metric.metric_variant == "customer_master"
                    else metric.synonyms
                )
            }
        )
        for metric in proposal.metrics
        if metric.business_concept_ref != "customers"
    ]

    result = asyncio.run(
        generate_semantic_layer(
            graph=adventureworks_graph(),
            seed=semantic_seed(),
            gateway=FakeGateway(
                proposal.model_copy(update={"metrics": metrics, "ambiguities": []})
            ),
            generated_at=GENERATED_AT,
        )
    )
    customer_ambiguity = next(
        ambiguity
        for ambiguity in result.semantic_layer.ambiguities
        if ambiguity.code == "CUSTOMER_POPULATION_AMBIGUOUS"
    )
    customer_metrics = [
        metric
        for metric in result.semantic_layer.metrics
        if metric.metric_variant in {"order_customers", "customer_master"}
    ]

    assert customer_ambiguity.provenance == "system"
    assert customer_ambiguity.severity == "material_ambiguity"
    assert all(
        metric.provenance_detail == "quality_profile"
        for metric in customer_metrics
    )
    assert all(
        metric.compiler_eligibility == "clarification_required"
        for metric in customer_metrics
    )


def test_unknown_ambiguity_target_is_ignored_with_quality_warning() -> None:
    proposal = proposal_from_fixture()
    invalid_ambiguity = proposal.ambiguities[0].model_copy(
        update={"target_ref": "missing_concept"}
    )

    compiled = compile_semantic_proposal(
        graph=adventureworks_graph(),
        seed=semantic_seed(),
        proposal=proposal.model_copy(update={"ambiguities": [invalid_ambiguity]}),
        model_version="fixture-model-v2",
    )

    assert "AI_AMBIGUITY_TARGET_NOT_RESOLVED" in {
        issue.code for issue in compiled.quality_report.issues
    }


@pytest.mark.parametrize(
    ("target_type", "target_ref"),
    [
        ("table", lambda: node_key("SalesOrderHeader")),
        (
            "column",
            lambda: column_key("SalesOrderHeader", "SubTotal"),
        ),
    ],
)
def test_table_and_column_revenue_ambiguities_do_not_block_policy_resolved_metric(
    target_type,
    target_ref,
) -> None:
    proposal = proposal_from_fixture()
    ambiguity = AISemanticAmbiguity(
        code="REVENUE_SOURCE_AMBIGUOUS",
        target_type=target_type,
        target_ref=target_ref(),
        summary="Revenue source requires confirmation.",
        clarification_question="Which revenue source should be used?",
        severity="material_ambiguity",
    )
    result = asyncio.run(
        generate_semantic_layer(
            graph=adventureworks_graph(),
            seed=semantic_seed(),
            gateway=FakeGateway(
                proposal.model_copy(
                    update={"ambiguities": [ambiguity]}
                )
            ),
            generated_at=GENERATED_AT,
        )
    )
    net_revenue = next(
        metric
        for metric in result.semantic_layer.metrics
        if metric.metric_variant == "net_header"
    )

    assert net_revenue.compiler_eligibility == "eligible_with_disclosure"
    assert "AI_PROPOSED_DISCLOSURE_REQUIRED" in net_revenue.eligibility_reasons
    assert "SEMANTIC_AMBIGUITY_DECLARED" in net_revenue.validation_warnings


def test_duplicate_metric_synonym_warns_without_blocking_required_metric() -> None:
    proposal = proposal_from_fixture()
    metrics = [
        metric.model_copy(
            update={
                "synonyms": (
                    [*metric.synonyms, "Product Revenue"]
                    if metric.metric_variant in {"net_header", "line_detail"}
                    else metric.synonyms
                )
            }
        )
        for metric in proposal.metrics
    ]

    result = asyncio.run(
        generate_semantic_layer(
            graph=adventureworks_graph(),
            seed=semantic_seed(),
            gateway=FakeGateway(proposal.model_copy(update={"metrics": metrics})),
            generated_at=GENERATED_AT,
        )
    )
    net_revenue = next(
        metric
        for metric in result.semantic_layer.metrics
        if metric.metric_variant == "net_header"
    )
    line_revenue = next(
        metric
        for metric in result.semantic_layer.metrics
        if metric.metric_variant == "line_detail"
    )

    assert net_revenue.compiler_eligibility == "eligible_with_disclosure"
    assert line_revenue.compiler_eligibility == "eligible_with_disclosure"
    assert "DUPLICATE_METRIC_SYNONYM" in net_revenue.validation_warnings
    assert "DUPLICATE_METRIC_SYNONYM" in line_revenue.validation_warnings


def test_server_computes_dimension_safety_and_blocks_header_detail_fanout() -> None:
    result = asyncio.run(
        generate_semantic_layer(
            graph=adventureworks_graph(),
            seed=semantic_seed(),
            gateway=FakeGateway(proposal_from_fixture()),
            generated_at=GENERATED_AT,
        )
    )
    net_revenue = next(
        metric
        for metric in result.semantic_layer.metrics
        if metric.metric_variant == "net_header"
    )
    line_revenue = next(
        metric
        for metric in result.semantic_layer.metrics
        if metric.metric_variant == "line_detail"
    )
    header_category = next(
        item
        for item in net_revenue.common_dimension_compatibility
        if item.dimension_column_key
        == column_key("ProductCategory", "ProductCategoryID")
    )
    detail_category = next(
        item
        for item in line_revenue.common_dimension_compatibility
        if item.dimension_column_key
        == column_key("ProductCategory", "ProductCategoryID")
    )

    assert header_category.safety == "forbidden"
    assert header_category.reason_code == "CHILD_ONE_TO_MANY"
    assert detail_category.safety == "safe"
    assert detail_category.reason_code == "TRUSTED_PARENT_PATH"


def test_compilation_is_canonical_and_assigns_stable_server_ids() -> None:
    proposal = proposal_from_fixture()
    first = compile_semantic_proposal(
        graph=adventureworks_graph(),
        seed=semantic_seed(),
        proposal=proposal,
        model_version="fixture-model-v2",
    )
    reordered = proposal.model_copy(
        update={
            "business_concepts": list(reversed(proposal.business_concepts)),
            "metrics": list(reversed(proposal.metrics)),
        }
    )
    second = compile_semantic_proposal(
        graph=adventureworks_graph(),
        seed=semantic_seed(),
        proposal=reordered,
        model_version="fixture-model-v2",
    )

    assert first.semantic_hash == second.semantic_hash
    assert {
        (metric.metric_variant, metric.metric_key) for metric in first.metrics
    } == {
        (metric.metric_variant, metric.metric_key) for metric in second.metrics
    }


def test_metric_hash_is_invariant_for_role_playing_dimension_order() -> None:
    compiled = compile_semantic_proposal(
        graph=adventureworks_graph(),
        seed=semantic_seed(),
        proposal=proposal_from_fixture(),
        model_version="fixture-model-v2",
    )
    metric = next(
        item for item in compiled.metrics if item.metric_variant == "net_header"
    )
    address_column_key = column_key("Address", "AddressID")
    dimensions = [
        SemanticDimensionCompatibility(
            dimension_column_key=address_column_key,
            edge_path=[edge_key("FK_Header_ShipAddress")],
            safety="safe",
            reason_code="TRUSTED_PARENT_PATH",
        ),
        SemanticDimensionCompatibility(
            dimension_column_key=address_column_key,
            edge_path=[edge_key("FK_Header_BillAddress")],
            safety="safe",
            reason_code="TRUSTED_PARENT_PATH",
        ),
    ]
    first = metric.model_copy(
        update={"common_dimension_compatibility": dimensions}
    )
    second = metric.model_copy(
        update={"common_dimension_compatibility": list(reversed(dimensions))}
    )

    assert compute_metric_definition_hash(first) == compute_metric_definition_hash(
        second
    )


def test_proposal_rejects_disallowed_columns_unknown_edges_and_duplicates() -> None:
    proposal = proposal_from_fixture()
    metrics = list(proposal.metrics)
    metrics[0] = metrics[0].model_copy(
        update={
            "measure_column_key": column_key(
                "SalesOrderHeader",
                "CreditCardApprovalCode",
            )
        }
    )
    compiled = compile_semantic_proposal(
        graph=adventureworks_graph(),
        seed=semantic_seed(),
        proposal=proposal.model_copy(update={"metrics": metrics}),
        model_version="fixture-model-v2",
    )
    assert compiled.quality_report.rejected_candidates[0].reason_code == (
        "AI_REFERENCE_NOT_ALLOWLISTED"
    )
    assert next(
        metric
        for metric in compiled.metrics
        if metric.metric_variant == "net_header"
    ).provenance_detail == "quality_profile"

    metrics = list(proposal.metrics)
    metrics[0] = metrics[0].model_copy(update={"metric_variant": "not_allowed"})
    compiled = compile_semantic_proposal(
        graph=adventureworks_graph(),
        seed=semantic_seed(),
        proposal=proposal.model_copy(update={"metrics": metrics}),
        model_version="fixture-model-v2",
    )
    assert compiled.quality_report.rejected_candidates[0].reason_code == (
        "AI_METRIC_VARIANT_NOT_ALLOWED"
    )

    compiled = compile_semantic_proposal(
        graph=adventureworks_graph(),
        seed=semantic_seed(),
        proposal=proposal.model_copy(
            update={"metrics": [*proposal.metrics, proposal.metrics[0]]}
        ),
        model_version="fixture-model-v2",
    )
    assert "AI_DUPLICATE_PROPOSAL_IGNORED" in {
        issue.code for issue in compiled.quality_report.issues
    }


def test_ai_contract_rejects_server_owned_fields() -> None:
    payload = proposal_from_fixture().model_dump(mode="json")
    payload["metrics"][0]["compiler_eligibility"] = "eligible"
    payload["metrics"][0]["confidence_score"] = 1
    payload["metrics"][0]["raw_sql"] = "select 1"
    payload["metrics"][0]["metric_key"] = (
        "10000000-0000-4000-8000-000000000001"
    )

    with pytest.raises(ValidationError):
        AISemanticDraftProposal.model_validate(payload)


def test_shared_ai_draft_fixture_matches_pydantic_contract() -> None:
    if SHARED_FIXTURE is None:
        pytest.skip("Shared TypeScript contract fixtures are not in this image.")
    proposal = AISemanticDraftProposal.model_validate(
        json.loads(SHARED_FIXTURE.read_text(encoding="utf-8"))
    )

    assert proposal.metrics[0].metric_variant == "net_header"


def test_generation_result_wire_dump_keeps_required_nullable_fields() -> None:
    result = asyncio.run(
        generate_semantic_layer(
            graph=adventureworks_graph(),
            seed=semantic_seed(),
            gateway=FakeGateway(proposal_from_fixture()),
            generated_at=GENERATED_AT,
        )
    )
    dumped = result.model_dump(mode="json")
    detail_metric = next(
        metric
        for metric in dumped["proposal"]["metrics"]
        if metric["metric_variant"] == "line_detail"
    )

    assert "default_date_column_key" in detail_metric
    assert detail_metric["default_date_column_key"] is None


def test_generation_rejects_tampered_seed_before_provider_call() -> None:
    seed = semantic_seed().model_copy(
        update={"semantic_hash": "f" * 64}
    )
    gateway = FakeGateway(proposal_from_fixture())

    with pytest.raises(SemanticProposalInvalid, match="seed hash"):
        asyncio.run(
            generate_semantic_layer(
                graph=adventureworks_graph(),
                seed=seed,
                gateway=gateway,
                generated_at=GENERATED_AT,
            )
        )
    assert gateway.received is None


def test_quality_profile_rejects_bad_ai_candidate_and_synthesizes_metric() -> None:
    proposal = proposal_from_fixture()
    metrics = list(proposal.metrics)
    metrics[0] = metrics[0].model_copy(
        update={
            "default_date_column_key": column_key(
                "ProductCategory", "FixtureColumn3"
            )
        }
    )
    ambiguity = AISemanticAmbiguity(
        code="AI_REJECTED_REVENUE_AMBIGUITY",
        target_type="metric",
        target_ref=metrics[0].canonical_name,
        summary="Rejected revenue candidate had ambiguity.",
        clarification_question="Which rejected revenue candidate should be used?",
        severity="material_ambiguity",
    )

    result = asyncio.run(
        generate_semantic_layer(
            graph=adventureworks_graph(),
            seed=semantic_seed(),
            gateway=FakeGateway(
                proposal.model_copy(
                    update={
                        "ambiguities": [ambiguity],
                        "metrics": metrics,
                    }
                )
            ),
            generated_at=GENERATED_AT,
        )
    )
    net_revenue = next(
        metric
        for metric in result.semantic_layer.metrics
        if metric.metric_variant == "net_header"
    )

    assert net_revenue.provenance == "system"
    assert net_revenue.provenance_detail == "quality_profile"
    assert net_revenue.source_spec_key == "adventureworks.revenue.net_header"
    assert net_revenue.reasoning_summary == (
        "Synthesized from configured quality profile spec "
        "adventureworks.revenue.net_header"
    )
    assert net_revenue.compiler_eligibility == "eligible_with_disclosure"
    assert "AI_REJECTED_REVENUE_AMBIGUITY" not in {
        ambiguity.code for ambiguity in result.semantic_layer.ambiguities
    }
    assert "AI_AMBIGUITY_TARGET_NOT_RESOLVED" in {
        issue.code for issue in result.semantic_layer.quality_report.issues
    }
    assert result.semantic_layer.quality_report.rejected_candidates[0].reason_code == (
        "AI_REQUIRED_METRIC_MISMATCH"
    )


def test_uncompilable_optional_ai_metric_is_rejected_not_global_failure() -> None:
    graph = adventureworks_graph()
    policy = semantic_policy()
    seed = build_semantic_seed(
        graph=graph,
        semantic_version_id=SEMANTIC_VERSION_ID,
        queryability_graph_version_id=GRAPH_VERSION_ID,
        version=1,
        semantic_policy=policy,
    )
    proposal = proposal_from_fixture()
    metrics = list(proposal.metrics)
    metrics[0] = metrics[0].model_copy(
        update={
            "default_date_column_key": column_key(
                "ProductCategory",
                "ProductCategoryID",
            )
        }
    )

    result = asyncio.run(
        generate_semantic_layer(
            graph=graph,
            seed=seed,
            gateway=FakeGateway(proposal.model_copy(update={"metrics": metrics})),
            semantic_policy=policy,
            generated_at=GENERATED_AT,
        )
    )

    assert "AI_METRIC_COMPILATION_FAILED" in {
        issue.code for issue in result.semantic_layer.quality_report.issues
    }
    assert "AI_METRIC_COMPILATION_FAILED" in {
        item.reason_code
        for item in result.semantic_layer.quality_report.rejected_candidates
    }


def test_multiple_shortest_safe_paths_become_material_metric_ambiguity() -> None:
    graph = adventureworks_graph()
    original_edge = next(
        edge
        for edge in graph.edges
        if edge.edge_key == edge_key("FK_Detail_Header")
    )
    duplicate_edge = original_edge.model_copy(
        update={
            "edge_key": edge_key("FK_Detail_Header_Alternate"),
            "constraint_name": "FK_Detail_Header_Alternate",
        }
    )
    proposal = proposal_from_fixture().model_copy(update={"ambiguities": []})
    graph = graph.model_copy(update={"edges": [*graph.edges, duplicate_edge]})

    result = asyncio.run(
        generate_semantic_layer(
            graph=graph,
            seed=build_semantic_seed(
                graph=graph,
                semantic_version_id=SEMANTIC_VERSION_ID,
                queryability_graph_version_id=GRAPH_VERSION_ID,
                version=1,
                semantic_policy=adventureworks_quality_policy(),
            ),
            gateway=FakeGateway(proposal),
            generated_at=GENERATED_AT,
        )
    )
    quantity = next(
        metric
        for metric in result.semantic_layer.metrics
        if metric.metric_variant == "line_quantity"
    )
    ambiguity = next(
        ambiguity
        for ambiguity in result.semantic_layer.ambiguities
        if ambiguity.code == "MULTIPLE_SHORTEST_SAFE_PATHS"
        and ambiguity.target_key == str(quantity.metric_key)
    )

    assert ambiguity.provenance == "system"
    assert ambiguity.severity == "material_ambiguity"
    assert quantity.compiler_eligibility == "clarification_required"


def test_openai_sdk_can_generate_strict_schema_for_ai_contract() -> None:
    from openai.lib._pydantic import to_strict_json_schema

    schema = to_strict_json_schema(AISemanticDraftProposal)

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "contract_version",
        "tables",
        "columns",
        "business_concepts",
        "metrics",
        "ambiguities",
    }


def test_anthropic_phases_have_bounded_budget_and_deadline() -> None:
    assert ANTHROPIC_ANNOTATION_OUTPUT_TOKENS == 8_000
    assert ANTHROPIC_METRIC_OUTPUT_TOKENS == 12_000
    assert ANTHROPIC_SEMANTIC_PHASE_TIMEOUT_SECONDS == 240
    assert ANTHROPIC_SEMANTIC_TOTAL_TIMEOUT_SECONDS == 450


def test_anthropic_sdk_generates_bounded_schemas_for_split_outputs() -> None:
    from anthropic.lib._parse._transform import transform_schema

    for output_model in (
        AnthropicSemanticAnnotationsOutput,
        AnthropicSemanticMetricsOutput,
    ):
        schema = transform_schema(output_model.model_json_schema())
        patterns: list[str] = []
        unsupported_constraints: list[str] = []
        optional_parameters = 0
        union_parameters = 0

        def collect_constraints(value: object) -> None:
            nonlocal optional_parameters, union_parameters
            if isinstance(value, dict):
                pattern = value.get("pattern")
                if isinstance(pattern, str):
                    patterns.append(pattern)
                unsupported_constraints.extend(
                    key
                    for key in (
                        "minLength",
                        "maxLength",
                        "minimum",
                        "maximum",
                    )
                    if key in value
                )
                properties = value.get("properties")
                if isinstance(properties, dict):
                    required = set(value.get("required", []))
                    optional_parameters += len(set(properties) - required)
                    union_parameters += sum(
                        "anyOf" in property_schema
                        or isinstance(property_schema.get("type"), list)
                        for property_schema in properties.values()
                        if isinstance(property_schema, dict)
                    )
                for child in value.values():
                    collect_constraints(child)
            elif isinstance(value, list):
                for child in value:
                    collect_constraints(child)

        collect_constraints(schema)

        assert patterns == []
        assert unsupported_constraints == []
        assert optional_parameters <= 24
        assert union_parameters <= 16
        assert len(json.dumps(schema, separators=(",", ":"))) < 7_000

def test_anthropic_bad_request_logs_sanitized_provider_detail(caplog) -> None:
    class FakeBadRequest(Exception):
        status_code = 400
        request_id = "req_fixture"
        body = {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "Invalid schema for sk-ant-api03-secret\npattern.",
            },
        }

    with caplog.at_level("WARNING"):
        with pytest.raises(SemanticDiscoveryProviderConfigurationError):
            _raise_anthropic_provider_error(FakeBadRequest())

    assert "req_fixture" in caplog.text
    assert "invalid_request_error" in caplog.text
    assert "Invalid schema for [redacted] pattern." in caplog.text
    assert "sk-ant-api03-secret" not in caplog.text


def test_anthropic_scoped_ambiguities_compile_to_existing_targets() -> None:
    proposal = proposal_from_fixture()
    concept_ambiguity = proposal.ambiguities[0]
    concept = AnthropicSemanticBusinessConceptProposal(
        **proposal.business_concepts[-1].model_dump(mode="json"),
        ambiguities=[
            {
                "code": concept_ambiguity.code,
                "summary": concept_ambiguity.summary,
                    "clarification_question": (
                        concept_ambiguity.clarification_question
                    ),
                    "severity": concept_ambiguity.severity,
            }
        ],
    )
    metric = AnthropicSemanticMetricsOutput.model_validate(
        {
            "metrics": [
                anthropic_metric_payload(
                    proposal.metrics[0],
                    ambiguities=[
                        {
                            "code": "REVENUE_VARIANT_AMBIGUOUS",
                            "summary": "Net and document totals differ.",
                            "clarification_question": (
                                "Should revenue mean net or document total?"
                            ),
                            "severity": "material_ambiguity",
                        }
                    ],
                )
            ]
        }
    )

    concepts, concept_ambiguities = _compile_anthropic_concepts([concept])
    metrics, metric_ambiguities = _compile_anthropic_metrics(metric)

    assert concepts == [proposal.business_concepts[-1]]
    assert metrics[0].canonical_name == proposal.metrics[0].canonical_name
    assert metrics[0].source_table_key == proposal.metrics[0].source_table_key
    assert metrics[0].default_date_column_key == (
        proposal.metrics[0].default_date_column_key
    )
    assert concept_ambiguities[0].target_type == "business_concept"
    assert concept_ambiguities[0].target_ref == concept.concept_ref
    assert metric_ambiguities[0].target_type == "metric"
    assert metric_ambiguities[0].target_ref == metrics[0].canonical_name

def test_openai_gateway_uses_structured_output_without_storing_payload() -> None:
    proposal = proposal_from_fixture()

    class FakeResponses:
        def __init__(self) -> None:
            self.kwargs = None

        async def parse(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                id="resp_openai_fixture",
                output_parsed=proposal,
            )

    responses = FakeResponses()
    client = SimpleNamespace(responses=responses)
    gateway = OpenAISemanticDiscoveryGateway(
        client=client,
        model_version="fixture-model-v2",
    )
    response = asyncio.run(
        gateway.generate(
            build_semantic_discovery_input(adventureworks_graph(), semantic_policy())
        )
    )

    assert response.response_id == "resp_openai_fixture"
    assert responses.kwargs["text_format"] is AISemanticDraftProposal
    assert responses.kwargs["store"] is False
    assert responses.kwargs["max_output_tokens"] == 20_000
    assert responses.kwargs["timeout"] == 120
    assert responses.kwargs["reasoning"] == {"effort": "medium"}
    assert responses.kwargs["verbosity"] == "low"
    assert "Never write SQL" in responses.kwargs["input"][0]["content"]


def test_anthropic_gateway_uses_structured_output_and_adaptive_effort() -> None:
    proposal = proposal_from_fixture()

    class FakeMessages:
        def __init__(self) -> None:
            self.calls = []

        def stream(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs["output_format"] is AnthropicSemanticAnnotationsOutput:
                parsed_output = AnthropicSemanticAnnotationsOutput(
                    contract_version=proposal.contract_version,
                    tables=proposal.tables,
                    columns=proposal.columns,
                    business_concepts=[
                        {
                            **concept.model_dump(mode="json"),
                            "ambiguities": [
                                {
                                    "code": ambiguity.code,
                                    "summary": ambiguity.summary,
                                    "clarification_question": (
                                        ambiguity.clarification_question
                                    ),
                                    "severity": ambiguity.severity,
                                }
                                for ambiguity in proposal.ambiguities
                                if ambiguity.target_type == "business_concept"
                                and ambiguity.target_ref == concept.concept_ref
                            ],
                        }
                        for concept in proposal.business_concepts
                    ],
                )
                response_id = "msg_anthropic_annotations"
            else:
                parsed_output = AnthropicSemanticMetricsOutput(
                    metrics=[
                        anthropic_metric_payload(
                            metric,
                            ambiguities=[
                                {
                                    "code": ambiguity.code,
                                    "summary": ambiguity.summary,
                                    "clarification_question": (
                                        ambiguity.clarification_question
                                    ),
                                    "severity": ambiguity.severity,
                                }
                                for ambiguity in proposal.ambiguities
                                if ambiguity.target_type == "metric"
                                and ambiguity.target_ref
                                == metric.canonical_name
                            ],
                        )
                        for metric in proposal.metrics
                    ],
                )
                response_id = "msg_anthropic_metrics"
            return FakeStreamManager(
                SimpleNamespace(
                    id=response_id,
                    parsed_output=parsed_output,
                )
            )

    class FakeStreamManager:
        def __init__(self, response) -> None:
            self.response = response

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def get_final_message(self):
            return self.response

    messages = FakeMessages()
    client = SimpleNamespace(messages=messages)
    gateway = AnthropicSemanticDiscoveryGateway(
        client=client,
        config=AnthropicProviderConfig.model_validate(
            {
                "provider": "anthropic",
                "setting_id": "00000000-0000-4000-8000-000000000001",
                "model_id": "claude-opus-4-8",
                "thinking": {
                    "type": "anthropic_adaptive",
                    "enabled": True,
                    "effort": "xhigh",
                },
                "secret_ref": (
                    "gcp-secret-manager://projects/demo/secrets/"
                    "atlantebi-tenant-setting-anthropic-ai-key"
                ),
            }
        ),
    )
    response = asyncio.run(
        gateway.generate(
            build_semantic_discovery_input(adventureworks_graph(), semantic_policy())
        )
    )

    assert response.response_id == (
        "msg_anthropic_annotations,msg_anthropic_metrics"
    )
    assert response.proposal.model_dump(mode="json") == proposal.model_dump(
        mode="json"
    )
    assert len(messages.calls) == 2
    annotations_call, metrics_call = messages.calls
    assert annotations_call["model"] == "claude-opus-4-8"
    assert (
        annotations_call["output_format"]
        is AnthropicSemanticAnnotationsOutput
    )
    assert metrics_call["output_format"] is AnthropicSemanticMetricsOutput
    assert annotations_call["output_config"] == {"effort": "low"}
    assert metrics_call["output_config"] == {"effort": "xhigh"}
    assert annotations_call["max_tokens"] == 8_000
    assert metrics_call["max_tokens"] == 12_000
    assert annotations_call["thinking"] == {"type": "adaptive"}
    assert metrics_call["thinking"] == {"type": "adaptive"}
    assert annotations_call["timeout"] == 240
    assert metrics_call["timeout"] == 240
    assert "Never write SQL" in annotations_call["system"]
    metrics_input = json.loads(metrics_call["messages"][0]["content"])
    assert metrics_input["proposed_business_concepts"] == [
        concept.model_dump(mode="json", exclude_none=True)
        for concept in proposal.business_concepts
    ]


def test_anthropic_gateway_enforces_total_phase_deadline(
    monkeypatch,
    caplog,
) -> None:
    class SlowStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def get_final_message(self):
            await asyncio.sleep(1)

    config = AnthropicProviderConfig.model_validate(
        {
            "provider": "anthropic",
            "setting_id": "00000000-0000-4000-8000-000000000001",
            "model_id": "claude-sonnet-4-6",
            "thinking": {
                "type": "anthropic_adaptive",
                "enabled": True,
                "effort": "medium",
            },
            "secret_ref": (
                "gcp-secret-manager://projects/demo/secrets/"
                "atlantebi-tenant-setting-anthropic-ai-key"
            ),
        }
    )
    gateway = AnthropicSemanticDiscoveryGateway(
        client=SimpleNamespace(
            messages=SimpleNamespace(stream=lambda **kwargs: SlowStream())
        ),
        config=config,
    )
    monkeypatch.setattr(
        "app.semantic_discovery.ANTHROPIC_SEMANTIC_PHASE_TIMEOUT_SECONDS",
        0.01,
    )

    with caplog.at_level("WARNING"):
        with pytest.raises(SemanticDiscoveryError, match="phase deadline"):
            asyncio.run(
                gateway._generate_part(
                    input_content="{}",
                    output_format=AnthropicSemanticAnnotationsOutput,
                    phase_name="annotations",
                    max_tokens=8_000,
                    effort="low",
                    phase_instruction="fixture",
                )
            )
    assert "phase=annotations" in caplog.text


def test_anthropic_gateway_enforces_total_generation_deadline(
    monkeypatch,
) -> None:
    config = AnthropicProviderConfig.model_validate(
        {
            "provider": "anthropic",
            "setting_id": "00000000-0000-4000-8000-000000000001",
            "model_id": "claude-sonnet-4-6",
            "thinking": {
                "type": "anthropic_adaptive",
                "enabled": True,
                "effort": "medium",
            },
            "secret_ref": (
                "gcp-secret-manager://projects/demo/secrets/"
                "atlantebi-tenant-setting-anthropic-ai-key"
            ),
        }
    )
    gateway = AnthropicSemanticDiscoveryGateway(
        client=SimpleNamespace(messages=SimpleNamespace()),
        config=config,
    )

    async def slow_generation(discovery_input):
        await asyncio.sleep(1)

    monkeypatch.setattr(gateway, "_generate", slow_generation)
    monkeypatch.setattr(
        "app.semantic_discovery.ANTHROPIC_SEMANTIC_TOTAL_TIMEOUT_SECONDS",
        0.01,
    )

    with pytest.raises(SemanticDiscoveryError, match="total deadline"):
        asyncio.run(
            gateway.generate(
                build_semantic_discovery_input(adventureworks_graph(), semantic_policy())
            )
        )


def test_anthropic_gateway_distinguishes_refusal_from_missing_structured_output() -> None:
    class FakeMessages:
        def __init__(self, response) -> None:
            self.response = response

        def stream(self, **kwargs):
            return FakeStreamManager(self.response)

    class FakeStreamManager:
        def __init__(self, response) -> None:
            self.response = response

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def get_final_message(self):
            return self.response

    config = AnthropicProviderConfig.model_validate(
        {
            "provider": "anthropic",
            "setting_id": "00000000-0000-4000-8000-000000000001",
            "model_id": "claude-opus-4-8",
            "thinking": {
                "type": "anthropic_adaptive",
                "enabled": True,
                "effort": "xhigh",
            },
            "secret_ref": (
                "gcp-secret-manager://projects/demo/secrets/"
                "atlantebi-tenant-setting-anthropic-ai-key"
            ),
        }
    )
    refusal_gateway = AnthropicSemanticDiscoveryGateway(
        client=SimpleNamespace(
            messages=FakeMessages(
                SimpleNamespace(
                    id="msg_refusal",
                    parsed_output=None,
                    stop_reason="refusal",
                    content=[],
                )
            )
        ),
        config=config,
    )
    with pytest.raises(SemanticDiscoveryRefused):
        asyncio.run(
            refusal_gateway.generate(
                build_semantic_discovery_input(adventureworks_graph(), semantic_policy())
            )
        )

    empty_gateway = AnthropicSemanticDiscoveryGateway(
        client=SimpleNamespace(
            messages=FakeMessages(
                SimpleNamespace(
                    id="msg_empty",
                    parsed_output=None,
                    stop_reason="end_turn",
                    content=[],
                )
            )
        ),
        config=config,
    )
    with pytest.raises(
        SemanticDiscoveryError,
        match="did not return a structured proposal",
    ):
        asyncio.run(
            empty_gateway.generate(
                build_semantic_discovery_input(adventureworks_graph(), semantic_policy())
            )
        )


def test_openai_gateway_distinguishes_refusal_from_missing_structured_output() -> None:
    class FakeResponses:
        def __init__(self, response) -> None:
            self.response = response

        async def parse(self, **kwargs):
            return self.response

    refusal_response = SimpleNamespace(
        id="resp_refusal",
        output_parsed=None,
        output=[
            SimpleNamespace(
                content=[SimpleNamespace(type="refusal", refusal="No.")]
            )
        ],
    )
    refusal_gateway = OpenAISemanticDiscoveryGateway(
        client=SimpleNamespace(responses=FakeResponses(refusal_response)),
        model_version="fixture-model-v2",
    )
    with pytest.raises(SemanticDiscoveryRefused):
        asyncio.run(
            refusal_gateway.generate(
                build_semantic_discovery_input(adventureworks_graph(), semantic_policy())
            )
        )

    empty_response = SimpleNamespace(
        id="resp_empty",
        output_parsed=None,
        output=[],
    )
    empty_gateway = OpenAISemanticDiscoveryGateway(
        client=SimpleNamespace(responses=FakeResponses(empty_response)),
        model_version="fixture-model-v2",
    )
    with pytest.raises(
        SemanticDiscoveryError,
        match="did not return a structured proposal",
    ):
        asyncio.run(
            empty_gateway.generate(
                build_semantic_discovery_input(adventureworks_graph(), semantic_policy())
            )
        )


def test_validator_blocks_ai_self_promotion() -> None:
    proposal = proposal_from_fixture()
    compiled = compile_semantic_proposal(
        graph=adventureworks_graph(),
        seed=semantic_seed(),
        proposal=proposal,
        model_version="fixture-model-v2",
    )
    promoted = compiled.metrics[0].model_copy(update={"status": "human_verified"})
    tampered = compiled.model_copy(
        update={"metrics": [promoted, *compiled.metrics[1:]]}
    )
    tampered = tampered.model_copy(
        update={"semantic_hash": compute_semantic_hash(tampered)}
    )
    validated = validate_semantic_layer(
        layer=tampered,
        graph=adventureworks_graph(),
        validated_at=GENERATED_AT,
    )
    assert "SEMANTIC_PROVENANCE_STATUS_MISMATCH" in {
        issue.code for issue in validated.validation_report.blocking_errors
    }


def test_ai_candidate_contract_rejects_structured_filters() -> None:
    payload = proposal_from_fixture().model_dump(mode="json")
    payload["metrics"][0]["filters"] = []

    with pytest.raises(ValidationError):
        AISemanticDraftProposal.model_validate(payload)
