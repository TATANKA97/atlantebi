import { describe, expect, it } from "vitest";

import graphFixture from "./fixtures/queryability-graph-v1.json";
import {
  QueryabilityGraphArtifactSchema,
  QueryabilityGraphVersionSchema,
  QueryabilityPathResultSchema
} from "./index";

describe("queryability graph contracts", () => {
  it("accepts the shared strict V1 graph fixture", () => {
    const graph = QueryabilityGraphArtifactSchema.parse(graphFixture);

    expect(graph.status).toBe("partial");
    expect(graph.semantic_status).toBe("not_initialized");
    expect(graph.edges.map((edge) => edge.edge_type)).toEqual([
      "fk_join",
      "view_depends_on",
      "view_column_derives_from"
    ]);
  });

  it("rejects unknown fields and invalid hashes", () => {
    expect(() =>
      QueryabilityGraphArtifactSchema.parse({
        ...graphFixture,
        graph_hash: "A".repeat(64)
      })
    ).toThrow();
    expect(() =>
      QueryabilityGraphArtifactSchema.parse({
        ...graphFixture,
        unexpected: true
      })
    ).toThrow();
  });

  it("keeps lineage edges evidence-only", () => {
    const lineage = graphFixture.edges[1];

    expect(() =>
      QueryabilityGraphArtifactSchema.parse({
        ...graphFixture,
        edges: [
          graphFixture.edges[0],
          { ...lineage, automatic_join_allowed: true }
        ]
      })
    ).toThrow();
  });

  it("validates persisted graph versions and path limits", () => {
    const version = QueryabilityGraphVersionSchema.parse({
      graph_version_id: "44444444-4444-4444-8444-444444444444",
      graph_version: 1,
      created_at: "2026-06-12T08:00:00.000Z",
      graph: graphFixture
    });
    expect(version.graph_version).toBe(1);

    const step = {
      edge_key: "5".repeat(64),
      from_node_key: "3".repeat(64),
      to_node_key: "1".repeat(64),
      traversal: "child_to_parent" as const,
      cardinality: "zero_or_one" as const
    };
    expect(() =>
      QueryabilityPathResultSchema.parse({
        status: "found",
        paths: [
          {
            steps: [step, step, step, step, step],
            fanout_warning: false
          }
        ],
        reason_codes: []
      })
    ).toThrow();
  });
});
