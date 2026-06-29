from dataclasses import dataclass
from typing import Literal

from app.models import (
    QueryabilityForeignKeyEdge,
    QueryabilityGraphArtifact,
    QueryabilityPathResult,
    QueryabilityViewColumnEdge,
    QueryabilityViewDependencyEdge,
    SemanticLayer,
)


QueryabilityValidationSeverity = Literal["error", "warning", "info"]
QueryabilityValidationStatus = Literal["valid", "valid_with_warnings", "invalid"]


@dataclass(frozen=True)
class QueryabilityExpectedRelationship:
    from_object_name: str
    to_object_name: str
    label: str | None = None


@dataclass(frozen=True)
class QueryabilityGraphValidationIssue:
    code: str
    severity: QueryabilityValidationSeverity
    message: str
    node_key: str | None = None
    column_key: str | None = None
    edge_key: str | None = None
    physical_label: str | None = None
    downstream_impact: str = ""
    suggested_action: str = ""


@dataclass(frozen=True)
class QueryabilityGraphValidationSummary:
    node_count: int
    column_count: int
    edge_count: int
    automatic_join_count: int
    bridge_candidate_count: int
    pii_column_count: int
    sensitive_column_count: int


@dataclass(frozen=True)
class QueryabilityGraphValidationReport:
    status: QueryabilityValidationStatus
    errors: list[QueryabilityGraphValidationIssue]
    warnings: list[QueryabilityGraphValidationIssue]
    info: list[QueryabilityGraphValidationIssue]
    summary: QueryabilityGraphValidationSummary
    blocking_codes: list[str]

    @property
    def issues(self) -> list[QueryabilityGraphValidationIssue]:
        return [*self.errors, *self.warnings, *self.info]


def validate_queryability_graph(
    graph: QueryabilityGraphArtifact,
    *,
    expected_missing_relationships: list[QueryabilityExpectedRelationship] | None = None,
) -> QueryabilityGraphValidationReport:
    nodes_by_key = {node.node_key: node for node in graph.nodes}
    columns_by_key = {
        column.column_key: (node, column)
        for node in graph.nodes
        for column in node.columns
    }
    issues: list[QueryabilityGraphValidationIssue] = []

    issues.extend(
        _duplicate_key_issues(
            code="DUPLICATE_NODE_KEY",
            values=[node.node_key for node in graph.nodes],
            downstream_impact="Compiler routing cannot safely identify tables.",
            suggested_action="Rebuild the graph from a coherent snapshot.",
        )
    )
    issues.extend(
        _duplicate_key_issues(
            code="DUPLICATE_COLUMN_KEY",
            values=[
                column.column_key
                for node in graph.nodes
                for column in node.columns
            ],
            downstream_impact="Compiler column references may resolve incorrectly.",
            suggested_action="Rebuild the graph and check stable key derivation.",
        )
    )
    issues.extend(
        _duplicate_key_issues(
            code="DUPLICATE_EDGE_KEY",
            values=[edge.edge_key for edge in graph.edges],
            downstream_impact="Compiler join paths may resolve incorrectly.",
            suggested_action="Rebuild the graph and check edge key derivation.",
        )
    )

    for node in graph.nodes:
        issues.extend(_node_queryability_issues(node))
        issues.extend(_node_date_issues(node))
        if (
            node.object_type == "table"
            and node.queryability_status == "queryable"
            and not node.candidate_keys
        ):
            issues.append(
                _issue(
                    code="TABLE_WITHOUT_PK_UNSAFE_FOR_GRAIN",
                    severity="warning",
                    message="Queryable table has no candidate key for deterministic grain.",
                    node_key=node.node_key,
                    physical_label=_node_label(node),
                    downstream_impact=(
                        "Aggregate metrics on this table need explicit semantic grain "
                        "before a compiler can use them safely."
                    ),
                    suggested_action="Add a PK/unique key or require explicit semantic grain.",
                )
            )
        if node.bridge_candidate:
            issues.append(
                _issue(
                    code="BRIDGE_PATH_REQUIRES_POLICY",
                    severity="warning",
                    message="Bridge-like table requires explicit compiler policy.",
                    node_key=node.node_key,
                    physical_label=_node_label(node),
                    downstream_impact=(
                        "Many-to-many paths can multiply rows if used as ordinary joins."
                    ),
                    suggested_action=(
                        "Block compiler traversal through this node unless a semantic "
                        "policy explicitly approves the path."
                    ),
                )
            )

    for edge in graph.edges:
        issues.extend(
            _edge_issues(
                edge=edge,
                nodes_by_key=nodes_by_key,
                columns_by_key=columns_by_key,
            )
        )

    for relationship in expected_missing_relationships or []:
        if not _has_automatic_join_between(graph, relationship):
            label = relationship.label or (
                f"{relationship.from_object_name} -> {relationship.to_object_name}"
            )
            issues.append(
                _issue(
                    code="MISSING_FK_NO_TRUSTED_JOIN",
                    severity="warning",
                    message="Expected relationship has no trusted FK join evidence.",
                    physical_label=label,
                    downstream_impact=(
                        "The compiler must fail closed because the graph did not "
                        "derive a trusted join from names."
                    ),
                    suggested_action=(
                        "Add a real FK, configure an explicit approved inference policy, "
                        "or keep this relationship unavailable to the compiler."
                    ),
                )
            )

    return _report(graph=graph, issues=issues)


