import asyncio
import os
from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from app.drivers.base import ConnectionMetadata, DatabaseCredentials
from app.drivers.sqlserver import SqlServerDriver
from app.models import Engine, SchemaIntrospectionResponse
from app.queryability import build_queryability_graph, find_queryability_paths


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
        network_mode="vpn",
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
    assert ("fixture", "vIndexedChild") in tables

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
        if foreign_key.constraint_name == "FK_ChildEntity_ParentEntity"
    )
    assert foreign_key.from_columns == ["TenantCode", "EntityCode"]
    assert foreign_key.to_columns == ["TenantCode", "EntityCode"]
    assert foreign_key.update_rule == "cascade"
    assert foreign_key.delete_rule == "cascade"

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
    assert unique_index.object_type == "table"
    assert [column.name for column in unique_index.key_columns] == [
        "TenantCode",
        "ExternalCode",
    ]
    assert [column.name for column in unique_index.included_columns] == ["EntityCode"]
    assert unique_index.filter_definition is not None
    indexed_view_index = next(
        index
        for index in result.indexes
        if index.name == "CUX_vIndexedChild_ChildId"
    )
    assert indexed_view_index.object_type == "view"
    assert indexed_view_index.is_unique is True
    assert indexed_view_index.index_type == "clustered"
    assert len(result.schema_hash) == 64

    snapshot = SchemaIntrospectionResponse(
        status="ok",
        message="Schema introspection completed.",
        introspected_at=datetime.now(UTC).isoformat(),
        duration_ms=0,
        engine=result.engine,
        database_name=result.database_name,
        engine_version=result.engine_version,
        schema_hash=result.schema_hash,
        snapshot_hash=result.snapshot_hash,
        coverage_status=result.coverage_status,
        tables=[asdict(table) for table in result.tables],
        foreign_keys=[asdict(item) for item in result.foreign_keys],
        unique_constraints=[asdict(item) for item in result.unique_constraints],
        check_constraints=[asdict(item) for item in result.check_constraints],
        default_constraints=[asdict(item) for item in result.default_constraints],
        indexes=[asdict(item) for item in result.indexes],
        coverage_warnings=[asdict(item) for item in result.coverage_warnings],
    )
    graph = build_queryability_graph(
        snapshot=snapshot,
        tenant_id="11111111-1111-4111-8111-111111111111",
        connection_id="33333333-3333-4333-8333-333333333333",
        schema_snapshot_id="44444444-4444-4444-8444-444444444444",
    )

    graph_nodes = {
        (node.schema_name, node.object_name): node for node in graph.nodes
    }
    assert len(graph_nodes) == 4
    child_node = graph_nodes[("fixture", "ChildEntity")]
    parent_node = graph_nodes[("fixture", "ParentEntity")]
    fk_edge = next(
        edge
        for edge in graph.edges
        if edge.edge_type == "fk_join"
        and edge.constraint_name == "FK_ChildEntity_ParentEntity"
    )
    assert fk_edge.automatic_join_allowed is True
    assert fk_edge.validation_status == "trusted"
    assert len(fk_edge.column_pairs) == 2

    path = find_queryability_paths(
        graph=graph,
        from_node_key=child_node.node_key,
        to_node_key=parent_node.node_key,
        max_hops=4,
    )
    assert path.status == "found"
    assert len(path.paths) == 1
    assert [step.edge_key for step in path.paths[0].steps] == [fk_edge.edge_key]
