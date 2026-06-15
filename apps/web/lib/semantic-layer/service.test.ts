import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const { SemanticDraftPatchSchema } = await import("./service");

const tenantId = "20000000-0000-4000-8000-000000000001";
const metricKey = "50000000-0000-4000-8000-000000000001";
const hash = "a".repeat(64);

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
