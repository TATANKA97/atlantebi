import hashlib
import json
import re
from collections import deque
from dataclasses import dataclass
from typing import Any, Literal

from app.drivers.base import (
    SchemaForeignKeyMetadata,
    SchemaIndexMetadata,
    SchemaIntrospectionResult,
    SchemaTableMetadata,
)
from app.models import (
    QueryabilityCandidateKey,
    QueryabilityColumn,
    QueryabilityColumnPair,
    QueryabilityForeignKeyEdge,
    QueryabilityGraphArtifact,
    QueryabilityNode,
    QueryabilityPath,
    QueryabilityPathResult,
    QueryabilityPathStep,
    QueryabilityViewColumnEdge,
    QueryabilityViewDependencyEdge,
)


QUERYABILITY_GRAPH_CONTRACT_VERSION = "queryability_graph.v1"
DEFAULT_BUILDER_VERSION = "1.0.0"
DEFAULT_POLICY_VERSION = "1.0.0"


@dataclass(frozen=True)
class _Traversal:
    edge: QueryabilityForeignKeyEdge
    from_node_key: str
    to_node_key: str
    direction: Literal["child_to_parent", "parent_to_child"]
    cardinality: Literal["zero_or_one", "exactly_one", "zero_or_many"]


def build_queryability_graph(
    *,
    snapshot: SchemaIntrospectionResult,
    tenant_id: str,
    connection_id: str,
    schema_snapshot_id: str,
    builder_version: str = DEFAULT_BUILDER_VERSION,
    policy_version: str = DEFAULT_POLICY_VERSION,
) -> QueryabilityGraphArtifact:
    status_reasons = {
        warning.code for warning in snapshot.coverage_warnings
    }
    if snapshot.coverage_status == "blocked":
        status_reasons.add("SNAPSHOT_BLOCKED")

    duplicate_objects = _duplicate_object_keys(snapshot.tables)
    if duplicate_objects:
        status_reasons.add("DUPLICATE_OBJECT_KEY")

    nodes = [
        _build_node(snapshot=snapshot, table=table)
        for table in snapshot.tables
    ]
    nodes_by_object = {
        (node.schema_name, node.object_name): node for node in nodes
    }

    fk_edges: list[QueryabilityForeignKeyEdge] = []
    for foreign_key in snapshot.foreign_keys:
        edge, reason = _build_fk_edge(
            foreign_key=foreign_key,
            nodes_by_object=nodes_by_object,
        )
        if edge is None:
            status_reasons.add(reason or "INVALID_FOREIGN_KEY_METADATA")
            continue
        fk_edges.append(edge)

    nodes = _mark_bridge_candidates(nodes=nodes, fk_edges=fk_edges)
    nodes_by_object = {
        (node.schema_name, node.object_name): node for node in nodes
    }
    lineage_edges = _build_lineage_edges(
        snapshot=snapshot,
        nodes_by_object=nodes_by_object,
    )

    if not nodes:
        status_reasons.add("NO_GRAPH_NODES")

    blocked_reasons = {
        "SNAPSHOT_BLOCKED",
        "DUPLICATE_OBJECT_KEY",
        "INVALID_FOREIGN_KEY_COLUMN_COUNT",
        "FOREIGN_KEY_OBJECT_NOT_FOUND",
        "FOREIGN_KEY_COLUMN_NOT_FOUND",
        "NO_GRAPH_NODES",
    }
    status: Literal["complete", "partial", "blocked"]
    if status_reasons & blocked_reasons:
        status = "blocked"
    elif snapshot.coverage_status != "ok" or status_reasons:
        status = "partial"
    else:
        status = "complete"

    ordered_nodes = sorted(nodes, key=lambda node: node.node_key)
    ordered_edges = sorted(
        [*fk_edges, *lineage_edges],
        key=lambda edge: edge.edge_key,
    )
    graph_input_hash = _hash_json(
        _graph_input_payload(snapshot=snapshot, nodes=ordered_nodes)
    )
    derivation_key = _hash_json(
        {
            "graph_input_hash": graph_input_hash,
            "builder_version": builder_version,
            "policy_version": policy_version,
        }
    )
    graph_hash = _hash_json(
        {
            "contract_version": QUERYABILITY_GRAPH_CONTRACT_VERSION,
            "nodes": [
                node.model_dump(mode="json", exclude_none=True)
                for node in ordered_nodes
            ],
            "edges": [
                edge.model_dump(mode="json", exclude_none=True)
                for edge in ordered_edges
            ],
        }
    )

    return QueryabilityGraphArtifact(
        contract_version=QUERYABILITY_GRAPH_CONTRACT_VERSION,
        tenant_id=tenant_id,
        connection_id=connection_id,
        schema_snapshot_id=schema_snapshot_id,
        engine="sqlserver",
        schema_hash=snapshot.schema_hash,
        snapshot_hash=snapshot.snapshot_hash,
        graph_input_hash=graph_input_hash,
        derivation_key=derivation_key,
        graph_hash=graph_hash,
        builder_version=builder_version,
        policy_version=policy_version,
        status=status,
        status_reasons=sorted(status_reasons),
        semantic_status="not_initialized",
        nodes=ordered_nodes,
        edges=ordered_edges,
    )


