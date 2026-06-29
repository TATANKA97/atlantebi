from dataclasses import replace

from app.models import QueryabilityForeignKeyEdge
from app.drivers.base import SchemaViewLineageDependency
from app.queryability import find_queryability_paths
from app.queryability_validation import (
    QueryabilityExpectedRelationship,
    validate_queryability_graph,
    validate_queryability_path_result,
    validate_semantic_graph_freshness,
)
from tests.test_query_intent import active_adventureworks_layer
from tests.test_queryability_builder import (
    build,
    column,
    fk_edges,
    foreign_key,
    node_by_name,
    snapshot,
    table,
)
from tests.test_semantic_builder import adventureworks_graph


def issue_codes(report_or_issues):
    issues = (
        report_or_issues.issues
        if hasattr(report_or_issues, "issues")
        else report_or_issues
    )
    return {issue.code for issue in issues}


def test_adventureworks_baseline_has_no_graph_invariant_errors() -> None:
    graph = adventureworks_graph()

    report = validate_queryability_graph(graph)

    assert report.status in {"valid", "valid_with_warnings"}
    assert report.errors == []
    assert any(
        isinstance(edge, QueryabilityForeignKeyEdge) and edge.automatic_join_allowed
        for edge in graph.edges
    )
    assert all(
        edge.automatic_join_allowed is False
        for edge in graph.edges
        if edge.edge_type != "fk_join"
    )


def test_structural_invariants_detect_duplicate_and_dangling_references() -> None:
    customer = table(
        "Customer",
        [column("CustomerID", 1), column("Name", 2, native_type="nvarchar")],
        primary_key=["CustomerID"],
    )
    order = table(
        "SalesOrder",
        [column("SalesOrderID", 1), column("CustomerID", 2)],
        primary_key=["SalesOrderID"],
    )
    graph = build(
        snapshot(
            tables=[customer, order],
            foreign_keys=[
                foreign_key(
                    "FK_Order_Customer",
                    "SalesOrder",
                    ["CustomerID"],
                    "Customer",
                    ["CustomerID"],
                )
            ],
        )
    )
    node = node_by_name(graph, "Customer")
    duplicated_column = node.columns[1].model_copy(
        update={"column_key": node.columns[0].column_key}
    )
    corrupted_node = node.model_copy(update={"columns": [node.columns[0], duplicated_column]})
    corrupted_edge = fk_edges(graph)[0].model_copy(update={"from_node_key": "0" * 64})
    corrupted = graph.model_copy(
        update={
            "nodes": [
                corrupted_node if item.node_key == node.node_key else item
                for item in graph.nodes
            ],
            "edges": [corrupted_edge],
        }
    )

    report = validate_queryability_graph(corrupted)

    assert "DUPLICATE_COLUMN_KEY" in issue_codes(report)
    assert "DANGLING_EDGE_REFERENCE" in issue_codes(report)
    assert report.status == "invalid"


def test_structural_invariants_detect_duplicate_nodes_and_edges() -> None:
    parent = table("Parent", [column("ParentID", 1)], primary_key=["ParentID"])
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
                    "FK_Child_Parent",
                    "Child",
                    ["ParentID"],
                    "Parent",
                    ["ParentID"],
                )
            ],
        )
    )
    parent_node = node_by_name(graph, "Parent")
    child_node = node_by_name(graph, "Child")
    duplicated_child = child_node.model_copy(
        update={"node_key": parent_node.node_key}
    )
    edge = fk_edges(graph)[0]
    corrupted = graph.model_copy(
        update={
            "nodes": [
                parent_node,
                duplicated_child,
            ],
            "edges": [edge, edge],
        }
    )

    report = validate_queryability_graph(corrupted)

    assert "DUPLICATE_NODE_KEY" in issue_codes(report)
    assert "DUPLICATE_EDGE_KEY" in issue_codes(report)
    assert report.status == "invalid"


