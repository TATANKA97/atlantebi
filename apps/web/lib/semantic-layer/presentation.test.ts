import { describe, expect, it } from "vitest";
import type {
  SemanticBusinessConcept,
  SemanticColumn,
  SemanticLayer,
  SemanticMetric,
  SemanticTable
} from "@atlantebi/contracts";

import {
  buildSemanticIndexes,
  confidenceLabel,
  metricConceptLabel,
  metricFormulaLabel,
  metricGrainLabel,
  groupSemanticValidationIssues,
  paginateItems,
  semanticLayerCounts,
  splitSemanticQualityGateReport,
  validationIssueCounts
} from "./presentation";

const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const TABLE: SemanticTable = {
  node_key: HASH_A,
  schema_name: "SalesLT",
  object_name: "SalesOrderHeader",
  object_type: "table",
  display_name: "Ordini",
  description: null,
  business_domain: "Vendite",
  synonyms: [],
  status: "ai_proposed",
  included: true,
  queryability_status: "queryable"
};
const COLUMN: SemanticColumn = {
  column_key: HASH_B,
  node_key: HASH_A,
  physical_name: "SubTotal",
  display_name: "Imponibile",
  description: null,
  synonyms: [],
  native_type: "money",
  normalized_type: "decimal",
  technical_role: "money_candidate",
  semantic_role: "measure",
  format_hint: "currency",
  nullable: false,
  status: "ai_proposed",
  included: true,
  queryability_status: "queryable",
  inherited_sensitivity: "none",
  sensitivity: "none"
};
const CONCEPT: SemanticBusinessConcept = {
  business_concept_key: "11111111-1111-4111-8111-111111111111",
  canonical_name: "revenue",
  display_name: "Fatturato",
  description: null,
  synonyms: [],
  status: "ai_proposed",
  provenance: "ai"
};
const METRIC: SemanticMetric = {
  metric_key: "22222222-2222-4222-8222-222222222222",
  canonical_name: "fatturato_netto",
  metric_definition_hash: "c".repeat(64),
  business_concept_key: CONCEPT.business_concept_key,
  metric_variant: "net_header",
  name: "Fatturato netto",
  description: null,
  status: "ai_proposed",
  source_table_key: HASH_A,
  aggregation: "sum",
  measure_column_key: HASH_B,
  grain_table_key: HASH_A,
  grain_column_keys: [HASH_B],
  aggregation_level: "entity",
  additivity: "additive",
  default_date_column_key: null,
  required_join_edge_keys: [],
  common_dimension_compatibility: [],
  dimension_policy: {
    same_grain: "safe",
    parent_many_to_one: "safe",
    child_one_to_many: "forbidden",
    bridge_or_many_to_many: "forbidden",
    self_reference: "conditional"
  },
  preferred_for_grains: [],
  preferred_for_dimensions: [],
  filters: [],
  format: { value_type: "currency", currency: "EUR", decimals: 2 },
  synonyms: [],
  confidence_score: 0.93,
  confidence_label: "high",
  compiler_eligibility: "eligible_with_disclosure",
  eligibility_reasons: [],
  reasoning_summary: "Uses the order header net amount.",
  validation_warnings: [],
  provenance: "ai",
  provenance_detail: "ai_generation",
  source_spec_key: null,
  enabled: true
};

const LAYER = {
  tables: [TABLE],
  columns: [COLUMN],
  business_concepts: [CONCEPT],
  metrics: [METRIC],
  ambiguities: [
    {
      ambiguity_key: "33333333-3333-4333-8333-333333333333",
      code: "REVENUE_VARIANT",
      target_type: "metric",
      target_key: METRIC.metric_key,
      summary: "Net or gross revenue.",
      clarification_question: "Net or document total?",
      status: "open",
      provenance: "ai",
      severity: "material_ambiguity"
    }
  ],
  validation_report: {
    status: "valid_with_warnings",
    blocking_errors: [],
    warnings: [
      {
        code: "AMBIGUITY_OPEN",
        severity: "warning",
        target_type: "metric",
        target_key: METRIC.metric_key,
        message: "Revenue variant is ambiguous.",
        evidence: {}
      }
    ],
    info: [],
    validated_revision: 2,
    validated_at: "2026-06-15T10:00:00Z",
    validator_version: "1.0.0"
  }
} as Pick<
  SemanticLayer,
  | "ambiguities"
  | "business_concepts"
  | "columns"
  | "metrics"
  | "tables"
  | "validation_report"
