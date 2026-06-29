import type {
  QueryabilityEdge,
  QueryabilityGraphArtifact,
  QueryIntentAuditEvent,
  QueryIntentResult,
  SemanticColumn,
  SemanticLayer
} from "@atlantebi/contracts";

import {
  buildSemanticIndexes,
  semanticColumnLabel
} from "../semantic-layer/presentation";

export type QueryIntentDebugPresentation = {
  metricLabel: string;
  dateLabel: string;
  timeRangeStartLabel: string;
  timeRangeEndLabel: string;
  groupByLabels: string[];
  edgeLabels: string[];
  auditLabels: string[];
};

export function buildQueryIntentDebugPresentation({
  graph,
  result,
  semanticLayer
}: {
  graph: QueryabilityGraphArtifact | null;
  result: QueryIntentResult;
  semanticLayer: SemanticLayer | null;
}): QueryIntentDebugPresentation {
  const indexes = semanticLayer ? buildSemanticIndexes(semanticLayer) : null;
  const graphIndexes = graph ? buildGraphIndexes(graph) : null;
  const metric =
    result.plan && semanticLayer
      ? semanticLayer.metrics.find(
          (item) => item.metric_key === result.plan?.primary_metric_key
        )
      : undefined;
  const dateColumn =
    result.plan?.effective_date_column_key && indexes
      ? indexes.columns.get(result.plan.effective_date_column_key)
      : undefined;
  const dimensionEdgeKeys = new Set(
    result.plan?.group_by_dimensions.flatMap((dimension) => dimension.edge_path) ??
      []
  );
  const datePathEdgeKeys = new Set(metric?.required_join_edge_keys ?? []);

  return {
    metricLabel:
      metric && indexes
        ? `${metric.name} - ${metricDebugFormulaLabel(metric, indexes)} - key ${metric.metric_key}`
        : result.plan
          ? `Metrica non disponibile - key ${result.plan.primary_metric_key}`
          : "-",
    dateLabel:
      result.plan?.effective_date_column_key && indexes
        ? `${semanticColumnDebugLabel(dateColumn, indexes)} - key ${result.plan.effective_date_column_key}`
        : "-",
    timeRangeStartLabel: result.plan?.time_range
      ? `${result.plan.time_range.start_date} (inclusive)`
      : "-",
    timeRangeEndLabel: result.plan?.time_range
      ? `${result.plan.time_range.end_date} (exclusive)`
      : "-",
    groupByLabels:
      result.plan?.group_by_dimensions.map((dimension) =>
        indexes && semanticLayer
          ? `${dimensionColumnLabel(dimension.column_key, semanticLayer, indexes)} - key ${dimension.column_key}`
          : `Dimensione non disponibile - key ${dimension.column_key}`
      ) ?? [],
    edgeLabels:
      result.plan?.required_edge_path_keys.map((edgeKey) =>
        edgeLabel({
          datePathEdgeKeys,
          dimensionEdgeKeys,
          edgeKey,
          graphIndexes
        })
      ) ?? [],
    auditLabels: readableAuditLabels({
      graphIndexes,
      indexes,
      result,
      semanticLayer
    })
  };
}

function buildGraphIndexes(graph: QueryabilityGraphArtifact) {
  return {
    edges: new Map(graph.edges.map((edge) => [edge.edge_key, edge])),
    nodes: new Map(graph.nodes.map((node) => [node.node_key, node]))
  };
}

function dimensionColumnLabel(
  columnKey: string,
  semanticLayer: SemanticLayer,
  indexes: ReturnType<typeof buildSemanticIndexes>
) {
  const column = indexes.columns.get(columnKey);
  if (!column) {
    return "Dimensione non disponibile";
  }
  const baseLabel = semanticColumnDebugLabel(column, indexes);
  const descriptiveColumn = semanticLayer.columns.find(
    (candidate) =>
      candidate.node_key === column.node_key &&
      candidate.column_key !== column.column_key &&
      candidate.included &&
      candidate.physical_name.toLowerCase() === "name"
  );
  if (!descriptiveColumn) {
    return baseLabel;
  }
  return `${baseLabel} / ${semanticColumnDebugLabel(descriptiveColumn, indexes)}`;
}

function metricDebugFormulaLabel(
  metric: SemanticLayer["metrics"][number],
  indexes: ReturnType<typeof buildSemanticIndexes>
) {
  const measure = metric.measure_column_key
    ? semanticColumnDebugLabel(indexes.columns.get(metric.measure_column_key), indexes)
    : "*";
  return `${metric.aggregation.toUpperCase()}(${measure})`;
}

function semanticColumnDebugLabel(
  column: SemanticColumn | undefined,
  indexes: ReturnType<typeof buildSemanticIndexes>
) {
  if (!column) {
    return "Colonna non disponibile";
  }
  const semanticLabel = semanticColumnLabel(column, indexes.tables);
  const table = indexes.tables.get(column.node_key);
  const physicalLabel = table
    ? `${table.schema_name}.${table.object_name}.${column.physical_name}`
    : column.physical_name;
  return semanticLabel.includes(physicalLabel)
    ? semanticLabel
    : `${semanticLabel} (${physicalLabel})`;
}

