import type {
  SemanticBusinessConcept,
  SemanticColumn,
  SemanticLayer,
  SemanticMetric,
  SemanticTable,
  SemanticValidationReport
} from "@atlantebi/contracts";

type SemanticIndexes = {
  columns: Map<string, SemanticColumn>;
  concepts: Map<string, SemanticBusinessConcept>;
  tables: Map<string, SemanticTable>;
};

const GENERATION_AUDIT_CODES = new Set([
  "AI_AMBIGUITY_TARGET_NOT_RESOLVED",
  "AI_REQUIRED_METRIC_MISMATCH"
]);

export function buildSemanticIndexes(layer: SemanticLayer): SemanticIndexes {
  return {
    columns: new Map(layer.columns.map((column) => [column.column_key, column])),
    concepts: new Map(
      layer.business_concepts.map((concept) => [
        concept.business_concept_key,
        concept
      ])
    ),
    tables: new Map(layer.tables.map((table) => [table.node_key, table]))
  };
}

export function splitSemanticQualityGateReport(
  report: SemanticLayer["quality_report"]
) {
  if (report.status !== "passed") {
    return {
      auditIssues: [],
      auditRejectedCandidates: [],
      mainIssues: report.issues,
      mainRejectedCandidates: report.rejected_candidates
    };
  }
  return {
    auditIssues: report.issues.filter((issue) =>
      GENERATION_AUDIT_CODES.has(issue.code)
    ),
    auditRejectedCandidates: report.rejected_candidates.filter((candidate) =>
      GENERATION_AUDIT_CODES.has(candidate.reason_code)
    ),
    mainIssues: report.issues.filter(
      (issue) => !GENERATION_AUDIT_CODES.has(issue.code)
    ),
    mainRejectedCandidates: report.rejected_candidates.filter(
      (candidate) => !GENERATION_AUDIT_CODES.has(candidate.reason_code)
    )
  };
}

export function semanticObjectLabel(table: SemanticTable | undefined) {
  if (!table) {
    return "Oggetto non disponibile";
  }
  return table.display_name ?? `${table.schema_name}.${table.object_name}`;
}

export function semanticColumnLabel(
  column: SemanticColumn | undefined,
  tables: Map<string, SemanticTable>
) {
  if (!column) {
    return "Colonna non disponibile";
  }
  const table = tables.get(column.node_key);
  const tableLabel = table
    ? table.display_name ?? table.object_name
    : "Oggetto non disponibile";
  return `${tableLabel}.${column.display_name ?? column.physical_name}`;
}

export function metricFormulaLabel(
  metric: SemanticMetric,
  indexes: Pick<SemanticIndexes, "columns" | "tables">
) {
  const measure = metric.measure_column_key
    ? semanticColumnLabel(
        indexes.columns.get(metric.measure_column_key),
        indexes.tables
      )
    : "*";
  const aggregation = metric.aggregation.toUpperCase();
  return `${aggregation}(${measure})`;
}

export function metricGrainLabel(
  metric: SemanticMetric,
  indexes: Pick<SemanticIndexes, "columns" | "tables">
) {
  const table = semanticObjectLabel(indexes.tables.get(metric.grain_table_key));
  const columns = metric.grain_column_keys.map((columnKey) => {
    const column = indexes.columns.get(columnKey);
    return column?.display_name ?? column?.physical_name ?? "colonna non disponibile";
  });
  return `${table}: ${columns.join(", ")}`;
}

export function metricConceptLabel(
  metric: SemanticMetric,
  concepts: Map<string, SemanticBusinessConcept>
) {
  const concept = concepts.get(metric.business_concept_key);
  return `${concept?.display_name ?? concept?.canonical_name ?? "Concept non disponibile"} / ${metric.metric_variant}`;
}

export function semanticLayerCounts(layer: SemanticLayer) {
  return {
    ambiguitiesOpen: layer.ambiguities.filter(
      (ambiguity) => ambiguity.status === "open"
    ).length,
    columns: layer.columns.length,
    concepts: layer.business_concepts.length,
    eligibleMetrics: layer.metrics.filter((metric) =>
      ["eligible", "eligible_with_disclosure"].includes(
        metric.compiler_eligibility
      )
    ).length,
    metrics: layer.metrics.length,
    tables: layer.tables.length
  };
}

export function validationIssueCounts(report: SemanticValidationReport) {
  return {
    blocking: report.blocking_errors.length,
    info: report.info.length,
    total:
      report.blocking_errors.length + report.warnings.length + report.info.length,
    warnings: report.warnings.length
  };
}

export function confidenceLabel(metric: SemanticMetric) {
  return `${metric.confidence_label} (${Math.round(metric.confidence_score * 100)}%)`;
}

export function paginateItems<T>(
  items: T[],
  requestedPage: string | undefined,
  pageSize: number
) {
  const parsedPage = Number.parseInt(requestedPage ?? "1", 10);
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const page = Number.isFinite(parsedPage)
    ? Math.min(Math.max(parsedPage, 1), pageCount)
    : 1;
  const start = (page - 1) * pageSize;

  return {
    items: items.slice(start, start + pageSize),
    page,
    pageCount,
    total: items.length
  };
}