def test_fk_column_pairs_must_exist_and_belong_to_edge_nodes() -> None:
    parent = table("Parent", [column("ParentID", 1)], primary_key=["ParentID"])
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
                    "FK_Child_Parent",
                    "Child",
                    ["ParentID"],
                    "Parent",
                    ["ParentID"],
                )
            ],
        )
    )
    edge = fk_edges(graph)[0]
    parent_key = node_by_name(graph, "Parent").columns[0].column_key
    missing_key_pair = edge.column_pairs[0].model_copy(
        update={"from_column_key": "2" * 64}
    )
    wrong_node_pair = edge.column_pairs[0].model_copy(
        update={"from_column_key": parent_key}
    )
    corrupted = graph.model_copy(
        update={
            "edges": [
                edge.model_copy(update={"column_pairs": [missing_key_pair]}),
                edge.model_copy(
                    update={
                        "edge_key": "3" * 64,
                        "column_pairs": [wrong_node_pair],
                    }
                ),
            ]
        }
    )

    report = validate_queryability_graph(corrupted)

    assert "FK_COLUMN_PAIR_NODE_MISMATCH" in issue_codes(report)
    assert report.status == "invalid"


def test_untrusted_fk_cannot_be_promoted_to_automatic_join() -> None:
    parent = table("Parent", [column("ParentID", 1)], primary_key=["ParentID"])
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
                    "FK_Child_Parent",
                    "Child",
                    ["ParentID"],
                    "Parent",
                    ["ParentID"],
                    untrusted=True,
                )
            ],
        )
    )
    corrupted = graph.model_copy(
        update={
            "edges": [
                fk_edges(graph)[0].model_copy(update={"automatic_join_allowed": True})
            ]
        }
    )

    report = validate_queryability_graph(corrupted)

    assert "AUTOMATIC_JOIN_ON_UNTRUSTED_FK" in issue_codes(report)
    assert report.status == "invalid"


def test_disabled_and_unverified_fk_cannot_be_promoted_to_automatic_join() -> None:
    parent = table("Parent", [column("ParentID", 1)], primary_key=["ParentID"])
    child = table(
        "Child",
        [column("ChildID", 1), column("ParentID", 2)],
        primary_key=["ChildID"],
    )

    for unsafe_fk in [
        foreign_key(
            "FK_Child_Parent_Disabled",
            "Child",
            ["ParentID"],
            "Parent",
            ["ParentID"],
            disabled=True,
        ),
        foreign_key(
            "FK_Child_Parent_Unverified",
            "Child",
            ["ParentID"],
            "Parent",
            ["ParentID"],
            verified_by_db=False,
        ),
    ]:
        graph = build(snapshot(tables=[parent, child], foreign_keys=[unsafe_fk]))
        corrupted = graph.model_copy(
            update={
                "edges": [
                    fk_edges(graph)[0].model_copy(
                        update={"automatic_join_allowed": True}
                    )
                ]
            }
        )

        report = validate_queryability_graph(corrupted)

        assert "AUTOMATIC_JOIN_ON_UNTRUSTED_FK" in issue_codes(report)
        assert report.status == "invalid"


def test_automatic_join_on_excluded_fk_column_is_invalid() -> None:
    parent = table("Parent", [column("ParentID", 1)], primary_key=["ParentID"])
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
                    "FK_Child_Parent",
                    "Child",
                    ["ParentID"],
                    "Parent",
                    ["ParentID"],
                )
            ],
        )
    )
    child_node = node_by_name(graph, "Child")
    excluded_parent_id = child_node.columns[1].model_copy(
        update={"queryability_status": "excluded"}
    )
    corrupted_child = child_node.model_copy(
        update={"columns": [child_node.columns[0], excluded_parent_id]}
    )
    corrupted = graph.model_copy(
        update={
            "nodes": [
                corrupted_child if node.node_key == child_node.node_key else node
                for node in graph.nodes
            ]
        }
    )

    report = validate_queryability_graph(corrupted)

    assert "AUTOMATIC_JOIN_ON_EXCLUDED_COLUMN" in issue_codes(report)
    assert report.status == "invalid"


def test_self_reference_is_not_compiler_safe_by_default() -> None:
    employee = table(
        "Employee",
        [column("EmployeeID", 1), column("ManagerID", 2)],
        primary_key=["EmployeeID"],
    )
    graph = build(
        snapshot(
            tables=[employee],
            foreign_keys=[
                foreign_key(
                    "FK_Employee_Manager",
                    "Employee",
                    ["ManagerID"],
                    "Employee",
                    ["EmployeeID"],
                )
            ],
        )
    )
    corrupted = graph.model_copy(
        update={
            "edges": [
                fk_edges(graph)[0].model_copy(update={"automatic_join_allowed": True})
            ]
        }
    )

    report = validate_queryability_graph(corrupted)

    assert "SELF_REFERENCE_REQUIRES_POLICY" in issue_codes(report)
    assert report.status == "valid_with_warnings"