>;

describe("semantic workspace presentation", () => {
  it("renders formula, grain and concept from stable-key references", () => {
    const indexes = buildSemanticIndexes(LAYER as SemanticLayer);

    expect(metricFormulaLabel(METRIC, indexes)).toBe("SUM(Ordini.Imponibile)");
    expect(metricGrainLabel(METRIC, indexes)).toBe("Ordini: Imponibile");
    expect(metricConceptLabel(METRIC, indexes.concepts)).toBe(
      "Fatturato / net_header"
    );
  });

  it("summarizes eligibility, ambiguities and validation issues", () => {
    expect(semanticLayerCounts(LAYER as SemanticLayer)).toMatchObject({
      ambiguitiesOpen: 1,
      eligibleMetrics: 1,
      metrics: 1
    });
    expect(validationIssueCounts(LAYER.validation_report)).toEqual({
      blocking: 0,
      info: 0,
      total: 1,
      warnings: 1
    });
    expect(confidenceLabel(METRIC)).toBe("high (93%)");
  });

  it("moves passed quality-gate technical audit details out of the main recap", () => {
    const split = splitSemanticQualityGateReport({
      status: "passed",
      issues: [
        {
          code: "AI_REQUIRED_METRIC_MISMATCH",
          severity: "warning",
          message: "Candidate did not match the quality profile.",
          spec_key: "adventureworks.revenue.net_header",
          metric_key: null
        },
        {
          code: "AI_PROVIDER_FALLBACK_USED",
          severity: "warning",
          message: "Provider fallback was used.",
          spec_key: null,
          metric_key: null
        }
      ],
      required_specs_count: 7,
      satisfied_specs_count: 7,
      compiler_eligible_required_count: 5,
      rejected_candidates: [
        {
          canonical_name: "fatturato_netto",
          business_concept_ref: "revenue",
          metric_variant: "net_header",
          source_table_key: HASH_A,
          measure_column_key: HASH_B,
          reason_code: "AI_REQUIRED_METRIC_MISMATCH"
        },
        {
          canonical_name: "ordini",
          business_concept_ref: "orders",
          metric_variant: "header_count",
          source_table_key: HASH_A,
          measure_column_key: HASH_B,
          reason_code: "AI_METRIC_COMPILATION_FAILED"
        }
      ]
    });

    expect(split.mainIssues.map((issue) => issue.code)).toEqual([
      "AI_PROVIDER_FALLBACK_USED"
    ]);
    expect(split.auditIssues.map((issue) => issue.code)).toEqual([
      "AI_REQUIRED_METRIC_MISMATCH"
    ]);
    expect(
      split.mainRejectedCandidates.map((candidate) => candidate.reason_code)
    ).toEqual(["AI_METRIC_COMPILATION_FAILED"]);
    expect(
      split.auditRejectedCandidates.map((candidate) => candidate.reason_code)
    ).toEqual(["AI_REQUIRED_METRIC_MISMATCH"]);
  });

  it("groups equivalent validation warnings by target family", () => {
    const grouped = groupSemanticValidationIssues(
      [
        {
          code: "SEMANTIC_MINOR_AMBIGUITY",
          severity: "warning",
          target_type: "business_concept",
          target_key: CONCEPT.business_concept_key,
          message: "Order status scope may affect the metric.",
          evidence: { ambiguity_code: "ORDER_STATUS_SCOPE" }
        },
        {
          code: "SEMANTIC_MINOR_AMBIGUITY",
          severity: "warning",
          target_type: "metric",
          target_key: METRIC.metric_key,
          message: "Order status scope may affect the metric.",
          evidence: { ambiguity_code: "ORDER_STATUS_SCOPE" }
        }
      ],
      [METRIC]
    );

    expect(grouped).toHaveLength(1);
    expect(grouped[0]).toMatchObject({ count: 2 });
  });

  it("paginates deterministically and clamps invalid pages", () => {
    expect(paginateItems([1, 2, 3, 4, 5], "2", 2)).toEqual({
      items: [3, 4],
      page: 2,
      pageCount: 3,
      total: 5
    });
    expect(paginateItems([1, 2, 3], "99", 2).page).toBe(2);
    expect(paginateItems([1, 2, 3], "invalid", 2).page).toBe(1);
    expect(paginateItems([], "-1", 2)).toEqual({
      items: [],
      page: 1,
      pageCount: 1,
      total: 0
    });
  });
});
