import asyncio
import json
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main as main_module
from app.drivers.base import (
    ConnectionMetadata,
    DatabaseCredentials,
    DatabaseDriver,
    ReadonlyQueryResult,
    SchemaColumnMetadata,
    SchemaForeignKeyMetadata,
    SchemaIntrospectionResult,
    SchemaPrimaryKeyMetadata,
    SchemaTableMetadata,
)
from app.drivers.sqlserver import SqlServerDriver
from app.main import app
from app.models import Engine, SchemaIntrospectionRequest, SchemaIntrospectionResponse


def _sqlserver_connection() -> ConnectionMetadata:
    return ConnectionMetadata(
        tenant_id="11111111-1111-4111-8111-111111111111",
        connection_id="33333333-3333-4333-8333-333333333333",
        name="SQL Server demo",
        engine=Engine.sqlserver,
        network_mode="public_allowlist",
        host="sql.example.com",
        port=1433,
        database_name="AdventureWorksLT",
        username="readonly_user",
        secret_ref="gcp-secret-manager://projects/demo/secrets/customer-db",
        tls_required=True,
        trust_server_certificate=False,
        tls_server_name=None,
    )


def test_schema_introspection_request_rejects_coercion() -> None:
    payload = {
        "connection": {
            "tenant_id": "11111111-1111-4111-8111-111111111111",
            "connection_id": "33333333-3333-4333-8333-333333333333",
            "name": "SQL Server demo",
            "engine": "sqlserver",
            "network_mode": "public_allowlist",
            "host": "sql.example.com",
            "port": "1433",
            "database_name": "AdventureWorksLT",
            "username": "readonly_user",
            "tls_required": "true",
            "trust_server_certificate": False,
            "secret_ref": "gcp-secret-manager://projects/demo/secrets/customer-db",
            "status": "ready",
        },
        "timeout_ms": "30000",
    }

    with pytest.raises(ValidationError):
        SchemaIntrospectionRequest.model_validate_json(json.dumps(payload))


def test_schema_introspection_response_serializes_schema_alias() -> None:
    response = SchemaIntrospectionResponse(
        status="ok",
        message="Schema introspection completed.",
        introspected_at="2026-06-04T10:00:00+00:00",
        duration_ms=12,
        engine="sqlserver",
        tables=[
            {
                "table_schema": "SalesLT",
                "name": "Customer",
                "table_type": "base_table",
                "columns": [
                    {
                        "name": "CustomerID",
                        "data_type": "int",
                        "ordinal_position": 1,
                        "is_nullable": False,
                    }
                ],
                "primary_key": {
                    "name": "PK_Customer",
                    "columns": ["CustomerID"],
                },
            }
        ],
        foreign_keys=[],
    )

    dumped = response.model_dump(mode="json")

    assert dumped["tables"][0]["schema"] == "SalesLT"
    assert "table_schema" not in dumped["tables"][0]


