from dataclasses import replace

from app.drivers.base import (
    SchemaColumnMetadata,
    SchemaCoverageWarning,
    SchemaForeignKeyMetadata,
    SchemaIndexColumnMetadata,
    SchemaIndexMetadata,
    SchemaIntrospectionResult,
    SchemaPrimaryKeyMetadata,
    SchemaTableMetadata,
    SchemaUniqueConstraintMetadata,
    SchemaViewLineageDependency,
)
from app.models import Engine, QueryabilityForeignKeyEdge
from app.queryability import (
    build_queryability_graph,
    find_queryability_paths,
)


TENANT_ID = "11111111-1111-4111-8111-111111111111"
CONNECTION_ID = "22222222-2222-4222-8222-222222222222"
SNAPSHOT_ID = "33333333-3333-4333-8333-333333333333"


def column(
    name: str,
    ordinal: int,
    *,
    nullable: bool = False,
    role: str = "identifier",
    native_type: str = "int",
) -> SchemaColumnMetadata:
    return SchemaColumnMetadata(
        name=name,
        data_type=native_type,
        native_type=native_type,
        normalized_type=native_type,
        technical_role=role,
        ordinal_position=ordinal,
        is_nullable=nullable,
    )


def table(
    name: str,
    columns: list[SchemaColumnMetadata],
    *,
    primary_key: list[str] | None = None,
    table_type: str = "base_table",
) -> SchemaTableMetadata:
    return SchemaTableMetadata(
        table_schema="SalesLT",
        name=name,
        table_type=table_type,
        columns=columns,
        primary_key=(
            SchemaPrimaryKeyMetadata(
                name=f"PK_{name}",
                columns=primary_key,
            )
            if primary_key
            else None
        ),
        view_definition_available=True if table_type == "view" else None,
        lineage_available=True if table_type == "view" else None,
    )


def foreign_key(
    name: str,
    from_table: str,
    from_columns: list[str],
    to_table: str,
    to_columns: list[str],
    *,
    disabled: bool = False,
    untrusted: bool = False,
) -> SchemaForeignKeyMetadata:
    return SchemaForeignKeyMetadata(
        constraint_name=name,
        from_schema="SalesLT",
        from_table=from_table,
        from_columns=from_columns,
        to_schema="SalesLT",
        to_table=to_table,
        to_columns=to_columns,
        delete_rule="no_action",
        update_rule="no_action",
        is_disabled=disabled,
        is_not_trusted=untrusted,
    )


def snapshot(
    *,
    tables: list[SchemaTableMetadata],
    foreign_keys: list[SchemaForeignKeyMetadata] | None = None,
    unique_constraints: list[SchemaUniqueConstraintMetadata] | None = None,
    indexes: list[SchemaIndexMetadata] | None = None,
    warnings: list[SchemaCoverageWarning] | None = None,
    coverage_status: str = "ok",
) -> SchemaIntrospectionResult:
    return SchemaIntrospectionResult(
        engine=Engine.sqlserver,
        database_name="AdventureWorksLT",
        engine_version="12.0.2000.8",
        schema_hash="a" * 64,
        snapshot_hash="b" * 64,
        coverage_status=coverage_status,
        tables=tables,
        foreign_keys=foreign_keys or [],
        unique_constraints=unique_constraints or [],
        indexes=indexes or [],
        coverage_warnings=warnings or [],
    )


def build(source: SchemaIntrospectionResult):
    return build_queryability_graph(
        snapshot=source,
        tenant_id=TENANT_ID,
        connection_id=CONNECTION_ID,
        schema_snapshot_id=SNAPSHOT_ID,
    )


def fk_edges(graph):
    return [
        edge
        for edge in graph.edges
        if isinstance(edge, QueryabilityForeignKeyEdge)
    ]


def node_by_name(graph, name: str):
    return next(node for node in graph.nodes if node.object_name == name)


