import { describe, expect, it } from "vitest";

import semanticFixture from "./fixtures/semantic-layer-v1.json";
import {
  NorthStarBenchmarkInputSchema,
  NorthStarBenchmarkSchema,
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

  it("accepts strict north star benchmarks without changing semantic metrics", () => {
    const benchmark = NorthStarBenchmarkSchema.parse({
      benchmark_key: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      tenant_id: semanticFixture.tenant_id,
      connection_id: semanticFixture.connection_id,
      dashboard_id: null,
      semantic_version_id: semanticFixture.semantic_version_id,
      metric_key: semanticFixture.metrics[0]!.metric_key,
      name: "Fatturato annuo atteso",
      description: null,
      expected_value: 10_000_000,
      value_type: "currency",
      currency: "EUR",
      period_type: "year",
      period_start: null,
      period_end: null,
      tolerance_mode: "percentage",
      tolerance_percentage: 10,
      min_value: null,
      max_value: null,
      severity: "high",
      enabled: true,
      created_by: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      updated_by: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      created_at: "2026-06-16T09:00:00Z",
      updated_at: "2026-06-16T09:00:00Z"
    });

    expect(benchmark.metric_key).toBe(semanticFixture.metrics[0]!.metric_key);
  });

  it("rejects ambiguous north star benchmark inputs", () => {
    const input = {
      connection_id: semanticFixture.connection_id,
      semantic_version_id: semanticFixture.semantic_version_id,
      metric_key: semanticFixture.metrics[0]!.metric_key,
      name: "Fatturato annuo atteso",
      expected_value: 10_000_000,
      value_type: "currency",
      currency: "EUR",
      period_type: "year",
      period_start: null,
      period_end: null,
      tolerance_mode: "percentage",
      tolerance_percentage: 10,
      min_value: null,
      max_value: null,
      severity: "high",
      enabled: true
    } as const;

    expect(() =>
      NorthStarBenchmarkInputSchema.parse({
        ...input,
        currency: null
      })
    ).toThrow();

    expect(() =>
      NorthStarBenchmarkInputSchema.parse({
        ...input,
        metric_key: null
      })
    ).toThrow();

    expect(() =>
      NorthStarBenchmarkInputSchema.parse({
        ...input,
        tolerance_mode: "range",
        tolerance_percentage: 10
      })
    ).toThrow();

    expect(() =>
      NorthStarBenchmarkInputSchema.parse({
        ...input,
        unexpected: true
      })
    ).toThrow();
  });
});