function edgeLabel({
  datePathEdgeKeys,
  dimensionEdgeKeys,
  edgeKey,
  graphIndexes
}: {
  datePathEdgeKeys: Set<string>;
  dimensionEdgeKeys: Set<string>;
  edgeKey: string;
  graphIndexes: ReturnType<typeof buildGraphIndexes> | null;
}) {
  const reasons = [
    datePathEdgeKeys.has(edgeKey) ? "date_path" : null,
    dimensionEdgeKeys.has(edgeKey) ? "dimension_path" : null
  ].filter(Boolean);
  const reasonLabel = reasons.length > 0 ? reasons.join(", ") : "required_path";
  const edge = graphIndexes?.edges.get(edgeKey);
  if (!edge || !graphIndexes) {
    return `Edge non disponibile - reason ${reasonLabel} - key ${edgeKey}`;
  }
  return `${edgeEndpointsLabel(edge, graphIndexes)} - reason ${reasonLabel} - key ${edgeKey}`;
}

function edgeEndpointsLabel(
  edge: QueryabilityEdge,
  graphIndexes: ReturnType<typeof buildGraphIndexes>
) {
  const from = graphIndexes.nodes.get(edge.from_node_key)?.object_name ?? edge.from_node_key;
  const to =
    "to_node_key" in edge && edge.to_node_key
      ? graphIndexes.nodes.get(edge.to_node_key)?.object_name ?? edge.to_node_key
      : "external/unresolved";
  return `${from} -> ${to}`;
}

function readableAuditLabels({
  graphIndexes,
  indexes,
  result,
  semanticLayer
}: {
  graphIndexes: ReturnType<typeof buildGraphIndexes> | null;
  indexes: ReturnType<typeof buildSemanticIndexes> | null;
  result: QueryIntentResult;
  semanticLayer: SemanticLayer | null;
}) {
  const labels: string[] = [];
  if (result.unsupported_reason) {
    labels.push(`Unsupported reason: ${result.unsupported_reason}`);
  }
  if (result.plan && semanticLayer && indexes) {
    const metric = semanticLayer.metrics.find(
      (item) => item.metric_key === result.plan?.primary_metric_key
    );
    if (metric) {
      labels.push(
        `Selected metric: ${metric.name} - ${metricDebugFormulaLabel(metric, indexes)}`
      );
    }
    for (const dimension of result.plan.group_by_dimensions) {
      labels.push(
        `Selected dimension: ${dimensionColumnLabel(dimension.column_key, semanticLayer, indexes)}`
      );
    }
  }
  for (const event of result.audit_trail) {
    labels.push(readableAuditEvent(event, semanticLayer, indexes, graphIndexes));
  }
  return labels;
}

function readableAuditEvent(
  event: QueryIntentAuditEvent,
  semanticLayer: SemanticLayer | null,
  indexes: ReturnType<typeof buildSemanticIndexes> | null,
  graphIndexes: ReturnType<typeof buildGraphIndexes> | null
) {
  const metadata = Object.entries(event.metadata).map(([key, value]) => {
    if (typeof value !== "string") {
      return `${key}: ${String(value)}`;
    }
    if (key.includes("metric_key")) {
      return `${key}: ${metricMetadataLabel(value, semanticLayer, indexes)}`;
    }
    if (key.includes("column_key")) {
      return `${key}: ${columnMetadataLabel(value, indexes)}`;
    }
    if (key.includes("edge_key")) {
      return `${key}: ${edgeMetadataLabel(value, graphIndexes)}`;
    }
    return `${key}: ${value}`;
  });
  return `${event.code}: ${event.message}${metadata.length > 0 ? ` (${metadata.join("; ")})` : ""}`;
}

function metricMetadataLabel(
  metricKey: string,
  semanticLayer: SemanticLayer | null,
  indexes: ReturnType<typeof buildSemanticIndexes> | null
) {
  const metric = semanticLayer?.metrics.find((item) => item.metric_key === metricKey);
  if (!metric || !indexes) {
    return metricKey;
  }
  return `${metric.name} - ${metricDebugFormulaLabel(metric, indexes)} - key ${metricKey}`;
}

function columnMetadataLabel(
  columnKey: string,
  indexes: ReturnType<typeof buildSemanticIndexes> | null
) {
  const column: SemanticColumn | undefined = indexes?.columns.get(columnKey);
  if (!column || !indexes) {
    return columnKey;
  }
  return `${semanticColumnDebugLabel(column, indexes)} - key ${columnKey}`;
}

function edgeMetadataLabel(
  edgeKey: string,
  graphIndexes: ReturnType<typeof buildGraphIndexes> | null
) {
  const edge = graphIndexes?.edges.get(edgeKey);
  if (!edge || !graphIndexes) {
    return edgeKey;
  }
  return `${edgeEndpointsLabel(edge, graphIndexes)} - key ${edgeKey}`;
}
