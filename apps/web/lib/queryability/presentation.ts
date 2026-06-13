import type {
  QueryabilityForeignKeyEdge,
  QueryabilityGraphArtifact,
  QueryabilityNode,
  SchemaColumnMetadata
} from "@atlantebi/contracts";

export function foreignKeyEdgeDetail(
  edge: QueryabilityForeignKeyEdge,
  targetObject: string
) {
  const columnPairs = edge.column_pairs
    .map(
      (pair) =>
        `${pair.from_column} → ${targetObject}.${pair.to_column}`
    )
    .join(", ");
  return `${edge.constraint_name}: ${columnPairs}`;
}

export function schemaColumnFlags({
  column,
  primaryKeyColumnCount,
  tableType
}: {
  column: SchemaColumnMetadata;
  primaryKeyColumnCount: number;
  tableType: "base_table" | "view";
}) {
  const compositePrimaryKey =
    column.is_primary_key && primaryKeyColumnCount > 1;
  return [
    column.is_primary_key
      ? compositePrimaryKey
        ? "part_of_composite_pk"
        : "PK"
      : null,
    column.is_foreign_key ? "FK" : null,
    column.is_single_column_unique ? "unique" : null,
    column.is_composite_unique_member ? "part_of_composite_unique" : null,
    column.is_identity
      ? tableType === "view"
        ? "identity_propagated"
        : "identity"
      : null,
    column.is_computed ? "computed" : null,
    column.default_value !== undefined ? "default" : null,
    column.is_nullable ? "nullable" : "not null",
    column.collation ? `collation ${column.collation}` : null
  ].filter((value): value is string => value !== null);
}

export function graphLineageCounts(graph: QueryabilityGraphArtifact) {
  return {
    objectEdges: graph.edges.filter(
      (edge) => edge.edge_type === "view_depends_on"
    ).length,
    columnEdges: graph.edges.filter(
      (edge) => edge.edge_type === "view_column_derives_from"
    ).length
  };
}

export function viewLineageLabel(node: QueryabilityNode | undefined) {
  if (!node || node.object_type !== "view") {
    return "unavailable";
  }
  return `object ${node.view_lineage_status ?? "unavailable"}, columns ${
    node.view_column_lineage_status ?? "unavailable"
  }`;
}