def find_queryability_paths(
    *,
    graph: QueryabilityGraphArtifact,
    from_node_key: str,
    to_node_key: str,
    max_hops: int = 4,
) -> QueryabilityPathResult:
    if graph.status == "blocked":
        return QueryabilityPathResult(
            status="blocked",
            paths=[],
            reason_codes=["GRAPH_BLOCKED"],
        )
    if max_hops < 1 or max_hops > 4:
        return QueryabilityPathResult(
            status="blocked",
            paths=[],
            reason_codes=["INVALID_MAX_HOPS"],
        )

    node_keys = {node.node_key for node in graph.nodes}
    if from_node_key not in node_keys or to_node_key not in node_keys:
        return QueryabilityPathResult(
            status="not_found",
            paths=[],
            reason_codes=["NODE_NOT_FOUND"],
        )
    if from_node_key == to_node_key:
        return QueryabilityPathResult(
            status="not_found",
            paths=[],
            reason_codes=["SAME_NODE_PATH_NOT_REQUIRED"],
        )

    traversals_by_node: dict[str, list[_Traversal]] = {}
    for edge in graph.edges:
        if (
            not isinstance(edge, QueryabilityForeignKeyEdge)
            or not edge.automatic_join_allowed
            or edge.self_reference
        ):
            continue
        traversals_by_node.setdefault(edge.from_node_key, []).append(
            _Traversal(
                edge=edge,
                from_node_key=edge.from_node_key,
                to_node_key=edge.to_node_key,
                direction="child_to_parent",
                cardinality=edge.child_to_parent,
            )
        )
        traversals_by_node.setdefault(edge.to_node_key, []).append(
            _Traversal(
                edge=edge,
                from_node_key=edge.to_node_key,
                to_node_key=edge.from_node_key,
                direction="parent_to_child",
                cardinality=edge.parent_to_child,
            )
        )

    queue = deque([(from_node_key, [], {from_node_key})])
    found: list[list[_Traversal]] = []
    shortest_length: int | None = None
    while queue:
        current_node, path, visited = queue.popleft()
        if shortest_length is not None and len(path) >= shortest_length:
            continue
        if len(path) >= max_hops:
            continue
        for traversal in sorted(
            traversals_by_node.get(current_node, []),
            key=lambda item: (
                item.to_node_key,
                item.edge.edge_key,
                item.direction,
            ),
        ):
            if traversal.to_node_key in visited:
                continue
            next_path = [*path, traversal]
            if traversal.to_node_key == to_node_key:
                shortest_length = len(next_path)
                found.append(next_path)
                continue
            queue.append(
                (
                    traversal.to_node_key,
                    next_path,
                    {*visited, traversal.to_node_key},
                )
            )

    if not found:
        return QueryabilityPathResult(
            status="not_found",
            paths=[],
            reason_codes=["NO_AUTOMATIC_JOIN_PATH"],
        )

    paths = [
        QueryabilityPath(
            steps=[
                QueryabilityPathStep(
                    edge_key=traversal.edge.edge_key,
                    from_node_key=traversal.from_node_key,
                    to_node_key=traversal.to_node_key,
                    traversal=traversal.direction,
                    cardinality=traversal.cardinality,
                )
                for traversal in path
            ],
            fanout_warning=any(
                traversal.direction == "parent_to_child"
                and traversal.cardinality == "zero_or_many"
                for traversal in path
            ),
        )
        for path in found
        if len(path) == shortest_length
    ]
    reason_codes = ["MULTIPLE_SHORTEST_PATHS"] if len(paths) > 1 else []
    if len(paths) > 100:
        paths = paths[:100]
        reason_codes.append("PATH_RESULT_TRUNCATED")
    return QueryabilityPathResult(
        status="ambiguous" if len(paths) > 1 else "found",
        paths=paths,
        reason_codes=reason_codes,
    )