def test_missing_fk_schema_fails_closed_without_invented_trusted_join() -> None:
    header = table(
        "DocumentHeader",
        [column("DocumentID", 1), column("CustomerID", 2)],
        primary_key=["DocumentID"],
    )
    detail = table(
        "DocumentLine",
        [column("DocumentLineID", 1), column("DocumentID", 2)],
        primary_key=["DocumentLineID"],
    )

    graph = build(snapshot(tables=[header, detail]))
    report = validate_queryability_graph(
        graph,
        expected_missing_relationships=[
            QueryabilityExpectedRelationship(
                from_object_name="DocumentLine",
                to_object_name="DocumentHeader",
            )
        ],
    )

    assert fk_edges(graph) == []
    assert "MISSING_FK_NO_TRUSTED_JOIN" in issue_codes(report)
    assert report.status == "valid_with_warnings"


def test_ugly_pmi_schema_gets_stable_keys_without_name_based_joins() -> None:
    graph = build(
        snapshot(
            tables=[
                table("DOTES", [column("IDTES", 1)], primary_key=["IDTES"]),
                table("DORIG", [column("IDRIG", 1), column("IDTES", 2)], primary_key=["IDRIG"]),
                table("ANACLI", [column("IDCLI", 1)], primary_key=["IDCLI"]),
                table("ARTICO", [column("IDART", 1)], primary_key=["IDART"]),
                table("CATART", [column("IDCAT", 1)], primary_key=["IDCAT"]),
            ]
        )
    )

    report = validate_queryability_graph(graph)

    assert len({node.node_key for node in graph.nodes}) == 5
    assert fk_edges(graph) == []
    assert "MISSING_FK_NO_TRUSTED_JOIN" not in issue_codes(report)
    assert report.errors == []


def test_path_ambiguity_is_reported_without_silent_choice() -> None:
    start = table(
        "Fact",
        [column("FactID", 1), column("ParentAID", 2), column("ParentBID", 3)],
        primary_key=["FactID"],
    )
    parent_a = table(
        "ParentA",
        [column("ParentAID", 1), column("TargetID", 2)],
        primary_key=["ParentAID"],
    )
    parent_b = table(
        "ParentB",
        [column("ParentBID", 1), column("TargetID", 2)],
        primary_key=["ParentBID"],
    )
    target = table("Target", [column("TargetID", 1)], primary_key=["TargetID"])
    graph = build(
        snapshot(
            tables=[start, parent_a, parent_b, target],
            foreign_keys=[
                foreign_key("FK_Fact_A", "Fact", ["ParentAID"], "ParentA", ["ParentAID"]),
                foreign_key("FK_Fact_B", "Fact", ["ParentBID"], "ParentB", ["ParentBID"]),
                foreign_key("FK_A_Target", "ParentA", ["TargetID"], "Target", ["TargetID"]),
                foreign_key("FK_B_Target", "ParentB", ["TargetID"], "Target", ["TargetID"]),
            ],
        )
    )

    path_result = find_queryability_paths(
        graph=graph,
        from_node_key=node_by_name(graph, "Fact").node_key,
        to_node_key=node_by_name(graph, "Target").node_key,
    )
    path_issues = validate_queryability_path_result(path_result)

    assert path_result.status == "ambiguous"
    assert len(path_result.paths) == 2
    assert "AMBIGUOUS_PATH_NOT_BLOCKED" in issue_codes(path_issues)


