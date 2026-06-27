from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import (
    QueryabilityGraphArtifact,
    SemanticRebaseRequest,
    SemanticSeedRequest,
)
from app.semantic import (
    compute_semantic_hash,
    rebase_semantic_layer,
    validate_semantic_layer,
)
from tests.test_semantic_builder import (
    GRAPH_VERSION_ID,
    SEMANTIC_VERSION_ID,
    adventureworks_graph,
    adventureworks_quality_policy,
    column_key,
    edge_key,
    key,
    semantic_draft,
    semantic_policy,
)


TARGET_GRAPH_VERSION_ID = "55555555-5555-4555-8555-555555555555"
TARGET_SEMANTIC_VERSION_ID = "99999999-9999-4999-8999-999999999999"
VALIDATED_AT = datetime(2026, 6, 14, 18, 0, tzinfo=UTC)


def _source_layer(graph: QueryabilityGraphArtifact):
    draft = semantic_draft(graph)
    tables = [
        table.model_copy(
            update={
                "display_name": "Indirizzi",
                "description": "Indirizzi disponibili.",
                "business_domain": "Anagrafiche",
                "synonyms": ["sedi"],
                "status": "human_verified",
            }
        )
        if table.object_name == "Address"
        else table
        for table in draft.tables
    ]
    columns = [
        column.model_copy(
            update={
                "display_name": "Quantita",
                "description": "Quantita tecnica della riga.",
                "semantic_role": "measure",
                "format_hint": "integer",
                "status": "human_verified",
            }
        )
        if column.column_key == column_key("SalesOrderDetail", "OrderQty")
        else column
        for column in draft.columns
    ]
    metrics = [
        metric.model_copy(
            update={
                "status": "human_verified",
                "provenance": "human",
                "provenance_detail": "human_override",
                "source_spec_key": None,
            }
        )
        if metric.canonical_name == "fatturato_netto"
        else metric
        for metric in draft.metrics
    ]
    updated = draft.model_copy(
        update={
            "tables": tables,
            "columns": columns,
            "metrics": metrics,
        }
    )
    updated = updated.model_copy(
        update={"semantic_hash": compute_semantic_hash(updated)}
    )
    validated = validate_semantic_layer(
        layer=updated,
        graph=graph,
        semantic_policy=semantic_policy(),
        validated_at=VALIDATED_AT,
    )
    return validated.model_copy(update={"status": "active"})


def _target_graph(
    graph: QueryabilityGraphArtifact,
    *,
    graph_hash: str = "f" * 64,
) -> QueryabilityGraphArtifact:
    return graph.model_copy(update={"graph_hash": graph_hash})


def _rebase(source_layer, target_graph):
    return rebase_semantic_layer(
        source_layer=source_layer,
        target_graph=target_graph,
        semantic_version_id=TARGET_SEMANTIC_VERSION_ID,
        queryability_graph_version_id=TARGET_GRAPH_VERSION_ID,
        version=2,
        semantic_policy=semantic_policy(),
        validated_at=VALIDATED_AT,
    )


def test_seed_and_rebase_requests_are_strict_and_reject_blocked_graphs() -> None:
    graph = adventureworks_graph()
    seed_payload = {
        "graph": graph.model_dump(mode="json"),
        "semantic_version_id": TARGET_SEMANTIC_VERSION_ID,
        "queryability_graph_version_id": TARGET_GRAPH_VERSION_ID,
        "version": 2,
        "semantic_policy": semantic_policy().model_dump(mode="json"),
    }
    SemanticSeedRequest.model_validate(seed_payload)

    with pytest.raises(ValidationError):
        SemanticSeedRequest.model_validate({**seed_payload, "legacy": True})

    with pytest.raises(ValidationError, match="graph must not be blocked"):
        SemanticSeedRequest(
            graph=graph.model_copy(update={"status": "blocked"}),
            semantic_version_id=TARGET_SEMANTIC_VERSION_ID,
            queryability_graph_version_id=TARGET_GRAPH_VERSION_ID,
            version=2,
            semantic_policy=semantic_policy(),
        )


