import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import (
    QueryabilityGraphArtifact,
    QueryabilityGraphVersion,
    QueryabilityPathResult,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "contracts"
    / "src"
    / "fixtures"
    / "queryability-graph-v1.json"
)


def graph_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_shared_queryability_graph_fixture_matches_pydantic_contract() -> None:
    graph = QueryabilityGraphArtifact.model_validate(graph_fixture())

    assert graph.status == "partial"
    assert graph.semantic_status == "not_initialized"
    assert [edge.edge_type for edge in graph.edges] == [
        "fk_join",
        "view_depends_on",
        "view_column_derives_from",
    ]


def test_queryability_graph_contract_rejects_extra_fields_and_bad_hashes() -> None:
    payload = graph_fixture()
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        QueryabilityGraphArtifact.model_validate(payload)

    payload = graph_fixture()
    payload["graph_hash"] = "A" * 64
    with pytest.raises(ValidationError):
        QueryabilityGraphArtifact.model_validate(payload)


def test_lineage_contract_cannot_enable_automatic_join() -> None:
    payload = graph_fixture()
    payload["edges"][1]["automatic_join_allowed"] = True

    with pytest.raises(ValidationError):
        QueryabilityGraphArtifact.model_validate(payload)


def test_graph_version_timestamp_and_path_hop_limit_are_strict() -> None:
    version = QueryabilityGraphVersion.model_validate(
        {
            "graph_version_id": "44444444-4444-4444-8444-444444444444",
            "graph_version": 1,
            "created_at": "2026-06-12T08:00:00.000Z",
            "graph": graph_fixture(),
        }
    )
    assert version.graph_version == 1

    step = {
        "edge_key": "5" * 64,
        "from_node_key": "3" * 64,
        "to_node_key": "1" * 64,
        "traversal": "child_to_parent",
        "cardinality": "zero_or_one",
    }
    with pytest.raises(ValidationError):
        QueryabilityPathResult.model_validate(
            {
                "status": "found",
                "paths": [
                    {
                        "steps": [step, step, step, step, step],
                        "fanout_warning": False,
                    }
                ],
                "reason_codes": [],
            }
        )


def test_queryability_compile_and_path_endpoints_use_pure_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUERY_ENGINE_ALLOW_UNAUTHENTICATED", "true")
    client = TestClient(app)
    snapshot = {
        "status": "ok",
        "message": "Schema introspection completed.",
        "introspected_at": "2026-06-12T08:00:00.000Z",
        "duration_ms": 10,
        "engine": "sqlserver",
        "database_name": "AdventureWorksLT",
        "engine_version": "12.0.2000.8",
        "schema_hash": "a" * 64,
        "snapshot_hash": "b" * 64,
        "coverage_status": "ok",
        "tables": [
            {
                "schema": "SalesLT",
                "name": "Parent",
                "table_type": "base_table",
                "columns": [
                    {
                        "name": "ParentID",
                        "data_type": "int",
                        "native_type": "int",
                        "normalized_type": "int",
                        "declared_type_available": True,
                        "technical_role": "identifier",
                        "ordinal_position": 1,
                        "is_nullable": False,
                        "is_primary_key": True,
                    }
                ],
                "primary_key": {
                    "name": "PK_Parent",
                    "columns": ["ParentID"],
                },
                "view_lineage": [],
            },
            {
                "schema": "SalesLT",
                "name": "Child",
                "table_type": "base_table",
                "columns": [
                    {
                        "name": "ChildID",
                        "data_type": "int",
                        "native_type": "int",
                        "normalized_type": "int",
                        "declared_type_available": True,
                        "technical_role": "identifier",
                        "ordinal_position": 1,
                        "is_nullable": False,
                        "is_primary_key": True,
                    },
                    {
                        "name": "ParentID",
                        "data_type": "int",
                        "native_type": "int",
                        "normalized_type": "int",
                        "declared_type_available": True,
                        "technical_role": "identifier",
                        "ordinal_position": 2,
                        "is_nullable": False,
                        "is_foreign_key": True,
                    },
                ],
                "primary_key": {
                    "name": "PK_Child",
                    "columns": ["ChildID"],
                },
                "view_lineage": [],
            },
        ],
        "foreign_keys": [
            {
                "constraint_name": "FK_Child_Parent",
                "from_schema": "SalesLT",
                "from_table": "Child",
                "from_columns": ["ParentID"],
                "to_schema": "SalesLT",
                "to_table": "Parent",
                "to_columns": ["ParentID"],
                "delete_rule": "no_action",
                "update_rule": "no_action",
                "source": "db_fk",
                "verified_by_db": True,
            }
        ],
        "unique_constraints": [],
        "check_constraints": [],
        "default_constraints": [],
        "indexes": [],
        "coverage_warnings": [],
    }
    compile_response = client.post(
        "/queryability/compile",
        json={
            "tenant_id": "11111111-1111-4111-8111-111111111111",
            "connection_id": "22222222-2222-4222-8222-222222222222",
            "schema_snapshot_id": "33333333-3333-4333-8333-333333333333",
            "snapshot": snapshot,
        },
    )
    assert compile_response.status_code == 200
    graph = compile_response.json()
    assert graph["status"] == "complete"
    assert graph["semantic_status"] == "not_initialized"

    nodes = {node["object_name"]: node["node_key"] for node in graph["nodes"]}
    path_response = client.post(
        "/queryability/paths",
        json={
            "graph": graph,
            "from_node_key": nodes["Child"],
            "to_node_key": nodes["Parent"],
            "max_hops": 4,
        },
    )
    assert path_response.status_code == 200
    assert path_response.json()["status"] == "found"