def _build_node(
    *,
    snapshot: SchemaIntrospectionResult,
    table: SchemaTableMetadata,
) -> QueryabilityNode:
    node_key = _node_key(
        database_name=snapshot.database_name,
        schema_name=table.table_schema,
        object_name=table.name,
        object_type=_object_type(table),
    )
    columns = [
        _build_column(node_key=node_key, column=column)
        for column in sorted(
            table.columns,
            key=lambda item: item.ordinal_position,
        )
    ]
    queryable = not table.is_system_object and any(
        column.queryability_status == "queryable" for column in columns
    )
    reason_codes: list[str] = []
    if table.is_system_object:
        reason_codes.append("SYSTEM_OBJECT")
    elif not queryable:
        reason_codes.append("NO_QUERYABLE_COLUMNS")
    view_lineage_status = None
    if table.table_type == "view":
        view_lineage_status = _view_lineage_status(
            snapshot=snapshot,
            table=table,
        )

    return QueryabilityNode(
        node_key=node_key,
        database_name=snapshot.database_name,
        schema_name=table.table_schema,
        object_name=table.name,
        object_type=_object_type(table),
        queryability_status="queryable" if queryable else "excluded",
        reason_codes=reason_codes,
        bridge_candidate=False,
        candidate_keys=_candidate_keys(snapshot=snapshot, table=table),
        columns=columns,
        view_definition_available=(
            table.view_definition_available
            if table.table_type == "view"
            else None
        ),
        view_lineage_status=view_lineage_status,
    )


def _build_column(*, node_key: str, column) -> QueryabilityColumn:
    sensitivity, sensitivity_reason = _column_sensitivity(column.name)
    reason_codes: list[str] = []
    queryability_status: Literal["queryable", "excluded"] = "queryable"
    if sensitivity == "sensitive":
        queryability_status = "excluded"
        reason_codes.append(sensitivity_reason)
    if column.technical_role == "binary":
        queryability_status = "excluded"
        reason_codes.append("UNSUPPORTED_BINARY_TYPE")
    elif column.technical_role == "xml":
        queryability_status = "excluded"
        reason_codes.append("UNSUPPORTED_COMPLEX_TYPE")

    return QueryabilityColumn(
        column_key=_hash_json(
            {
                "node_key": node_key,
                "column_name": column.name,
                "ordinal_position": column.ordinal_position,
            }
        ),
        name=column.name,
        ordinal_position=column.ordinal_position,
        native_type=column.native_type,
        normalized_type=column.normalized_type,
        technical_role=column.technical_role,
        nullable=column.is_nullable,
        queryability_status=queryability_status,
        sensitivity=sensitivity,
        reason_codes=sorted(set(reason_codes)),
    )


def _candidate_keys(
    *,
    snapshot: SchemaIntrospectionResult,
    table: SchemaTableMetadata,
) -> list[QueryabilityCandidateKey]:
    keys: list[QueryabilityCandidateKey] = []
    if table.primary_key:
        keys.append(
            QueryabilityCandidateKey(
                key_type="primary_key",
                name=table.primary_key.name,
                columns=table.primary_key.columns,
                eligible_for_cardinality=True,
            )
        )
    keys.extend(
        QueryabilityCandidateKey(
            key_type="unique_constraint",
            name=constraint.name,
            columns=constraint.columns,
            eligible_for_cardinality=True,
        )
        for constraint in snapshot.unique_constraints
        if constraint.schema_name == table.table_schema
        and constraint.table_name == table.name
    )
    keys.extend(
        QueryabilityCandidateKey(
            key_type="unique_index",
            name=index.name,
            columns=[
                column.name
                for column in sorted(
                    index.key_columns,
                    key=lambda item: item.ordinal_position,
                )
            ],
            eligible_for_cardinality=_eligible_unique_index(index),
        )
        for index in snapshot.indexes
        if index.schema_name == table.table_schema
        and index.table_name == table.name
        and index.is_unique
        and not index.is_primary_key
    )
    return sorted(
        keys,
        key=lambda key: (key.key_type, key.name, tuple(key.columns)),
    )


