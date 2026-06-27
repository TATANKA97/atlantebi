import hashlib
import json
from datetime import UTC, date, datetime
from typing import Literal

from app.models import (
    QueryabilityForeignKeyEdge,
    QueryabilityGraphArtifact,
    QueryabilityNode,
    SemanticBusinessConcept,
    SemanticColumn,
    SemanticDimensionCompatibility,
    SemanticElementStatus,
    SemanticLayer,
    SemanticAmbiguity,
    SemanticMetric,
    SemanticPolicySnapshot,
    SemanticQualityIssue,
    SemanticQualityReport,
    SemanticRequiredMetricSpec,
    SemanticReviewPatch,
    SemanticRebaseDropReasonCode,
    SemanticRebaseDroppedColumn,
    SemanticRebaseDroppedMetric,
    SemanticRebaseDroppedTable,
    SemanticRebaseReport,
    SemanticRebaseResult,
    SemanticRelationship,
    SemanticTable,
    SemanticValidationIssue,
    SemanticValidationReport,
)


SEMANTIC_LAYER_CONTRACT_VERSION = "semantic_layer.v1"
DEFAULT_SEMANTIC_BUILDER_VERSION = "1.0.0"
DEFAULT_SEMANTIC_POLICY_VERSION = "1.0.0"
DEFAULT_SEMANTIC_VALIDATOR_VERSION = "1.0.0"

_SENSITIVITY_RANK = {"none": 0, "pii": 1, "sensitive": 2}
_NUMERIC_TYPES = {
    "bigint",
    "decimal",
    "float",
    "int",
    "money",
    "numeric",
    "real",
    "smallint",
    "smallmoney",
    "tinyint",
}
_AMBIGUITY_CODES = {
    "AMBIGUOUS_BUSINESS_CONCEPT",
    "AMBIGUOUS_METRIC_VARIANT",
    "DUPLICATE_METRIC_SYNONYM",
    "AI_FILTER_VALUE_UNVERIFIED",
    "METRIC_CURRENCY_UNRESOLVED",
}
_DECLARED_AMBIGUITY_CLARIFICATION_CODES = {
    "CUSTOMER_POPULATION_AMBIGUOUS",
    "MULTIPLE_SHORTEST_SAFE_PATHS",
}


def build_semantic_seed(
    *,
    graph: QueryabilityGraphArtifact,
    semantic_version_id: str,
    queryability_graph_version_id: str,
    version: int,
    semantic_policy: SemanticPolicySnapshot,
    builder_version: str = DEFAULT_SEMANTIC_BUILDER_VERSION,
    policy_version: str = DEFAULT_SEMANTIC_POLICY_VERSION,
    validator_version: str = DEFAULT_SEMANTIC_VALIDATOR_VERSION,
) -> SemanticLayer:
    if semantic_policy.policy_hash != compute_semantic_policy_hash(semantic_policy):
        raise ValueError("semantic policy hash is invalid")
    tables = sorted(
        [
            SemanticTable(
                node_key=node.node_key,
                schema_name=node.schema_name,
                object_name=node.object_name,
                object_type=node.object_type,
                status="system_seeded",
                included=node.queryability_status == "queryable",
                queryability_status=node.queryability_status,
            )
            for node in graph.nodes
        ],
        key=lambda table: table.node_key,
    )
    columns = sorted(
        [
            SemanticColumn(
                column_key=column.column_key,
                node_key=node.node_key,
                physical_name=column.name,
                native_type=column.native_type,
                normalized_type=column.normalized_type,
                technical_role=column.technical_role,
                nullable=column.nullable,
                status="system_seeded",
                included=(
                    node.queryability_status == "queryable"
                    and column.queryability_status == "queryable"
                ),
                queryability_status=column.queryability_status,
                inherited_sensitivity=column.sensitivity,
                sensitivity=column.sensitivity,
            )
            for node in graph.nodes
            for column in node.columns
        ],
        key=lambda column: column.column_key,
    )
    relationships = sorted(
        [
            SemanticRelationship(
                edge_key=edge.edge_key,
                from_node_key=edge.from_node_key,
                to_node_key=edge.to_node_key,
                status="system_seeded",
                enabled=True,
                relationship_shape=edge.relationship_shape,
                child_to_parent=edge.child_to_parent,
                parent_to_child=edge.parent_to_child,
                nullable_fk=edge.nullable_fk,
                self_reference=edge.self_reference,
            )
            for edge in graph.edges
            if isinstance(edge, QueryabilityForeignKeyEdge)
            and edge.automatic_join_allowed
            and edge.verified_by_db
            and edge.enforcement_status == "enabled"
            and edge.validation_status == "trusted"
        ],
        key=lambda relationship: relationship.edge_key,
    )
    report = SemanticValidationReport(
        status="not_validated",
        validator_version=validator_version,
    )
    layer = SemanticLayer(
        contract_version=SEMANTIC_LAYER_CONTRACT_VERSION,
        tenant_id=graph.tenant_id,
        connection_id=graph.connection_id,
        semantic_version_id=semantic_version_id,
        queryability_graph_version_id=queryability_graph_version_id,
        base_graph_hash=graph.graph_hash,
        base_policy_hash=semantic_policy.policy_hash,
        semantic_policy_snapshot=semantic_policy,
        version=version,
        status="draft",
        freshness="fresh",
        builder_version=builder_version,
        validator_version=validator_version,
        policy_version=policy_version,
        revision=1,
        semantic_hash="0" * 64,
        tables=tables,
        columns=columns,
        relationships=relationships,
        business_concepts=[],
        ambiguities=[],
        metrics=[],
        quality_report=SemanticQualityReport(status="not_evaluated"),
        validation_report=report,
    )
    return layer.model_copy(update={"semantic_hash": compute_semantic_hash(layer)})


def compute_metric_definition_hash(metric: SemanticMetric) -> str:
    return _hash_json(
        {
            "source_table_key": metric.source_table_key,
            "aggregation": metric.aggregation,
            "measure_column_key": metric.measure_column_key,
            "grain_table_key": metric.grain_table_key,
            "grain_column_keys": sorted(metric.grain_column_keys),
            "aggregation_level": metric.aggregation_level,
            "additivity": metric.additivity,
            "default_date_column_key": metric.default_date_column_key,
            "required_join_edge_keys": metric.required_join_edge_keys,
            "common_dimension_compatibility": sorted(
                [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in metric.common_dimension_compatibility
                ],
                key=_dimension_compatibility_sort_key,
            ),
            "dimension_policy": metric.dimension_policy.model_dump(mode="json"),
            "filters": sorted(
                [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in metric.filters
                ],
                key=lambda item: (
                    item["column_key"],
                    item["operator"],
                    json.dumps(item.get("value"), sort_keys=True),
                ),
            ),
        }
    )


def compute_semantic_policy_hash(policy: SemanticPolicySnapshot) -> str:
    payload = policy.model_dump(mode="json", exclude_none=False)
    payload.pop("policy_hash", None)
    return _hash_json(payload)


def compute_semantic_hash(layer: SemanticLayer) -> str:
    return _hash_json(
        {
            "contract_version": layer.contract_version,
            "base_graph_hash": layer.base_graph_hash,
            "base_policy_hash": layer.base_policy_hash,
            "semantic_policy_snapshot": layer.semantic_policy_snapshot.model_dump(
                mode="json",
                exclude_none=False,
            ),
            "builder_version": layer.builder_version,
            "policy_version": layer.policy_version,
            "tables": _canonical_models(
                layer.tables,
                "node_key",
                unordered_fields={"synonyms"},
            ),
            "columns": _canonical_models(
                layer.columns,
                "column_key",
                unordered_fields={"synonyms"},
            ),
            "relationships": _canonical_models(layer.relationships, "edge_key"),
            "business_concepts": _canonical_models(
                layer.business_concepts,
                "business_concept_key",
                unordered_fields={"synonyms"},
            ),
            "ambiguities": _canonical_models(
                layer.ambiguities,
                "ambiguity_key",
            ),
            "metrics": _canonical_models(
                layer.metrics,
                "metric_key",
                unordered_fields={
                    "eligibility_reasons",
                    "grain_column_keys",
                    "preferred_for_dimensions",
                    "preferred_for_grains",
                    "synonyms",
                    "validation_warnings",
                },
            ),
        }
    )