def test_bridge_many_to_many_requires_explicit_policy() -> None:
    customer = table("Customer", [column("CustomerID", 1)], primary_key=["CustomerID"])
    product = table("Product", [column("ProductID", 1)], primary_key=["ProductID"])
    bridge = table(
        "CustomerProduct",
        [column("CustomerID", 1), column("ProductID", 2)],
        primary_key=["CustomerID", "ProductID"],
    )
    graph = build(
        snapshot(
            tables=[customer, product, bridge],
            foreign_keys=[
                foreign_key(
                    "FK_CustomerProduct_Customer",
                    "CustomerProduct",
                    ["CustomerID"],
                    "Customer",
                    ["CustomerID"],
                ),
                foreign_key(
                    "FK_CustomerProduct_Product",
                    "CustomerProduct",
                    ["ProductID"],
                    "Product",
                    ["ProductID"],
                ),
            ],
        )
    )

    path_result = find_queryability_paths(
        graph=graph,
        from_node_key=node_by_name(graph, "Customer").node_key,
        to_node_key=node_by_name(graph, "Product").node_key,
    )
    report = validate_queryability_graph(graph)

    assert node_by_name(graph, "CustomerProduct").bridge_candidate is True
    assert "BRIDGE_PATH_REQUIRES_POLICY" in issue_codes(report)
    assert "FANOUT_PATH_REQUIRES_COMPILER_GUARD" in issue_codes(
        validate_queryability_path_result(path_result)
    )


def test_view_lineage_is_provenance_not_join_evidence() -> None:
    customer = table("Customer", [column("CustomerID", 1)], primary_key=["CustomerID"])
    view = replace(
        table("vCustomer", [column("CustomerID", 1)], table_type="view"),
        view_lineage=[
            SchemaViewLineageDependency(
                source="dm_sql_referenced_entities",
                referencing_column="CustomerID",
                referenced_schema_name="SalesLT",
                referenced_entity_name="Customer",
                referenced_column_name="CustomerID",
                referenced_class="OBJECT_OR_COLUMN",
            )
        ],
    )
    graph = build(snapshot(tables=[customer, view]))

    report = validate_queryability_graph(graph)

    assert {edge.edge_type for edge in graph.edges} == {
        "view_depends_on",
        "view_column_derives_from",
    }
    assert all(edge.automatic_join_allowed is False for edge in graph.edges)
    assert "LINEAGE_USED_AS_JOIN" not in issue_codes(report)


def test_lineage_edges_cannot_be_promoted_to_automatic_join() -> None:
    customer = table("Customer", [column("CustomerID", 1)], primary_key=["CustomerID"])
    view = replace(
        table("vCustomer", [column("CustomerID", 1)], table_type="view"),
        view_lineage=[
            SchemaViewLineageDependency(
                source="dm_sql_referenced_entities",
                referencing_column="CustomerID",
                referenced_schema_name="SalesLT",
                referenced_entity_name="Customer",
                referenced_column_name="CustomerID",
                referenced_class="OBJECT_OR_COLUMN",
            )
        ],
    )
    graph = build(snapshot(tables=[customer, view]))
    corrupted = graph.model_copy(
        update={
            "edges": [
                edge.model_copy(update={"automatic_join_allowed": True})
                for edge in graph.edges
            ]
        }
    )

    report = validate_queryability_graph(corrupted)

    assert "LINEAGE_USED_AS_JOIN" in issue_codes(report)
    assert report.status == "invalid"


def test_multiple_dates_require_semantic_selection() -> None:
    graph = build(
        snapshot(
            tables=[
                table(
                    "DocumentHeader",
                    [
                        column("DocumentID", 1),
                        column("OrderDate", 2, role="date", native_type="datetime"),
                        column("PostingDate", 3, role="date", native_type="datetime"),
                        column("InvoiceDate", 4, role="date", native_type="datetime"),
                        column("ModifiedDate", 5, role="date", native_type="datetime"),
                    ],
                    primary_key=["DocumentID"],
                )
            ]
        )
    )

    report = validate_queryability_graph(graph)

    assert "MULTIPLE_DATE_COLUMNS_REQUIRES_SEMANTIC_SELECTION" in issue_codes(report)
    assert report.errors == []


