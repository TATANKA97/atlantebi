import asyncio
import os

import pytest

from app.drivers.base import ConnectionMetadata, DatabaseCredentials
from app.drivers.sqlserver import SqlServerDriver
from app.models import Engine


pytestmark = pytest.mark.skipif(
    not os.getenv("SQLSERVER_INTEGRATION_HOST"),
    reason="SQL Server integration fixture is not running.",
)


def test_sqlserver_snapshot_v1_against_real_catalog_views() -> None:
    connection = ConnectionMetadata(
        tenant_id="11111111-1111-4111-8111-111111111111",
        connection_id="33333333-3333-4333-8333-333333333333",
        name="SQL Server integration fixture",
        engine=Engine.sqlserver,
        network_mode="public_allowlist",
        host=os.environ["SQLSERVER_INTEGRATION_HOST"],
        port=1433,
        database_name="AtlanteBiSnapshotTest",
        username="atlante_snapshot_ro",
        secret_ref="gcp-secret-manager://projects/demo/secrets/integration",
        tls_required=False,
        trust_server_certificate=True,
        tls_server_name=None,
    )

    result = asyncio.run(
        SqlServerDriver().introspect_schema(
            connection,
            DatabaseCredentials(password="Fixture-Only-Password-42!"),
            30000,
        )
    )

    tables = {(table.table_schema, table.name): table for table in result.tables}
    assert ("fixture", "ParentEntity") in tables
    assert ("fixture", "ChildEntity") in tables
    assert ("fixture", "vActiveChild") in tables

    parent = tables[("fixture", "ParentEntity")]
    child = tables[("fixture", "ChildEntity")]
    view = tables[("fixture", "vActiveChild")]

    assert parent.primary_key is not None
    assert parent.primary_key.columns == ["TenantCode", "EntityCode"]
    assert next(
        column for column in parent.columns if column.name == "NormalizedName"
    ).is_computed
    assert next(column for column in child.columns if column.name == "ChildId").is_identity
    assert view.view_definition_available is True
    assert view.lineage_available is True

    foreign_key = next(
        foreign_key
        for foreign_key in result.foreign_keys
        if foreign_key.name == "FK_ChildEntity_ParentEntity"
    )
    assert foreign_key.from_columns == ["TenantCode", "EntityCode"]
    assert foreign_key.to_columns == ["TenantCode", "EntityCode"]
    assert foreign_key.on_update == "cascade"
    assert foreign_key.on_delete == "cascade"

    assert any(
        constraint.name == "UQ_ParentEntity_DisplayName"
        for constraint in result.unique_constraints
    )
    assert any(
        constraint.name == "CK_ParentEntity_TenantCode"
        for constraint in result.check_constraints
    )
    assert any(
        constraint.name == "DF_ChildEntity_IsActive"
        for constraint in result.default_constraints
    )
    unique_index = next(
        index
        for index in result.indexes
        if index.name == "UX_ChildEntity_ExternalCode"
    )
    assert unique_index.is_unique is True
    assert [column.name for column in unique_index.key_columns] == [
        "TenantCode",
        "ExternalCode",
    ]
    assert [column.name for column in unique_index.included_columns] == ["EntityCode"]
    assert unique_index.filter_definition is not None
    assert len(result.schema_hash) == 64
