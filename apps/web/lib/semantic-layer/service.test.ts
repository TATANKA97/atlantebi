import graphFixture from "../../../../packages/contracts/src/fixtures/queryability-graph-v1.json";

import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const mocks = vi.hoisted(() => {
  class MockQueryEngineRequestError extends Error {
    constructor(
      message: string,
      readonly status: number
    ) {
      super(message);
      this.name = "QueryEngineRequestError";
    }
  }

  return {
    canManageSemanticLayer: vi.fn(() => true),
    createSupabaseAdminClient: vi.fn(),
    isSecurityOperationLimitError: vi.fn(() => false),
    postQueryEngine: vi.fn(),
    QueryEngineRequestError: MockQueryEngineRequestError,
    readDefaultAIProviderConfig: vi.fn(),
    rpc: vi.fn(),
    withSecurityOperationLease: vi.fn(
      async ({ run }: { run: () => Promise<unknown> }) => run()
    )
  };
});

vi.mock("../query-engine/client", () => ({
  postQueryEngine: mocks.postQueryEngine,
  QueryEngineRequestError: mocks.QueryEngineRequestError
}));

vi.mock("../ai-provider-settings/service", () => ({
  readDefaultAIProviderConfig: mocks.readDefaultAIProviderConfig
}));

vi.mock("../security/operation-lease", () => ({
  isSecurityOperationLimitError: mocks.isSecurityOperationLimitError,
  withSecurityOperationLease: mocks.withSecurityOperationLease
}));

vi.mock("../supabase/admin", () => ({
  createSupabaseAdminClient: mocks.createSupabaseAdminClient
}));

vi.mock("../tenant", () => ({
  canManageSemanticLayer: mocks.canManageSemanticLayer
}));

const {
  createAndGenerateSemanticDraft,
  listSemanticVersions,
  SemanticDraftPatchSchema
} = await import("./service");

const tenantId = "20000000-0000-4000-8000-000000000001";
const userId = "10000000-0000-4000-8000-000000000001";
const connectionId = "30000000-0000-4000-8000-000000000001";
const graphVersionId = "40000000-0000-4000-8000-000000000001";
const metricKey = "50000000-0000-4000-8000-000000000001";
const hash = "a".repeat(64);

function semanticTableRows() {
  return {
    db_connections: {
      data: {
        default_currency: "USD",
        semantic_policy_config: null
      },
      single: true
    },
    queryability_graph_derivations: {
      data: {
        graph_version_id: graphVersionId
      },
      single: true
    },
    queryability_graph_versions: {
      data: {
        connection_id: connectionId,
        graph: graphFixture,
        graph_hash: graphFixture.graph_hash,
        id: graphVersionId,
        version: 1
      },
      single: true
    },
    semantic_layer_versions: {
      data: [],
      single: false
    },
    tenants: {
      data: {
        default_currency: "USD"
      },
      single: true
    }
  };
}

function createSupabaseMock() {
  const tableRows = semanticTableRows();
  const selectedFields: Record<string, string[]> = {};
  const from = vi.fn((table: keyof ReturnType<typeof semanticTableRows>) => {
    const response = tableRows[table] ?? { data: null, single: true };
    const chain = {
      eq: vi.fn(() => chain),
      limit: vi.fn(() => chain),
      maybeSingle: vi.fn(async () => ({
        data: response.single ? response.data : null,
        error: null
      })),
      order: vi.fn(() => chain),
      select: vi.fn((fields: string) => {
        const tableName = String(table);
        selectedFields[tableName] ??= [];
        selectedFields[tableName].push(fields);
        return chain;
      }),
      then: (
        resolve: (value: { data: unknown; error: null }) => unknown,
        reject?: (reason: unknown) => unknown
      ) =>
        Promise.resolve({ data: response.data, error: null }).then(
          resolve,
          reject
        )
    };
    return chain;
  });
  return {
    from,
    selectedFields,
    rpc: mocks.rpc
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.createSupabaseAdminClient.mockReturnValue(createSupabaseMock());
  mocks.readDefaultAIProviderConfig.mockResolvedValue({
    model: "claude-sonnet-4-6",
    provider: "anthropic",
    thinking: {
      enabled: true,
      mode: "dynamic"
    }
  });
  mocks.rpc.mockResolvedValue({ data: {}, error: null });
});

describe("SemanticDraftPatchSchema", () => {
  it("accepts a structured metric correction", () => {
    const parsed = SemanticDraftPatchSchema.parse({
      tenant_id: tenantId,
      expected_revision: 2,
      metrics: [
        {
          metric_key: metricKey,
          canonical_name: "revenue_net",
          metric_variant: "net_header",
          aggregation: "sum",
          source_table_key: hash,
          measure_column_key: hash,
          grain_table_key: hash,
          grain_column_keys: [hash],
          required_join_edge_keys: [],
          common_dimensions: [],
          format: {
            value_type: "currency",
            currency: "EUR",
            decimals: 2
          }
        }
      ]
    });

    expect(parsed.metrics[0]).toMatchObject({
      aggregation: "sum",
      canonical_name: "revenue_net",
      metric_key: metricKey
    });
  });

  it("rejects empty patches so PATCH cannot create meaningless revisions", () => {
    const parsed = SemanticDraftPatchSchema.safeParse({
      tenant_id: tenantId,
      expected_revision: 2
    });

    expect(parsed.success).toBe(false);
  });

  it("rejects raw SQL and unknown fields", () => {
    const parsed = SemanticDraftPatchSchema.safeParse({
      tenant_id: tenantId,
      expected_revision: 2,
      metrics: [
        {
          metric_key: metricKey,
          raw_sql: "select 1"
        }
      ]
    });

    expect(parsed.success).toBe(false);
  });
});

describe("createAndGenerateSemanticDraft", () => {
  it("does not persist an orphan draft when query-engine generation fails", async () => {
    mocks.postQueryEngine.mockImplementation(async (path: string) => {
      if (path === "/semantic/seed") {
        return {
          base_graph_hash: graphFixture.graph_hash,
          connection_id: connectionId,
          semantic_hash: hash,
          semantic_version_id: "60000000-0000-4000-8000-000000000001",
          tenant_id: tenantId,
          version: 1
        };
      }
      throw new mocks.QueryEngineRequestError(
        "AI semantic proposal violates queryability graph constraints.",
        422
      );
    });

    await expect(
      createAndGenerateSemanticDraft({
        activationPolicy: "auto_validated",
        connectionId,
        context: {
          role: "owner",
          supabase: {} as never,
          tenantId,
          userId
        }
      })
    ).rejects.toMatchObject({
      code: "semantic_proposal_invalid"
    });

    expect(mocks.rpc).toHaveBeenCalledWith(
      "save_resolved_semantic_policy",
      expect.any(Object)
    );
    expect(mocks.rpc).not.toHaveBeenCalledWith(
      "persist_semantic_layer_version",
      expect.any(Object)
    );
  });
});

describe("listSemanticVersions", () => {
  it("loads artifacts before computing compatibility badges", async () => {
    const client = createSupabaseMock();
    mocks.createSupabaseAdminClient.mockReturnValue(client);

    await listSemanticVersions({
      connectionId,
      context: {
        role: "owner",
        supabase: {} as never,
        tenantId,
        userId
      }
    });

    expect(client.selectedFields.semantic_layer_versions).toEqual(
      expect.arrayContaining([expect.stringContaining("artifact")])
    );
  });
});