def test_schema_introspection_endpoint_uses_secret_resolver_and_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSecretResolver:
        async def resolve_database_credentials(self, secret_ref: str) -> DatabaseCredentials:
            assert secret_ref == "gcp-secret-manager://projects/demo/secrets/customer-db"
            return DatabaseCredentials(password="secret")

    class FakeDriver(DatabaseDriver):
        engine = Engine.sqlserver

        async def test_connection(
            self,
            connection: ConnectionMetadata,
            credentials: DatabaseCredentials,
            timeout_ms: int,
        ):
            raise NotImplementedError

        async def introspect_schema(
            self,
            connection: ConnectionMetadata,
            credentials: DatabaseCredentials,
            timeout_ms: int,
        ) -> SchemaIntrospectionResult:
            assert connection.database_name == "AdventureWorksLT"
            assert credentials.password == "secret"
            assert timeout_ms == 30000
            return SchemaIntrospectionResult(
                engine=Engine.sqlserver,
                tables=[
                    SchemaTableMetadata(
                        table_schema="SalesLT",
                        name="Customer",
                        table_type="base_table",
                        columns=[
                            SchemaColumnMetadata(
                                name="CustomerID",
                                data_type="int",
                                ordinal_position=1,
                                is_nullable=False,
                                is_identity=True,
                            )
                        ],
                        primary_key=SchemaPrimaryKeyMetadata(
                            name="PK_Customer",
                            columns=["CustomerID"],
                        ),
                    )
                ],
                foreign_keys=[
                    SchemaForeignKeyMetadata(
                        name="FK_Order_Customer",
                        from_schema="SalesLT",
                        from_table="SalesOrderHeader",
                        from_columns=["CustomerID"],
                        to_schema="SalesLT",
                        to_table="Customer",
                        to_columns=["CustomerID"],
                        on_delete="no_action",
                        on_update="no_action",
                    )
                ],
            )

        async def execute_readonly(
            self,
            connection: ConnectionMetadata,
            sql: str,
            row_limit: int,
            timeout_ms: int,
        ) -> ReadonlyQueryResult:
            raise NotImplementedError

    monkeypatch.setattr(app.state, "secret_resolver", FakeSecretResolver())
    monkeypatch.setattr(main_module, "get_driver", lambda engine: FakeDriver())
    client = TestClient(app)

    response = client.post(
        "/schema/introspect",
        json={
            "connection": {
                "tenant_id": "11111111-1111-4111-8111-111111111111",
                "connection_id": "33333333-3333-4333-8333-333333333333",
                "name": "SQL Server demo",
                "engine": "sqlserver",
                "network_mode": "public_allowlist",
                "host": "sql.example.com",
                "port": 1433,
                "database_name": "AdventureWorksLT",
                "username": "readonly_user",
                "tls_required": True,
                "trust_server_certificate": False,
                "secret_ref": "gcp-secret-manager://projects/demo/secrets/customer-db",
                "status": "ready",
            },
            "timeout_ms": 30000,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["engine"] == "sqlserver"
    assert body["tables"][0]["schema"] == "SalesLT"
    assert body["tables"][0]["primary_key"]["columns"] == ["CustomerID"]
    assert body["foreign_keys"][0]["from_columns"] == ["CustomerID"]
    assert "sanitized_error" not in body


def test_sqlserver_driver_reads_only_metadata_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    executed_queries: list[str] = []

    class FakeCursor:
        def __init__(self):
            self.query = ""

        def execute(self, query: str):
            self.query = query
            executed_queries.append(query)
            return self

        def fetchall(self):
            if "INFORMATION_SCHEMA.COLUMNS" in self.query:
                return [
                    ("SalesLT", "Customer", "CustomerID", 1, "int", "NO", None, 10, 0, None, 1, 0),
                    (
                        "SalesLT",
                        "SalesOrderHeader",
                        "SalesOrderID",
                        1,
                        "int",
                        "NO",
                        None,
                        10,
                        0,
                        None,
                        1,
                        0,
                    ),
                    (
                        "SalesLT",
                        "SalesOrderHeader",
                        "CustomerID",
                        2,
                        "int",
                        "NO",
                        None,
                        10,
                        0,
                        None,
                        0,
                        0,
                    ),
                ]
            if "INFORMATION_SCHEMA.TABLE_CONSTRAINTS" in self.query:
                return [
                    ("SalesLT", "Customer", "PK_Customer", "CustomerID", 1),
                    ("SalesLT", "SalesOrderHeader", "PK_SalesOrderHeader", "SalesOrderID", 1),
                ]
            if "INFORMATION_SCHEMA.TABLES" in self.query and "TABLE_TYPE" in self.query:
                return [
                    ("SalesLT", "Customer", "BASE TABLE"),
                    ("SalesLT", "SalesOrderHeader", "BASE TABLE"),
                ]
            if "sys.foreign_keys" in self.query:
                return [
                    (
                        "FK_SalesOrderHeader_Customer",
                        "SalesLT",
                        "SalesOrderHeader",
                        "CustomerID",
                        "SalesLT",
                        "Customer",
                        "CustomerID",
                        1,
                        "NO_ACTION",
                        "NO_ACTION",
                    )
                ]
            raise AssertionError(f"Unexpected query: {self.query}")

        def close(self) -> None:
            return None

    class FakeConnection:
        def __init__(self):
            self.connection_string = None

        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def close(self) -> None:
            return None

    fake_connection = FakeConnection()

    def fake_connect(connection_string: str, autocommit: bool, timeout: int):
        fake_connection.connection_string = connection_string
        assert autocommit is True
        assert timeout == 30
        return fake_connection

    fake_pyodbc = SimpleNamespace(connect=fake_connect, Error=Exception)
    monkeypatch.setitem(sys.modules, "pyodbc", fake_pyodbc)

    result = asyncio.run(
        SqlServerDriver().introspect_schema(
            _sqlserver_connection(),
            DatabaseCredentials(password="secret"),
            30000,
        )
    )

    assert fake_connection.connection_string is not None
    assert "PWD=secret" in fake_connection.connection_string
    assert len(executed_queries) == 4
    assert all("INFORMATION_SCHEMA" in query or "sys." in query for query in executed_queries)
    assert all("select *" not in query.lower() for query in executed_queries)
    assert result.engine == Engine.sqlserver
    assert result.tables[0].name == "Customer"
    assert result.tables[0].primary_key is not None
    assert result.tables[0].primary_key.columns == ["CustomerID"]
    assert result.tables[1].columns[1].name == "CustomerID"
    assert result.foreign_keys[0].from_table == "SalesOrderHeader"
    assert result.foreign_keys[0].to_table == "Customer"
