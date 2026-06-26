import "server-only";

import { createHash } from "node:crypto";
import {
  SemanticPolicySnapshotSchema,
  type SemanticPolicySnapshot
} from "@atlantebi/contracts";
import { z } from "zod";

const SemanticPolicyConfigSchema = z.strictObject({
  activation_policy: SemanticPolicySnapshotSchema.shape.activation_policy,
  minimum_eligible_metrics:
    SemanticPolicySnapshotSchema.shape.minimum_eligible_metrics,
  missing_currency_behavior:
    SemanticPolicySnapshotSchema.shape.missing_currency_behavior,
  policy_version: SemanticPolicySnapshotSchema.shape.policy_version,
  required_concepts: SemanticPolicySnapshotSchema.shape.required_concepts,
  required_metric_specs:
    SemanticPolicySnapshotSchema.shape.required_metric_specs
});

export type SemanticPolicyConfig = z.infer<typeof SemanticPolicyConfigSchema>;

const DEFAULT_POLICY_CONFIG: SemanticPolicyConfig = {
  policy_version: "1.0.0",
  missing_currency_behavior: "clarification_required",
  activation_policy: "auto_validated",
  minimum_eligible_metrics: 1,
  required_concepts: [
    {
      concept_ref: "revenue",
      preferred_variants: ["document_total", "line_detail", "net_header"],
      required: false,
      required_for_activation: false
    },
    {
      concept_ref: "quantity_sold",
      preferred_variants: ["line_quantity"],
      required: false,
      required_for_activation: false
    },
    {
      concept_ref: "orders",
      preferred_variants: ["header_count"],
      required: false,
      required_for_activation: false
    },
    {
      concept_ref: "customers",
      preferred_variants: ["customer_master", "order_customers"],
      required: false,
      required_for_activation: false
    }
  ],
  required_metric_specs: []
};

export function resolveSemanticPolicy({
  connectionDefaultCurrency,
  policyConfig,
  tenantDefaultCurrency
}: {
  connectionDefaultCurrency: string | null;
  policyConfig: unknown;
  tenantDefaultCurrency: string | null;
}): SemanticPolicySnapshot {
  const config = canonicalizePolicyConfig(
    policyConfig == null
      ? DEFAULT_POLICY_CONFIG
      : SemanticPolicyConfigSchema.parse(policyConfig)
  );
  const withoutHash = {
    ...config,
    default_currency: connectionDefaultCurrency ?? tenantDefaultCurrency
  };
  return SemanticPolicySnapshotSchema.parse({
    ...withoutHash,
    policy_hash: sha256Canonical(withoutHash)
  });
}

export function semanticPolicyConfigSchema() {
  return SemanticPolicyConfigSchema;
}

function canonicalizePolicyConfig(
  policy: SemanticPolicyConfig
): SemanticPolicyConfig {
  return {
    ...policy,
    required_concepts: [...policy.required_concepts]
      .map((concept) => ({
        ...concept,
        preferred_variants: [...concept.preferred_variants].sort()
      }))
      .sort((left, right) => left.concept_ref.localeCompare(right.concept_ref)),
    required_metric_specs: [...policy.required_metric_specs]
      .map((spec) => ({
        ...spec,
        allowed_eligibility: [...spec.allowed_eligibility].sort(),
        dimension_expectations: [...spec.dimension_expectations].sort((left, right) =>
          left.dimension_column_key.localeCompare(right.dimension_column_key)
        ),
        grain_column_keys: [...spec.grain_column_keys].sort(),
        synonyms: [...spec.synonyms].sort()
      }))
      .sort((left, right) => left.spec_key.localeCompare(right.spec_key))
  };
}

function sha256Canonical(value: unknown): string {
  return createHash("sha256").update(canonicalJson(value)).digest("hex");
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== undefined)
      .sort(([left], [right]) => left.localeCompare(right));
    return `{${entries
      .map(([key, item]) => `${asciiJsonString(key)}:${canonicalJson(item)}`)
      .join(",")}}`;
  }
  return typeof value === "string" ? asciiJsonString(value) : JSON.stringify(value);
}

function asciiJsonString(value: string): string {
  return JSON.stringify(value).replace(/[\u007f-\uffff]/g, (character) =>
    `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`
  );
}
