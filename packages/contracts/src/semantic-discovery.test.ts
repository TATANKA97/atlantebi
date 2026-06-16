import { describe, expect, it } from "vitest";

import semanticLayerFixture from "./fixtures/semantic-layer-v1.json";
import semanticAiDraftFixture from "./fixtures/semantic-ai-draft-v1.json";
import {
  AISemanticDraftProposalSchema,
  AISemanticMetricProposalSchema,
  AISemanticProviderConfigSchema,
  SemanticDiscoveryInputSchema,
  SemanticGenerationResultSchema
} from "./index";

const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const HASH_C = "c".repeat(64);

const emptyDiscoveryInput = {
  contract_version: "semantic_discovery_input.v1",
  engine: "sqlserver",
  base_graph_hash: HASH_A,
  graph_status: "complete",
  tables: [],
  columns: [],
  relationships: []
} as const;

const metricProposal = {
  canonical_name: "net_revenue",
  business_concept_ref: "revenue",
  metric_variant: "net",
  name: "Net revenue",
  description: "Revenue after adjustments.",
  source_table_key: HASH_A,
  aggregation: "sum",
  measure_column_key: HASH_B,
  grain_table_key: HASH_A,
  grain_column_keys: [HASH_C],
  aggregation_level: "entity",
  additivity: "additive",
  default_date_column_key: null,
  required_join_edge_keys: [],
  common_dimensions: [
    {
      dimension_column_key: HASH_C,
      edge_path: []
    }
  ],
  preferred_for_grains: [],
  preferred_for_dimensions: [],
  filters: [],
  format: {
    value_type: "currency",
    currency: "EUR",
    decimals: 2
  },
  synonyms: [],
  reasoning_summary: "Uses the validated revenue measure."
} as const;

const emptyDraftProposal = {
  contract_version: "semantic_ai_draft.v1",
  tables: [],
  columns: [],
  business_concepts: [],
  metrics: [],
  ambiguities: []
} as const;

