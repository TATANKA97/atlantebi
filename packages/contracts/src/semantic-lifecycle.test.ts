import { describe, expect, it } from "vitest";

import graphFixture from "./fixtures/queryability-graph-v1.json";
import semanticFixture from "./fixtures/semantic-layer-v1.json";
import {
  SemanticRebaseDroppedItemSchema,
  SemanticRebaseReportSchema,
  SemanticRebaseRequestSchema,
  SemanticRebaseResultSchema,
  SemanticSeedRequestSchema
} from "./index";

const nextSemanticVersionId = "99999999-9999-4999-8999-999999999999";
const nextGraphVersionId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

const validReport = {
  carried_table_keys: [semanticFixture.tables[0]!.node_key],
  dropped_tables: [
    {
      item_type: "table" as const,
      item_key: semanticFixture.tables[1]!.node_key,
      reason_codes: ["TARGET_KEY_MISSING" as const]
    }
  ],
  carried_column_keys: [semanticFixture.columns[0]!.column_key],
  dropped_columns: [
    {
      item_type: "column" as const,
      item_key: semanticFixture.columns[1]!.column_key,
      reason_codes: ["TARGET_NOT_QUERYABLE" as const]
    }
  ],
  carried_business_concept_keys: [
    semanticFixture.business_concepts[0]!.business_concept_key
  ],
  dropped_business_concepts: [
    {
      item_type: "business_concept" as const,
      item_key: "aaaaaaaa-1111-4111-8111-111111111111",
      reason_codes: ["DEPENDENCY_DROPPED" as const]
    }
  ],
  carried_metric_keys: [semanticFixture.metrics[0]!.metric_key],
  dropped_metrics: [
    {
      item_type: "metric" as const,
      item_key: "bbbbbbbb-2222-4222-8222-222222222222",
      reason_codes: [
        "TARGET_EDGE_NOT_TRUSTED" as const,
        "INVALID_AFTER_REBASE" as const
      ]
    }
  ]
};