def test_rebase_request_rejects_scope_reuse_and_blocked_target() -> None:
    graph = adventureworks_graph()
    source = _source_layer(graph)

    with pytest.raises(ValidationError, match="tenant and connection"):
        SemanticRebaseRequest(
            source_layer=source,
            target_graph=graph.model_copy(
                update={"tenant_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}
            ),
            semantic_version_id=TARGET_SEMANTIC_VERSION_ID,
            queryability_graph_version_id=TARGET_GRAPH_VERSION_ID,
            version=2,
            semantic_policy=semantic_policy(),
        )

    with pytest.raises(ValidationError, match="must differ"):
        SemanticRebaseRequest(
            source_layer=source,
            target_graph=graph,
            semantic_version_id=SEMANTIC_VERSION_ID,
            queryability_graph_version_id=TARGET_GRAPH_VERSION_ID,
            version=2,
            semantic_policy=semantic_policy(),
        )

    with pytest.raises(ValidationError, match="newer"):
        SemanticRebaseRequest(
            source_layer=source,
            target_graph=graph,
            semantic_version_id=TARGET_SEMANTIC_VERSION_ID,
            queryability_graph_version_id=TARGET_GRAPH_VERSION_ID,
            version=source.version,
            semantic_policy=semantic_policy(),
        )

    with pytest.raises(ValidationError, match="active or archived"):
        SemanticRebaseRequest(
            source_layer=source.model_copy(update={"status": "proposed"}),
            target_graph=graph,
            semantic_version_id=TARGET_SEMANTIC_VERSION_ID,
            queryability_graph_version_id=TARGET_GRAPH_VERSION_ID,
            version=2,
            semantic_policy=semantic_policy(),
        )

    with pytest.raises(ValidationError, match="must not be blocked"):
        SemanticRebaseRequest(
            source_layer=source,
            target_graph=graph.model_copy(update={"status": "blocked"}),
            semantic_version_id=TARGET_SEMANTIC_VERSION_ID,
            queryability_graph_version_id=TARGET_GRAPH_VERSION_ID,
            version=2,
            semantic_policy=semantic_policy(),
        )


def test_rebase_carries_exact_keys_annotations_concepts_and_valid_metrics() -> None:
    graph = adventureworks_graph()
    source = _source_layer(graph)
    result = _rebase(source, _target_graph(graph))
    layer = result.semantic_layer
    report = result.rebase_report

    assert layer.status == "draft"
    assert layer.freshness == "fresh"
    assert layer.revision == 1
    assert str(layer.semantic_version_id) == TARGET_SEMANTIC_VERSION_ID
    assert str(layer.queryability_graph_version_id) == TARGET_GRAPH_VERSION_ID
    assert layer.base_graph_hash == "f" * 64
    assert layer.semantic_hash == compute_semantic_hash(layer)
    assert layer.validation_report.status in {"valid", "valid_with_warnings"}
    assert layer.validation_report.validated_revision == 1

    address = next(table for table in layer.tables if table.object_name == "Address")
    assert address.display_name == "Indirizzi"
    assert address.status == "human_verified"
    quantity = next(
        column
        for column in layer.columns
        if column.column_key == column_key("SalesOrderDetail", "OrderQty")
    )
    assert quantity.display_name == "Quantita"
    assert quantity.status == "human_verified"

    net_revenue = next(
        metric for metric in layer.metrics if metric.canonical_name == "fatturato_netto"
    )
    assert net_revenue.status == "human_verified"
    assert net_revenue.provenance == "human"

    assert len(report.carried_table_keys) == len(source.tables)
    assert len(report.carried_column_keys) == len(source.columns)
    assert len(report.carried_business_concept_keys) == len(
        source.business_concepts
    )
    assert len(report.carried_metric_keys) == len(source.metrics)
    assert report.dropped_tables == []
    assert report.dropped_columns == []
    assert report.dropped_business_concepts == []
    assert report.dropped_metrics == []


def test_rebase_drops_metric_when_column_disappears() -> None:
    graph = adventureworks_graph()
    source = _source_layer(graph)
    nodes = [
        node.model_copy(
            update={
                "columns": [
                    column
                    for column in node.columns
                    if column.name != "OrderQty"
                ]
            }
        )
        if node.object_name == "SalesOrderDetail"
        else node
        for node in graph.nodes
    ]
    target = _target_graph(graph).model_copy(update={"nodes": nodes})

    result = _rebase(source, target)

    dropped_column = next(
        item
        for item in result.rebase_report.dropped_columns
        if item.item_key == column_key("SalesOrderDetail", "OrderQty")
    )
    assert dropped_column.item_type == "column"
    assert dropped_column.reason_codes == ["TARGET_KEY_MISSING"]
    dropped_metric = next(
        item
        for item in result.rebase_report.dropped_metrics
        if str(item.item_key) == "10000000-0000-4000-8000-000000000004"
    )
    assert dropped_metric.item_type == "metric"
    assert "TARGET_KEY_MISSING" in dropped_metric.reason_codes
    assert all(
        metric.canonical_name != "quantita_venduta"
        for metric in result.semantic_layer.metrics
    )


def test_rebase_drops_metrics_when_required_edge_is_removed_or_untrusted() -> None:
    graph = adventureworks_graph()
    source = _source_layer(graph)
    product_category_edge = edge_key("FK_Product_ProductCategory")

    removed_target = _target_graph(graph).model_copy(
        update={
            "edges": [
                edge
                for edge in graph.edges
                if edge.edge_key != product_category_edge
            ]
        }
    )
    removed = _rebase(source, removed_target)
    line_revenue_drop = next(
        item
        for item in removed.rebase_report.dropped_metrics
        if str(item.item_key) == "10000000-0000-4000-8000-000000000003"
    )
    assert "TARGET_KEY_MISSING" in line_revenue_drop.reason_codes

    untrusted_target = _target_graph(graph).model_copy(
        update={
            "edges": [
                edge.model_copy(
                    update={
                        "validation_status": "untrusted",
                        "automatic_join_allowed": False,
                    }
                )
                if edge.edge_key == product_category_edge
                else edge
                for edge in graph.edges
            ]
        }
    )
    untrusted = _rebase(source, untrusted_target)
    line_revenue_drop = next(
        item
        for item in untrusted.rebase_report.dropped_metrics
        if str(item.item_key) == "10000000-0000-4000-8000-000000000003"
    )
    assert "TARGET_EDGE_NOT_TRUSTED" in line_revenue_drop.reason_codes


def test_rebase_does_not_preserve_human_verified_metric_with_changed_definition() -> None:
    graph = adventureworks_graph()
    source = _source_layer(graph)
    metrics = [
        metric.model_copy(update={"metric_definition_hash": "0" * 64})
        if metric.canonical_name == "fatturato_netto"
        else metric
        for metric in source.metrics
    ]
    tampered = source.model_copy(update={"metrics": metrics})
    tampered = tampered.model_copy(
        update={"semantic_hash": compute_semantic_hash(tampered)}
    )

    result = _rebase(tampered, _target_graph(graph))
    dropped = next(
        item
        for item in result.rebase_report.dropped_metrics
        if str(item.item_key) == "10000000-0000-4000-8000-000000000001"
    )

    assert dropped.reason_codes == ["DEFINITION_CHANGED"]
    assert all(
        metric.canonical_name != "fatturato_netto"
        for metric in result.semantic_layer.metrics
    )


def test_rebase_rejects_tampered_source_artifact() -> None:
    graph = adventureworks_graph()
    source = _source_layer(graph)
    tampered = source.model_copy(update={"semantic_hash": "0" * 64})

    with pytest.raises(ValueError, match="hash is invalid"):
        _rebase(tampered, _target_graph(graph))


def test_rebase_does_not_match_renamed_keys_by_physical_name() -> None:
    graph = adventureworks_graph()
    source = _source_layer(graph)
    original = next(
        node
        for node in graph.nodes
        if node.object_name == "vProductModelCatalogDescription"
    )
    replacement_node_key = key("renamed-view-key")
    replacement = original.model_copy(
        update={
            "node_key": replacement_node_key,
            "columns": [
                column.model_copy(
                    update={
                        "column_key": key(
                            f"renamed-view-column:{column.name}"
                        )
                    }
                )
                for column in original.columns
            ],
        }
    )
    target = _target_graph(graph).model_copy(
        update={
            "nodes": [
                replacement if node.node_key == original.node_key else node
                for node in graph.nodes
            ]
        }
    )

    result = _rebase(source, target)
    replacement_table = next(
        table
        for table in result.semantic_layer.tables
        if table.node_key == replacement_node_key
    )

    assert replacement_table.object_name == original.object_name
    assert replacement_table.display_name is None
    assert replacement_table.status == "system_seeded"
    assert original.node_key not in result.rebase_report.carried_table_keys
    dropped = next(
        item
        for item in result.rebase_report.dropped_tables
        if item.item_key == original.node_key
    )
    assert dropped.reason_codes == ["TARGET_KEY_MISSING"]


def test_semantic_seed_and_rebase_endpoints_are_authenticated_and_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = adventureworks_graph()
    source = _source_layer(graph)
    client = TestClient(app)
    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "semantic-token")
    monkeypatch.delenv("QUERY_ENGINE_ALLOW_UNAUTHENTICATED", raising=False)

    seed_payload = {
        "graph": graph.model_dump(mode="json"),
        "semantic_version_id": TARGET_SEMANTIC_VERSION_ID,
        "queryability_graph_version_id": TARGET_GRAPH_VERSION_ID,
        "version": 2,
        "semantic_policy": semantic_policy().model_dump(mode="json"),
    }
    assert client.post("/semantic/seed", json=seed_payload).status_code == 401

    headers = {"x-atlante-query-engine-token": "semantic-token"}
    seed_response = client.post(
        "/semantic/seed",
        headers=headers,
        json=seed_payload,
    )
    assert seed_response.status_code == 200
    assert seed_response.json()["status"] == "draft"

    quality_policy_payload = adventureworks_quality_policy().model_dump(
        mode="json"
    )
    quality_seed_response = client.post(
        "/semantic/seed",
        headers=headers,
        json={**seed_payload, "semantic_policy": quality_policy_payload},
    )
    assert quality_seed_response.status_code == 200
    quality_seed = quality_seed_response.json()
    customer_master_spec = next(
        spec
        for spec in quality_seed["semantic_policy_snapshot"][
            "required_metric_specs"
        ]
        if spec["spec_key"] == "adventureworks.customers.customer_master"
    )
    assert "default_date_column_key" in customer_master_spec
    assert customer_master_spec["default_date_column_key"] is None

    strict_response = client.post(
        "/semantic/seed",
        headers=headers,
        json={**seed_payload, "unexpected": True},
    )
    assert strict_response.status_code == 422

    rebase_response = client.post(
        "/semantic/rebase",
        headers=headers,
        json={
            "source_layer": source.model_dump(mode="json"),
            "target_graph": _target_graph(graph).model_dump(mode="json"),
            "semantic_version_id": TARGET_SEMANTIC_VERSION_ID,
            "queryability_graph_version_id": TARGET_GRAPH_VERSION_ID,
            "version": 2,
            "semantic_policy": semantic_policy().model_dump(mode="json"),
        },
    )
    assert rebase_response.status_code == 200
    payload = rebase_response.json()
    assert payload["semantic_layer"]["status"] == "draft"
    assert "carried_table_keys" in payload["rebase_report"]
    assert "carried" not in payload["rebase_report"]

    scope_response = client.post(
        "/semantic/rebase",
        headers=headers,
        json={
            "source_layer": source.model_dump(mode="json"),
            "target_graph": _target_graph(graph)
            .model_copy(
                update={
                    "connection_id": UUID(
                        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
                    )
                }
            )
            .model_dump(mode="json"),
            "semantic_version_id": TARGET_SEMANTIC_VERSION_ID,
            "queryability_graph_version_id": TARGET_GRAPH_VERSION_ID,
            "version": 2,
            "semantic_policy": semantic_policy().model_dump(mode="json"),
        },
    )
    assert scope_response.status_code == 422

    tampered_response = client.post(
        "/semantic/rebase",
        headers=headers,
        json={
            "source_layer": source.model_copy(
                update={"semantic_hash": "0" * 64}
            ).model_dump(mode="json"),
            "target_graph": _target_graph(graph).model_dump(mode="json"),
            "semantic_version_id": TARGET_SEMANTIC_VERSION_ID,
            "queryability_graph_version_id": TARGET_GRAPH_VERSION_ID,
            "version": 2,
            "semantic_policy": semantic_policy().model_dump(mode="json"),
        },
    )
    assert tampered_response.status_code == 422
    assert tampered_response.json()["detail"] == (
        "source semantic layer hash is invalid"
    )