def test_builds_composite_fk_cardinality_and_preserves_pair_order() -> None:
    parent = table(
        "Parent",
        [column("TenantID", 1), column("ParentID", 2)],
        primary_key=["TenantID", "ParentID"],
    )
    child = table(
        "Child",
        [
            column("ChildID", 1),
            column("TenantID", 2),
            column("ParentID", 3, nullable=True),
        ],
        primary_key=["ChildID"],
    )

    graph = build(
        snapshot(
            tables=[child, parent],
            foreign_keys=[
                foreign_key(
                    "FK_Child_Parent",
                    "Child",
                    ["TenantID", "ParentID"],
                    "Parent",
                    ["TenantID", "ParentID"],
                )
            ],
        )
    )

    edge = fk_edges(graph)[0]
    assert edge.relationship_shape == "many_to_one"
    assert edge.nullable_fk is True
    assert edge.child_to_parent == "zero_or_one"
    assert edge.parent_to_child == "zero_or_many"
    assert [
        (pair.ordinal_position, pair.from_column, pair.to_column)
        for pair in edge.column_pairs
    ] == [
        (1, "TenantID", "TenantID"),
        (2, "ParentID", "ParentID"),
    ]


def test_only_global_enabled_unique_keys_prove_one_to_one() -> None:
    parent = table(
        "Parent",
        [column("ParentID", 1)],
        primary_key=["ParentID"],
    )
    child = table(
        "Child",
        [column("ParentID", 1)],
    )
    filtered_index = SchemaIndexMetadata(
        name="UX_Child_Parent_Filtered",
        schema_name="SalesLT",
        table_name="Child",
        object_type="table",
        is_unique=True,
        is_primary_key=False,
        index_type="nonclustered",
        key_columns=[
            SchemaIndexColumnMetadata(
                name="ParentID",
                ordinal_position=1,
                is_descending=False,
            )
        ],
        filter_definition="([ParentID] IS NOT NULL)",
    )
    graph = build(
        snapshot(
            tables=[parent, child],
            foreign_keys=[
                foreign_key(
                    "FK_Child_Parent",
                    "Child",
                    ["ParentID"],
                    "Parent",
                    ["ParentID"],
                )
            ],
            indexes=[filtered_index],
        )
    )

    edge = fk_edges(graph)[0]
    child_node = node_by_name(graph, "Child")
    assert edge.relationship_shape == "many_to_one"
    assert child_node.candidate_keys[0].eligible_for_cardinality is False

    global_index = replace(filtered_index, filter_definition=None)
    global_graph = build(
        snapshot(
            tables=[parent, child],
            foreign_keys=[
                foreign_key(
                    "FK_Child_Parent",
                    "Child",
                    ["ParentID"],
                    "Parent",
                    ["ParentID"],
                )
            ],
            indexes=[global_index],
        )
    )
    global_edge = fk_edges(global_graph)[0]
    assert global_edge.relationship_shape == "one_to_one"
    assert global_edge.parent_to_child == "zero_or_one"


def test_disabled_and_untrusted_fk_are_evidence_only() -> None:
    parent = table(
        "Parent",
        [column("ParentID", 1)],
        primary_key=["ParentID"],
    )
    child = table(
        "Child",
        [
            column("ChildID", 1),
            column("ParentID", 2),
            column("OtherParentID", 3),
        ],
        primary_key=["ChildID"],
    )
    graph = build(
        snapshot(
            tables=[parent, child],
            foreign_keys=[
                foreign_key(
                    "FK_Disabled",
                    "Child",
                    ["ParentID"],
                    "Parent",
                    ["ParentID"],
                    disabled=True,
                ),
                foreign_key(
                    "FK_Untrusted",
                    "Child",
                    ["OtherParentID"],
                    "Parent",
                    ["ParentID"],
                    untrusted=True,
                ),
            ],
        )
    )

    edges = {edge.constraint_name: edge for edge in fk_edges(graph)}
    assert edges["FK_Disabled"].automatic_join_allowed is False
    assert edges["FK_Disabled"].enforcement_status == "disabled"
    assert edges["FK_Untrusted"].automatic_join_allowed is False
    assert edges["FK_Untrusted"].validation_status == "untrusted"


