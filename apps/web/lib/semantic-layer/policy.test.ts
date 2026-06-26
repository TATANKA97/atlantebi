import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { resolveSemanticPolicy } from "./policy";

describe("semantic policy resolution", () => {
  it("uses connection currency before tenant currency", () => {
    expect(
      resolveSemanticPolicy({
        connectionDefaultCurrency: "USD",
        policyConfig: null,
        tenantDefaultCurrency: "EUR"
      }).default_currency
    ).toBe("USD");
  });

  it("changes policy hash when resolved currency changes", () => {
    const eur = resolveSemanticPolicy({
      connectionDefaultCurrency: null,
      policyConfig: null,
      tenantDefaultCurrency: "EUR"
    });
    const usd = resolveSemanticPolicy({
      connectionDefaultCurrency: null,
      policyConfig: null,
      tenantDefaultCurrency: "USD"
    });

    expect(eur.policy_hash).not.toBe(usd.policy_hash);
  });

  it("matches the Python canonical hash for Unicode policy labels", () => {
    const policy = resolveSemanticPolicy({
      connectionDefaultCurrency: "EUR",
      tenantDefaultCurrency: null,
      policyConfig: {
        policy_version: "1.0.0",
        missing_currency_behavior: "clarification_required",
        activation_policy: "auto_validated",
        minimum_eligible_metrics: 1,
        required_concepts: [
          {
            concept_ref: "quantity_sold",
            preferred_variants: ["line_quantity"],
            required: true,
            required_for_activation: true
          }
        ],
        required_metric_specs: [
          {
            spec_key: "demo.quantity",
            intent_key: "quantity_sold",
            business_concept_ref: "quantity_sold",
            expected_variant: "line_quantity",
            canonical_name: "quantita_venduta",
            name: "Quantità venduta",
            description: null,
            source_table_key: "a".repeat(64),
            aggregation: "sum",
            measure_column_key: "b".repeat(64),
            grain_column_keys: ["c".repeat(64)],
            default_date_column_key: null,
            value_type: "number",
            default_for_concept: true,
            required_for_activation: true,
            allowed_eligibility: ["eligible_with_disclosure"],
            dimension_expectations: [],
            synonyms: ["quantità"]
          }
        ]
      }
    });

    expect(policy.policy_hash).toBe(
      "012c58a3be9016762a9b25bce9b3811bea8947aabd5672d833057dd1e9206bed"
    );
  });

  it("rejects stable-key specs outside the concept allowlist", () => {
    expect(() =>
      resolveSemanticPolicy({
        connectionDefaultCurrency: "EUR",
        tenantDefaultCurrency: null,
        policyConfig: {
          policy_version: "1.0.0",
          missing_currency_behavior: "clarification_required",
          activation_policy: "auto_validated",
          minimum_eligible_metrics: 1,
          required_concepts: [],
          required_metric_specs: [
            {
              spec_key: "demo.revenue",
              intent_key: "revenue",
              business_concept_ref: "revenue",
              expected_variant: "net_header",
              canonical_name: "fatturato_netto",
              name: "Fatturato netto",
              description: null,
              source_table_key: "a".repeat(64),
              aggregation: "sum",
              measure_column_key: "b".repeat(64),
              grain_column_keys: ["c".repeat(64)],
              default_date_column_key: null,
              value_type: "currency",
              default_for_concept: true,
              required_for_activation: true,
              allowed_eligibility: ["eligible_with_disclosure"],
              dimension_expectations: [],
              synonyms: []
            }
          ]
        }
      })
    ).toThrow();
  });
});