def rebase_semantic_layer(
    *,
    source_layer: SemanticLayer,
    target_graph: QueryabilityGraphArtifact,
    semantic_version_id: str,
    queryability_graph_version_id: str,
    version: int,
    semantic_policy: SemanticPolicySnapshot,
    validated_at: datetime | None = None,
) -> SemanticRebaseResult:
    if source_layer.semantic_hash != compute_semantic_hash(source_layer):
        raise ValueError("source semantic layer hash is invalid")

    seed = build_semantic_seed(
        graph=target_graph,
        semantic_version_id=semantic_version_id,
        queryability_graph_version_id=queryability_graph_version_id,
        version=version,
        semantic_policy=semantic_policy,
    )
    carried_table_keys: list[str] = []
    dropped_tables: list[SemanticRebaseDroppedTable] = []
    carried_column_keys: list[str] = []
    dropped_columns: list[SemanticRebaseDroppedColumn] = []
    carried_business_concept_keys: list[str] = []
    carried_metric_keys: list[str] = []
    dropped_metrics: list[SemanticRebaseDroppedMetric] = []

    source_tables = {table.node_key: table for table in source_layer.tables}
    target_table_keys = {table.node_key for table in seed.tables}
    tables = [
        _carry_table(
            seed_table,
            source_tables.get(seed_table.node_key),
            carried_table_keys,
        )
        for seed_table in seed.tables
    ]
    dropped_tables.extend(
        SemanticRebaseDroppedTable(
            item_type="table",
            item_key=table_key,
            reason_codes=["TARGET_KEY_MISSING"],
        )
        for table_key in sorted(set(source_tables) - target_table_keys)
    )

    source_columns = {
        column.column_key: column for column in source_layer.columns
    }
    target_column_keys = {column.column_key for column in seed.columns}
    columns = [
        _carry_column(
            seed_column,
            source_columns.get(seed_column.column_key),
            carried_column_keys,
        )
        for seed_column in seed.columns
    ]
    dropped_columns.extend(
        SemanticRebaseDroppedColumn(
            item_type="column",
            item_key=column_key,
            reason_codes=["TARGET_KEY_MISSING"],
        )
        for column_key in sorted(set(source_columns) - target_column_keys)
    )

    source_relationships = {
        relationship.edge_key: relationship
        for relationship in source_layer.relationships
    }
    relationships = [
        _carry_relationship(
            seed_relationship,
            source_relationships.get(seed_relationship.edge_key),
        )
        for seed_relationship in seed.relationships
    ]

    concepts = [
        _restore_concept_status(concept)
        for concept in source_layer.business_concepts
    ]
    carried_business_concept_keys.extend(
        str(concept.business_concept_key) for concept in concepts
    )
    concept_keys = {str(concept.business_concept_key) for concept in concepts}

    usable_table_keys = {
        table.node_key
        for table in tables
        if table.included and _semantic_status_is_enabled(table.status)
    }
    usable_column_keys = {
        column.column_key
        for column in columns
        if column.included
        and _semantic_status_is_enabled(column.status)
        and column.node_key in usable_table_keys
    }
    usable_edge_keys = {
        relationship.edge_key
        for relationship in relationships
        if relationship.enabled
        and _semantic_status_is_enabled(relationship.status)
    }
    target_fk_edge_keys = {
        edge.edge_key
        for edge in target_graph.edges
        if isinstance(edge, QueryabilityForeignKeyEdge)
    }

    metrics: list[SemanticMetric] = []
    for metric in source_layer.metrics:
        reason_codes = _metric_rebase_drop_reasons(
            metric=metric,
            concept_keys=concept_keys,
            target_table_keys=target_table_keys,
            usable_table_keys=usable_table_keys,
            target_column_keys=target_column_keys,
            usable_column_keys=usable_column_keys,
            target_fk_edge_keys=target_fk_edge_keys,
            usable_edge_keys=usable_edge_keys,
        )
        if reason_codes:
            dropped_metrics.append(
                SemanticRebaseDroppedMetric(
                    item_type="metric",
                    item_key=metric.metric_key,
                    reason_codes=reason_codes,
                )
            )
            continue
        restored_metric = _restore_metric_status(metric)
        metrics.append(restored_metric)
        carried_metric_keys.append(str(metric.metric_key))

    carried_metric_key_set = {str(metric.metric_key) for metric in metrics}
    ambiguities = []
    for ambiguity in source_layer.ambiguities:
        if not _ambiguity_target_survives(
            ambiguity=ambiguity,
            table_keys=target_table_keys,
            column_keys=target_column_keys,
            concept_keys=concept_keys,
            metric_keys=carried_metric_key_set,
        ):
            continue
        ambiguities.append(ambiguity)

    candidate = seed.model_copy(
        update={
            "status": "draft",
            "freshness": "fresh",
            "revision": 1,
            "ai_model_version": source_layer.ai_model_version,
            "ai_prompt_version": source_layer.ai_prompt_version,
            "tables": tables,
            "columns": columns,
            "relationships": relationships,
            "business_concepts": concepts,
            "ambiguities": ambiguities,
            "metrics": metrics,
        }
    )
    candidate = candidate.model_copy(
        update={"semantic_hash": compute_semantic_hash(candidate)}
    )

    first_validation = validate_semantic_layer(
        layer=candidate,
        graph=target_graph,
        semantic_policy=semantic_policy,
        validated_at=validated_at,
    )
    blocked_metric_keys = {
        issue.target_key
        for issue in first_validation.validation_report.blocking_errors
        if issue.target_type == "metric"
    }
    if blocked_metric_keys:
        metrics = [
            metric
            for metric in metrics
            if str(metric.metric_key) not in blocked_metric_keys
        ]
        carried_metric_keys = [
            metric_key
            for metric_key in carried_metric_keys
            if metric_key not in blocked_metric_keys
        ]
        dropped_metrics.extend(
            SemanticRebaseDroppedMetric(
                item_type="metric",
                item_key=metric_key,
                reason_codes=["INVALID_AFTER_REBASE"],
            )
            for metric_key in sorted(blocked_metric_keys)
        )
        blocked_ambiguity_keys = {
            str(ambiguity.ambiguity_key)
            for ambiguity in ambiguities
            if ambiguity.target_type == "metric"
            and ambiguity.target_key in blocked_metric_keys
        }
        ambiguities = [
            ambiguity
            for ambiguity in ambiguities
            if str(ambiguity.ambiguity_key) not in blocked_ambiguity_keys
        ]
        candidate = candidate.model_copy(
            update={
                "metrics": metrics,
                "ambiguities": ambiguities,
            }
        )
        candidate = candidate.model_copy(
            update={"semantic_hash": compute_semantic_hash(candidate)}
        )

    validated = validate_semantic_layer(
        layer=candidate,
        graph=target_graph,
        semantic_policy=semantic_policy,
        validated_at=validated_at,
    )
    rebased = validated.model_copy(update={"status": "draft", "freshness": "fresh"})
    rebased = rebased.model_copy(
        update={"semantic_hash": compute_semantic_hash(rebased)}
    )
    return SemanticRebaseResult(
        semantic_layer=rebased,
        rebase_report=SemanticRebaseReport(
            carried_table_keys=sorted(carried_table_keys),
            dropped_tables=sorted(
                dropped_tables,
                key=lambda item: item.item_key,
            ),
            carried_column_keys=sorted(carried_column_keys),
            dropped_columns=sorted(
                dropped_columns,
                key=lambda item: item.item_key,
            ),
            carried_business_concept_keys=sorted(
                carried_business_concept_keys
            ),
            dropped_business_concepts=[],
            carried_metric_keys=sorted(carried_metric_keys),
            dropped_metrics=sorted(
                dropped_metrics,
                key=lambda item: str(item.item_key),
            ),
        ),
    )


