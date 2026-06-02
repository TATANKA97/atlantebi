import json
import asyncio
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.drivers.base import ConnectionMetadata, DriverNotImplementedError
from app.drivers.registry import DRIVER_REGISTRY, get_driver
from app.main import app
from app.models import Engine, QueryRequest, QueryResponse, Relationship, VerificationSummary


def test_health_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "atlantebi-query-engine",
        "status": "ok",
        "version": "0.1.0",
    }


def test_driver_registry_accepts_only_v1_engines() -> None:
    assert set(DRIVER_REGISTRY.keys()) == {Engine.sqlserver, Engine.mysql}
    assert get_driver(Engine.sqlserver).engine == Engine.sqlserver
    assert get_driver(Engine.mysql).engine == Engine.mysql


def test_relationship_confidence_is_not_numeric() -> None:
    relationship = Relationship(
        id=UUID("55555555-5555-4555-8555-555555555555"),
        from_table="SalesOrderHeader",
        from_columns=["CustomerID"],
        to_table="Customer",
        to_columns=["CustomerID"],
        cardinality="many_to_one",
        semantic_status="confirmed",
        source="database_fk",
    )

    assert relationship.semantic_status == "confirmed"

    with pytest.raises(ValidationError):
        Relationship(
            id=UUID("55555555-5555-4555-8555-555555555555"),
            from_table="SalesOrderHeader",
            from_columns=["CustomerID"],
            to_table="Customer",
            to_columns=["CustomerID"],
            cardinality="many_to_one",
            semantic_status=0.91,
            source="database_fk",
        )

    with pytest.raises(ValidationError):
        Relationship(
            id=UUID("55555555-5555-4555-8555-555555555555"),
            from_table="SalesOrderHeader",
            from_columns=[""],
            to_table="Customer",
            to_columns=["CustomerID"],
            cardinality="many_to_one",
            semantic_status="confirmed",
            source="database_fk",
        )


def test_verification_summary_keeps_skips_visible() -> None:
    summary = VerificationSummary(
        status="pass",
        confidence_label="high",
        result_visible=True,
        checks=[
            {
                "type": "historical_plausibility",
                "status": "skip",
                "message": "Baseline storica non disponibile",
                "evidence": {},
            }
        ],
    )

    assert summary.result_visible is True


def test_query_run_validates_contract_then_returns_not_implemented() -> None:
    client = TestClient(app)
    request = {
        "tenant_id": "11111111-1111-4111-8111-111111111111",
        "connection_id": "33333333-3333-4333-8333-333333333333",
        "user_id": "44444444-4444-4444-8444-444444444444",
        "question": "Fatturato 2025 per mese",
        "semantic_layer": {
            "tenant_id": "11111111-1111-4111-8111-111111111111",
            "version_id": "22222222-2222-4222-8222-222222222222",
            "version": 1,
            "status": "active",
            "engine": "sqlserver",
            "tables": [],
            "relationships": [],
            "metrics": [],
            "business_anchors": [],
        },
        "permissions": {
            "can_view_sql": False,
            "can_save_widget": True,
        },
        "execution": {
            "mode": "run",
            "row_limit": 500,
            "timeout_ms": 30000,
        },
    }

    parsed = QueryRequest.model_validate_json(json.dumps(request))
    assert parsed.question == "Fatturato 2025 per mese"

    response = client.post("/query/run", json=request)

    assert response.status_code == 501
    assert "not implemented" in response.json()["detail"]


def test_query_request_rejects_coercion() -> None:
    request = {
        "tenant_id": "11111111-1111-4111-8111-111111111111",
        "connection_id": "33333333-3333-4333-8333-333333333333",
        "user_id": "44444444-4444-4444-8444-444444444444",
        "question": "Fatturato 2025 per mese",
        "semantic_layer": {
            "tenant_id": "11111111-1111-4111-8111-111111111111",
            "version_id": "22222222-2222-4222-8222-222222222222",
            "version": 1,
            "status": "active",
            "engine": "sqlserver",
            "tables": [],
            "relationships": [],
            "metrics": [],
            "business_anchors": [],
        },
        "permissions": {
            "can_view_sql": "false",
            "can_save_widget": True,
        },
        "execution": {
            "mode": "run",
            "row_limit": "500",
            "timeout_ms": 30000,
        },
    }

    with pytest.raises(ValidationError):
        QueryRequest.model_validate_json(json.dumps(request))


def test_query_response_omits_optional_none_fields_for_zod_compatibility() -> None:
    response = QueryResponse(
        query_id=UUID("88888888-8888-4888-8888-888888888888"),
        status="failed",
        result_metadata={"columns": [], "row_count": 0, "truncated": False},
        verification={
            "status": "engine_error",
            "checks": [
                {
                    "type": "dry_run",
                    "status": "engine_error",
                    "message": "Query execution is not implemented.",
                    "evidence": {},
                }
            ],
            "confidence_label": "blocked",
            "result_visible": False,
        },
        sanitized_error="Query execution is not implemented.",
    )

    dumped = response.model_dump(mode="json")

    assert "sql" not in dumped
    assert "chart" not in dumped


def test_driver_execute_readonly_raises_until_implemented() -> None:
    driver = get_driver(Engine.sqlserver)
    connection = ConnectionMetadata(
        tenant_id="11111111-1111-4111-8111-111111111111",
        connection_id="33333333-3333-4333-8333-333333333333",
        engine=Engine.sqlserver,
        host="db.example.com",
        port=1433,
        database_name="Demo",
        secret_ref="gcp-secret-manager://projects/demo/secrets/customer-db",
        tls_required=True,
        tls_server_name=None,
    )

    with pytest.raises(DriverNotImplementedError):
        asyncio.run(driver.execute_readonly(connection, "select 1", 100, 30000))
