import graphFixture from "../../../../packages/contracts/src/fixtures/queryability-graph-v1.json";
import semanticLayerFixture from "../../../../packages/contracts/src/fixtures/semantic-layer-v1.json";

import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ActiveTenantContext } from "../tenant";

vi.mock("server-only", () => ({}));

const mocks = vi.hoisted(() => ({
  postQueryEngine: vi.fn(),
  readCurrentQueryabilityGraph: vi.fn(),
  readCurrentSemanticLayer: vi.fn()
}));

vi.mock("../query-engine/client", () => ({
  postQueryEngine: mocks.postQueryEngine
}));

vi.mock("../semantic-layer/service", () => ({
  graphForSemanticService: (graph: unknown) => graph,
  readCurrentQueryabilityGraph: mocks.readCurrentQueryabilityGraph,
  readCurrentSemanticLayer: mocks.readCurrentSemanticLayer
}));

const { resolveQueryIntent } = await import("./service");

const context = {
  supabase: {},
  tenantId: semanticLayerFixture.tenant_id,
  userId: "11111111-1111-4111-8111-111111111111",
  role: "owner"
} as unknown as ActiveTenantContext;

describe("query intent service", () => {
  beforeEach(() => {
    const metric = semanticLayerFixture.metrics[0];
    if (!metric) {
      throw new Error("semantic fixture must include at least one metric");
    }
    vi.clearAllMocks();
    mocks.readCurrentSemanticLayer.mockResolvedValue({
      artifact: semanticLayerFixture,
      summary: {}
    });
    mocks.readCurrentQueryabilityGraph.mockResolvedValue({
      id: semanticLayerFixture.queryability_graph_version_id,
      connection_id: semanticLayerFixture.connection_id,
      version: 1,
      graph_hash: semanticLayerFixture.base_graph_hash,
      graph: graphFixture
    });
    mocks.postQueryEngine.mockResolvedValue({
      status: "ready",
      plan: {
        primary_metric_key: metric.metric_key,
        requested_concept_ref: "records",
        selected_variant: metric.metric_variant,
        group_by_dimensions: [],
        required_edge_path_keys: [],
        grain_safety_decision: "safe",
        filters: [],
        rejected_alternatives: [],
        disclosures: [],
        audit_trail: []
      },
      audit_trail: [],
      message: "Query intent resolved without SQL generation."
    });
  });

  it("posts a deterministic resolver request without SQL or execution payloads", async () => {
    const resolution = await resolveQueryIntent({
      connectionId: semanticLayerFixture.connection_id,
      context,
      question: "fatturato 2008"
    });

    expect(mocks.postQueryEngine).toHaveBeenCalledWith(
      "/query/intent/resolve",
      expect.objectContaining({
        tenant_id: semanticLayerFixture.tenant_id,
        connection_id: semanticLayerFixture.connection_id,
        user_id: context.userId,
        question: "fatturato 2008",
        semantic_layer: semanticLayerFixture,
        graph: graphFixture,
        ai_enabled: false
      }),
      expect.anything(),
      30_000
    );
    const payload = mocks.postQueryEngine.mock.calls[0]?.[1] as Record<
      string,
      unknown
    >;
    expect(payload.sql).toBeUndefined();
    expect(payload.execution).toBeUndefined();
    expect(resolution.graph).toEqual(graphFixture);
    expect(resolution.semanticLayer).toEqual(semanticLayerFixture);
    expect(resolution.result.status).toBe("ready");
  });
});