def validate_semantic_layer(
    *,
    layer: SemanticLayer,
    graph: QueryabilityGraphArtifact,
    semantic_policy: SemanticPolicySnapshot | None = None,
    validated_at: datetime | None = None,
) -> SemanticLayer:
    current_policy = semantic_policy or layer.semantic_policy_snapshot
    issues: list[SemanticValidationIssue] = []
    nodes = {node.node_key: node for node in graph.nodes}
    graph_columns = {
        column.column_key: (node, column)
        for node in graph.nodes
        for column in node.columns
    }
    fk_edges = {
        edge.edge_key: edge
        for edge in graph.edges
        if isinstance(edge, QueryabilityForeignKeyEdge)
    }
    semantic_tables = {table.node_key: table for table in layer.tables}
    semantic_columns = {column.column_key: column for column in layer.columns}
    concepts = {
        str(concept.business_concept_key): concept
        for concept in layer.business_concepts
    }
    ambiguities = {
        str(ambiguity.ambiguity_key): ambiguity
        for ambiguity in layer.ambiguities
    }
    semantic_relationships = {
        relationship.edge_key: relationship
        for relationship in layer.relationships
    }
    routing_edges = {
        edge_key: edge
        for edge_key, edge in fk_edges.items()
        if _semantic_relationship_is_available(
            semantic_relationships.get(edge_key),
            edge,
        )
    }

    if layer.semantic_hash != compute_semantic_hash(layer):
        _issue(
            issues,
            "SEMANTIC_HASH_MISMATCH",
            "blocking",
            "layer",
            str(layer.semantic_version_id),
            "Semantic hash does not match the canonical artifact.",
        )
    if layer.base_graph_hash != graph.graph_hash:
        _issue(
            issues,
            "BASE_GRAPH_HASH_MISMATCH",
            "blocking",
            "layer",
            str(layer.semantic_version_id),
            "Semantic layer base graph hash does not match the supplied graph.",
        )
    policy_hash_valid = (
        layer.base_policy_hash == layer.semantic_policy_snapshot.policy_hash
        and layer.base_policy_hash
        == compute_semantic_policy_hash(layer.semantic_policy_snapshot)
    )
    if not policy_hash_valid:
        _issue(
            issues,
            "SEMANTIC_POLICY_HASH_MISMATCH",
            "blocking",
            "layer",
            str(layer.semantic_version_id),
            "Semantic policy hash does not match the canonical policy snapshot.",
        )
    if current_policy.policy_hash != compute_semantic_policy_hash(current_policy):
        _issue(
            issues,
            "CURRENT_SEMANTIC_POLICY_HASH_MISMATCH",
            "blocking",
            "layer",
            str(layer.semantic_version_id),
            "Current semantic policy hash is invalid.",
        )
    if layer.tenant_id != graph.tenant_id or layer.connection_id != graph.connection_id:
        _issue(
            issues,
            "GRAPH_SCOPE_MISMATCH",
            "blocking",
            "layer",
            str(layer.semantic_version_id),
            "Semantic layer tenant or connection does not match the graph.",
        )
    if graph.status == "blocked":
        _issue(
            issues,
            "QUERYABILITY_GRAPH_BLOCKED",
            "blocking",
            "layer",
            str(layer.semantic_version_id),
            "Blocked Queryability Graph cannot produce an eligible semantic layer.",
        )
    elif graph.status == "partial":
        _issue(
            issues,
            "QUERYABILITY_GRAPH_PARTIAL",
            "warning",
            "layer",
            str(layer.semantic_version_id),
            "Queryability Graph is usable but has non-blocking coverage gaps.",
        )

    _validate_unique_keys(
        issues,
        [table.node_key for table in layer.tables],
        "DUPLICATE_SEMANTIC_TABLE",
        "table",
    )
    _validate_unique_keys(
        issues,
        [column.column_key for column in layer.columns],
        "DUPLICATE_SEMANTIC_COLUMN",
        "column",
    )
    _validate_unique_keys(
        issues,
        [relationship.edge_key for relationship in layer.relationships],
        "DUPLICATE_SEMANTIC_RELATIONSHIP",
        "relationship",
    )
    _validate_unique_keys(
        issues,
        [str(metric.metric_key) for metric in layer.metrics],
        "DUPLICATE_SEMANTIC_METRIC",
        "metric",
    )
    _validate_unique_keys(
        issues,
        [
            str(concept.business_concept_key)
            for concept in layer.business_concepts
        ],
        "DUPLICATE_BUSINESS_CONCEPT",
        "business_concept",
    )
    _validate_unique_keys(
        issues,
        list(ambiguities),
        "DUPLICATE_SEMANTIC_AMBIGUITY",
        "ambiguity",
    )
    _validate_graph_coverage(
        issues=issues,
        layer=layer,
        nodes=nodes,
        graph_columns=graph_columns,
        fk_edges=fk_edges,
    )

    for table in layer.tables:
        graph_node = nodes.get(table.node_key)
        if graph_node is None:
            _issue(
                issues,
                "SEMANTIC_TABLE_NOT_IN_GRAPH",
                "blocking",
                "table",
                table.node_key,
                "Semantic table does not reference a graph node.",
            )
            continue
        if table.included and graph_node.queryability_status != "queryable":
            _issue(
                issues,
                "EXCLUDED_TABLE_REENABLED",
                "blocking",
                "table",
                table.node_key,
                "Semantic layer cannot re-enable an excluded graph node.",
            )
        if table.included and not _semantic_status_is_enabled(table.status):
            _issue(
                issues,
                "TABLE_STATUS_CONFLICT",
                "blocking",
                "table",
                table.node_key,
                "Rejected, disabled, or stale tables cannot remain included.",
            )
        if (
            table.schema_name != graph_node.schema_name
            or table.object_name != graph_node.object_name
            or table.object_type != graph_node.object_type
            or table.queryability_status != graph_node.queryability_status
        ):
            _issue(
                issues,
                "SEMANTIC_TABLE_TECHNICAL_METADATA_MISMATCH",
                "blocking",
                "table",
                table.node_key,
                "Semantic table technical metadata must match the graph node.",
            )

    for column in layer.columns:
        graph_item = graph_columns.get(column.column_key)
        if graph_item is None:
            _issue(
                issues,
                "SEMANTIC_COLUMN_NOT_IN_GRAPH",
                "blocking",
                "column",
                column.column_key,
                "Semantic column does not reference a graph column.",
            )
            continue
        graph_node, graph_column = graph_item
        if column.node_key != graph_node.node_key:
            _issue(
                issues,
                "SEMANTIC_COLUMN_NODE_MISMATCH",
                "blocking",
                "column",
                column.column_key,
                "Semantic column belongs to a different graph node.",
            )
        semantic_table = semantic_tables.get(column.node_key)
        if (
            column.included
            and semantic_table is not None
            and not semantic_table.included
        ):
            _issue(
                issues,
                "COLUMN_INCLUDED_IN_EXCLUDED_TABLE",
                "blocking",
                "column",
                column.column_key,
                "A semantic column cannot remain included when its table is excluded.",
            )
        if column.included and not _semantic_status_is_enabled(column.status):
            _issue(
                issues,
                "COLUMN_STATUS_CONFLICT",
                "blocking",
                "column",
                column.column_key,
                "Rejected, disabled, or stale columns cannot remain included.",
            )
        if column.included and (
            graph_node.queryability_status != "queryable"
            or graph_column.queryability_status != "queryable"
        ):
            _issue(
                issues,
                "EXCLUDED_COLUMN_REENABLED",
                "blocking",
                "column",
                column.column_key,
                "Semantic layer cannot re-enable an excluded graph column.",
            )
        if _SENSITIVITY_RANK[column.sensitivity] < _SENSITIVITY_RANK[graph_column.sensitivity]:
            _issue(
                issues,
                "SENSITIVITY_WEAKENED",
                "blocking",
                "column",
                column.column_key,
                "Semantic layer cannot weaken inherited sensitivity.",
            )
        if (
            column.physical_name != graph_column.name
            or column.native_type != graph_column.native_type
            or column.normalized_type != graph_column.normalized_type
            or column.technical_role != graph_column.technical_role
            or column.nullable != graph_column.nullable
            or column.queryability_status != graph_column.queryability_status
            or column.inherited_sensitivity != graph_column.sensitivity
        ):
            _issue(
                issues,
                "SEMANTIC_COLUMN_TECHNICAL_METADATA_MISMATCH",
                "blocking",
                "column",
                column.column_key,
                "Semantic column technical metadata must match the graph column.",
            )

    for relationship in layer.relationships:
        edge = fk_edges.get(relationship.edge_key)
        if edge is None:
            _issue(
                issues,
                "RELATIONSHIP_NOT_GRAPH_FK",
                "blocking",
                "relationship",
                relationship.edge_key,
                "Semantic relationships must reference a graph FK edge.",
            )
            continue
        if not _edge_is_automatic(edge):
            _issue(
                issues,
                "RELATIONSHIP_NOT_TRUSTED",
                "blocking",
                "relationship",
                relationship.edge_key,
                "Semantic relationships must use enabled and trusted DB FKs.",
            )
        if relationship.enabled and not _semantic_status_is_enabled(
            relationship.status
        ):
            _issue(
                issues,
                "RELATIONSHIP_STATUS_CONFLICT",
                "blocking",
                "relationship",
                relationship.edge_key,
                "Rejected, disabled, or stale relationships cannot remain enabled.",
            )
        if (
            relationship.from_node_key != edge.from_node_key
            or relationship.to_node_key != edge.to_node_key
        ):
            _issue(
                issues,
                "RELATIONSHIP_ENDPOINT_MISMATCH",
                "blocking",
                "relationship",
                relationship.edge_key,
                "Semantic relationship endpoints differ from the graph FK.",
            )
        if (
            relationship.relationship_shape != edge.relationship_shape
            or relationship.child_to_parent != edge.child_to_parent
            or relationship.parent_to_child != edge.parent_to_child
            or relationship.nullable_fk != edge.nullable_fk
            or relationship.self_reference != edge.self_reference
        ):
            _issue(
                issues,
                "RELATIONSHIP_TECHNICAL_METADATA_MISMATCH",
                "blocking",
                "relationship",
                relationship.edge_key,
                "Semantic relationship metadata must match the graph FK.",
            )

    concept_names: dict[str, list[str]] = {}
    allowed_concepts = {
        item.concept_ref: item
        for item in layer.semantic_policy_snapshot.required_concepts
    }
    for concept in layer.business_concepts:
        key = str(concept.business_concept_key)
        if concept.canonical_name not in allowed_concepts:
            _issue(
                issues,
                "BUSINESS_CONCEPT_NOT_ALLOWLISTED",
                "blocking",
                "business_concept",
                key,
                "Business concept is not present in the semantic policy allowlist.",
            )
        if (
            concept.status == "human_verified"
            and concept.provenance != "human"
        ) or (concept.status == "ai_proposed" and concept.provenance != "ai"):
            _issue(
                issues,
                "SEMANTIC_PROVENANCE_STATUS_MISMATCH",
                "blocking",
                "business_concept",
                key,
                "Semantic concept status is inconsistent with its provenance.",
            )
        concept_names.setdefault(concept.canonical_name, []).append(key)
    ambiguous_concept_keys: set[str] = set()
    for keys in concept_names.values():
        unique_keys = set(keys)
        if len(unique_keys) <= 1:
            continue
        ambiguous_concept_keys.update(unique_keys)
        for key in unique_keys:
            _issue(
                issues,
                "AMBIGUOUS_BUSINESS_CONCEPT",
                "warning",
                "business_concept",
                key,
                "Multiple business concepts use the same canonical name.",
            )

    metrics = [
        _validate_metric(
            metric=metric,
            issues=issues,
            nodes=nodes,
            graph_columns=graph_columns,
            semantic_tables=semantic_tables,
            semantic_columns=semantic_columns,
            fk_edges=routing_edges,
            concepts=concepts,
            missing_currency_behavior=(
                layer.semantic_policy_snapshot.missing_currency_behavior
            ),
        )
        for metric in layer.metrics
    ]
    for metric in metrics:
        concept = concepts.get(str(metric.business_concept_key))
        concept_policy = (
            allowed_concepts.get(concept.canonical_name)
            if concept is not None
            else None
        )
        if (
            concept_policy is not None
            and concept_policy.preferred_variants
            and metric.metric_variant not in concept_policy.preferred_variants
        ):
            _issue(
                issues,
                "METRIC_VARIANT_NOT_ALLOWLISTED",
                "blocking",
                "metric",
                str(metric.metric_key),
                "Metric variant is not allowed by its semantic concept policy.",
            )
        if (
            metric.status == "human_verified"
            and metric.provenance != "human"
        ) or (metric.status == "ai_proposed" and metric.provenance != "ai"):
            _issue(
                issues,
                "SEMANTIC_PROVENANCE_STATUS_MISMATCH",
                "blocking",
                "metric",
                str(metric.metric_key),
                "Semantic metric status is inconsistent with its provenance.",
            )
    _validate_declared_ambiguities(
        issues=issues,
        ambiguities=list(ambiguities.values()),
        semantic_tables=semantic_tables,
        semantic_columns=semantic_columns,
        concepts=concepts,
        metrics=metrics,
    )
    for metric in metrics:
        if str(metric.business_concept_key) in ambiguous_concept_keys:
            _issue_once(
                issues,
                "AMBIGUOUS_BUSINESS_CONCEPT",
                "warning",
                "metric",
                str(metric.metric_key),
                "Metric references an ambiguous business concept.",
            )
    _validate_metric_names_and_variants(issues, metrics)
    global_blocking_codes = sorted(
        {
            issue.code
            for issue in issues
            if issue.severity == "blocking" and issue.target_type != "metric"
        }
    )
    metrics = [
        _apply_metric_eligibility(
            metric,
            issues,
            global_blocking_codes=global_blocking_codes,
        )
        for metric in metrics
    ]

    quality_report = _evaluate_quality_gate(
        layer=layer,
        metrics=metrics,
        issues=issues,
    )

    blocking = sorted(
        [issue for issue in issues if issue.severity == "blocking"],
        key=_issue_sort_key,
    )
    warnings = sorted(
        [issue for issue in issues if issue.severity == "warning"],
        key=_issue_sort_key,
    )
    info = sorted(
        [issue for issue in issues if issue.severity == "info"],
        key=_issue_sort_key,
    )
    report_status: Literal["valid", "valid_with_warnings", "blocked"]
    if blocking:
        report_status = "blocked"
    elif warnings:
        report_status = "valid_with_warnings"
    else:
        report_status = "valid"
    report = SemanticValidationReport(
        status=report_status,
        blocking_errors=blocking,
        warnings=warnings,
        info=info,
        validated_revision=layer.revision,
        validated_at=(validated_at or datetime.now(UTC)).isoformat(),
        validator_version=layer.validator_version,
    )
    updated = layer.model_copy(
        update={
            "status": (
                "proposed"
                if layer.status == "draft" and report_status != "blocked"
                else layer.status
            ),
            "freshness": (
                "fresh"
                if layer.base_graph_hash == graph.graph_hash
                and layer.base_policy_hash == current_policy.policy_hash
                else "stale"
            ),
            "metrics": metrics,
            "quality_report": quality_report,
            "validation_report": report,
        }
    )
    return updated.model_copy(
        update={"semantic_hash": compute_semantic_hash(updated)}
    )