def test_marks_self_reference_and_structural_bridge_candidate() -> None:
    customer = table(
        "Customer",
        [column("CustomerID", 1)],
        primary_key=["CustomerID"],
    )
    address = table(
        "Address",
        [column("AddressID", 1)],
        primary_key=["AddressID"],
    )
    bridge = table(
        "CustomerAddress",
        [column("CustomerID", 1), column("AddressID", 2)],
        primary_key=["CustomerID", "AddressID"],
    )
    category = table(
        "ProductCategory",
        [
            column("ProductCategoryID", 1),
            column("ParentProductCategoryID", 2, nullable=True),
        ],
        primary_key=["ProductCategoryID"],
    )
    graph = build(
        snapshot(
            tables=[customer, address, bridge, category],
            foreign_keys=[
                foreign_key(
                    "FK_CustomerAddress_Customer",
                    "CustomerAddress",
                    ["CustomerID"],
                    "Customer",
                    ["CustomerID"],
                ),
                foreign_key(
                    "FK_CustomerAddress_Address",
                    "CustomerAddress",
                    ["AddressID"],
                    "Address",
                    ["AddressID"],
                ),
                foreign_key(
                    "FK_Category_Parent",
                    "ProductCategory",
                    ["ParentProductCategoryID"],
                    "ProductCategory",
                    ["ProductCategoryID"],
                ),
            ],
        )
    )

    assert node_by_name(graph, "CustomerAddress").bridge_candidate is True
    self_edge = next(
        edge for edge in fk_edges(graph) if edge.constraint_name == "FK_Category_Parent"
    )
    assert self_edge.self_reference is True
    assert self_edge.nullable_fk is True


def test_classifies_queryability_without_conflating_pii_and_exclusion() -> None:
    customer = table(
        "Customer",
        [
            column("CustomerID", 1),
            column("EmailAddress", 2, role="text", native_type="nvarchar"),
            column("PasswordHash", 3, role="text", native_type="varchar"),
            column("ProfileXml", 4, role="xml", native_type="xml"),
        ],
        primary_key=["CustomerID"],
    )

    graph = build(snapshot(tables=[customer]))
    columns = {
        item.name: item for item in node_by_name(graph, "Customer").columns
    }

    assert columns["EmailAddress"].sensitivity == "pii"
    assert columns["EmailAddress"].queryability_status == "queryable"
    assert columns["PasswordHash"].sensitivity == "sensitive"
    assert columns["PasswordHash"].queryability_status == "excluded"
    assert columns["ProfileXml"].queryability_status == "excluded"


def test_lineage_is_provenance_only_and_partial_status_is_preserved() -> None:
    customer = table(
        "Customer",
        [column("CustomerID", 1)],
        primary_key=["CustomerID"],
    )
    view = table(
        "vCustomer",
        [column("CustomerID", 1)],
        table_type="view",
    )
    view = replace(
        view,
        view_lineage=[
            SchemaViewLineageDependency(
                source="dm_sql_referenced_entities",
                referencing_column="CustomerID",
                referenced_schema_name="SalesLT",
                referenced_entity_name="Customer",
                referenced_column_name="CustomerID",
                referenced_class="OBJECT_OR_COLUMN",
                is_incomplete=True,
            )
        ],
    )
    warning = SchemaCoverageWarning(
        code="VIEW_LINEAGE_PARTIAL",
        severity="warning",
        message="Partial lineage.",
        object_schema="SalesLT",
        object_name="vCustomer",
    )

    graph = build(
        snapshot(
            tables=[customer, view],
            warnings=[warning],
            coverage_status="partial",
        )
    )

    assert graph.status == "partial"
    assert node_by_name(graph, "vCustomer").view_lineage_status == "partial"
    assert all(edge.automatic_join_allowed is False for edge in graph.edges)
    assert {edge.edge_type for edge in graph.edges} == {
        "view_depends_on",
        "view_column_derives_from",
    }


