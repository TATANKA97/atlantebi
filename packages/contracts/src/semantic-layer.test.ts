import { describe, expect, it } from "vitest";

import semanticFixture from "./fixtures/semantic-layer-v1.json";
import {
  SemanticLayerSchema,
  SemanticMetricSchema
} from "./index";

describe("semantic layer contracts", () => {
  it("accepts the shared strict semantic_layer.v1 fixture", () => {
    const layer = SemanticLayerSchema.parse(semanticFixture);

    expect(layer.contract_version).toBe("semantic_layer.v1");
    expect(layer.metrics[0]?.compiler_eligibility).toBe(
      "eligible_with_disclosure"
    );
    expect(layer.metrics[0]?.dimension_policy.child_one_to_many).toBe(
      "forbidden"
    );
  });

  it("rejects legacy semantic payloads and unknown fields", () => {
    expect(() =>
      SemanticLayerSchema.parse({
        tenant_id: semanticFixture.tenant_id,
        version_id: semanticFixture.semantic_version_id,
        version: 1,
        status: "draft",
        engine: "sqlserver",
        tables: [],
        relationships: [],
        metrics: [],
        business_anchors: []
      })
    ).toThrow();

    expect(() =>
      SemanticLayerSchema.parse({
        ...semanticFixture,
        raw_sql: "select 1"
      })
    ).toThrow();
  });

  it("requires grain, stable identities, and explicit compiler eligibility", () => {
    const metric = semanticFixture.metrics[0]!;

    expect(() => {
      const withoutGrain: Partial<typeof metric> = { ...metric };
      delete withoutGrain.grain_column_keys;
      return SemanticMetricSchema.parse(withoutGrain);
    }).toThrow();

    expect(() => {
      const withoutEligibility: Partial<typeof metric> = { ...metric };
      delete withoutEligibility.compiler_eligibility;
      return SemanticMetricSchema.parse(withoutEligibility);
    }).toThrow();

    expect(() =>
      SemanticMetricSchema.parse({
        ...metric,
        metric_key: "fatturato_netto"
      })
    ).toThrow();

    expect(() =>
      SemanticMetricSchema.parse({
        ...metric,
        filters: [
          {
            column_key: metric.grain_column_keys[0],
            operator: "in",
            value: [],
            value_type: "integer"
          }
        ]
      })
    ).toThrow();
  });

  it("keeps nullable fields and canonical wire formats aligned", () => {
    expect(() =>
      SemanticLayerSchema.parse({
        ...semanticFixture,
        ai_model_version: null,
        ai_prompt_version: null,
        validation_report: {
          ...semanticFixture.validation_report,
          validated_at: null,
          validated_revision: null
        },
        metrics: [
          {
            ...semanticFixture.metrics[0],
            description: null,
            default_date_column_key: null,
            measure_column_key: null,
            reasoning_summary: null,
            format: {
              ...semanticFixture.metrics[0]!.format,
              currency: null
            }
          }
        ]
      })
    ).not.toThrow();

    expect(() =>
      SemanticLayerSchema.parse({
        ...semanticFixture,
        semantic_version_id: "88888888888848888888888888888888"
      })
    ).toThrow();
    expect(() =>
      SemanticLayerSchema.parse({
        ...semanticFixture,
        semantic_version_id: "88888888-8888-0888-8888-888888888888"
      })
    ).toThrow();

    expect(() =>
      SemanticLayerSchema.parse({
        ...semanticFixture,
        validation_report: {
          ...semanticFixture.validation_report,
          validated_at: "2026-06-14 08:00:00+00:00"
        }
      })
    ).toThrow();
    expect(() =>
      SemanticLayerSchema.parse({
        ...semanticFixture,
        validation_report: {
          ...semanticFixture.validation_report,
          validated_at: "2026-06-14T08:00Z"
        }
      })
    ).toThrow();
  });
});