def test_sensitive_and_pii_columns_are_diagnosed_without_blocking_queryability() -> None:
    graph = build(
        snapshot(
            tables=[
                table(
                    "Customer",
                    [
                        column("CustomerID", 1),
                        column("Email", 2, role="text", native_type="nvarchar"),
                        column("Telefono", 3, role="text", native_type="nvarchar"),
                        column("CodiceFiscale", 4, role="text", native_type="nvarchar"),
                        column("PartitaIVA", 5, role="text", native_type="nvarchar"),
                        column("IBAN", 6, role="text", native_type="nvarchar"),
                        column("PasswordHash", 7, role="text", native_type="nvarchar"),
                        column("ApiToken", 8, role="text", native_type="nvarchar"),
                    ],
                    primary_key=["CustomerID"],
                )
            ]
        )
    )
    columns = {column.name: column for column in node_by_name(graph, "Customer").columns}

    report = validate_queryability_graph(graph)

    assert columns["PasswordHash"].sensitivity == "sensitive"
    assert columns["PasswordHash"].queryability_status == "excluded"
    assert columns["ApiToken"].sensitivity == "sensitive"
    assert columns["Email"].sensitivity == "pii"
    assert columns["CodiceFiscale"].sensitivity == "pii"
    assert columns["PartitaIVA"].sensitivity == "pii"
    assert columns["IBAN"].sensitivity == "pii"
    assert "PII_REQUIRES_DOWNSTREAM_POLICY" in issue_codes(report)
    assert report.errors == []


def test_unsupported_type_cannot_remain_queryable() -> None:
    graph = build(
        snapshot(
            tables=[
                table(
                    "Documents",
                    [
                        column("DocumentID", 1),
                        column("RawPayload", 2, role="binary", native_type="varbinary"),
                    ],
                    primary_key=["DocumentID"],
                )
            ]
        )
    )
    node = node_by_name(graph, "Documents")
    forced_queryable_payload = node.columns[1].model_copy(
        update={"queryability_status": "queryable"}
    )
    corrupted_node = node.model_copy(
        update={"columns": [node.columns[0], forced_queryable_payload]}
    )
    corrupted = graph.model_copy(update={"nodes": [corrupted_node]})

    report = validate_queryability_graph(corrupted)

    assert "UNSUPPORTED_TYPE_QUERYABLE" in issue_codes(report)
    assert report.status == "invalid"


def test_composite_fk_pair_order_remains_validated() -> None:
    parent = table(
        "Parent",
        [column("TenantID", 1), column("ParentID", 2)],
        primary_key=["TenantID", "ParentID"],
    )
    child = table(
        "Child",
        [column("ChildID", 1), column("TenantID", 2), column("ParentID", 3)],
        primary_key=["ChildID"],
    )
    graph = build(
        snapshot(
            tables=[parent, child],
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
    report = validate_queryability_graph(graph)

    assert [(pair.from_column, pair.to_column) for pair in edge.column_pairs] == [
        ("TenantID", "TenantID"),
        ("ParentID", "ParentID"),
    ]
    assert report.errors == []


def test_table_without_pk_is_not_grain_safe_by_default() -> None:
    graph = build(
        snapshot(
            tables=[
                table(
                    "FactSales",
                    [column("Amount", 1, role="money_candidate", native_type="money")],
                )
            ]
        )
    )

    report = validate_queryability_graph(graph)

    assert "TABLE_WITHOUT_PK_UNSAFE_FOR_GRAIN" in issue_codes(report)
    assert report.errors == []


def test_semantic_graph_freshness_helper_is_separate_from_graph_invariants() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    stale_layer = layer.model_copy(update={"base_graph_hash": "0" * 64})
    mismatched_policy_hash = (
        "0" * 64
        if layer.semantic_policy_snapshot.policy_hash != "0" * 64
        else "1" * 64
    )
    policy_stale_layer = layer.model_copy(
        update={"base_policy_hash": mismatched_policy_hash}
    )

    graph_report = validate_queryability_graph(graph)
    freshness_report = validate_semantic_graph_freshness(graph, stale_layer)
    policy_freshness_report = validate_semantic_graph_freshness(
        graph, policy_stale_layer
    )

    assert "SEMANTIC_GRAPH_HASH_STALE" not in issue_codes(graph_report)
    assert "SEMANTIC_GRAPH_HASH_STALE" in issue_codes(freshness_report)
    assert freshness_report.status == "invalid"
    assert "SEMANTIC_POLICY_HASH_STALE" in issue_codes(policy_freshness_report)
    assert policy_freshness_report.status == "invalid"