def validate_queryability_path_result(
    path_result: QueryabilityPathResult,
    *,
    compiler_context: bool = True,
) -> list[QueryabilityGraphValidationIssue]:
    issues: list[QueryabilityGraphValidationIssue] = []
    if path_result.status == "ambiguous":
        issues.append(
            _issue(
                code="AMBIGUOUS_PATH_NOT_BLOCKED",
                severity="warning" if compiler_context else "info",
                message="Multiple shortest trusted paths are available.",
                downstream_impact=(
                    "A compiler must not silently choose one path because this can "
                    "change query semantics."
                ),
                suggested_action="Require semantic disambiguation or block compilation.",
            )
        )
    if any(path.fanout_warning for path in path_result.paths):
        issues.append(
            _issue(
                code="FANOUT_PATH_REQUIRES_COMPILER_GUARD",
                severity="warning" if compiler_context else "info",
                message="Path contains parent-to-child fanout traversal.",
                downstream_impact=(
                    "Aggregates can be multiplied if the compiler joins through this path "
                    "without metric-grain safeguards."
                ),
                suggested_action="Use semantic grain compatibility or block the path.",
            )
        )
    return issues


def validate_semantic_graph_freshness(
    graph: QueryabilityGraphArtifact,
    semantic_layer: SemanticLayer,
) -> QueryabilityGraphValidationReport:
    issues: list[QueryabilityGraphValidationIssue] = []
    if semantic_layer.base_graph_hash != graph.graph_hash:
        issues.append(
            _issue(
                code="SEMANTIC_GRAPH_HASH_STALE",
                severity="error",
                message="Semantic layer base graph hash differs from the current graph.",
                downstream_impact="Resolver and compiler must not use this semantic layer.",
                suggested_action="Rebase or regenerate the semantic layer on the current graph.",
            )
        )
    if (
        semantic_layer.base_policy_hash
        != semantic_layer.semantic_policy_snapshot.policy_hash
    ):
        issues.append(
            _issue(
                code="SEMANTIC_POLICY_HASH_STALE",
                severity="error",
                message="Semantic layer base policy hash differs from its policy snapshot.",
                downstream_impact="Resolver and compiler must not use this semantic layer.",
                suggested_action="Synchronize semantic policy and regenerate validation.",
            )
        )
    return _report(graph=graph, issues=issues)