def _eligible_unique_index(index: SchemaIndexMetadata) -> bool:
    return (
        index.is_unique
        and not index.is_disabled
        and index.filter_definition is None
        and bool(index.key_columns)
    )


def _build_fk_edge(
    *,
    foreign_key: SchemaForeignKeyMetadata,
    nodes_by_object: dict[tuple[str, str], QueryabilityNode],
) -> tuple[QueryabilityForeignKeyEdge | None, str | None]:
    if len(foreign_key.from_columns) != len(foreign_key.to_columns):
        return None, "INVALID_FOREIGN_KEY_COLUMN_COUNT"

    from_node = nodes_by_object.get(
        (foreign_key.from_schema, foreign_key.from_table)
    )
    to_node = nodes_by_object.get(
        (foreign_key.to_schema, foreign_key.to_table)
    )
    if from_node is None or to_node is None:
        return None, "FOREIGN_KEY_OBJECT_NOT_FOUND"

    from_columns = {column.name: column for column in from_node.columns}
    to_columns = {column.name: column for column in to_node.columns}
    pairs: list[QueryabilityColumnPair] = []
    for ordinal, (from_name, to_name) in enumerate(
        zip(foreign_key.from_columns, foreign_key.to_columns, strict=True),
        start=1,
    ):
        from_column = from_columns.get(from_name)
        to_column = to_columns.get(to_name)
        if from_column is None or to_column is None:
            return None, "FOREIGN_KEY_COLUMN_NOT_FOUND"
        pairs.append(
            QueryabilityColumnPair(
                ordinal_position=ordinal,
                from_column=from_name,
                from_column_key=from_column.column_key,
                to_column=to_name,
                to_column_key=to_column.column_key,
            )
        )

    nullable_fk = any(
        from_columns[column].nullable for column in foreign_key.from_columns
    )
    source_unique = _columns_are_unique(
        columns=foreign_key.from_columns,
        candidate_keys=from_node.candidate_keys,
    )
    reasons: list[str] = []
    if foreign_key.is_disabled:
        reasons.append("FK_DISABLED")
    if foreign_key.is_not_trusted:
        reasons.append("FK_UNTRUSTED")
    if any(
        from_columns[column].queryability_status != "queryable"
        or to_columns[target].queryability_status != "queryable"
        for column, target in zip(
            foreign_key.from_columns,
            foreign_key.to_columns,
            strict=True,
        )
    ):
        reasons.append("FK_COLUMN_EXCLUDED")

    automatic_join_allowed = (
        not foreign_key.is_disabled
        and not foreign_key.is_not_trusted
        and "FK_COLUMN_EXCLUDED" not in reasons
        and from_node.queryability_status == "queryable"
        and to_node.queryability_status == "queryable"
    )
    edge_payload = {
        "edge_type": "fk_join",
        "constraint_name": foreign_key.constraint_name,
        "from_node_key": from_node.node_key,
        "to_node_key": to_node.node_key,
        "column_pairs": [
            pair.model_dump(mode="json") for pair in pairs
        ],
    }
    return (
        QueryabilityForeignKeyEdge(
            edge_key=_hash_json(edge_payload),
            edge_type="fk_join",
            constraint_name=foreign_key.constraint_name,
            from_node_key=from_node.node_key,
            to_node_key=to_node.node_key,
            column_pairs=pairs,
            relationship_shape="one_to_one" if source_unique else "many_to_one",
            child_to_parent="zero_or_one" if nullable_fk else "exactly_one",
            parent_to_child="zero_or_one" if source_unique else "zero_or_many",
            nullable_fk=nullable_fk,
            self_reference=from_node.node_key == to_node.node_key,
            verified_by_db=foreign_key.verified_by_db,
            enforcement_status=(
                "disabled" if foreign_key.is_disabled else "enabled"
            ),
            validation_status=(
                "untrusted" if foreign_key.is_not_trusted else "trusted"
            ),
            automatic_join_allowed=automatic_join_allowed,
            reason_codes=reasons,
        ),
        None,
    )