def _evaluate_quality_gate(
    *,
    layer: SemanticLayer,
    metrics: list[SemanticMetric],
    issues: list[SemanticValidationIssue],
) -> SemanticQualityReport:
    policy = layer.semantic_policy_snapshot
    quality_issues = list(layer.quality_report.issues)
    concept_keys = {
        concept.canonical_name: concept.business_concept_key
        for concept in layer.business_concepts
    }
    satisfied_specs = 0
    compiler_eligible_required = 0

    for spec in policy.required_metric_specs:
        concept_key = concept_keys.get(spec.business_concept_ref)
        matches = [
            metric
            for metric in metrics
            if concept_key is not None
            and metric.business_concept_key == concept_key
            and metric.metric_variant == spec.expected_variant
            and _metric_matches_quality_spec(metric, spec)
        ]
        if not matches:
            quality_issues.append(
                SemanticQualityIssue(
                    code="REQUIRED_METRIC_SPEC_UNSATISFIED",
                    severity="blocking",
                    message="No metric satisfies the configured quality profile spec.",
                    spec_key=spec.spec_key,
                )
            )
            continue

        metric = matches[0]
        expectation_failures = _quality_dimension_expectation_failures(metric, spec)
        if expectation_failures:
            quality_issues.append(
                SemanticQualityIssue(
                    code="REQUIRED_METRIC_DIMENSION_POLICY_UNSATISFIED",
                    severity="blocking",
                    message=(
                        "Metric does not satisfy "
                        f"{len(expectation_failures)} configured dimension safety "
                        "expectation(s)."
                    ),
                    spec_key=spec.spec_key,
                    metric_key=metric.metric_key,
                )
            )
            continue

        satisfied_specs += 1
        if metric.compiler_eligibility not in spec.allowed_eligibility:
            quality_issues.append(
                SemanticQualityIssue(
                    code="REQUIRED_METRIC_ELIGIBILITY_UNSATISFIED",
                    severity="blocking" if spec.required_for_activation else "warning",
                    message=(
                        "Metric compiler eligibility is not allowed by its quality spec."
                    ),
                    spec_key=spec.spec_key,
                    metric_key=metric.metric_key,
                )
            )
        elif spec.required_for_activation:
            compiler_eligible_required += 1

    metrics_by_concept = {
        concept_key: [
            metric for metric in metrics if metric.business_concept_key == concept_key
        ]
        for concept_key in concept_keys.values()
    }
    compiler_eligible = {
        "eligible",
        "eligible_with_disclosure",
    }
    for concept_policy in policy.required_concepts:
        concept_key = concept_keys.get(concept_policy.concept_ref)
        concept_metrics = metrics_by_concept.get(concept_key, [])
        if concept_policy.required and not concept_metrics:
            quality_issues.append(
                SemanticQualityIssue(
                    code="REQUIRED_CONCEPT_UNSATISFIED",
                    severity="blocking",
                    message=(
                        "Required semantic concept has no metric candidate or synthesis."
                    ),
                )
            )
        if concept_policy.required_for_activation and not any(
            metric.compiler_eligibility in compiler_eligible
            for metric in concept_metrics
        ):
            quality_issues.append(
                SemanticQualityIssue(
                    code="ACTIVATION_CONCEPT_NOT_ELIGIBLE",
                    severity="blocking",
                    message=(
                        "Activation-required semantic concept has no compiler-eligible metric."
                    ),
                )
            )

    eligible_count = sum(
        metric.compiler_eligibility in compiler_eligible for metric in metrics
    )
    if eligible_count < policy.minimum_eligible_metrics:
        quality_issues.append(
            SemanticQualityIssue(
                code="MINIMUM_ELIGIBLE_METRICS_UNSATISFIED",
                severity="blocking",
                message=(
                    "Semantic layer does not meet the configured minimum eligible metrics."
                ),
            )
        )

    quality_issues = sorted(
        quality_issues,
        key=lambda item: (
            {"blocking": 0, "warning": 1, "info": 2}[item.severity],
            item.code,
            item.spec_key or "",
            str(item.metric_key or ""),
        ),
    )
    status = (
        "blocked"
        if any(issue.severity == "blocking" for issue in quality_issues)
        else "passed"
    )
    if status == "blocked":
        _issue_once(
            issues,
            "SEMANTIC_QUALITY_GATE_BLOCKED",
            "blocking",
            "layer",
            str(layer.semantic_version_id),
            "Semantic quality profile requirements are not satisfied.",
        )
    return SemanticQualityReport(
        status=status,
        issues=quality_issues,
        required_specs_count=len(policy.required_metric_specs),
        satisfied_specs_count=satisfied_specs,
        compiler_eligible_required_count=compiler_eligible_required,
        rejected_candidates=layer.quality_report.rejected_candidates,
    )


def _metric_matches_quality_spec(
    metric: SemanticMetric,
    spec: SemanticRequiredMetricSpec,
) -> bool:
    return (
        metric.source_table_key == spec.source_table_key
        and metric.aggregation == spec.aggregation
        and metric.measure_column_key == spec.measure_column_key
        and sorted(metric.grain_column_keys) == sorted(spec.grain_column_keys)
        and metric.default_date_column_key == spec.default_date_column_key
        and metric.format.value_type == spec.value_type
    )


def _quality_dimension_expectation_failures(
    metric: SemanticMetric,
    spec: SemanticRequiredMetricSpec,
) -> list[str]:
    compatibilities = {
        item.dimension_column_key: item.safety
        for item in metric.common_dimension_compatibility
    }
    return [
        expectation.dimension_column_key
        for expectation in spec.dimension_expectations
        if compatibilities.get(expectation.dimension_column_key)
        != expectation.expected_safety
    ]


def review_semantic_layer(
    *,
    source_layer: SemanticLayer,
    graph: QueryabilityGraphArtifact,
    semantic_policy: SemanticPolicySnapshot | None = None,
    patch: SemanticReviewPatch,
    validated_at: datetime | None = None,
) -> SemanticLayer:
    if source_layer.semantic_hash != compute_semantic_hash(source_layer):
        raise ValueError("source semantic layer hash is invalid")
    current_policy = semantic_policy or source_layer.semantic_policy_snapshot

    table_patches = _unique_review_patches(
        patch.tables,
        "node_key",
        "table review patch",
    )
    column_patches = _unique_review_patches(
        patch.columns,
        "column_key",
        "column review patch",
    )
    concept_patches = _unique_review_patches(
        patch.business_concepts,
        "business_concept_key",
        "business concept review patch",
    )
    metric_patches = _unique_review_patches(
        patch.metrics,
        "metric_key",
        "metric review patch",
    )
    ambiguity_patches = _unique_review_patches(
        patch.ambiguities,
        "ambiguity_key",
        "ambiguity review patch",
    )

    _reject_missing_review_targets(
        table_patches,
        {table.node_key for table in source_layer.tables},
        "table",
    )
    _reject_missing_review_targets(
        column_patches,
        {column.column_key for column in source_layer.columns},
        "column",
    )
    _reject_missing_review_targets(
        concept_patches,
        {
            str(concept.business_concept_key)
            for concept in source_layer.business_concepts
        },
        "business concept",
    )
    _reject_missing_review_targets(
        metric_patches,
        {str(metric.metric_key) for metric in source_layer.metrics},
        "metric",
    )
    _reject_missing_review_targets(
        ambiguity_patches,
        {
            str(ambiguity.ambiguity_key)
            for ambiguity in source_layer.ambiguities
        },
        "ambiguity",
    )

    tables = [
        _apply_review_patch(
            table,
            table_patches.get(table.node_key),
        )
        for table in source_layer.tables
    ]
    columns = [
        _apply_review_patch(
            column,
            column_patches.get(column.column_key),
        )
        for column in source_layer.columns
    ]
    concepts = [
        _apply_review_patch(
            concept,
            concept_patches.get(str(concept.business_concept_key)),
            force_provenance="human",
        )
        for concept in source_layer.business_concepts
    ]
    metrics = [
        _apply_metric_review_patch(
            metric=metric,
            patch=metric_patches.get(str(metric.metric_key)),
            graph=graph,
        )
        for metric in source_layer.metrics
    ]
    ambiguities = [
        _apply_review_patch(
            ambiguity,
            ambiguity_patches.get(str(ambiguity.ambiguity_key)),
            force_provenance="human",
        )
        for ambiguity in source_layer.ambiguities
    ]
    candidate = source_layer.model_copy(
        update={
            "status": "draft",
            "revision": source_layer.revision + 1,
            "tables": tables,
            "columns": columns,
            "business_concepts": concepts,
            "metrics": metrics,
            "ambiguities": ambiguities,
            "validation_report": SemanticValidationReport(
                status="not_validated",
                validator_version=source_layer.validator_version,
            ),
        }
    )
    candidate = SemanticLayer.model_validate(candidate.model_dump())
    candidate = candidate.model_copy(
        update={"semantic_hash": compute_semantic_hash(candidate)}
    )
    return validate_semantic_layer(
        layer=candidate,
        graph=graph,
        semantic_policy=current_policy,
        validated_at=validated_at,
    )