def _node_queryability_issues(node) -> list[QueryabilityGraphValidationIssue]:
    issues: list[QueryabilityGraphValidationIssue] = []
    for column in node.columns:
        label = _column_label(node, column)
        if column.technical_role in {"binary", "xml"} and (
            column.queryability_status != "excluded"
        ):
            issues.append(
                _issue(
                    code="UNSUPPORTED_TYPE_QUERYABLE",
                    severity="error",
                    message="Unsupported technical type is still queryable.",
                    node_key=node.node_key,
                    column_key=column.column_key,
                    physical_label=label,
                    downstream_impact="Compiler could expose or filter unsupported data.",
                    suggested_action="Mark this column excluded in the graph builder.",
                )
            )
        if column.sensitivity == "sensitive" and (
            column.queryability_status != "excluded"
        ):
            issues.append(
                _issue(
                    code="SENSITIVE_COLUMN_QUERYABLE",
                    severity="error",
                    message="Sensitive column is still queryable.",
                    node_key=node.node_key,
                    column_key=column.column_key,
                    physical_label=label,
                    downstream_impact="Compiler could expose secrets or credentials.",
                    suggested_action="Exclude sensitive columns in the graph builder.",
                )
            )
        if column.sensitivity == "pii" and column.queryability_status == "queryable":
            issues.append(
                _issue(
                    code="PII_REQUIRES_DOWNSTREAM_POLICY",
                    severity="warning",
                    message="PII column is technically queryable but not compiler-safe by default.",
                    node_key=node.node_key,
                    column_key=column.column_key,
                    physical_label=label,
                    downstream_impact=(
                        "Group-by/filter use requires an explicit downstream privacy policy."
                    ),
                    suggested_action=(
                        "Keep the column available only to policy-aware semantic/compiler gates."
                    ),
                )
            )
    return issues


def _node_date_issues(node) -> list[QueryabilityGraphValidationIssue]:
    date_columns = [
        column
        for column in node.columns
        if column.queryability_status == "queryable" and column.technical_role == "date"
    ]
    if len(date_columns) <= 1:
        return []
    return [
        _issue(
            code="MULTIPLE_DATE_COLUMNS_REQUIRES_SEMANTIC_SELECTION",
            severity="warning",
            message="Table has multiple queryable date columns.",
            node_key=node.node_key,
            physical_label=_node_label(node),
            downstream_impact=(
                "The graph cannot choose a business date; Semantic Layer or user policy "
                "must select one."
            ),
            suggested_action="Require semantic date selection before compilation.",
        )
    ]


def _edge_issues(
    *,
    edge,
    nodes_by_key: dict[str, object],
    columns_by_key: dict[str, tuple[object, object]],
) -> list[QueryabilityGraphValidationIssue]:
    issues: list[QueryabilityGraphValidationIssue] = []
    from_node = nodes_by_key.get(edge.from_node_key)
    if from_node is None:
        issues.append(
            _issue(
                code="DANGLING_EDGE_REFERENCE",
                severity="error",
                message="Edge references a missing from_node.",
                edge_key=edge.edge_key,
                downstream_impact="Compiler path resolution cannot trust this edge.",
                suggested_action="Rebuild the graph from a coherent snapshot.",
            )
        )

    if isinstance(edge, QueryabilityForeignKeyEdge):
        issues.extend(
            _fk_edge_issues(
                edge=edge,
                nodes_by_key=nodes_by_key,
                columns_by_key=columns_by_key,
            )
        )
    elif isinstance(edge, QueryabilityViewDependencyEdge):
        if edge.automatic_join_allowed:
            issues.append(_lineage_join_issue(edge.edge_key))
        if edge.resolution_status == "resolved" and (
            edge.to_node_key is None or edge.to_node_key not in nodes_by_key
        ):
            issues.append(
                _issue(
                    code="DANGLING_LINEAGE_REFERENCE",
                    severity="error",
                    message="Resolved view lineage references a missing target node.",
                    edge_key=edge.edge_key,
                    physical_label=edge.referenced_object_name,
                    downstream_impact="Lineage audit is unreliable.",
                    suggested_action="Rebuild lineage from the current snapshot.",
                )
            )
    elif isinstance(edge, QueryabilityViewColumnEdge):
        if edge.automatic_join_allowed:
            issues.append(_lineage_join_issue(edge.edge_key))
        from_column = columns_by_key.get(edge.from_column_key)
        if from_column is None or from_column[0].node_key != edge.from_node_key:
            issues.append(
                _issue(
                    code="DANGLING_LINEAGE_REFERENCE",
                    severity="error",
                    message="View column lineage references a missing source column.",
                    edge_key=edge.edge_key,
                    column_key=edge.from_column_key,
                    downstream_impact="Lineage audit is unreliable.",
                    suggested_action="Rebuild lineage from the current snapshot.",
                )
            )
        if edge.resolution_status == "resolved":
            to_column = (
                columns_by_key.get(edge.to_column_key)
                if edge.to_column_key is not None
                else None
            )
            if (
                edge.to_node_key is None
                or edge.to_node_key not in nodes_by_key
                or to_column is None
                or to_column[0].node_key != edge.to_node_key
            ):
                issues.append(
                    _issue(
                        code="DANGLING_LINEAGE_REFERENCE",
                        severity="error",
                        message="Resolved view column lineage references a missing target.",
                        edge_key=edge.edge_key,
                        column_key=edge.to_column_key,
                        physical_label=edge.referenced_column_name,
                        downstream_impact="Lineage audit is unreliable.",
                        suggested_action="Rebuild lineage from the current snapshot.",
                    )
                )
    return issues


