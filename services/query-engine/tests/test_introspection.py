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
    SchemaCheckConstraintMetadata,
    SchemaDefaultConstraintMetadata,
    SchemaForeignKeyMetadata,
    SchemaIndexColumnMetadata,
    SchemaIndexMetadata,
    SchemaIntrospectionResult,
    SchemaPrimaryKeyMetadata,
    SchemaTableMetadata,
    SchemaUniqueConstraintMetadata,
    SchemaViewLineageDependency,
)
from app.drivers.sqlserver import (
    SQLSERVER_COLUMNS_QUERY,
    SqlServerDriver,
    _build_coverage_warnings,
    _fetch_view_lineage,
    _schema_hash,
)
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
                    },
                    {
                        "name": "FirstName",
                        "data_type": "nvarchar",
                        "declared_type": "Name",
                        "ordinal_position": 2,
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
    assert dumped["tables"][0]["columns"][1]["declared_type"] == "Name"


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
                database_name="AdventureWorksLT",
                engine_version="12.0.2000.8",
                schema_hash="a" * 64,
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
                coverage_warnings=[],
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
            self.params = ()

        def execute(self, query: str, params=()):
            self.query = query
            self.params = params
            executed_queries.append(query)
            return self

        def fetchall(self):
            if "serverproperty('ProductVersion')" in self.query:
                return [("AdventureWorksLT", "12.0.2000.8")]
            if "sys.dm_db_partition_stats" in self.query:
                raise fake_pyodbc.Error("row counts unavailable")
            if "sys.dm_sql_referenced_entities" in self.query:
                assert self.params == ("[SalesLT].[vCustomer]",)
                return [
                    (
                        0,
                        None,
                        None,
                        "SalesLT",
                        "Customer",
                        None,
                        1001,
                        0,
                        "OBJECT_OR_COLUMN",
                        1,
                        0,
                        0,
                        1,
                        0,
                        0,
                        0,
                    ),
                    (
                        1,
                        None,
                        None,
                        "SalesLT",
                        "Customer",
                        "CustomerID",
                        1001,
                        1,
                        "OBJECT_OR_COLUMN",
                        1,
                        0,
                        0,
                        1,
                        0,
                        0,
                        0,
                    ),
                ]
            if "sys.check_constraints" in self.query:
                return [
                    (
                        "SalesLT",
                        "SalesOrderHeader",
                        "CK_Order_TotalDue",
                        "([TotalDue]>=(0))",
                        0,
                        0,
                    )
                ]
            if "sys.indexes" in self.query:
                return [
                    (
                        "SalesLT",
                        "Customer",
                        "IX_Customer_Email",
                        1,
                        0,
                        "NONCLUSTERED",
                        "EmailAddress",
                        1,
                        1,
                        0,
                        0,
                        None,
                        0,
                    ),
                    (
                        "SalesLT",
                        "Customer",
                        "IX_Customer_Email",
                        1,
                        0,
                        "NONCLUSTERED",
                        "Phone",
                        0,
                        2,
                        0,
                        1,
                        None,
                        0,
                    ),
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
                        0,
                        0,
                    )
                ]
            if "sys.key_constraints" in self.query:
                return [
                    ("SalesLT", "Customer", "PK_Customer", "PK", "CustomerID", 1),
                    (
                        "SalesLT",
                        "Customer",
                        "UQ_Customer_Email",
                        "UQ",
                        "EmailAddress",
                        1,
                    ),
                    (
                        "SalesLT",
                        "SalesOrderHeader",
                        "PK_SalesOrderHeader",
                        "PK",
                        "SalesOrderID",
                        1,
                    ),
                ]
            if "sys.columns" in self.query:
                return [
                    (
                        "SalesLT",
                        "Customer",
                        "CustomerID",
                        1,
                        "int",
                        "int",
                        0,
                        None,
                        10,
                        0,
                        None,
                        None,
                        1,
                        0,
                        "1",
                        "1",
                        None,
                        None,
                        None,
                        None,
                    ),
                    (
                        "SalesLT",
                        "Customer",
                        "FirstName",
                        2,
                        "nvarchar",
                        "Name",
                        0,
                        50,
                        0,
                        0,
                        None,
                        "SQL_Latin1_General_CP1_CI_AS",
                        0,
                        0,
                        None,
                        None,
                        None,
                        None,
                        None,
                        "Customer first name",
                        0,
                        "SalesLT",
                        "Name",
                        1,
                        0,
                        257,
                        231,
                    ),
                    (
                        "SalesLT",
                        "Customer",
                        "EmailAddress",
                        4,
                        "nvarchar",
                        "nvarchar",
                        1,
                        50,
                        0,
                        0,
                        None,
                        "SQL_Latin1_General_CP1_CI_AS",
                        0,
                        0,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ),
                    (
                        "SalesLT",
                        "Customer",
                        "MiddleName",
                        3,
                        "nvarchar",
                        None,
                        1,
                        50,
                        0,
                        0,
                        None,
                        "SQL_Latin1_General_CP1_CI_AS",
                        0,
                        0,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        1,
                    ),
                    (
                        "SalesLT",
                        "SalesOrderHeader",
                        "SalesOrderID",
                        1,
                        "int",
                        "int",
                        0,
                        None,
                        10,
                        0,
                        None,
                        None,
                        1,
                        0,
                        "1",
                        "1",
                        None,
                        None,
                        None,
                        None,
                    ),
                    (
                        "SalesLT",
                        "SalesOrderHeader",
                        "CustomerID",
                        2,
                        "int",
                        "int",
                        0,
                        None,
                        10,
                        0,
                        None,
                        None,
                        0,
                        0,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ),
                    (
                        "SalesLT",
                        "vCustomer",
                        "CustomerID",
                        1,
                        "int",
                        "int",
                        0,
                        None,
                        10,
                        0,
                        None,
                        None,
                        0,
                        0,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ),
                ]
            if "sys.objects" in self.query and "sys.sql_modules" in self.query:
                return [
                    ("SalesLT", "Customer", "base_table", 1001, 0, None, None),
                    ("SalesLT", "SalesOrderHeader", "base_table", 1002, 0, None, None),
                    ("SalesLT", "vCustomer", "view", 1003, 0, None, "select CustomerID from SalesLT.Customer"),
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
    assert len(executed_queries) == 9
    assert all("sys." in query or "serverproperty" in query for query in executed_queries)
    assert all("select *" not in query.lower() for query in executed_queries)
    assert all("count(*)" not in query.lower() for query in executed_queries)
    assert result.engine == Engine.sqlserver
    assert result.database_name == "AdventureWorksLT"
    assert result.engine_version == "12.0.2000.8"
    assert len(result.schema_hash) == 64
    assert result.tables[0].name == "Customer"
    assert result.tables[0].primary_key is not None
    assert result.tables[0].primary_key.columns == ["CustomerID"]
    customer_columns = {column.name: column for column in result.tables[0].columns}
    assert customer_columns["FirstName"].data_type == "nvarchar"
    assert customer_columns["FirstName"].declared_type == "Name"
    assert customer_columns["FirstName"].declared_type_schema == "SalesLT"
    assert customer_columns["FirstName"].declared_type_name == "Name"
    assert customer_columns["FirstName"].declared_type_is_user_defined is True
    assert customer_columns["MiddleName"].data_type == "nvarchar"
    assert customer_columns["MiddleName"].declared_type is None
    assert customer_columns["EmailAddress"].is_unique_member is True
    assert result.tables[1].columns[1].name == "CustomerID"
    assert result.foreign_keys[0].from_table == "SalesOrderHeader"
    assert result.foreign_keys[0].to_table == "Customer"
    assert result.foreign_keys[0].source == "db_fk"
    assert result.unique_constraints[0].name == "UQ_Customer_Email"
    assert result.indexes[0].included_columns[0].name == "Phone"
    assert result.check_constraints[0].definition == "([TotalDue]>=(0))"
    view_table = next(table for table in result.tables if table.name == "vCustomer")
    assert view_table.lineage_available is True
    assert len(view_table.view_lineage) == 2
    assert view_table.view_lineage[1].source == "dm_sql_referenced_entities"
    assert view_table.view_lineage[1].referencing_column == "CustomerID"
    assert view_table.view_lineage[1].referenced_schema_name == "SalesLT"
    assert view_table.view_lineage[1].referenced_entity_name == "Customer"
    assert view_table.view_lineage[1].referenced_column_name == "CustomerID"
    assert result.coverage_warnings[0].code == "ROW_COUNT_ESTIMATE_UNAVAILABLE"
    assert any(
        warning.code == "COLUMN_DECLARED_TYPE_UNAVAILABLE"
        and warning.object_schema == "SalesLT"
        and warning.object_name == "Customer"
        for warning in result.coverage_warnings
    )


def test_sqlserver_columns_query_keeps_alias_type_columns() -> None:
    normalized_query = " ".join(SQLSERVER_COLUMNS_QUERY.lower().split())

    assert "left join sys.types as user_type" in normalized_query
    assert "outer apply" in normalized_query
    assert "type_name(column_item.system_type_id)" in normalized_query
    assert "type_name(column_item.user_type_id)" in normalized_query
    assert "base_type.is_user_defined = 0" in normalized_query
    assert "as declared_type_unavailable" in normalized_query


def test_sqlserver_view_lineage_falls_back_when_dmf_permission_denied() -> None:
    class FakeCursor:
        def __init__(self):
            self.query = ""

        def execute(self, query: str, params=()):
            self.query = query
            if "sys.dm_sql_referenced_entities" in query:
                raise PermissionError("VIEW DEFINITION permission was denied")
            return self

        def fetchall(self):
            if "sys.sql_expression_dependencies" in self.query:
                return [
                    (
                        1,
                        None,
                        None,
                        "SalesLT",
                        "Customer",
                        1001,
                        1,
                        "OBJECT_OR_COLUMN",
                        0,
                        0,
                        0,
                    )
                ]
            raise AssertionError(f"Unexpected query: {self.query}")

        def close(self) -> None:
            return None

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

    lineage_by_view, status_by_view = asyncio.run(
        _fetch_view_lineage(
            sql_connection=FakeConnection(),
            object_rows=[("SalesLT", "vLimited", "view", 1003)],
            column_rows=[("SalesLT", "vLimited", "CustomerID", 1)],
            error_type=PermissionError,
        )
    )

    key = ("SalesLT", "vLimited")
    assert status_by_view[key].available is True
    assert status_by_view[key].partial is True
    assert status_by_view[key].permission_denied is True
    assert lineage_by_view[key][0].source == "sql_expression_dependencies"
    assert lineage_by_view[key][0].referencing_column == "CustomerID"
    assert lineage_by_view[key][0].referenced_entity_name == "Customer"

    warnings = _build_coverage_warnings(
        tables=[
            SchemaTableMetadata(
                table_schema="SalesLT",
                name="vLimited",
                table_type="view",
                columns=[],
                view_definition_available=True,
                lineage_available=True,
                view_lineage=lineage_by_view[key],
            )
        ],
        foreign_keys=[
            SchemaForeignKeyMetadata(
                name="FK_Dummy",
                from_schema="SalesLT",
                from_table="Child",
                from_columns=["CustomerID"],
                to_schema="SalesLT",
                to_table="Customer",
                to_columns=["CustomerID"],
                on_delete="no_action",
                on_update="no_action",
            )
        ],
        indexes_available=True,
        row_counts_available=True,
        view_lineage_status_by_view=status_by_view,
    )
    warning_codes = {warning.code for warning in warnings}
    assert "VIEW_LINEAGE_PARTIAL" in warning_codes
    assert "VIEW_LINEAGE_PERMISSION_DENIED" in warning_codes


def test_sqlserver_schema_hash_ignores_unstable_object_id_and_row_count() -> None:
    base_table = SchemaTableMetadata(
        table_schema="dbo",
        name="Synthetic",
        table_type="base_table",
        object_id=100,
        row_count_estimate=10,
        columns=[
            SchemaColumnMetadata(
                name="SyntheticID",
                data_type="int",
                native_type="int",
                normalized_type="int",
                ordinal_position=1,
                is_nullable=False,
                is_identity=True,
                identity_seed="1",
                identity_increment="1",
                is_primary_key=True,
            ),
            SchemaColumnMetadata(
                name="Total",
                data_type="decimal",
                native_type="decimal",
                normalized_type="decimal",
                ordinal_position=2,
                is_nullable=False,
                numeric_precision=18,
                numeric_scale=2,
                default_value="((0))",
            ),
            SchemaColumnMetadata(
                name="TotalWithTax",
                data_type="decimal",
                native_type="decimal",
                normalized_type="decimal",
                ordinal_position=3,
                is_nullable=True,
                numeric_precision=18,
                numeric_scale=2,
                is_computed=True,
                computed_expression="([Total]*(1.22))",
            ),
        ],
        primary_key=SchemaPrimaryKeyMetadata(name="PK_Synthetic", columns=["SyntheticID"]),
    )
    recreated_table = SchemaTableMetadata(
        **{
            **base_table.__dict__,
            "object_id": 200,
            "row_count_estimate": 999,
        }
    )
    unique_constraints = [
        SchemaUniqueConstraintMetadata(
            name="UQ_Synthetic_Total",
            schema_name="dbo",
            table_name="Synthetic",
            columns=["Total"],
        )
    ]
    indexes = [
        SchemaIndexMetadata(
            name="IX_Synthetic_Total",
            schema_name="dbo",
            table_name="Synthetic",
            is_unique=True,
            is_primary_key=False,
            index_type="nonclustered",
            key_columns=[
                SchemaIndexColumnMetadata(
                    name="Total",
                    ordinal_position=1,
                    is_descending=True,
                )
            ],
            included_columns=[
                SchemaIndexColumnMetadata(
                    name="TotalWithTax",
                    ordinal_position=2,
                    is_descending=False,
                    is_included=True,
                )
            ],
            filter_definition="([Total]>(0))",
        )
    ]
    check_constraints = [
        SchemaCheckConstraintMetadata(
            name="CK_Synthetic_Total",
            schema_name="dbo",
            table_name="Synthetic",
            definition="([Total]>=(0))",
        )
    ]
    default_constraints = [
        SchemaDefaultConstraintMetadata(
            name="DF_Synthetic_Total",
            schema_name="dbo",
            table_name="Synthetic",
            column_name="Total",
            definition="((0))",
        )
    ]

    first_hash = _schema_hash(
        tables=[base_table],
        foreign_keys=[],
        unique_constraints=unique_constraints,
        check_constraints=check_constraints,
        default_constraints=default_constraints,
        indexes=indexes,
    )
    second_hash = _schema_hash(
        tables=[recreated_table],
        foreign_keys=[],
        unique_constraints=unique_constraints,
        check_constraints=check_constraints,
        default_constraints=default_constraints,
        indexes=indexes,
    )

    assert first_hash == second_hash


def test_sqlserver_schema_hash_canonicalizes_view_lineage_order() -> None:
    first_dependency = SchemaViewLineageDependency(
        source="dm_sql_referenced_entities",
        referencing_column="CustomerID",
        referenced_server_name="linked-a",
        referenced_database_name="AdventureWorksLT",
        referenced_schema_name="SalesLT",
        referenced_entity_name="Customer",
        referenced_column_name="CustomerID",
        referenced_class="OBJECT_OR_COLUMN",
        is_selected=True,
        is_updated=False,
        is_select_all=False,
        is_all_columns_found=True,
        is_caller_dependent=False,
        is_ambiguous=False,
        is_incomplete=False,
    )
    second_dependency = SchemaViewLineageDependency(
        source="dm_sql_referenced_entities",
        referencing_column="CustomerID",
        referenced_server_name="linked-b",
        referenced_database_name="AdventureWorksLT",
        referenced_schema_name="SalesLT",
        referenced_entity_name="Customer",
        referenced_column_name="CustomerID",
        referenced_class="OBJECT_OR_COLUMN",
        is_selected=True,
        is_updated=False,
        is_select_all=False,
        is_all_columns_found=True,
        is_caller_dependent=False,
        is_ambiguous=False,
        is_incomplete=False,
    )
    base_view = SchemaTableMetadata(
        table_schema="SalesLT",
        name="vCustomer",
        table_type="view",
        columns=[
            SchemaColumnMetadata(
                name="CustomerID",
                data_type="int",
                ordinal_position=1,
                is_nullable=False,
            )
        ],
        view_lineage=[first_dependency, second_dependency],
    )
    reversed_view = SchemaTableMetadata(
        **{
            **base_view.__dict__,
            "view_lineage": [second_dependency, first_dependency],
        }
    )

    first_hash = _schema_hash(
        tables=[base_view],
        foreign_keys=[],
        unique_constraints=[],
        check_constraints=[],
        default_constraints=[],
        indexes=[],
    )
    second_hash = _schema_hash(
        tables=[reversed_view],
        foreign_keys=[],
        unique_constraints=[],
        check_constraints=[],
        default_constraints=[],
        indexes=[],
    )

    assert first_hash == second_hash