def _build_lineage_edges(
    *,
    snapshot: SchemaIntrospectionResult,
    nodes_by_object: dict[tuple[str, str], QueryabilityNode],
) -> list[QueryabilityViewDependencyEdge | QueryabilityViewColumnEdge]:
    edges: list[
        QueryabilityViewDependencyEdge | QueryabilityViewColumnEdge
    ] = []
    dependency_keys: set[tuple[Any, ...]] = set()
    for table in snapshot.tables:
        if table.table_type != "view":
            continue
        from_node = nodes_by_object[(table.table_schema, table.name)]
        from_columns = {column.name: column for column in from_node.columns}
        for dependency in table.view_lineage:
            resolution_status, to_node = _resolve_lineage_target(
                snapshot=snapshot,
                dependency=dependency,
                nodes_by_object=nodes_by_object,
            )
            reason_codes = _lineage_reason_codes(
                dependency=dependency,
                resolution_status=resolution_status,
            )
            dependency_identity = (
                from_node.node_key,
                dependency.source,
                dependency.referenced_server_name,
                dependency.referenced_database_name,
                dependency.referenced_schema_name,
                dependency.referenced_entity_name,
                to_node.node_key if to_node else None,
            )
            if dependency_identity not in dependency_keys:
                dependency_keys.add(dependency_identity)
                payload = {
                    "edge_type": "view_depends_on",
                    "from_node_key": from_node.node_key,
                    "to_node_key": to_node.node_key if to_node else None,
                    "source": dependency.source,
                    "referenced_server_name": dependency.referenced_server_name,
                    "referenced_database_name": dependency.referenced_database_name,
                    "referenced_schema_name": dependency.referenced_schema_name,
                    "referenced_object_name": dependency.referenced_entity_name,
                }
                edges.append(
                    QueryabilityViewDependencyEdge(
                        edge_key=_hash_json(payload),
                        edge_type="view_depends_on",
                        from_node_key=from_node.node_key,
                        to_node_key=to_node.node_key if to_node else None,
                        source=dependency.source,
                        referenced_server_name=dependency.referenced_server_name,
                        referenced_database_name=dependency.referenced_database_name,
                        referenced_schema_name=dependency.referenced_schema_name,
                        referenced_object_name=dependency.referenced_entity_name,
                        resolution_status=resolution_status,
                        automatic_join_allowed=False,
                        reason_codes=reason_codes,
                    )
                )

            if not dependency.referencing_column:
                continue
            from_column = from_columns.get(dependency.referencing_column)
            if from_column is None:
                continue
            to_column = None
            if to_node and dependency.referenced_column_name:
                to_column = next(
                    (
                        column
                        for column in to_node.columns
                        if column.name == dependency.referenced_column_name
                    ),
                    None,
                )
            lineage_status: Literal["complete", "partial"] = (
                "complete"
                if resolution_status == "resolved"
                and to_column is not None
                and not dependency.is_incomplete
                and not dependency.is_ambiguous
                else "partial"
            )
            payload = {
                "edge_type": "view_column_derives_from",
                "from_node_key": from_node.node_key,
                "from_column_key": from_column.column_key,
                "to_node_key": to_node.node_key if to_node else None,
                "to_column_key": to_column.column_key if to_column else None,
                "source": dependency.source,
                "referenced_schema_name": dependency.referenced_schema_name,
                "referenced_object_name": dependency.referenced_entity_name,
                "referenced_column_name": dependency.referenced_column_name,
            }
            edges.append(
                QueryabilityViewColumnEdge(
                    edge_key=_hash_json(payload),
                    edge_type="view_column_derives_from",
                    from_node_key=from_node.node_key,
                    from_column_key=from_column.column_key,
                    to_node_key=to_node.node_key if to_node else None,
                    to_column_key=to_column.column_key if to_column else None,
                    source=dependency.source,
                    referenced_server_name=dependency.referenced_server_name,
                    referenced_database_name=dependency.referenced_database_name,
                    referenced_schema_name=dependency.referenced_schema_name,
                    referenced_object_name=dependency.referenced_entity_name,
                    referenced_column_name=dependency.referenced_column_name,
                    resolution_status=resolution_status,
                    lineage_status=lineage_status,
                    automatic_join_allowed=False,
                    reason_codes=reason_codes,
                )
            )
    return edges