def _fk_edge_issues(
    *,
    edge: QueryabilityForeignKeyEdge,
    nodes_by_key: dict[str, object],
    columns_by_key: dict[str, tuple[object, object]],
) -> list[QueryabilityGraphValidationIssue]:
    issues: list[QueryabilityGraphValidationIssue] = []
    to_node = nodes_by_key.get(edge.to_node_key)
    if to_node is None:
        issues.append(
            _issue(
                code="DANGLING_EDGE_REFERENCE",
                severity="error",
                message="FK edge references a missing target node.",
                edge_key=edge.edge_key,
                physical_label=edge.constraint_name,
                downstream_impact="Compiler path resolution cannot trust this edge.",
                suggested_action="Rebuild the graph from a coherent snapshot.",
            )
        )
    if edge.automatic_join_allowed and (
        not edge.verified_by_db
        or edge.enforcement_status != "enabled"
        or edge.validation_status != "trusted"
    ):
        issues.append(
            _issue(
                code="AUTOMATIC_JOIN_ON_UNTRUSTED_FK",
                severity="error",
                message="Automatic join is enabled on a non-trusted FK edge.",
                edge_key=edge.edge_key,
                physical_label=edge.constraint_name,
                downstream_impact="Compiler could generate joins from unsafe metadata.",
                suggested_action="Disable automatic join unless FK is enabled, trusted, and DB verified.",
            )
        )
    if edge.self_reference and edge.automatic_join_allowed:
        issues.append(
            _issue(
                code="SELF_REFERENCE_REQUIRES_POLICY",
                severity="warning",
                message="Self-referential FK is not compiler-safe by default.",
                edge_key=edge.edge_key,
                physical_label=edge.constraint_name,
                downstream_impact="Recursive hierarchy traversal needs explicit compiler policy.",
                suggested_action="Exclude from ordinary routing unless a semantic policy opts in.",
            )
        )
    for pair in edge.column_pairs:
        from_column = columns_by_key.get(pair.from_column_key)
        to_column = columns_by_key.get(pair.to_column_key)
        if from_column is None or from_column[0].node_key != edge.from_node_key:
            issues.append(
                _issue(
                    code="FK_COLUMN_PAIR_NODE_MISMATCH",
                    severity="error",
                    message="FK source column does not belong to the source node.",
                    edge_key=edge.edge_key,
                    column_key=pair.from_column_key,
                    physical_label=f"{edge.constraint_name}.{pair.from_column}",
                    downstream_impact="Compiler join condition would be invalid.",
                    suggested_action="Rebuild FK metadata from the snapshot.",
                )
            )
        if to_column is None or to_column[0].node_key != edge.to_node_key:
            issues.append(
                _issue(
                    code="FK_COLUMN_PAIR_NODE_MISMATCH",
                    severity="error",
                    message="FK target column does not belong to the target node.",
                    edge_key=edge.edge_key,
                    column_key=pair.to_column_key,
                    physical_label=f"{edge.constraint_name}.{pair.to_column}",
                    downstream_impact="Compiler join condition would be invalid.",
                    suggested_action="Rebuild FK metadata from the snapshot.",
                )
            )
        if edge.automatic_join_allowed:
            for item in [from_column, to_column]:
                if item is None:
                    continue
                node, column = item
                if column.queryability_status != "queryable":
                    issues.append(
                        _issue(
                            code="AUTOMATIC_JOIN_ON_EXCLUDED_COLUMN",
                            severity="error",
                            message="Automatic FK join uses an excluded column.",
                            node_key=node.node_key,
                            column_key=column.column_key,
                            edge_key=edge.edge_key,
                            physical_label=_column_label(node, column),
                            downstream_impact="Compiler would depend on a non-queryable column.",
                            suggested_action="Disable automatic join or make the FK column queryable.",
                        )
                    )
    return issues