describe("semantic lifecycle contracts", () => {
  it("accepts a strict semantic seed request", () => {
    const parsed = SemanticSeedRequestSchema.parse({
      graph: graphFixture,
      semantic_version_id: nextSemanticVersionId,
      queryability_graph_version_id: nextGraphVersionId,
      version: 2,
      semantic_policy: semanticFixture.semantic_policy_snapshot
    });

    expect(parsed.version).toBe(2);
    expect(parsed.graph.contract_version).toBe("queryability_graph.v1");
  });

  it("accepts a strict semantic rebase request", () => {
    const parsed = SemanticRebaseRequestSchema.parse({
      source_layer: semanticFixture,
      target_graph: graphFixture,
      semantic_version_id: nextSemanticVersionId,
      queryability_graph_version_id: nextGraphVersionId,
      version: 2,
      semantic_policy: semanticFixture.semantic_policy_snapshot
    });

    expect(parsed.source_layer.semantic_version_id).toBe(
      semanticFixture.semantic_version_id
    );
    expect(parsed.target_graph.graph_hash).toBe(graphFixture.graph_hash);
  });

  it("accepts separated carried and dropped lifecycle results", () => {
    const report = SemanticRebaseReportSchema.parse(validReport);
    const result = SemanticRebaseResultSchema.parse({
      semantic_layer: {
        ...semanticFixture,
        semantic_version_id: nextSemanticVersionId,
        queryability_graph_version_id: nextGraphVersionId,
        version: 2,
        status: "draft",
        revision: 1
      },
      rebase_report: report
    });

    expect(result.rebase_report.carried_table_keys).toHaveLength(1);
    expect(result.rebase_report.dropped_metrics[0]?.reason_codes).toEqual([
      "TARGET_EDGE_NOT_TRUSTED",
      "INVALID_AFTER_REBASE"
    ]);
  });

  it("allows empty carried and dropped lists", () => {
    expect(() =>
      SemanticRebaseReportSchema.parse({
        carried_table_keys: [],
        dropped_tables: [],
        carried_column_keys: [],
        dropped_columns: [],
        carried_business_concept_keys: [],
        dropped_business_concepts: [],
        carried_metric_keys: [],
        dropped_metrics: []
      })
    ).not.toThrow();
  });

  it("rejects unknown fields at every lifecycle envelope", () => {
    expect(() =>
      SemanticSeedRequestSchema.parse({
        graph: graphFixture,
        semantic_version_id: nextSemanticVersionId,
        queryability_graph_version_id: nextGraphVersionId,
        version: 2,
        legacy_mode: true
      })
    ).toThrow();

    expect(() =>
      SemanticRebaseRequestSchema.parse({
        source_layer: semanticFixture,
        target_graph: graphFixture,
        semantic_version_id: nextSemanticVersionId,
        queryability_graph_version_id: nextGraphVersionId,
        version: 2,
        match_by_name: true
      })
    ).toThrow();

    expect(() =>
      SemanticRebaseResultSchema.parse({
        semantic_layer: semanticFixture,
        rebase_report: validReport,
        warnings: []
      })
    ).toThrow();
  });

  it("enforces canonical UUIDs and sha256 stable keys", () => {
    expect(() =>
      SemanticSeedRequestSchema.parse({
        graph: graphFixture,
        semantic_version_id: "not-a-uuid",
        queryability_graph_version_id: nextGraphVersionId,
        version: 1
      })
    ).toThrow();

    expect(() =>
      SemanticRebaseDroppedItemSchema.parse({
        item_type: "table",
        item_key: "not-a-sha256",
        reason_codes: ["TARGET_KEY_MISSING"]
      })
    ).toThrow();

    expect(() =>
      SemanticRebaseDroppedItemSchema.parse({
        item_type: "metric",
        item_key: semanticFixture.metrics[0]!.metric_definition_hash,
        reason_codes: ["DEFINITION_CHANGED"]
      })
    ).toThrow();

    expect(() =>
      SemanticRebaseReportSchema.parse({
        ...validReport,
        carried_business_concept_keys: [
          "aaaaaaaa-aaaa-0aaa-8aaa-aaaaaaaaaaaa"
        ]
      })
    ).toThrow();
  });

  it("rejects invalid reason codes, empty reasons, and non-positive versions", () => {
    expect(() =>
      SemanticRebaseDroppedItemSchema.parse({
        item_type: "column",
        item_key: semanticFixture.columns[0]!.column_key,
        reason_codes: []
      })
    ).toThrow();

    expect(() =>
      SemanticRebaseDroppedItemSchema.parse({
        item_type: "business_concept",
        item_key: semanticFixture.business_concepts[0]!.business_concept_key,
        reason_codes: ["RENAMED_BY_HEURISTIC"]
      })
    ).toThrow();

    expect(() =>
      SemanticRebaseRequestSchema.parse({
        source_layer: semanticFixture,
        target_graph: graphFixture,
        semantic_version_id: nextSemanticVersionId,
        queryability_graph_version_id: nextGraphVersionId,
        version: 0
      })
    ).toThrow();
  });

  it("rejects blocked graphs, cross-scope rebases, and in-place rebases", () => {
    expect(() =>
      SemanticSeedRequestSchema.parse({
        graph: { ...graphFixture, status: "blocked" },
        semantic_version_id: nextSemanticVersionId,
        queryability_graph_version_id: nextGraphVersionId,
        version: 1
      })
    ).toThrow();

    expect(() =>
      SemanticRebaseRequestSchema.parse({
        source_layer: semanticFixture,
        target_graph: {
          ...graphFixture,
          connection_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        },
        semantic_version_id: nextSemanticVersionId,
        queryability_graph_version_id: nextGraphVersionId,
        version: 2
      })
    ).toThrow();

    expect(() =>
      SemanticRebaseRequestSchema.parse({
        source_layer: semanticFixture,
        target_graph: graphFixture,
        semantic_version_id: semanticFixture.semantic_version_id,
        queryability_graph_version_id: nextGraphVersionId,
        version: 2
      })
    ).toThrow();

    expect(() =>
      SemanticRebaseRequestSchema.parse({
        source_layer: semanticFixture,
        target_graph: graphFixture,
        semantic_version_id: nextSemanticVersionId,
        queryability_graph_version_id: nextGraphVersionId,
        version: semanticFixture.version
      })
    ).toThrow();

    expect(() =>
      SemanticRebaseRequestSchema.parse({
        source_layer: { ...semanticFixture, status: "proposed" },
        target_graph: graphFixture,
        semantic_version_id: nextSemanticVersionId,
        queryability_graph_version_id: nextGraphVersionId,
        version: 2
      })
    ).toThrow();
  });
});