def _mark_bridge_candidates(
    *,
    nodes: list[QueryabilityNode],
    fk_edges: list[QueryabilityForeignKeyEdge],
) -> list[QueryabilityNode]:
    eligible_edges_by_node: dict[str, list[QueryabilityForeignKeyEdge]] = {}
    for edge in fk_edges:
        if (
            edge.enforcement_status == "enabled"
            and edge.validation_status == "trusted"
            and not edge.self_reference
        ):
            eligible_edges_by_node.setdefault(edge.from_node_key, []).append(edge)

    result: list[QueryabilityNode] = []
    for node in nodes:
        outgoing = eligible_edges_by_node.get(node.node_key, [])
        targets = {edge.to_node_key for edge in outgoing}
        fk_columns = {
            pair.from_column for edge in outgoing for pair in edge.column_pairs
        }
        bridge_candidate = (
            len(targets) >= 2
            and any(
                key.eligible_for_cardinality
                and len(key.columns) == len(fk_columns)
                and set(key.columns) == fk_columns
                for key in node.candidate_keys
            )
        )
        result.append(node.model_copy(update={"bridge_candidate": bridge_candidate}))
    return result


def _columns_are_unique(
    *,
    columns: list[str],
    candidate_keys: list[QueryabilityCandidateKey],
) -> bool:
    expected = set(columns)
    return any(
        key.eligible_for_cardinality
        and len(key.columns) == len(columns)
        and set(key.columns) == expected
        for key in candidate_keys
    )


def _view_lineage_status(
    *,
    snapshot: SchemaIntrospectionResult,
    table: SchemaTableMetadata,
) -> Literal["complete", "partial", "unavailable"]:
    if table.lineage_available is not True:
        return "unavailable"
    partial_codes = {
        "VIEW_LINEAGE_PARTIAL",
        "VIEW_LINEAGE_UNRESOLVED_REFERENCE",
    }
    if any(
        warning.code in partial_codes
        and warning.object_schema == table.table_schema
        and warning.object_name == table.name
        for warning in snapshot.coverage_warnings
    ):
        return "partial"
    return "complete"


def _resolve_lineage_target(
    *,
    snapshot: SchemaIntrospectionResult,
    dependency,
    nodes_by_object: dict[tuple[str, str], QueryabilityNode],
) -> tuple[
    Literal["resolved", "external", "unresolved"],
    QueryabilityNode | None,
]:
    if dependency.referenced_server_name:
        return "external", None
    if (
        dependency.referenced_database_name
        and dependency.referenced_database_name != snapshot.database_name
    ):
        return "external", None
    if (
        dependency.referenced_schema_name
        and dependency.referenced_entity_name
    ):
        node = nodes_by_object.get(
            (
                dependency.referenced_schema_name,
                dependency.referenced_entity_name,
            )
        )
        if node:
            return "resolved", node
    return "unresolved", None


def _lineage_reason_codes(
    *,
    dependency,
    resolution_status: str,
) -> list[str]:
    reasons = ["LINEAGE_NOT_JOIN_EVIDENCE"]
    if resolution_status == "external":
        reasons.append("LINEAGE_EXTERNAL_REFERENCE")
    elif resolution_status == "unresolved":
        reasons.append("LINEAGE_UNRESOLVED_REFERENCE")
    if dependency.is_incomplete:
        reasons.append("LINEAGE_INCOMPLETE")
    if dependency.is_ambiguous:
        reasons.append("LINEAGE_AMBIGUOUS")
    return sorted(reasons)


