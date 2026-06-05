import json
import asyncio
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main as main_module
from app.drivers.base import (
    ConnectionMetadata,
    ConnectionTestResult,
    DatabaseCredentials,
    DatabaseDriver,
    DriverNotImplementedError,
    ReadonlyQueryResult,
    SchemaIntrospectionResult,
)
from app.drivers.registry import DRIVER_REGISTRY, get_driver
from app.drivers.sqlserver import _connection_string_parts, _login_username
from app.main import app
from app.models import (
    ConnectionTestRequest,
    Engine,
    QueryRequest,
    QueryResponse,
    Relationship,
    VerificationSummary,
)
from app.secrets import SecretResolutionError, parse_secret_ref


@pytest.fixture(autouse=True)
def allow_unauthenticated_test_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUERY_ENGINE_ALLOW_UNAUTHENTICATED", "true")


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


def test_secret_ref_parser_targets_gcp_secret_manager() -> None:
    parsed = parse_secret_ref(
        "gcp-secret-manager://projects/atlantebi/secrets/demo-password"
    )

    assert parsed.resource_name == "projects/atlantebi/secrets/demo-password/versions/latest"

    with pytest.raises(SecretResolutionError):
        parse_secret_ref("postgres://readonly:password@example.com/db")


def test_connection_test_request_rejects_coercion() -> None:
    payload = {
        "connection": {
            "tenant_id": "11111111-1111-4111-8111-111111111111",
            "connection_id": "33333333-3333-4333-8333-333333333333",
            "name": "MySQL demo",
            "engine": "mysql",
            "network_mode": "public_allowlist",
            "host": "mysql.example.com",
            "port": "3306",
            "database_name": "demo",
            "username": "readonly_user",
            "tls_required": "true",
            "secret_ref": "gcp-secret-manager://projects/demo/secrets/customer-db",
            "status": "draft",
        },
        "timeout_ms": "30000",
    }

    with pytest.raises(ValidationError):
        ConnectionTestRequest.model_validate_json(json.dumps(payload))


def test_shared_nullable_tls_fixture_matches_typescript_contract() -> None:
    fixture_path = (
        Path(__file__).parents[3]
        / "packages"
        / "contracts"
        / "src"
        / "fixtures"
        / "connection-null-tls.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    parsed = ConnectionTestRequest.model_validate(
        {"connection": payload, "timeout_ms": 30000}
    )

    assert parsed.connection.tls_server_name is None