def test_path_finding_detects_parallel_fk_ambiguity_and_fanout() -> None:
    address = table(
        "Address",
        [column("AddressID", 1)],
        primary_key=["AddressID"],
    )
    order = table(
        "SalesOrderHeader",
        [
            column("SalesOrderID", 1),
            column("BillToAddressID", 2),
            column("ShipToAddressID", 3),
        ],
        primary_key=["SalesOrderID"],
    )
    graph = build(
        snapshot(
            tables=[address, order],
            foreign_keys=[
                foreign_key(
                    "FK_Order_BillTo",
                    "SalesOrderHeader",
                    ["BillToAddressID"],
                    "Address",
                    ["AddressID"],
                ),
                foreign_key(
                    "FK_Order_ShipTo",
                    "SalesOrderHeader",
                    ["ShipToAddressID"],
                    "Address",
                    ["AddressID"],
                ),
            ],
        )
    )
    order_node = node_by_name(graph, "SalesOrderHeader")
    address_node = node_by_name(graph, "Address")

    ambiguous = find_queryability_paths(
        graph=graph,
        from_node_key=order_node.node_key,
        to_node_key=address_node.node_key,
    )
    assert ambiguous.status == "ambiguous"
    assert len(ambiguous.paths) == 2

    reverse = find_queryability_paths(
        graph=graph,
        from_node_key=address_node.node_key,
        to_node_key=order_node.node_key,
    )
    assert reverse.status == "ambiguous"
    assert all(path.fanout_warning for path in reverse.paths)


def test_hashes_are_deterministic_and_policy_relevant_input_changes_them() -> None:
    parent = table(
        "Parent",
        [column("ParentID", 1)],
        primary_key=["ParentID"],
    )
    child = table(
        "Child",
        [column("ChildID", 1), column("ParentID", 2)],
        primary_key=["ChildID"],
    )
    trusted = snapshot(
        tables=[parent, child],
        foreign_keys=[
            foreign_key(
                "FK_Child_Parent",
                "Child",
                ["ParentID"],
                "Parent",
                ["ParentID"],
            )
        ],
    )
    reordered = replace(trusted, tables=[child, parent])
    untrusted = replace(
        trusted,
        foreign_keys=[
            replace(trusted.foreign_keys[0], is_not_trusted=True)
        ],
    )

    first = build(trusted)
    second = build(reordered)
    degraded = build(untrusted)
    assert first.graph_input_hash == second.graph_input_hash
    assert first.graph_hash == second.graph_hash
    assert first.graph_input_hash != degraded.graph_input_hash
    assert first.graph_hash != degraded.graph_hash


def test_incoherent_fk_metadata_blocks_graph() -> None:
    parent = table(
        "Parent",
        [column("ParentID", 1)],
        primary_key=["ParentID"],
    )
    child = table(
        "Child",
        [column("ChildID", 1), column("ParentID", 2)],
        primary_key=["ChildID"],
    )
    graph = build(
        snapshot(
            tables=[parent, child],
            foreign_keys=[
                foreign_key(
                    "FK_Broken",
                    "Child",
                    ["ParentID", "Missing"],
                    "Parent",
                    ["ParentID"],
                )
            ],
        )
    )

    assert graph.status == "blocked"
    assert "INVALID_FOREIGN_KEY_COLUMN_COUNT" in graph.status_reasons


def test_system_objects_are_not_automatic_routing_nodes() -> None:
    system_table = replace(
        table(
            "InternalTable",
            [column("InternalID", 1)],
            primary_key=["InternalID"],
        ),
        is_system_object=True,
    )

    graph = build(snapshot(tables=[system_table]))
    node = node_by_name(graph, "InternalTable")

    assert node.queryability_status == "excluded"
    assert node.reason_codes == ["SYSTEM_OBJECT"]


def test_path_results_are_deterministically_capped() -> None:
    parent = table(
        "Parent",
        [column("ParentID", 1)],
        primary_key=["ParentID"],
    )
    child_columns = [column("ChildID", 1)]
    child_columns.extend(
        column(f"ParentID{ordinal}", ordinal + 1)
        for ordinal in range(1, 102)
    )
    child = table("Child", child_columns, primary_key=["ChildID"])
    graph = build(
        snapshot(
            tables=[parent, child],
            foreign_keys=[
                foreign_key(
                    f"FK_Child_Parent_{ordinal}",
                    "Child",
                    [f"ParentID{ordinal}"],
                    "Parent",
                    ["ParentID"],
                )
                for ordinal in range(1, 102)
            ],
        )
    )

    result = find_queryability_paths(
        graph=graph,
        from_node_key=node_by_name(graph, "Child").node_key,
        to_node_key=node_by_name(graph, "Parent").node_key,
    )

    assert result.status == "ambiguous"
    assert len(result.paths) == 100
    assert result.reason_codes == [
        "MULTIPLE_SHORTEST_PATHS",
        "PATH_RESULT_TRUNCATED",
    ]