def _unique_review_patches(items, key_name: str, label: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in items:
        key = str(getattr(item, key_name))
        if key in result:
            raise ValueError(f"duplicate {label}: {key}")
        result[key] = item
    return result


def _reject_missing_review_targets(
    patches: dict[str, object],
    existing_keys: set[str],
    label: str,
) -> None:
    missing = sorted(set(patches) - existing_keys)
    if missing:
        raise ValueError(f"{label} review target not found: {missing[0]}")


def _apply_review_patch(
    item,
    patch,
    *,
    force_provenance: str | None = None,
):
    if patch is None:
        return item
    updates = patch.model_dump(exclude_unset=True, exclude_none=False)
    for identity_key in (
        "node_key",
        "column_key",
        "business_concept_key",
        "metric_key",
        "ambiguity_key",
    ):
        updates.pop(identity_key, None)
    if force_provenance is not None:
        updates["provenance"] = force_provenance
    if updates.get("status") in {"disabled", "rejected"}:
        if hasattr(item, "included"):
            updates["included"] = False
        if hasattr(item, "enabled"):
            updates["enabled"] = False
    return item.model_copy(update=updates)


def _apply_metric_review_patch(
    *,
    metric: SemanticMetric,
    patch,
    graph: QueryabilityGraphArtifact,
) -> SemanticMetric:
    if patch is None:
        return metric
    updates = patch.model_dump(exclude_unset=True, exclude_none=False)
    updates.pop("metric_key", None)
    common_dimensions = updates.pop("common_dimensions", None)
    if common_dimensions is not None:
        updates["common_dimension_compatibility"] = [
            evaluate_dimension_compatibility(
                graph=graph,
                grain_node_key=(
                    updates.get("grain_table_key")
                    or metric.grain_table_key
                ),
                dimension_column_key=item.dimension_column_key,
                edge_path=item.edge_path,
            )
            for item in common_dimensions
        ]
    elif {
        "grain_table_key",
        "required_join_edge_keys",
    } & updates.keys():
        updates["common_dimension_compatibility"] = []
    updates["provenance"] = "human"
    updates["provenance_detail"] = "human_override"
    updates["source_spec_key"] = None
    if updates.get("status") in {"disabled", "rejected"}:
        updates["enabled"] = False
    updates.update(
        {
            "confidence_score": 0,
            "confidence_label": "blocked",
            "compiler_eligibility": "not_eligible",
            "eligibility_reasons": ["NOT_VALIDATED"],
            "validation_warnings": [],
        }
    )
    reviewed = metric.model_copy(update=updates)
    reviewed = SemanticMetric.model_validate(reviewed.model_dump())
    return reviewed.model_copy(
        update={
            "metric_definition_hash": compute_metric_definition_hash(reviewed)
        }
    )


def _validate_metric(
    *,
    metric: SemanticMetric,
    issues: list[SemanticValidationIssue],
    nodes: dict[str, QueryabilityNode],
    graph_columns: dict[str, tuple[QueryabilityNode, object]],
    semantic_tables: dict[str, SemanticTable],
    semantic_columns: dict[str, SemanticColumn],
    fk_edges: dict[str, QueryabilityForeignKeyEdge],
    concepts: dict[str, object],
    missing_currency_behavior: Literal["clarification_required", "blocked"],
) -> SemanticMetric:
    metric_key = str(metric.metric_key)
    source = semantic_tables.get(metric.source_table_key)
    grain = semantic_tables.get(metric.grain_table_key)
    grain_graph_node = nodes.get(metric.grain_table_key)
    if source is None or metric.source_table_key not in nodes:
        _issue(
            issues,
            "METRIC_SOURCE_TABLE_NOT_FOUND",
            "blocking",
            "metric",
            metric_key,
            "Metric source table is not present in the semantic layer and graph.",
        )
    elif not _semantic_table_is_usable(source):
        _issue(
            issues,
            "METRIC_SOURCE_TABLE_EXCLUDED",
            "blocking",
            "metric",
            metric_key,
            "Metric source table is excluded.",
        )
    if grain is None or metric.grain_table_key not in nodes:
        _issue(
            issues,
            "METRIC_GRAIN_TABLE_NOT_FOUND",
            "blocking",
            "metric",
            metric_key,
            "Metric grain table is not present in the semantic layer and graph.",
        )
    concept = concepts.get(str(metric.business_concept_key))
    if concept is None:
        _issue(
            issues,
            "METRIC_BUSINESS_CONCEPT_NOT_FOUND",
            "blocking",
            "metric",
            metric_key,
            "Metric business concept does not exist.",
        )
    elif not _semantic_status_is_enabled(concept.status):
        _issue(
            issues,
            "METRIC_BUSINESS_CONCEPT_DISABLED",
            "blocking",
            "metric",
            metric_key,
            "Metric business concept is rejected, disabled, or stale.",
        )

    measure = (
        semantic_columns.get(metric.measure_column_key)
        if metric.measure_column_key
        else None
    )
    if metric.aggregation == "count":
        if metric.measure_column_key is not None and measure is None:
            _issue(
                issues,
                "METRIC_MEASURE_NOT_FOUND",
                "blocking",
                "metric",
                metric_key,
                "Metric measure column does not exist.",
            )
        elif measure is not None:
            _validate_measure_column(
                metric=metric,
                measure=measure,
                issues=issues,
                semantic_tables=semantic_tables,
            )
    elif measure is None:
        _issue(
            issues,
            "METRIC_MEASURE_REQUIRED",
            "blocking",
            "metric",
            metric_key,
            "This aggregation requires a measure column.",
        )
    else:
        _validate_measure_column(
            metric=metric,
            measure=measure,
            issues=issues,
            semantic_tables=semantic_tables,
        )
    if measure is not None and metric.aggregation in {"sum", "avg"} and (
        (measure.normalized_type or measure.native_type or "").lower()
        not in _NUMERIC_TYPES
    ):
        _issue(
            issues,
            "METRIC_MEASURE_NOT_NUMERIC",
            "blocking",
            "metric",
            metric_key,
            "SUM and AVG require a numeric measure column.",
        )

    for column_key in metric.grain_column_keys:
        column = semantic_columns.get(column_key)
        if column is None:
            _issue(
                issues,
                "METRIC_GRAIN_COLUMN_NOT_FOUND",
                "blocking",
                "metric",
                metric_key,
                "Metric grain references a missing column.",
                evidence={"column_key": column_key},
            )
        elif column.node_key != metric.grain_table_key or not column.included:
            _issue(
                issues,
                "METRIC_GRAIN_COLUMN_INVALID",
                "blocking",
                "metric",
                metric_key,
                "Metric grain column must be included and belong to the grain table.",
                evidence={"column_key": column_key},
            )

    if grain_graph_node is not None and not _grain_matches_candidate_key(
        metric.grain_column_keys,
        grain_graph_node,
    ):
        _issue(
            issues,
            "METRIC_GRAIN_NOT_CANDIDATE_KEY",
            "blocking",
            "metric",
            metric_key,
            "Metric grain must match an eligible graph candidate key in V1.",
        )

    if metric.source_table_key != metric.grain_table_key:
        _issue(
            issues,
            "METRIC_SOURCE_GRAIN_MISMATCH",
            "blocking",
            "metric",
            metric_key,
            "Metric source and grain table must match in V1.",
        )

    reachable_nodes = _path_node_keys(
        metric.source_table_key,
        metric.required_join_edge_keys,
        fk_edges,
    )

    if metric.default_date_column_key:
        date_column = semantic_columns.get(metric.default_date_column_key)
        if (
            date_column is None
            or not _semantic_column_is_usable(
                date_column,
                semantic_tables,
            )
            or date_column.technical_role != "date"
            or date_column.node_key not in reachable_nodes
        ):
            _issue(
                issues,
                "METRIC_DEFAULT_DATE_INVALID",
                "blocking",
                "metric",
                metric_key,
                "Default date must reference an included technical date column.",
            )

    for edge_key in metric.required_join_edge_keys:
        edge = fk_edges.get(edge_key)
        if edge is None or not _edge_is_automatic(edge):
            _issue(
                issues,
                "METRIC_JOIN_EDGE_INVALID",
                "blocking",
                "metric",
                metric_key,
                "Metric required join edge is missing, disabled, or untrusted.",
                evidence={"edge_key": edge_key},
            )
    if metric.required_join_edge_keys and not _edge_path_is_connected(
        metric.source_table_key,
        metric.required_join_edge_keys,
        fk_edges,
    ):
        _issue(
            issues,
            "METRIC_JOIN_PATH_DISCONNECTED",
            "blocking",
            "metric",
            metric_key,
            "Metric required join edges do not form a connected path.",
        )
    required_path_safety = _evaluate_required_join_path(
        metric.source_table_key,
        metric.required_join_edge_keys,
        nodes,
        fk_edges,
    )
    if required_path_safety == "forbidden":
        _issue(
            issues,
            "METRIC_REQUIRED_JOIN_MULTIPLICATION",
            "blocking",
            "metric",
            metric_key,
            "Metric required join path crosses to a lower-grain child or bridge.",
        )

    for item in metric.common_dimension_compatibility:
        _validate_dimension_compatibility(
            metric=metric,
            compatibility=item,
            issues=issues,
            semantic_columns=semantic_columns,
            semantic_tables=semantic_tables,
            nodes=nodes,
            fk_edges=fk_edges,
        )

    for column_key in metric.preferred_for_dimensions:
        column = semantic_columns.get(column_key)
        compatible_dimension_keys = {
            item.dimension_column_key
            for item in metric.common_dimension_compatibility
            if item.safety == "safe"
        }
        if (
            column is None
            or not _semantic_column_is_usable(column, semantic_tables)
            or (
                column.node_key != metric.grain_table_key
                and column_key not in compatible_dimension_keys
            )
        ):
            _issue(
                issues,
                "PREFERRED_DIMENSION_INVALID",
                "blocking",
                "metric",
                metric_key,
                "Preferred dimension must reference an included semantic column.",
                evidence={"column_key": column_key},
            )

    for item in metric.filters:
        column = semantic_columns.get(item.column_key)
        if (
            column is None
            or not _semantic_column_is_usable(column, semantic_tables)
            or column.node_key not in reachable_nodes
        ):
            _issue(
                issues,
                "METRIC_FILTER_COLUMN_INVALID",
                "blocking",
                "metric",
                metric_key,
                "Metric filter must reference an included semantic column.",
                evidence={"column_key": item.column_key},
            )
        if item.operator in {"is_null", "is_not_null"} and item.value is not None:
            _issue(
                issues,
                "METRIC_FILTER_VALUE_FORBIDDEN",
                "blocking",
                "metric",
                metric_key,
                "Null operators cannot include a value.",
            )
        if item.operator not in {"is_null", "is_not_null"} and item.value is None:
            _issue(
                issues,
                "METRIC_FILTER_VALUE_REQUIRED",
                "blocking",
                "metric",
                metric_key,
                "Non-null filter operators require a value.",
            )
        if item.operator in {"in", "not_in", "between"} and not isinstance(
            item.value,
            list,
        ):
            _issue(
                issues,
                "METRIC_FILTER_LIST_REQUIRED",
                "blocking",
                "metric",
                metric_key,
                "IN, NOT IN, and BETWEEN require a list value.",
            )
        if item.operator == "between" and (
            not isinstance(item.value, list) or len(item.value) != 2
        ):
            _issue(
                issues,
                "METRIC_FILTER_BETWEEN_ARITY",
                "blocking",
                "metric",
                metric_key,
                "BETWEEN requires exactly two values.",
            )
        if item.value is not None and not _filter_value_matches_type(
            item.value,
            item.value_type,
        ):
            _issue(
                issues,
                "METRIC_FILTER_VALUE_TYPE_MISMATCH",
                "blocking",
                "metric",
                metric_key,
                "Metric filter value does not match its declared value type.",
            )
        if column is not None and not _filter_type_matches_column(
            item.value_type,
            column,
        ):
            _issue(
                issues,
                "METRIC_FILTER_COLUMN_TYPE_MISMATCH",
                "blocking",
                "metric",
                metric_key,
                "Metric filter value type is incompatible with the column.",
                evidence={"column_key": item.column_key},
            )
        if (
            column is not None
            and column.technical_role == "boolean"
            and item.operator not in {"eq", "neq", "in", "not_in", "is_null", "is_not_null"}
        ):
            _issue(
                issues,
                "METRIC_FILTER_OPERATOR_TYPE_MISMATCH",
                "blocking",
                "metric",
                metric_key,
                "Boolean columns do not support ordered comparison operators.",
            )
    if metric.filters and metric.provenance == "ai":
        _issue_once(
            issues,
            "AI_FILTER_VALUE_UNVERIFIED",
            "warning",
            "metric",
            metric_key,
            "AI-proposed filter values are structurally valid but require "
            "human confirmation without data profiling.",
        )

    expected_definition_hash = compute_metric_definition_hash(metric)
    if metric.metric_definition_hash != expected_definition_hash:
        _issue(
            issues,
            "METRIC_DEFINITION_HASH_MISMATCH",
            "blocking",
            "metric",
            metric_key,
            "Metric definition hash does not match its canonical definition.",
        )
    if metric.format.value_type == "currency" and not metric.format.currency:
        _issue(
            issues,
            "METRIC_CURRENCY_UNRESOLVED",
            (
                "blocking"
                if missing_currency_behavior == "blocked"
                else "warning"
            ),
            "metric",
            metric_key,
            "Currency metric has no resolved ISO currency code.",
        )
    if metric.format.value_type != "currency" and metric.format.currency:
        _issue(
            issues,
            "METRIC_CURRENCY_FORBIDDEN",
            "blocking",
            "metric",
            metric_key,
            "Non-currency metrics cannot declare a currency code.",
        )

    return metric


def _validate_measure_column(
    *,
    metric: SemanticMetric,
    measure: SemanticColumn,
    issues: list[SemanticValidationIssue],
    semantic_tables: dict[str, SemanticTable],
) -> None:
    metric_key = str(metric.metric_key)
    if measure.node_key != metric.source_table_key:
        _issue(
            issues,
            "METRIC_MEASURE_SOURCE_MISMATCH",
            "blocking",
            "metric",
            metric_key,
            "Metric measure must belong to the source table in V1.",
        )
    if not _semantic_column_is_usable(measure, semantic_tables):
        _issue(
            issues,
            "METRIC_MEASURE_EXCLUDED",
            "blocking",
            "metric",
            metric_key,
            "Metric measure column is excluded.",
        )


def _filter_value_matches_type(value: object, value_type: str) -> bool:
    values = value if isinstance(value, list) else [value]
    if value_type == "string":
        return all(isinstance(item, str) for item in values)
    if value_type == "integer":
        return all(isinstance(item, int) and not isinstance(item, bool) for item in values)
    if value_type == "decimal":
        return all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in values
        )
    if value_type == "boolean":
        return all(isinstance(item, bool) for item in values)
    if value_type == "date":
        return all(
            isinstance(item, str) and _is_iso_date(item)
            for item in values
        )
    if value_type == "datetime":
        return all(
            isinstance(item, str) and _is_iso_datetime(item)
            for item in values
        )
    return False