def _graph_input_payload(
    *,
    snapshot: SchemaIntrospectionResult,
    nodes: list[QueryabilityNode],
) -> dict[str, Any]:
    return {
        "schema_hash": snapshot.schema_hash,
        "coverage_status": snapshot.coverage_status,
        "coverage_warnings": [
            {
                "code": warning.code,
                "severity": warning.severity,
                "object_schema": warning.object_schema,
                "object_name": warning.object_name,
            }
            for warning in sorted(
                snapshot.coverage_warnings,
                key=lambda item: (
                    item.code,
                    item.object_schema or "",
                    item.object_name or "",
                ),
            )
        ],
        "nodes": [
            {
                "node_key": node.node_key,
                "object_type": node.object_type,
                "queryability_status": node.queryability_status,
                "bridge_candidate": node.bridge_candidate,
                "view_lineage_status": node.view_lineage_status,
                "candidate_keys": [
                    key.model_dump(mode="json") for key in node.candidate_keys
                ],
                "columns": [
                    {
                        "column_key": column.column_key,
                        "name": column.name,
                        "nullable": column.nullable,
                        "technical_role": column.technical_role,
                        "queryability_status": column.queryability_status,
                        "sensitivity": column.sensitivity,
                    }
                    for column in node.columns
                ],
            }
            for node in nodes
        ],
        "foreign_keys": [
            {
                "constraint_name": foreign_key.constraint_name,
                "from_schema": foreign_key.from_schema,
                "from_table": foreign_key.from_table,
                "from_columns": foreign_key.from_columns,
                "to_schema": foreign_key.to_schema,
                "to_table": foreign_key.to_table,
                "to_columns": foreign_key.to_columns,
                "is_disabled": foreign_key.is_disabled,
                "is_not_trusted": foreign_key.is_not_trusted,
                "verified_by_db": foreign_key.verified_by_db,
            }
            for foreign_key in sorted(
                snapshot.foreign_keys,
                key=lambda item: (
                    item.from_schema,
                    item.from_table,
                    item.constraint_name,
                ),
            )
        ],
        "view_lineage": [
            {
                "schema_name": table.table_schema,
                "object_name": table.name,
                "lineage_available": table.lineage_available,
                "dependencies": [
                    dependency.__dict__
                    for dependency in sorted(
                        table.view_lineage,
                        key=lambda item: (
                            item.source,
                            item.referencing_column or "",
                            item.referenced_server_name or "",
                            item.referenced_database_name or "",
                            item.referenced_schema_name or "",
                            item.referenced_entity_name or "",
                            item.referenced_column_name or "",
                        ),
                    )
                ],
            }
            for table in sorted(
                snapshot.tables,
                key=lambda item: (item.table_schema, item.name),
            )
            if table.table_type == "view"
        ],
    }


def _duplicate_object_keys(
    tables: list[SchemaTableMetadata],
) -> set[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    duplicates: set[tuple[str, str]] = set()
    for table in tables:
        key = (table.table_schema, table.name)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return duplicates


def _object_type(table: SchemaTableMetadata) -> Literal["table", "view"]:
    return "view" if table.table_type == "view" else "table"


def _node_key(
    *,
    database_name: str,
    schema_name: str,
    object_name: str,
    object_type: str,
) -> str:
    return _hash_json(
        {
            "database_name": database_name,
            "schema_name": schema_name,
            "object_name": object_name,
            "object_type": object_type,
        }
    )


def _column_sensitivity(
    column_name: str,
) -> tuple[
    Literal["none", "pii", "sensitive"],
    str,
]:
    tokens = _column_name_tokens(column_name)
    token_set = set(tokens)
    compact_name = "".join(tokens)
    if compact_name == "creditcardapprovalcode":
        return "sensitive", "PAYMENT_AUTHORIZATION_CODE"
    if any(token in {"password", "passwd", "pwd"} for token in tokens):
        return "sensitive", "CREDENTIAL_NAME"
    if any(token in {"hash", "salt"} for token in tokens):
        return "sensitive", "CREDENTIAL_DERIVATIVE_NAME"
    if any(
        token in {"secret", "token", "credential", "credentials"}
        for token in tokens
    ):
        return "sensitive", "SECRET_NAME"
    if "key" in token_set and token_set & {"api", "access", "private", "secret"}:
        return "sensitive", "SECRET_KEY_NAME"
    if any(token in {"email", "phone"} for token in tokens):
        return "pii", "CONTACT_IDENTIFIER"
    if compact_name in {
        "firstname",
        "middlename",
        "lastname",
        "fullname",
        "addressline",
        "addressline1",
        "addressline2",
    }:
        return "pii", "DIRECT_PERSON_IDENTIFIER"
    return "none", "NONE"


def _column_name_tokens(column_name: str) -> list[str]:
    with_boundaries = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", column_name)
    return [
        token
        for token in re.split(r"[^a-z0-9]+", with_boundaries.lower())
        if token
    ]


def _hash_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