def _has_automatic_join_between(
    graph: QueryabilityGraphArtifact,
    relationship: QueryabilityExpectedRelationship,
) -> bool:
    nodes = {node.node_key: node for node in graph.nodes}
    for edge in graph.edges:
        if not isinstance(edge, QueryabilityForeignKeyEdge):
            continue
        if not edge.automatic_join_allowed:
            continue
        from_node = nodes.get(edge.from_node_key)
        to_node = nodes.get(edge.to_node_key)
        if from_node is None or to_node is None:
            continue
        if (
            from_node.object_name == relationship.from_object_name
            and to_node.object_name == relationship.to_object_name
        ):
            return True
    return False


def _lineage_join_issue(edge_key: str) -> QueryabilityGraphValidationIssue:
    return _issue(
        code="LINEAGE_USED_AS_JOIN",
        severity="error",
        message="View lineage edge cannot be used as a join path.",
        edge_key=edge_key,
        downstream_impact="Compiler could join through provenance evidence.",
        suggested_action="Keep lineage as audit/provenance only.",
    )


def _duplicate_key_issues(
    *,
    code: str,
    values: list[str],
    downstream_impact: str,
    suggested_action: str,
) -> list[QueryabilityGraphValidationIssue]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return [
        _issue(
            code=code,
            severity="error",
            message="Graph contains a duplicate stable key.",
            physical_label=value,
            downstream_impact=downstream_impact,
            suggested_action=suggested_action,
        )
        for value in sorted(duplicates)
    ]


def _report(
    *,
    graph: QueryabilityGraphArtifact,
    issues: list[QueryabilityGraphValidationIssue],
) -> QueryabilityGraphValidationReport:
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    info = [issue for issue in issues if issue.severity == "info"]
    status: QueryabilityValidationStatus
    if errors:
        status = "invalid"
    elif warnings:
        status = "valid_with_warnings"
    else:
        status = "valid"
    return QueryabilityGraphValidationReport(
        status=status,
        errors=errors,
        warnings=warnings,
        info=info,
        summary=QueryabilityGraphValidationSummary(
            node_count=len(graph.nodes),
            column_count=sum(len(node.columns) for node in graph.nodes),
            edge_count=len(graph.edges),
            automatic_join_count=sum(
                1 for edge in graph.edges if edge.automatic_join_allowed
            ),
            bridge_candidate_count=sum(1 for node in graph.nodes if node.bridge_candidate),
            pii_column_count=sum(
                1
                for node in graph.nodes
                for column in node.columns
                if column.sensitivity == "pii"
            ),
            sensitive_column_count=sum(
                1
                for node in graph.nodes
                for column in node.columns
                if column.sensitivity == "sensitive"
            ),
        ),
        blocking_codes=sorted({issue.code for issue in errors}),
    )


def _issue(
    *,
    code: str,
    severity: QueryabilityValidationSeverity,
    message: str,
    node_key: str | None = None,
    column_key: str | None = None,
    edge_key: str | None = None,
    physical_label: str | None = None,
    downstream_impact: str,
    suggested_action: str,
) -> QueryabilityGraphValidationIssue:
    return QueryabilityGraphValidationIssue(
        code=code,
        severity=severity,
        message=message,
        node_key=node_key,
        column_key=column_key,
        edge_key=edge_key,
        physical_label=physical_label,
        downstream_impact=downstream_impact,
        suggested_action=suggested_action,
    )


def _node_label(node) -> str:
    return f"{node.schema_name}.{node.object_name}"


def _column_label(node, column) -> str:
    return f"{node.schema_name}.{node.object_name}.{column.name}"