def _filter_type_matches_column(
    value_type: str,
    column: SemanticColumn,
) -> bool:
    native_type = (column.normalized_type or column.native_type or "").lower()
    if column.technical_role == "boolean":
        return value_type == "boolean"
    if column.technical_role == "date":
        return value_type in {"date", "datetime"}
    if native_type in _NUMERIC_TYPES:
        return value_type in {"integer", "decimal"}
    return value_type == "string"


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return "T" not in value


def _is_iso_datetime(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _apply_metric_eligibility(
    metric: SemanticMetric,
    issues: list[SemanticValidationIssue],
    *,
    global_blocking_codes: list[str],
) -> SemanticMetric:
    metric_key = str(metric.metric_key)
    metric_issues = [
        issue
        for issue in issues
        if issue.target_type == "metric" and issue.target_key == metric_key
    ]
    blocking = any(issue.severity == "blocking" for issue in metric_issues)
    warning_codes = sorted(
        {issue.code for issue in metric_issues if issue.severity == "warning"}
    )
    ambiguous = any(_issue_requires_clarification(issue) for issue in metric_issues)
    if (
        blocking
        or global_blocking_codes
        or not metric.enabled
        or metric.status in {"rejected", "disabled", "stale"}
    ):
        eligibility = "not_eligible"
        reasons = sorted(
            {
                issue.code
                for issue in metric_issues
                if issue.severity == "blocking"
            }
            | set(global_blocking_codes)
            or {"METRIC_DISABLED"}
        )
        score = 0.0
        label = "blocked"
    elif ambiguous:
        eligibility = "clarification_required"
        reasons = warning_codes
        score = 0.6
        label = "medium"
    elif metric.status == "human_verified":
        eligibility = "eligible"
        reasons = []
        score = 0.98
        label = "high"
    elif metric.provenance_detail == "quality_profile":
        eligibility = "eligible_with_disclosure"
        reasons = ["QUALITY_PROFILE_DISCLOSURE_REQUIRED"]
        score = max(0.8, 0.96 - 0.03 * len(warning_codes))
        label = "high" if score >= 0.8 else "medium"
    else:
        eligibility = "eligible_with_disclosure"
        reasons = ["AI_PROPOSED_DISCLOSURE_REQUIRED"]
        score = max(0.8, 0.9 - 0.03 * len(warning_codes))
        label = "high" if score >= 0.8 else "medium"

    return metric.model_copy(
        update={
            "confidence_score": score,
            "confidence_label": label,
            "compiler_eligibility": eligibility,
            "eligibility_reasons": reasons,
            "validation_warnings": warning_codes,
        }
    )


def _issue_requires_clarification(issue: SemanticValidationIssue) -> bool:
    if issue.severity != "warning":
        return False
    if issue.code in _AMBIGUITY_CODES:
        return True
    if issue.code != "SEMANTIC_AMBIGUITY_DECLARED":
        return False
    return (
        issue.evidence.get("ambiguity_code")
        in _DECLARED_AMBIGUITY_CLARIFICATION_CODES
    )


def _validate_dimension_compatibility(
    *,
    metric: SemanticMetric,
    compatibility: SemanticDimensionCompatibility,
    issues: list[SemanticValidationIssue],
    semantic_columns: dict[str, SemanticColumn],
    semantic_tables: dict[str, SemanticTable],
    nodes: dict[str, QueryabilityNode],
    fk_edges: dict[str, QueryabilityForeignKeyEdge],
) -> None:
    dimension = semantic_columns.get(compatibility.dimension_column_key)
    metric_key = str(metric.metric_key)
    if dimension is None or not _semantic_column_is_usable(
        dimension,
        semantic_tables,
    ):
        _issue(
            issues,
            "DIMENSION_COLUMN_INVALID",
            "blocking",
            "metric",
            metric_key,
            "Common dimension must reference an included semantic column.",
            evidence={"column_key": compatibility.dimension_column_key},
        )
        return
    computed_safety, reason = _evaluate_dimension_path(
        grain_node_key=metric.grain_table_key,
        dimension_node_key=dimension.node_key,
        edge_path=compatibility.edge_path,
        nodes=nodes,
        fk_edges=fk_edges,
    )
    if computed_safety == "invalid":
        _issue(
            issues,
            "DIMENSION_PATH_INVALID",
            "blocking",
            "metric",
            metric_key,
            "Common dimension edge path is missing or disconnected.",
            evidence={"dimension_column_key": compatibility.dimension_column_key},
        )
    elif computed_safety == "forbidden" and compatibility.safety == "safe":
        _issue(
            issues,
            "HEADER_DETAIL_DIMENSION_FORBIDDEN",
            "blocking",
            "metric",
            metric_key,
            "Header-level metrics cannot use lower-grain detail dimensions in V1.",
            evidence={
                "dimension_column_key": compatibility.dimension_column_key,
                "reason_code": reason,
            },
        )
    elif computed_safety == "safe" and compatibility.safety == "forbidden":
        _issue(
            issues,
            "DIMENSION_SAFETY_DECLARATION_MISMATCH",
            "blocking",
            "metric",
            metric_key,
            "Dimension safety declaration does not match the graph path.",
            evidence={
                "dimension_column_key": compatibility.dimension_column_key,
                "declared_safety": compatibility.safety,
                "computed_safety": computed_safety,
            },
        )
    elif compatibility.reason_code != reason:
        _issue(
            issues,
            "DIMENSION_SAFETY_REASON_MISMATCH",
            "blocking",
            "metric",
            metric_key,
            "Dimension compatibility reason does not match the graph path.",
            evidence={
                "declared_reason": compatibility.reason_code,
                "computed_reason": reason,
            },
        )


def _evaluate_dimension_path(
    *,
    grain_node_key: str,
    dimension_node_key: str,
    edge_path: list[str],
    nodes: dict[str, QueryabilityNode],
    fk_edges: dict[str, QueryabilityForeignKeyEdge],
) -> tuple[Literal["safe", "forbidden", "invalid"], str]:
    if not edge_path:
        if grain_node_key == dimension_node_key:
            return "safe", "SAME_GRAIN"
        return "invalid", "MISSING_EDGE_PATH"
    current = grain_node_key
    visited_nodes = {current}
    visited_edges: set[str] = set()
    forbidden_reason: str | None = None
    for edge_key in edge_path:
        if edge_key in visited_edges:
            return "invalid", "REPEATED_EDGE"
        visited_edges.add(edge_key)
        edge = fk_edges.get(edge_key)
        if edge is None or not _edge_is_automatic(edge):
            return "invalid", "INVALID_EDGE"
        if edge.self_reference:
            forbidden_reason = forbidden_reason or "SELF_REFERENCE_CONDITIONAL"
        if current == edge.from_node_key:
            next_node = edge.to_node_key
        elif current == edge.to_node_key:
            next_node = edge.from_node_key
            if edge.parent_to_child == "zero_or_many":
                forbidden_reason = forbidden_reason or "CHILD_ONE_TO_MANY"
        else:
            return "invalid", "DISCONNECTED_EDGE_PATH"
        if next_node in visited_nodes and not edge.self_reference:
            return "invalid", "CYCLIC_EDGE_PATH"
        visited_nodes.add(next_node)
        if nodes.get(current) and nodes[current].bridge_candidate:
            forbidden_reason = forbidden_reason or "BRIDGE_OR_MANY_TO_MANY"
        if nodes.get(next_node) and nodes[next_node].bridge_candidate:
            forbidden_reason = forbidden_reason or "BRIDGE_OR_MANY_TO_MANY"
        current = next_node
    if current != dimension_node_key:
        return "invalid", "DIMENSION_ENDPOINT_MISMATCH"
    if forbidden_reason is not None:
        return "forbidden", forbidden_reason
    return "safe", "TRUSTED_PARENT_PATH"


def evaluate_dimension_compatibility(
    *,
    graph: QueryabilityGraphArtifact,
    grain_node_key: str,
    dimension_column_key: str,
    edge_path: list[str],
) -> SemanticDimensionCompatibility:
    nodes = {node.node_key: node for node in graph.nodes}
    columns = {
        column.column_key: node.node_key
        for node in graph.nodes
        for column in node.columns
    }
    dimension_node_key = columns.get(dimension_column_key)
    if dimension_node_key is None:
        raise ValueError("dimension column is not present in the graph")
    fk_edges = {
        edge.edge_key: edge
        for edge in graph.edges
        if isinstance(edge, QueryabilityForeignKeyEdge)
    }
    safety, reason_code = _evaluate_dimension_path(
        grain_node_key=grain_node_key,
        dimension_node_key=dimension_node_key,
        edge_path=edge_path,
        nodes=nodes,
        fk_edges=fk_edges,
    )
    if safety == "invalid":
        raise ValueError(f"invalid dimension path: {reason_code}")
    return SemanticDimensionCompatibility(
        dimension_column_key=dimension_column_key,
        edge_path=edge_path,
        safety=safety,
        reason_code=reason_code,
    )


def _validate_metric_names_and_variants(
    issues: list[SemanticValidationIssue],
    metrics: list[SemanticMetric],
) -> None:
    variants: dict[tuple[str, str], str] = {}
    synonyms: dict[str, str] = {}
    for metric in metrics:
        key = str(metric.metric_key)
        variant_key = (str(metric.business_concept_key), metric.metric_variant)
        previous_variant = variants.setdefault(variant_key, key)
        if previous_variant != key:
            for target_key in (previous_variant, key):
                _issue_once(
                    issues,
                    "AMBIGUOUS_METRIC_VARIANT",
                    "warning",
                    "metric",
                    target_key,
                    "Business concept contains duplicate metric variants.",
                )
        for synonym in {metric.name, metric.canonical_name, *metric.synonyms}:
            normalized = synonym.casefold().strip()
            previous_metric = synonyms.setdefault(normalized, key)
            if previous_metric != key:
                for target_key in (previous_metric, key):
                    _issue_once(
                        issues,
                        "DUPLICATE_METRIC_SYNONYM",
                        "warning",
                        "metric",
                        target_key,
                        "Metric name or synonym is shared by another metric.",
                        evidence={"synonym": synonym},
                    )


def _validate_declared_ambiguities(
    *,
    issues: list[SemanticValidationIssue],
    ambiguities: list[SemanticAmbiguity],
    semantic_tables: dict[str, SemanticTable],
    semantic_columns: dict[str, SemanticColumn],
    concepts: dict[str, object],
    metrics: list[SemanticMetric],
) -> None:
    metric_keys = {str(metric.metric_key) for metric in metrics}
    for ambiguity in ambiguities:
        target_exists = (
            ambiguity.target_key in semantic_tables
            if ambiguity.target_type == "table"
            else ambiguity.target_key in semantic_columns
            if ambiguity.target_type == "column"
            else ambiguity.target_key in concepts
            if ambiguity.target_type == "business_concept"
            else ambiguity.target_key in metric_keys
        )
        if not target_exists:
            _issue(
                issues,
                "SEMANTIC_AMBIGUITY_TARGET_INVALID",
                "blocking",
                ambiguity.target_type,
                ambiguity.target_key,
                "Semantic ambiguity references a missing target.",
            )
            continue
        if ambiguity.status != "open":
            continue
        issue_code = (
            "SEMANTIC_AMBIGUITY_DECLARED"
            if ambiguity.severity == "material_ambiguity"
            else "SEMANTIC_MINOR_AMBIGUITY"
            if ambiguity.severity == "minor_ambiguity"
            else "SEMANTIC_AMBIGUITY_INFO"
        )
        issue_severity = "info" if ambiguity.severity == "info" else "warning"
        _issue_once(
            issues,
            issue_code,
            issue_severity,
            ambiguity.target_type,
            ambiguity.target_key,
            ambiguity.summary,
            evidence={"ambiguity_code": ambiguity.code},
        )
        if ambiguity.target_type == "business_concept":
            for metric in metrics:
                if str(metric.business_concept_key) == ambiguity.target_key:
                    _issue_once(
                        issues,
                        issue_code,
                        issue_severity,
                        "metric",
                        str(metric.metric_key),
                        ambiguity.summary,
                        evidence={"ambiguity_code": ambiguity.code},
                    )
        elif ambiguity.target_type in {"table", "column"}:
            for metric in metrics:
                referenced_column_keys = {
                    *metric.grain_column_keys,
                    *metric.preferred_for_dimensions,
                    *(
                        item.dimension_column_key
                        for item in metric.common_dimension_compatibility
                    ),
                    *(item.column_key for item in metric.filters),
                }
                if metric.measure_column_key is not None:
                    referenced_column_keys.add(metric.measure_column_key)
                if metric.default_date_column_key is not None:
                    referenced_column_keys.add(metric.default_date_column_key)
                uses_target = (
                    ambiguity.target_key
                    in {metric.source_table_key, metric.grain_table_key}
                    if ambiguity.target_type == "table"
                    else ambiguity.target_key in referenced_column_keys
                )
                if (
                    ambiguity.target_type == "table"
                    and not uses_target
                    and any(
                        semantic_columns[column_key].node_key
                        == ambiguity.target_key
                        for column_key in referenced_column_keys
                        if column_key in semantic_columns
                    )
                ):
                    uses_target = True
                if uses_target:
                    _issue_once(
                        issues,
                        issue_code,
                        issue_severity,
                        "metric",
                        str(metric.metric_key),
                        ambiguity.summary,
                        evidence={"ambiguity_code": ambiguity.code},
                    )


def _validate_graph_coverage(
    *,
    issues: list[SemanticValidationIssue],
    layer: SemanticLayer,
    nodes: dict[str, QueryabilityNode],
    graph_columns: dict[str, tuple[QueryabilityNode, object]],
    fk_edges: dict[str, QueryabilityForeignKeyEdge],
) -> None:
    table_keys = {table.node_key for table in layer.tables}
    column_keys = {column.column_key for column in layer.columns}
    relationship_keys = {
        relationship.edge_key for relationship in layer.relationships
    }
    expected_relationship_keys = {
        edge_key
        for edge_key, edge in fk_edges.items()
        if _edge_is_automatic(edge)
    }
    for node_key in sorted(set(nodes) - table_keys):
        _issue(
            issues,
            "SEMANTIC_TABLE_MISSING",
            "blocking",
            "table",
            node_key,
            "Semantic artifact must preserve every graph node.",
        )
    for column_key in sorted(set(graph_columns) - column_keys):
        _issue(
            issues,
            "SEMANTIC_COLUMN_MISSING",
            "blocking",
            "column",
            column_key,
            "Semantic artifact must preserve every graph column.",
        )
    for edge_key in sorted(expected_relationship_keys - relationship_keys):
        _issue(
            issues,
            "SEMANTIC_RELATIONSHIP_MISSING",
            "blocking",
            "relationship",
            edge_key,
            "Semantic artifact must preserve every automatic graph FK.",
        )


def _carry_table(
    seed_table: SemanticTable,
    source_table: SemanticTable | None,
    carried_table_keys: list[str],
) -> SemanticTable:
    if source_table is None:
        return seed_table
    carried_table_keys.append(seed_table.node_key)
    return seed_table.model_copy(
        update={
            "display_name": source_table.display_name,
            "description": source_table.description,
            "business_domain": source_table.business_domain,
            "synonyms": source_table.synonyms,
            "status": _restore_unowned_element_status(source_table.status),
            "included": seed_table.included and source_table.included,
        }
    )


def _carry_column(
    seed_column: SemanticColumn,
    source_column: SemanticColumn | None,
    carried_column_keys: list[str],
) -> SemanticColumn:
    if source_column is None:
        return seed_column
    carried_column_keys.append(seed_column.column_key)
    sensitivity = (
        source_column.sensitivity
        if _SENSITIVITY_RANK[source_column.sensitivity]
        >= _SENSITIVITY_RANK[seed_column.sensitivity]
        else seed_column.sensitivity
    )
    return seed_column.model_copy(
        update={
            "display_name": source_column.display_name,
            "description": source_column.description,
            "synonyms": source_column.synonyms,
            "semantic_role": source_column.semantic_role,
            "format_hint": source_column.format_hint,
            "status": _restore_unowned_element_status(source_column.status),
            "included": seed_column.included and source_column.included,
            "sensitivity": sensitivity,
        }
    )


def _carry_relationship(
    seed_relationship: SemanticRelationship,
    source_relationship: SemanticRelationship | None,
) -> SemanticRelationship:
    if source_relationship is None:
        return seed_relationship
    return seed_relationship.model_copy(
        update={
            "status": _restore_unowned_element_status(
                source_relationship.status
            ),
            "enabled": source_relationship.enabled,
        }
    )


def _restore_concept_status(
    concept: SemanticBusinessConcept,
) -> SemanticBusinessConcept:
    if concept.status != "stale":
        return concept
    return concept.model_copy(
        update={"status": _status_for_provenance(concept.provenance)}
    )


def _restore_metric_status(metric: SemanticMetric) -> SemanticMetric:
    if metric.status != "stale":
        return metric
    return metric.model_copy(
        update={"status": _status_for_provenance(metric.provenance)}
    )


def _status_for_provenance(
    provenance: Literal["system", "ai", "human"],
) -> Literal["system_seeded", "ai_proposed", "human_verified"]:
    if provenance == "human":
        return "human_verified"
    if provenance == "ai":
        return "ai_proposed"
    return "system_seeded"


def _restore_unowned_element_status(
    status: SemanticElementStatus,
) -> SemanticElementStatus:
    return "system_seeded" if status == "stale" else status


def _metric_rebase_drop_reasons(
    *,
    metric: SemanticMetric,
    concept_keys: set[str],
    target_table_keys: set[str],
    usable_table_keys: set[str],
    target_column_keys: set[str],
    usable_column_keys: set[str],
    target_fk_edge_keys: set[str],
    usable_edge_keys: set[str],
) -> list[SemanticRebaseDropReasonCode]:
    reasons: list[SemanticRebaseDropReasonCode] = []
    if metric.metric_definition_hash != compute_metric_definition_hash(metric):
        reasons.append("DEFINITION_CHANGED")
    if str(metric.business_concept_key) not in concept_keys:
        reasons.append("DEPENDENCY_DROPPED")
    table_keys = {metric.source_table_key, metric.grain_table_key}
    if not table_keys.issubset(target_table_keys):
        reasons.append("TARGET_KEY_MISSING")
    elif not table_keys.issubset(usable_table_keys):
        reasons.append("TARGET_NOT_QUERYABLE")
    column_keys = {
        *metric.grain_column_keys,
        *metric.preferred_for_dimensions,
        *(
            item.dimension_column_key
            for item in metric.common_dimension_compatibility
        ),
        *(item.column_key for item in metric.filters),
    }
    if metric.measure_column_key is not None:
        column_keys.add(metric.measure_column_key)
    if metric.default_date_column_key is not None:
        column_keys.add(metric.default_date_column_key)
    if not column_keys.issubset(target_column_keys):
        reasons.append("TARGET_KEY_MISSING")
    elif not column_keys.issubset(usable_column_keys):
        reasons.append("TARGET_NOT_QUERYABLE")
    edge_keys = {
        *metric.required_join_edge_keys,
        *(
            edge_key
            for item in metric.common_dimension_compatibility
            for edge_key in item.edge_path
        ),
    }
    if not edge_keys.issubset(target_fk_edge_keys):
        reasons.append("TARGET_KEY_MISSING")
    elif not edge_keys.issubset(usable_edge_keys):
        reasons.append("TARGET_EDGE_NOT_TRUSTED")
    order = {
        "TARGET_KEY_MISSING": 0,
        "TARGET_NOT_QUERYABLE": 1,
        "TARGET_EDGE_NOT_TRUSTED": 2,
        "DEPENDENCY_DROPPED": 3,
        "DEFINITION_CHANGED": 4,
        "INVALID_AFTER_REBASE": 5,
    }
    return sorted(set(reasons), key=order.__getitem__)


def _ambiguity_target_survives(
    *,
    ambiguity: SemanticAmbiguity,
    table_keys: set[str],
    column_keys: set[str],
    concept_keys: set[str],
    metric_keys: set[str],
) -> bool:
    if ambiguity.target_type == "table":
        return ambiguity.target_key in table_keys
    if ambiguity.target_type == "column":
        return ambiguity.target_key in column_keys
    if ambiguity.target_type == "business_concept":
        return ambiguity.target_key in concept_keys
    return ambiguity.target_key in metric_keys


def _semantic_relationship_is_available(
    relationship: SemanticRelationship | None,
    edge: QueryabilityForeignKeyEdge,
) -> bool:
    return (
        relationship is not None
        and relationship.enabled
        and relationship.status
        not in {"rejected", "disabled", "stale"}
        and _edge_is_automatic(edge)
    )


def _semantic_status_is_enabled(status: str) -> bool:
    return status not in {"rejected", "disabled", "stale"}


def _semantic_table_is_usable(table: SemanticTable) -> bool:
    return table.included and _semantic_status_is_enabled(table.status)


def _semantic_column_is_usable(
    column: SemanticColumn,
    semantic_tables: dict[str, SemanticTable],
) -> bool:
    table = semantic_tables.get(column.node_key)
    return (
        column.included
        and _semantic_status_is_enabled(column.status)
        and table is not None
        and _semantic_table_is_usable(table)
    )


def _grain_matches_candidate_key(
    grain_column_keys: list[str],
    grain_node: QueryabilityNode,
) -> bool:
    graph_columns_by_name = {
        column.name: column.column_key for column in grain_node.columns
    }
    declared = set(grain_column_keys)
    if len(declared) != len(grain_column_keys):
        return False
    return any(
        candidate.eligible_for_cardinality
        and {
            graph_columns_by_name[column_name]
            for column_name in candidate.columns
            if column_name in graph_columns_by_name
        }
        == declared
        and len(candidate.columns) == len(declared)
        for candidate in grain_node.candidate_keys
    )


def _validate_unique_keys(
    issues: list[SemanticValidationIssue],
    keys: list[str],
    code: str,
    target_type: Literal[
        "table",
        "column",
        "relationship",
        "business_concept",
        "ambiguity",
        "metric",
    ],
) -> None:
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            _issue(
                issues,
                code,
                "blocking",
                target_type,
                key,
                "Semantic artifact contains a duplicate stable key.",
            )
        seen.add(key)


def _edge_is_automatic(edge: QueryabilityForeignKeyEdge) -> bool:
    return (
        edge.automatic_join_allowed
        and edge.verified_by_db
        and edge.enforcement_status == "enabled"
        and edge.validation_status == "trusted"
    )


def _edge_path_is_connected(
    start_node_key: str,
    edge_keys: list[str],
    edges: dict[str, QueryabilityForeignKeyEdge],
) -> bool:
    return bool(_path_node_keys(start_node_key, edge_keys, edges))


def _path_node_keys(
    start_node_key: str,
    edge_keys: list[str],
    edges: dict[str, QueryabilityForeignKeyEdge],
) -> set[str]:
    current = start_node_key
    nodes = {current}
    visited_edges: set[str] = set()
    for edge_key in edge_keys:
        if edge_key in visited_edges:
            return set()
        visited_edges.add(edge_key)
        edge = edges.get(edge_key)
        if edge is None:
            return set()
        if current == edge.from_node_key:
            current = edge.to_node_key
        elif current == edge.to_node_key:
            current = edge.from_node_key
        else:
            return set()
        if current in nodes and not edge.self_reference:
            return set()
        nodes.add(current)
    return nodes


def _evaluate_required_join_path(
    start_node_key: str,
    edge_keys: list[str],
    nodes: dict[str, QueryabilityNode],
    edges: dict[str, QueryabilityForeignKeyEdge],
) -> Literal["safe", "forbidden", "invalid"]:
    current = start_node_key
    visited_nodes = {current}
    visited_edges: set[str] = set()
    for edge_key in edge_keys:
        if edge_key in visited_edges:
            return "invalid"
        visited_edges.add(edge_key)
        edge = edges.get(edge_key)
        if edge is None or not _edge_is_automatic(edge):
            return "invalid"
        if edge.self_reference:
            return "forbidden"
        if current == edge.from_node_key:
            next_node = edge.to_node_key
        elif current == edge.to_node_key:
            next_node = edge.from_node_key
            if edge.parent_to_child == "zero_or_many":
                return "forbidden"
        else:
            return "invalid"
        if next_node in visited_nodes and not edge.self_reference:
            return "invalid"
        visited_nodes.add(next_node)
        if nodes[current].bridge_candidate or nodes[next_node].bridge_candidate:
            return "forbidden"
        current = next_node
    return "safe"


def _canonical_models(
    items: list[object],
    key: str,
    *,
    unordered_fields: set[str] | None = None,
) -> list[dict[str, object]]:
    dumped = [
        item.model_dump(mode="json", exclude_none=True)  # type: ignore[attr-defined]
        for item in items
    ]
    for item in dumped:
        for field in unordered_fields or set():
            if field in item:
                item[field] = sorted(item[field])  # type: ignore[arg-type]
        if "common_dimension_compatibility" in item:
            item["common_dimension_compatibility"] = sorted(
                item["common_dimension_compatibility"],  # type: ignore[arg-type]
                key=_dimension_compatibility_sort_key,
            )
        if "filters" in item:
            item["filters"] = sorted(
                item["filters"],  # type: ignore[arg-type]
                key=lambda value: (
                    value["column_key"],
                    value["operator"],
                    json.dumps(value.get("value"), sort_keys=True),
                ),
            )
    return sorted(
        dumped,
        key=lambda item: (
            str(item[key]),
            json.dumps(
                item,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )


def _dimension_compatibility_sort_key(
    value: dict[str, object],
) -> tuple[str, str, str, str]:
    return (
        str(value["dimension_column_key"]),
        json.dumps(value.get("edge_path", []), separators=(",", ":")),
        str(value.get("safety", "")),
        str(value.get("reason_code", "")),
    )


def _hash_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _issue(
    issues: list[SemanticValidationIssue],
    code: str,
    severity: Literal["blocking", "warning", "info"],
    target_type: Literal[
        "layer",
        "table",
        "column",
        "relationship",
        "business_concept",
        "ambiguity",
        "metric",
    ],
    target_key: str,
    message: str,
    evidence: dict[str, str | int | float | bool] | None = None,
) -> None:
    issues.append(
        SemanticValidationIssue(
            code=code,
            severity=severity,
            target_type=target_type,
            target_key=target_key,
            message=message,
            evidence=evidence or {},
        )
    )


def _issue_once(
    issues: list[SemanticValidationIssue],
    code: str,
    severity: Literal["blocking", "warning", "info"],
    target_type: Literal[
        "layer",
        "table",
        "column",
        "relationship",
        "business_concept",
        "ambiguity",
        "metric",
    ],
    target_key: str,
    message: str,
    evidence: dict[str, str | int | float | bool] | None = None,
) -> None:
    if any(
        issue.code == code
        and issue.target_type == target_type
        and issue.target_key == target_key
        for issue in issues
    ):
        return
    _issue(
        issues,
        code,
        severity,
        target_type,
        target_key,
        message,
        evidence,
    )


def _issue_sort_key(issue: SemanticValidationIssue) -> tuple[str, str, str]:
    return issue.code, issue.target_type, issue.target_key