describe("semantic discovery and AI draft contracts", () => {
  it("accepts valid empty discovery and proposal lists", () => {
    expect(SemanticDiscoveryInputSchema.parse(emptyDiscoveryInput).tables).toEqual(
      []
    );
    expect(AISemanticDraftProposalSchema.parse(emptyDraftProposal).metrics).toEqual(
      []
    );
  });

  it("requires candidate keys to reference stable column keys", () => {
    const table = {
      node_key: HASH_A,
      schema_name: "SalesLT",
      object_name: "Customer",
      object_type: "table",
      queryability_status: "queryable",
      bridge_candidate: false,
      candidate_keys: [
        {
          key_type: "primary_key",
          column_keys: [HASH_B]
        }
      ],
      view_lineage_status: null
    } as const;

    expect(
      SemanticDiscoveryInputSchema.parse({
        ...emptyDiscoveryInput,
        tables: [table]
      }).tables[0]?.candidate_keys[0]?.column_keys
    ).toEqual([HASH_B]);

    expect(() =>
      SemanticDiscoveryInputSchema.parse({
        ...emptyDiscoveryInput,
        tables: [
          {
            ...table,
            candidate_keys: [
              {
                key_type: "primary_key",
                column_keys: ["CustomerID"]
              }
            ]
          }
        ]
      })
    ).toThrow();
  });

  it("accepts the shared AI draft fixture", () => {
    expect(
      AISemanticDraftProposalSchema.parse(semanticAiDraftFixture).metrics[0]
        ?.metric_variant
    ).toBe("net_header");
  });

  it("accepts common dimension proposals without AI safety metadata", () => {
    const parsed = AISemanticMetricProposalSchema.parse(metricProposal);

    expect(parsed.common_dimensions).toEqual([
      {
        dimension_column_key: HASH_C,
        edge_path: []
      }
    ]);
    expect(parsed.default_date_column_key).toBeNull();
  });

  it("rejects unknown fields, including AI safety and confidence decisions", () => {
    expect(() =>
      SemanticDiscoveryInputSchema.parse({
        ...emptyDiscoveryInput,
        unknown_field: true
      })
    ).toThrow();

    expect(() =>
      AISemanticMetricProposalSchema.parse({
        ...metricProposal,
        preliminary_confidence: 0.9
      })
    ).toThrow();

    expect(() =>
      AISemanticMetricProposalSchema.parse({
        ...metricProposal,
        confidence_score: 0.9,
        compiler_eligibility: "eligible"
      })
    ).toThrow();

    expect(() =>
      AISemanticMetricProposalSchema.parse({
        ...metricProposal,
        common_dimensions: [
          {
            dimension_column_key: HASH_C,
            edge_path: [],
            safety: "safe"
          }
        ]
      })
    ).toThrow();
  });

  it("rejects invalid stable references, UUIDs, and RFC 3339 dates", () => {
    expect(() =>
      AISemanticMetricProposalSchema.parse({
        ...metricProposal,
        business_concept_ref: "Revenue-2026"
      })
    ).toThrow();

    expect(() =>
      AISemanticMetricProposalSchema.parse({
        ...metricProposal,
        source_table_key: "not-a-sha256"
      })
    ).toThrow();

    expect(() =>
      SemanticGenerationResultSchema.parse({
        proposal: emptyDraftProposal,
        provenance: {
          provider: "openai",
          model_version: "gpt-test",
          thinking_config: {
            type: "openai_reasoning",
            effort: "medium"
          },
          prompt_version: "semantic-v1",
          generated_at: "2026-06-14T08:00:00+00:00",
          input_hash: HASH_A,
          proposal_hash: HASH_B,
          response_id: "resp_123"
        },
        semantic_layer: {
          ...semanticLayerFixture,
          semantic_version_id: "not-a-uuid"
        }
      })
    ).toThrow();

    expect(() =>
      SemanticGenerationResultSchema.parse({
        proposal: emptyDraftProposal,
        provenance: {
          provider: "openai",
          model_version: "gpt-test",
          thinking_config: {
            type: "openai_reasoning",
            effort: "medium"
          },
          prompt_version: "semantic-v1",
          generated_at: "2026-06-14 08:00:00+00:00",
          input_hash: HASH_A,
          proposal_hash: HASH_B,
          response_id: "resp_123"
        },
        semantic_layer: semanticLayerFixture
      })
    ).toThrow();
  });

  it("accepts a complete generation result with canonical wire values", () => {
    expect(() =>
      SemanticGenerationResultSchema.parse({
        proposal: {
          ...emptyDraftProposal,
          metrics: [metricProposal]
        },
        provenance: {
          provider: "openai",
          model_version: "gpt-test",
          thinking_config: {
            type: "openai_reasoning",
            effort: "medium"
          },
          prompt_version: "semantic-v1",
          generated_at: "2026-06-14T08:00:00+00:00",
          input_hash: HASH_A,
          proposal_hash: HASH_B,
          response_id: "resp_123"
        },
        semantic_layer: semanticLayerFixture
      })
    ).not.toThrow();
  });

  it("allowlists semantic discovery providers, models, and thinking settings", () => {
    expect(
      AISemanticProviderConfigSchema.parse({
        provider: "openai",
        setting_id: "00000000-0000-4000-8000-000000000001",
        model_id: "gpt-5.5",
        thinking: {
          type: "openai_reasoning",
          effort: "xhigh"
        },
        secret_ref:
          "gcp-secret-manager://projects/demo/secrets/atlantebi-ai-key"
      }).model_id
    ).toBe("gpt-5.5");

    expect(
      AISemanticProviderConfigSchema.parse({
        provider: "anthropic",
        setting_id: "00000000-0000-4000-8000-000000000001",
        model_id: "claude-opus-4-8",
        thinking: {
          type: "anthropic_adaptive",
          enabled: true,
          effort: "xhigh"
        },
        secret_ref:
          "gcp-secret-manager://projects/demo/secrets/atlantebi-ai-key"
      }).provider
    ).toBe("anthropic");

    expect(() =>
      AISemanticProviderConfigSchema.parse({
        provider: "anthropic",
        setting_id: "00000000-0000-4000-8000-000000000001",
        model_id: "claude-sonnet-4-6",
        thinking: {
          type: "anthropic_adaptive",
          enabled: true,
          effort: "xhigh"
        },
        secret_ref:
          "gcp-secret-manager://projects/demo/secrets/atlantebi-ai-key"
      })
    ).toThrow();

    expect(() =>
      AISemanticProviderConfigSchema.parse({
        provider: "anthropic",
        setting_id: "00000000-0000-4000-8000-000000000001",
        model_id: "claude-sonnet-4-6",
        thinking: {
          type: "anthropic_adaptive",
          enabled: true,
          effort: "max"
        },
        secret_ref:
          "gcp-secret-manager://projects/demo/secrets/atlantebi-ai-key"
      })
    ).toThrow();

    expect(() =>
      AISemanticProviderConfigSchema.parse({
        provider: "openai",
        setting_id: "00000000-0000-4000-8000-000000000001",
        model_id: "gpt-5.4",
        thinking: {
          type: "openai_reasoning",
          effort: "medium"
        },
        secret_ref:
          "gcp-secret-manager://projects/demo/secrets/atlantebi-ai-key"
      })
    ).toThrow();
  });
});
