import graphFixture from "../../../../packages/contracts/src/fixtures/queryability-graph-v1.json";
import semanticLayerFixture from "../../../../packages/contracts/src/fixtures/semantic-layer-v1.json";

import { describe, expect, it } from "vitest";

import type {
  QueryabilityGraphArtifact,
  QueryIntentResult,
  SemanticLayer
} from "@atlantebi/contracts";

import { buildQueryIntentDebugPresentation } from "./presentation";

const CHILD_PARENT_COLUMN_KEY =
  "3311111111111111111111111111111111111111111111111111111111111111";
const CHILD_NAME_COLUMN_KEY =
  "9911111111111111111111111111111111111111111111111111111111111111";
const EDGE_KEY =
  "5111111111111111111111111111111111111111111111111111111111111111";
const PARENT_TENANT_COLUMN_KEY =
  "2111111111111111111111111111111111111111111111111111111111111111";

function debugLayer(): SemanticLayer {
  const layer = structuredClone(semanticLayerFixture) as SemanticLayer;
  const metric = layer.metrics[0];
  const childColumn = layer.columns.find(
    (column) => column.column_key === CHILD_PARENT_COLUMN_KEY
  );
  if (!metric || !childColumn) {
    throw new Error("semantic fixture is missing debug test fields");
  }

  metric.name = "Fatturato righe";
  metric.aggregation = "sum";
  metric.measure_column_key = CHILD_PARENT_COLUMN_KEY;
  metric.default_date_column_key = PARENT_TENANT_COLUMN_KEY;
  metric.required_join_edge_keys = [EDGE_KEY];

  layer.columns.push({
    ...childColumn,
    column_key: CHILD_NAME_COLUMN_KEY,
    physical_name: "Name",
    display_name: "Nome dettaglio",
    technical_role: "text"
  });

  return layer;
}

function readyResult(layer: SemanticLayer): QueryIntentResult {
  const metric = layer.metrics[0];
  if (!metric) {
    throw new Error("semantic fixture is missing metric");
  }

  return {
    status: "ready",
    plan: {
      primary_metric_key: metric.metric_key,
      requested_concept_ref: "records",
      selected_variant: metric.metric_variant,
      effective_date_column_key: PARENT_TENANT_COLUMN_KEY,
      time_range: {
        kind: "year",
        start_date: "2008-01-01",
        end_date: "2009-01-01",
        label: "2008"
      },
      group_by_dimensions: [
        {
          column_key: CHILD_PARENT_COLUMN_KEY,
          edge_path: [EDGE_KEY],
          safety: "safe"
        }
      ],
      required_edge_path_keys: [EDGE_KEY],
      grain_safety_decision: "safe",
      filters: [],
      rejected_alternatives: [],
      disclosures: [],
      audit_trail: []
    },
    audit_trail: [
      {
        code: "DIMENSION_SELECTED",
        message: "Dimension selected.",
        metadata: {
          dimension_column_key: CHILD_PARENT_COLUMN_KEY,
          metric_key: metric.metric_key
        }
      }
    ],
    message: "Query intent resolved without SQL generation."
  };
}

describe("query intent debug presentation", () => {
  it("renders readable labels while keeping stable keys visible", () => {
    const layer = debugLayer();
    const result = readyResult(layer);

    const debug = buildQueryIntentDebugPresentation({
      graph: graphFixture as QueryabilityGraphArtifact,
      result,
      semanticLayer: layer
    });

    expect(debug.metricLabel).toContain("Fatturato righe");
    expect(debug.metricLabel).toContain("SUM(");
    expect(debug.metricLabel).toContain("SalesLT.Child.ParentID");
    expect(debug.metricLabel).toContain(layer.metrics[0]?.metric_key);
    expect(debug.dateLabel).toContain("SalesLT.Parent.TenantID");
    expect(debug.dateLabel).toContain(PARENT_TENANT_COLUMN_KEY);
    expect(debug.timeRangeStartLabel).toBe("2008-01-01 (inclusive)");
    expect(debug.timeRangeEndLabel).toBe("2009-01-01 (exclusive)");
    expect(debug.groupByLabels[0]).toContain(CHILD_PARENT_COLUMN_KEY);
    expect(debug.groupByLabels[0]).toContain("SalesLT.Child.Name");
    expect(debug.edgeLabels[0]).toContain("Child -> Parent");
    expect(debug.edgeLabels[0]).toContain("date_path");
    expect(debug.edgeLabels[0]).toContain("dimension_path");
    expect(debug.edgeLabels[0]).toContain(EDGE_KEY);
    expect(debug.auditLabels).toEqual(
      expect.arrayContaining([
        expect.stringContaining("Selected metric: Fatturato righe"),
        expect.stringContaining("dimension_column_key:"),
        expect.stringContaining(CHILD_PARENT_COLUMN_KEY)
      ])
    );
  });

  it("keeps unsupported reasons readable for blocked results", () => {
    const result: QueryIntentResult = {
      status: "blocked",
      unsupported_reason: "unsafe_dimension_for_metric",
      audit_trail: [],
      message: "Requested dimension is not safe for the selected metric."
    };

    const debug = buildQueryIntentDebugPresentation({
      graph: graphFixture as QueryabilityGraphArtifact,
      result,
      semanticLayer: debugLayer()
    });

    expect(debug.metricLabel).toBe("-");
    expect(debug.auditLabels).toContain(
      "Unsupported reason: unsafe_dimension_for_metric"
    );
  });
});