def test_connection_test_endpoint_uses_secret_resolver_and_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSecretResolver:
        async def resolve_database_credentials(
            self, secret_ref: str, timeout_ms: int
        ) -> DatabaseCredentials:
            assert secret_ref == "gcp-secret-manager://projects/demo/secrets/customer-db"
            assert timeout_ms == 30000
            return DatabaseCredentials(password="secret")

    class FakeDriver(DatabaseDriver):
        engine = Engine.mysql

        async def test_connection(
            self,
            connection: ConnectionMetadata,
            credentials: DatabaseCredentials,
            timeout_ms: int,
        ) -> ConnectionTestResult:
            assert connection.username == "readonly_user"
            assert credentials.password == "secret"
            assert 29000 <= timeout_ms <= 30000
            return ConnectionTestResult(status="ok", message="MySQL connection verified.")

        async def introspect_schema(
            self,
            connection: ConnectionMetadata,
            credentials: DatabaseCredentials,
            timeout_ms: int,
        ) -> SchemaIntrospectionResult:
            raise DriverNotImplementedError("not implemented")

        async def execute_readonly(
            self,
            connection: ConnectionMetadata,
            sql: str,
            row_limit: int,
            timeout_ms: int,
        ) -> ReadonlyQueryResult:
            raise DriverNotImplementedError("not implemented")

    client = TestClient(app)
    monkeypatch.setattr(app.state, "secret_resolver", FakeSecretResolver())
    monkeypatch.setattr(main_module, "get_driver", lambda engine: FakeDriver())

    response = client.post(
        "/connections/test",
        json={
            "connection": {
                "tenant_id": "11111111-1111-4111-8111-111111111111",
                "connection_id": "33333333-3333-4333-8333-333333333333",
                "name": "MySQL demo",
                "engine": "mysql",
                "network_mode": "public_allowlist",
                "host": "mysql.example.com",
                "port": 3306,
                "database_name": "demo",
                "username": "readonly_user",
                "tls_required": True,
                "trust_server_certificate": False,
                "secret_ref": "gcp-secret-manager://projects/demo/secrets/customer-db",
                "status": "draft",
            },
            "timeout_ms": 30000,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "sanitized_error" not in response.json()


def test_connection_test_endpoint_requires_token_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "test-token")
    client = TestClient(app)

    response = client.post(
        "/connections/test",
        json={
            "connection": {
                "tenant_id": "11111111-1111-4111-8111-111111111111",
                "connection_id": "33333333-3333-4333-8333-333333333333",
                "name": "MySQL demo",
                "engine": "mysql",
                "network_mode": "public_allowlist",
                "host": "mysql.example.com",
                "port": 3306,
                "database_name": "demo",
                "username": "readonly_user",
                "tls_required": True,
                "trust_server_certificate": False,
                "secret_ref": "gcp-secret-manager://projects/demo/secrets/customer-db",
                "status": "draft",
            },
            "timeout_ms": 30000,
        },
    )

    assert response.status_code == 401


def test_connection_test_endpoint_fails_closed_without_auth_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QUERY_ENGINE_API_TOKEN", raising=False)
    monkeypatch.delenv("QUERY_ENGINE_ALLOW_UNAUTHENTICATED", raising=False)
    client = TestClient(app)

    response = client.post(
        "/connections/test",
        json={
            "connection": {
                "tenant_id": "11111111-1111-4111-8111-111111111111",
                "connection_id": "33333333-3333-4333-8333-333333333333",
                "name": "SQL Server demo",
                "engine": "sqlserver",
                "network_mode": "public_allowlist",
                "host": "sql.example.com",
                "port": 1433,
                "database_name": "demo",
                "username": "readonly_user",
                "tls_required": True,
                "trust_server_certificate": False,
                "tls_server_name": None,
                "secret_ref": "gcp-secret-manager://projects/demo/secrets/customer-db",
                "status": "draft",
            },
            "timeout_ms": 30000,
        },
    )

    assert response.status_code == 503


def test_connection_test_endpoint_accepts_internal_token_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSecretResolver:
        async def resolve_database_credentials(
            self, secret_ref: str, timeout_ms: int
        ) -> DatabaseCredentials:
            return DatabaseCredentials(password="secret")

    class FakeDriver(DatabaseDriver):
        engine = Engine.mysql

        async def test_connection(
            self,
            connection: ConnectionMetadata,
            credentials: DatabaseCredentials,
            timeout_ms: int,
        ) -> ConnectionTestResult:
            return ConnectionTestResult(status="ok", message="MySQL connection verified.")

        async def introspect_schema(
            self,
            connection: ConnectionMetadata,
            credentials: DatabaseCredentials,
            timeout_ms: int,
        ) -> SchemaIntrospectionResult:
            raise DriverNotImplementedError("not implemented")

        async def execute_readonly(
            self,
            connection: ConnectionMetadata,
            sql: str,
            row_limit: int,
            timeout_ms: int,
        ) -> ReadonlyQueryResult:
            raise DriverNotImplementedError("not implemented")

    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "test-token")
    monkeypatch.setattr(app.state, "secret_resolver", FakeSecretResolver())
    monkeypatch.setattr(main_module, "get_driver", lambda engine: FakeDriver())
    client = TestClient(app)

    response = client.post(
        "/connections/test",
        headers={"x-atlante-query-engine-token": "test-token"},
        json={
            "connection": {
                "tenant_id": "11111111-1111-4111-8111-111111111111",
                "connection_id": "33333333-3333-4333-8333-333333333333",
                "name": "MySQL demo",
                "engine": "mysql",
                "network_mode": "public_allowlist",
                "host": "mysql.example.com",
                "port": 3306,
                "database_name": "demo",
                "username": "readonly_user",
                "tls_required": True,
                "trust_server_certificate": False,
                "secret_ref": "gcp-secret-manager://projects/demo/secrets/customer-db",
                "status": "draft",
            },
            "timeout_ms": 30000,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_sqlserver_proxy_derives_azure_login_server_name() -> None:
    connection = ConnectionMetadata(
        tenant_id="11111111-1111-4111-8111-111111111111",
        connection_id="33333333-3333-4333-8333-333333333333",
        name="Azure SQL proxy test",
        engine=Engine.sqlserver,
        network_mode="public_allowlist",
        host="136.111.143.3",
        port=10002,
        database_name="AdventureWorksLT",
        username="atlante_demo_ro",
        secret_ref="gcp-secret-manager://projects/demo/secrets/customer-db",
        tls_required=True,
        trust_server_certificate=False,
        tls_server_name="atlanteadmin.database.windows.net",
    )

    assert _login_username(connection) == "atlante_demo_ro@atlanteadmin"

    already_qualified = ConnectionMetadata(
        **{**connection.__dict__, "username": "atlante_demo_ro@atlanteadmin"}
    )
    assert _login_username(already_qualified) == "atlante_demo_ro@atlanteadmin"


def test_sqlserver_odbc_values_are_brace_escaped() -> None:
    connection = ConnectionMetadata(
        tenant_id="11111111-1111-4111-8111-111111111111",
        connection_id="33333333-3333-4333-8333-333333333333",
        name="Escaping test",
        engine=Engine.sqlserver,
        network_mode="public_allowlist",
        host="sql.example.com",
        port=1433,
        database_name="demo;Encrypt=no",
        username="readonly}user",
        secret_ref="gcp-secret-manager://projects/demo/secrets/customer-db",
        tls_required=True,
        trust_server_certificate=False,
        tls_server_name=None,
    )

    connection_string = ";".join(
        _connection_string_parts(
            connection,
            DatabaseCredentials(password="secret};UID=attacker"),
            30,
        )
    )

    assert "Database={demo;Encrypt=no}" in connection_string
    assert "UID={readonly}}user}" in connection_string
    assert "PWD={secret}};UID=attacker}" in connection_string


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
        name="Demo",
        engine=Engine.sqlserver,
        network_mode="public_allowlist",
        host="db.example.com",
        port=1433,
        database_name="Demo",
        username="readonly_user",
        secret_ref="gcp-secret-manager://projects/demo/secrets/customer-db",
        tls_required=True,
        trust_server_certificate=False,
        tls_server_name=None,
    )

    with pytest.raises(DriverNotImplementedError):
        asyncio.run(driver.execute_readonly(connection, "select 1", 100, 30000))

    mysql_driver = get_driver(Engine.mysql)
    with pytest.raises(DriverNotImplementedError):
        asyncio.run(
            mysql_driver.introspect_schema(
                connection,
                DatabaseCredentials(password="secret"),
                30000,
            )
        )
