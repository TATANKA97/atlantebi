import "server-only";

import { randomUUID } from "node:crypto";
import {
  AISemanticDimensionProposalSchema,
  QueryabilityGraphArtifactSchema,
  SemanticFilterSchema,
  SemanticGenerationResultSchema,
  SemanticLayerSchema,
  SemanticMetricFormatSchema,
  SemanticRebaseResultSchema,
  type QueryabilityGraphArtifact,
  type SemanticGenerationResult,
  type SemanticLayer,
  type SemanticPolicySnapshot
} from "@atlantebi/contracts";
import { z } from "zod";

import { postQueryEngine, QueryEngineRequestError } from "../query-engine/client";
import { readDefaultAIProviderConfig } from "../ai-provider-settings/service";
import {
  isSecurityOperationLimitError,
  withSecurityOperationLease
} from "../security/operation-lease";
import { createSupabaseAdminClient } from "../supabase/admin";
import { resolveSemanticPolicy } from "./policy";
import {
  canManageSemanticLayer,
  type ActiveTenantContext
} from "../tenant";

const ElementStatusSchema = z.enum([
  "human_verified",
  "rejected",
  "disabled"
]);

const AnnotationPatchSchema = z.strictObject({
  display_name: z.string().trim().min(1).max(255).optional(),
  description: z.string().trim().min(1).max(2_000).nullable().optional(),
  synonyms: z.array(z.string().trim().min(1).max(255)).max(100).optional(),
  status: ElementStatusSchema.optional()
});

export const SemanticDraftPatchSchema = z
  .strictObject({
    tenant_id: z.string().uuid(),
    expected_revision: z.number().int().positive(),
    tables: z
      .array(
        AnnotationPatchSchema.extend({
          node_key: z.string().regex(/^[0-9a-f]{64}$/),
          business_domain: z
            .string()
            .trim()
            .min(1)
            .max(255)
            .nullable()
            .optional(),
          included: z.boolean().optional()
        }).strict()
      )
      .max(500)
      .default([]),
    columns: z
      .array(
        AnnotationPatchSchema.extend({
          column_key: z.string().regex(/^[0-9a-f]{64}$/),
          semantic_role: z
            .string()
            .trim()
            .min(1)
            .max(100)
            .nullable()
            .optional(),
          format_hint: z
            .enum([
              "text",
              "integer",
              "decimal",
              "currency",
              "percentage",
              "date",
              "datetime",
              "boolean",
              "identifier"
            ])
            .nullable()
            .optional(),
          included: z.boolean().optional()
        }).strict()
      )
      .max(2_000)
      .default([]),
    business_concepts: z
      .array(
        AnnotationPatchSchema.extend({
          business_concept_key: z.string().uuid()
        }).strict()
      )
      .max(500)
      .default([]),
    metrics: z
      .array(
        z
          .strictObject({
            metric_key: z.string().uuid(),
            canonical_name: z
              .string()
              .regex(/^[a-z][a-z0-9_]{1,99}$/)
              .optional(),
            business_concept_key: z.string().uuid().optional(),
            metric_variant: z
              .string()
              .regex(/^[a-z][a-z0-9_]{1,99}$/)
              .optional(),
            name: z.string().trim().min(1).max(255).optional(),
            description: z.string().trim().min(1).max(2_000).nullable().optional(),
            source_table_key: z.string().regex(/^[0-9a-f]{64}$/).optional(),
            aggregation: z
              .enum(["count", "count_distinct", "sum", "avg", "min", "max"])
              .optional(),
            measure_column_key: z
              .string()
              .regex(/^[0-9a-f]{64}$/)
              .nullable()
              .optional(),
            grain_table_key: z.string().regex(/^[0-9a-f]{64}$/).optional(),
            grain_column_keys: z
              .array(z.string().regex(/^[0-9a-f]{64}$/))
              .min(1)
              .max(100)
              .optional(),
            aggregation_level: z.enum(["row", "entity", "period"]).optional(),
            additivity: z
              .enum(["additive", "semi_additive", "non_additive"])
              .optional(),
            default_date_column_key: z
              .string()
              .regex(/^[0-9a-f]{64}$/)
              .nullable()
              .optional(),
            required_join_edge_keys: z
              .array(z.string().regex(/^[0-9a-f]{64}$/))
              .max(4)
              .optional(),
            common_dimensions: z
              .array(AISemanticDimensionProposalSchema)
              .max(100)
              .optional(),
            preferred_for_grains: z
              .array(z.string().trim().min(1).max(100))
              .max(100)
              .optional(),
            preferred_for_dimensions: z
              .array(z.string().regex(/^[0-9a-f]{64}$/))
              .max(100)
              .optional(),
            filters: z.array(SemanticFilterSchema).max(100).optional(),
            format: SemanticMetricFormatSchema.optional(),
            synonyms: z
              .array(z.string().trim().min(1).max(255))
              .max(100)
              .optional(),
            reasoning_summary: z
              .string()
              .trim()
              .min(1)
              .max(1_000)
              .nullable()
              .optional(),
            status: ElementStatusSchema.optional(),
            enabled: z.boolean().optional()
          })
      )
      .max(500)
      .default([]),
    ambiguities: z
      .array(
        z.strictObject({
          ambiguity_key: z.string().uuid(),
          status: z.literal("resolved")
        })
      )
      .max(500)
      .default([])
  })
  .superRefine((patch, context) => {
    const updateCount =
      patch.tables.length +
      patch.columns.length +
      patch.business_concepts.length +
      patch.metrics.length +
      patch.ambiguities.length;
    if (updateCount === 0) {
      context.addIssue({
        code: "custom",
        message: "At least one semantic update is required."
      });
    }
  });

export type SemanticDraftPatch = z.infer<typeof SemanticDraftPatchSchema>;
export type SemanticActivationPolicy = "auto_validated" | "manual_review";

export type SemanticVersionSummary = {
  id: string;
  connection_id: string;
  queryability_graph_version_id: string;
  version: number;
  status: "draft" | "proposed" | "active" | "archived";
  freshness: "fresh" | "stale";
  effective_freshness: "fresh" | "stale";
  revision: number;
  semantic_hash: string;
  validation_status:
    | "not_validated"
    | "valid"
    | "valid_with_warnings"
    | "blocked";
  activation_policy: SemanticActivationPolicy;
  created_at: string;
  updated_at: string;
  activated_at: string | null;
  archived_at: string | null;
  artifact_status: "compatible" | "incompatible";
  artifact_error: string | null;
};

type SemanticVersionRow = Omit<
  SemanticVersionSummary,
  "artifact_error" | "artifact_status" | "effective_freshness"
> & {
  artifact: unknown;
  base_graph_hash: string;
  base_policy_hash: string;
  rebased_from_version_id: string | null;
};

type GraphRow = {
  id: string;
  connection_id: string;
  version: number;
  graph_hash: string;
  graph: unknown;
};

export class SemanticLayerServiceError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status = 400,
    readonly semanticVersionId?: string
  ) {
    super(message);
    this.name = "SemanticLayerServiceError";
  }
}

export async function listSemanticVersions({
  connectionId,
  context
}: {
  connectionId: string;
  context: ActiveTenantContext;
}): Promise<SemanticVersionSummary[]> {
  const [versions, currentGraph, currentPolicy] = await Promise.all([
    readSemanticVersionRows(context.tenantId, connectionId, false),
    readCurrentGraph(context.tenantId, connectionId, false),
    readCurrentSemanticPolicy(context.tenantId, connectionId, false).catch(
      (error: unknown) => {
        console.error("Semantic policy could not be read while listing versions", {
          connection_id: connectionId,
          error:
            error instanceof Error
              ? { message: error.message, name: error.name }
              : { type: typeof error }
        });
        return null;
      }
    )
  ]);
  const currentGraphHash = currentGraph?.graph_hash;
  return versions.map((version) =>
    toVersionSummary(version, currentGraphHash, currentPolicy?.policy_hash)
  );
}

export async function readSemanticLayerVersion({
  context,
  semanticVersionId
}: {
  context: ActiveTenantContext;
  semanticVersionId: string;
}) {
  const row = await readSemanticVersionRow(
    context.tenantId,
    semanticVersionId
  );
  const [graph, policy] = await Promise.all([
    readCurrentGraph(context.tenantId, row.connection_id, false),
    readCurrentSemanticPolicy(context.tenantId, row.connection_id, false)
  ]);
  return {
    artifact: parseSemanticLayerArtifact(row.artifact, row.id),
    summary: toVersionSummary(row, graph?.graph_hash, policy?.policy_hash)
  };
}

export async function readCurrentSemanticLayer({
  connectionId,
  context
}: {
  connectionId: string;
  context: ActiveTenantContext;
}) {
  const versions = await readSemanticVersionRows(
    context.tenantId,
    connectionId,
    true
  );
  const compatibleVersions = versions.filter(
    (version) => semanticArtifactCompatibility(version.artifact).status === "compatible"
  );
  const selected =
    compatibleVersions.find((version) => version.status === "active") ??
    compatibleVersions.find((version) => version.status === "proposed") ??
    compatibleVersions.find((version) => version.status === "draft") ??
    null;
  if (!selected) {
    return null;
  }
  const [graph, policy] = await Promise.all([
    readCurrentGraph(context.tenantId, connectionId, false),
    readCurrentSemanticPolicy(context.tenantId, connectionId, false)
  ]);
  return {
    artifact: parseSemanticLayerArtifact(selected.artifact, selected.id),
    summary: toVersionSummary(
      selected,
      graph?.graph_hash,
      policy?.policy_hash
    )
  };
}

export async function readConnectionSemanticPolicy({
  connectionId,
  context
}: {
  connectionId: string;
  context: ActiveTenantContext;
}) {
  return readCurrentSemanticPolicy(context.tenantId, connectionId, true);
}

export async function createSemanticDraft({
  activationPolicy,
  connectionId,
  context
}: {
  activationPolicy: SemanticActivationPolicy;
  connectionId: string;
  context: ActiveTenantContext;
}) {
  assertSemanticAdmin(context);
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const [graphRow, versions, semanticPolicy] = await Promise.all([
      readCurrentGraph(context.tenantId, connectionId, true),
      readSemanticVersionRows(context.tenantId, connectionId, false),
      readCurrentSemanticPolicy(context.tenantId, connectionId, true)
    ]);
    const version = Math.max(0, ...versions.map((item) => item.version)) + 1;
    await synchronizeSemanticPolicy({
      connectionId,
      context,
      policy: semanticPolicy
    });
    const semanticVersionId = randomUUID();
    const artifact = await postQueryEngine(
      "/semantic/seed",
      {
        graph: graphRow.graph,
        queryability_graph_version_id: graphRow.id,
        semantic_version_id: semanticVersionId,
        version,
        semantic_policy: semanticPolicy
      },
      SemanticLayerSchema,
      30_000
    );
    try {
      return await persistSemanticArtifact({
        activationPolicy,
        artifact,
        context,
        graphVersionId: graphRow.id
      });
    } catch (error) {
      if (attempt === 0 && isSemanticRevisionConflict(error)) {
        continue;
      }
      throw error;
    }
  }
  throw new SemanticLayerServiceError(
    "semantic_revision_conflict",
    "Impossibile allocare una nuova versione Semantic Layer.",
    409
  );
}

export async function generateSemanticDraft({
  context,
  semanticVersionId
}: {
  context: ActiveTenantContext;
  semanticVersionId: string;
}) {
  assertSemanticAdmin(context);
  const row = await readMutableSemanticVersion(context, semanticVersionId);
  if (row.status === "proposed") {
    const draft = await createSemanticDraft({
      activationPolicy: row.activation_policy,
      connectionId: row.connection_id,
      context
    });
    return generateSemanticDraft({
      context,
      semanticVersionId: draft.artifact.semantic_version_id
    });
  }
  const graphRow = await readCurrentGraph(
    context.tenantId,
    row.connection_id,
    true
  );
  const semanticPolicy = await readCurrentSemanticPolicy(
    context.tenantId,
    row.connection_id,
    true
  );
  await synchronizeSemanticPolicy({
    connectionId: row.connection_id,
    context,
    policy: semanticPolicy
  });
  if (!versionTargetsCurrentContext(row, graphRow, semanticPolicy)) {
    const draft = await createSemanticDraft({
      activationPolicy: row.activation_policy,
      connectionId: row.connection_id,
      context
    });
    return generateSemanticDraft({
      context,
      semanticVersionId: draft.artifact.semantic_version_id
    });
  }
  assertVersionTargetsCurrentContext(row, graphRow, semanticPolicy);
  const providerConfig = await readDefaultAIProviderConfig({ context });
  if (!providerConfig) {
    throw new SemanticLayerServiceError(
      "semantic_ai_provider_not_configured",
      "Configura un provider AI prima di generare una proposta.",
      409
    );
  }

  let generated: SemanticGenerationResult;
  try {
    generated = await withSecurityOperationLease({
      actorUserId: context.userId,
      operation: "semantic_generation",
      resourceKey: row.connection_id,
      tenantId: context.tenantId,
      run: () =>
        postQueryEngine(
          "/semantic/generate",
          {
            graph: graphRow.graph,
            provider_config: providerConfig,
            seed: parseSemanticLayerArtifact(row.artifact, row.id),
            semantic_policy: semanticPolicy
          },
          SemanticGenerationResultSchema,
          500_000
        )
    });
  } catch (error) {
    if (isSecurityOperationLimitError(error)) {
      throw new SemanticLayerServiceError(
        "semantic_generation_rate_limited",
        "Una generazione Semantic Layer e gia in corso o il limite e stato raggiunto.",
        429
      );
    }
    throw mapQueryEngineError(error, "semantic_generation_failed");
  }

  const persisted = await persistSemanticArtifact({
    activationPolicy: row.activation_policy,
    artifact: generated.semantic_layer,
    context,
    expectedRevision: row.revision,
    generationProvenance: generated.provenance,
    graphVersionId: graphRow.id,
    semanticVersionId
  });
  if (
    row.activation_policy === "auto_validated" &&
    persisted.artifact.status === "proposed"
  ) {
    try {
      return await activateSemanticVersion({
        context,
        expectedRevision: persisted.artifact.revision,
        semanticVersionId
      });
    } catch {
      throw new SemanticLayerServiceError(
        "semantic_activation_failed_after_persistence",
        "La proposta e stata salvata e validata, ma l'attivazione automatica e fallita.",
        500,
        persisted.artifact.semantic_version_id
      );
    }
  }
  return persisted;
}

export async function patchSemanticDraft({
  context,
  patch,
  semanticVersionId
}: {
  context: ActiveTenantContext;
  patch: SemanticDraftPatch;
  semanticVersionId: string;
}) {
  assertSemanticAdmin(context);
  const row = await readMutableSemanticVersion(context, semanticVersionId);
  if (row.revision !== patch.expected_revision) {
    throw new SemanticLayerServiceError(
      "semantic_revision_conflict",
      "La proposta è stata modificata da un'altra sessione.",
      409
    );
  }
  const graphRow = await readCurrentGraph(
    context.tenantId,
    row.connection_id,
    true
  );
  const semanticPolicy = await readCurrentSemanticPolicy(
    context.tenantId,
    row.connection_id,
    true
  );
  await synchronizeSemanticPolicy({
    connectionId: row.connection_id,
    context,
    policy: semanticPolicy
  });
  assertVersionTargetsCurrentContext(row, graphRow, semanticPolicy);
  const reviewPatch = {
    tables: patch.tables,
    columns: patch.columns,
    business_concepts: patch.business_concepts,
    metrics: patch.metrics,
    ambiguities: patch.ambiguities
  };
  return reviewAndPersist({
    activationPolicy: row.activation_policy,
    context,
    expectedRevision: row.revision,
    graphRow,
    patch: reviewPatch,
    semanticPolicy,
    semanticVersionId
  });
}

export async function validateSemanticDraft({
  context,
  expectedRevision,
  semanticVersionId
}: {
  context: ActiveTenantContext;
  expectedRevision: number;
  semanticVersionId: string;
}) {
  assertSemanticAdmin(context);
  const row = await readMutableSemanticVersion(context, semanticVersionId);
  if (row.revision !== expectedRevision) {
    throw new SemanticLayerServiceError(
      "semantic_revision_conflict",
      "La proposta è stata modificata da un'altra sessione.",
      409
    );
  }
  const graphRow = await readCurrentGraph(
    context.tenantId,
    row.connection_id,
    true
  );
  const semanticPolicy = await readCurrentSemanticPolicy(
    context.tenantId,
    row.connection_id,
    true
  );
  await synchronizeSemanticPolicy({
    connectionId: row.connection_id,
    context,
    policy: semanticPolicy
  });
  assertVersionTargetsCurrentContext(row, graphRow, semanticPolicy);
  return reviewAndPersist({
    activationPolicy: row.activation_policy,
    context,
    expectedRevision,
    graphRow,
    patch: {},
    semanticPolicy,
    semanticVersionId
  });
}

export async function activateSemanticVersion({
  context,
  expectedRevision,
  semanticVersionId
}: {
  context: ActiveTenantContext;
  expectedRevision: number;
  semanticVersionId: string;
}) {
  assertSemanticAdmin(context);
  const row = await readSemanticVersionRow(context.tenantId, semanticVersionId);
  const semanticPolicy = await readCurrentSemanticPolicy(
    context.tenantId,
    row.connection_id,
    true
  );
  await synchronizeSemanticPolicy({
    connectionId: row.connection_id,
    context,
    policy: semanticPolicy
  });
  if (row.base_policy_hash !== semanticPolicy.policy_hash) {
    throw new SemanticLayerServiceError(
      "semantic_version_stale",
      "La versione Semantic Layer e stale e deve essere ribasata.",
      409
    );
  }
  const { data, error } = await createSupabaseAdminClient().rpc(
    "activate_semantic_layer_version",
    {
      actor_user_id: context.userId,
      expected_revision: expectedRevision,
      target_connection_id: row.connection_id,
      target_semantic_version_id: semanticVersionId,
      target_tenant_id: context.tenantId
    }
  );
  if (error || data !== semanticVersionId) {
    throw mapDatabaseError(error, "semantic_activation_failed");
  }
  return readSemanticLayerVersion({ context, semanticVersionId });
}

export async function archiveSemanticVersion({
  context,
  semanticVersionId
}: {
  context: ActiveTenantContext;
  semanticVersionId: string;
}) {
  assertSemanticAdmin(context);
  const row = await readSemanticVersionRow(context.tenantId, semanticVersionId);
  const { data, error } = await createSupabaseAdminClient().rpc(
    "archive_semantic_layer_version",
    {
      actor_user_id: context.userId,
      target_connection_id: row.connection_id,
      target_semantic_version_id: semanticVersionId,
      target_tenant_id: context.tenantId
    }
  );
  if (error || data !== semanticVersionId) {
    throw mapDatabaseError(error, "semantic_archive_failed");
  }
  return readSemanticLayerVersion({ context, semanticVersionId });
}

export async function setConnectionSemanticCurrency({
  connectionId,
  context,
  defaultCurrency
}: {
  connectionId: string;
  context: ActiveTenantContext;
  defaultCurrency: string | null;
}) {
  assertSemanticAdmin(context);
  const { error } = await createSupabaseAdminClient().rpc(
    "update_semantic_policy_settings",
    {
      actor_user_id: context.userId,
      target_connection_id: connectionId,
      target_default_currency: defaultCurrency,
      target_policy_config: null,
      target_tenant_id: context.tenantId,
      update_policy_config: false
    }
  );
  if (error) {
    throw mapDatabaseError(error, "semantic_policy_save_failed");
  }
}

export async function rebaseSemanticVersion({
  context,
  semanticVersionId
}: {
  context: ActiveTenantContext;
  semanticVersionId: string;
}) {
  assertSemanticAdmin(context);
  const source = await readSemanticVersionRow(
    context.tenantId,
    semanticVersionId
  );
  if (!["active", "archived"].includes(source.status)) {
    throw new SemanticLayerServiceError(
      "semantic_rebase_source_invalid",
      "Solo versioni active o archived possono essere ribasate."
    );
  }
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const [graphRow, versions, semanticPolicy] = await Promise.all([
      readCurrentGraph(context.tenantId, source.connection_id, true),
      readSemanticVersionRows(context.tenantId, source.connection_id, false),
      readCurrentSemanticPolicy(context.tenantId, source.connection_id, true)
    ]);
    const version = Math.max(0, ...versions.map((item) => item.version)) + 1;
    await synchronizeSemanticPolicy({
      connectionId: source.connection_id,
      context,
      policy: semanticPolicy
    });
    const targetVersionId = randomUUID();
    const rebased = await postQueryEngine(
      "/semantic/rebase",
      {
        queryability_graph_version_id: graphRow.id,
        semantic_version_id: targetVersionId,
        source_layer: parseSemanticLayerArtifact(source.artifact, source.id),
        semantic_policy: semanticPolicy,
        target_graph: graphRow.graph,
        version
      },
      SemanticRebaseResultSchema,
      60_000
    );
    try {
      const persisted = await persistSemanticArtifact({
        activationPolicy: source.activation_policy,
        artifact: rebased.semantic_layer,
        context,
        graphVersionId: graphRow.id,
        rebasedFromVersionId: source.id
      });
      return { ...persisted, rebase_report: rebased.rebase_report };
    } catch (error) {
      if (attempt === 0 && isSemanticRevisionConflict(error)) {
        continue;
      }
      throw error;
    }
  }
  throw new SemanticLayerServiceError(
    "semantic_revision_conflict",
    "Impossibile allocare una nuova versione Semantic Layer.",
    409
  );
}

async function reviewAndPersist({
  activationPolicy,
  context,
  expectedRevision,
  graphRow,
  patch,
  semanticPolicy,
  semanticVersionId
}: {
  activationPolicy: SemanticActivationPolicy;
  context: ActiveTenantContext;
  expectedRevision: number;
  graphRow: GraphRow;
  patch: Record<string, unknown>;
  semanticPolicy: SemanticPolicySnapshot;
  semanticVersionId: string;
}) {
  const row = await readMutableSemanticVersion(context, semanticVersionId);
  if (row.revision !== expectedRevision) {
    throw new SemanticLayerServiceError(
      "semantic_revision_conflict",
      "La proposta e stata modificata da un'altra sessione.",
      409
    );
  }
  let validated: SemanticLayer;
  try {
    validated = await postQueryEngine(
      "/semantic/review",
      {
        graph: graphRow.graph,
        patch,
        semantic_policy: semanticPolicy,
        source_layer: parseSemanticLayerArtifact(row.artifact, row.id)
      },
      SemanticLayerSchema,
      60_000
    );
  } catch (error) {
    throw mapQueryEngineError(error, "semantic_review_failed");
  }
  return persistSemanticArtifact({
    activationPolicy,
    artifact: validated,
    context,
    expectedRevision,
    graphVersionId: graphRow.id,
    semanticVersionId
  });
}

async function persistSemanticArtifact({
  activationPolicy,
  artifact,
  context,
  expectedRevision,
  generationProvenance,
  graphVersionId,
  rebasedFromVersionId,
  semanticVersionId
}: {
  activationPolicy: SemanticActivationPolicy;
  artifact: SemanticLayer;
  context: ActiveTenantContext;
  expectedRevision?: number;
  generationProvenance?: unknown;
  graphVersionId: string;
  rebasedFromVersionId?: string;
  semanticVersionId?: string;
}) {
  const { data, error } = await createSupabaseAdminClient().rpc(
    "persist_semantic_layer_version",
    {
      actor_user_id: context.userId,
      expected_revision: expectedRevision ?? null,
      target_activation_policy: activationPolicy,
      target_artifact: artifact,
      target_connection_id: artifact.connection_id,
      target_generation_provenance: generationProvenance ?? null,
      target_graph_version_id: graphVersionId,
      target_rebased_from_version_id: rebasedFromVersionId ?? null,
      target_semantic_version_id: semanticVersionId ?? null,
      target_tenant_id: context.tenantId
    }
  );
  const result = Array.isArray(data) ? data[0] : data;
  if (error || !result) {
    throw mapDatabaseError(error, "semantic_persist_failed");
  }
  return readSemanticLayerVersion({
    context,
    semanticVersionId: artifact.semantic_version_id
  });
}

async function readMutableSemanticVersion(
  context: ActiveTenantContext,
  semanticVersionId: string
) {
  const row = await readSemanticVersionRow(
    context.tenantId,
    semanticVersionId
  );
  if (!["draft", "proposed"].includes(row.status)) {
    throw new SemanticLayerServiceError(
      "semantic_version_immutable",
      "La versione semantic selezionata è immutabile.",
      409
    );
  }
  return row;
}

async function readSemanticVersionRow(
  tenantId: string,
  semanticVersionId: string
): Promise<SemanticVersionRow> {
  const { data, error } = await createSupabaseAdminClient()
    .from("semantic_layer_versions")
    .select(
      "id,connection_id,queryability_graph_version_id,base_graph_hash,base_policy_hash,version,status,freshness,revision,semantic_hash,validation_report,activation_policy,artifact,rebased_from_version_id,created_at,updated_at,activated_at,archived_at"
    )
    .eq("tenant_id", tenantId)
    .eq("id", semanticVersionId)
    .maybeSingle();
  if (error) {
    throw new SemanticLayerServiceError(
      "semantic_read_failed",
      "Lettura Semantic Layer fallita.",
      500
    );
  }
  if (!data) {
    throw new SemanticLayerServiceError(
      "semantic_version_not_found",
      "Versione Semantic Layer non trovata.",
      404
    );
  }
  return parseSemanticVersionRow(data);
}

async function readSemanticVersionRows(
  tenantId: string,
  connectionId: string,
  includeArtifact: boolean
): Promise<SemanticVersionRow[]> {
  const fields = [
    "id",
    "connection_id",
    "queryability_graph_version_id",
    "base_graph_hash",
    "base_policy_hash",
    "version",
    "status",
    "freshness",
    "revision",
    "semantic_hash",
    "validation_report",
    "activation_policy",
    "rebased_from_version_id",
    "created_at",
    "updated_at",
    "activated_at",
    "archived_at"
  ];
  if (includeArtifact) {
    fields.push("artifact");
  }
  const { data, error } = await createSupabaseAdminClient()
    .from("semantic_layer_versions")
    .select(fields.join(","))
    .eq("tenant_id", tenantId)
    .eq("connection_id", connectionId)
    .order("version", { ascending: false })
    .limit(100);
  if (error) {
    throw new SemanticLayerServiceError(
      "semantic_read_failed",
      "Lettura versioni Semantic Layer fallita.",
      500
    );
  }
  const rows = (data ?? []) as unknown as Array<Record<string, unknown>>;
  return rows.map((row) =>
    parseSemanticVersionRow({
      ...row,
      artifact: "artifact" in row ? row.artifact : null
    })
  );
}

async function readCurrentGraph(
  tenantId: string,
  connectionId: string,
  required: true
): Promise<GraphRow>;
async function readCurrentGraph(
  tenantId: string,
  connectionId: string,
  required: false
): Promise<GraphRow | null>;
async function readCurrentGraph(
  tenantId: string,
  connectionId: string,
  required: boolean
): Promise<GraphRow | null> {
  const admin = createSupabaseAdminClient();
  const { data: derivation, error: derivationError } = await admin
    .from("queryability_graph_derivations")
    .select("graph_version_id")
    .eq("tenant_id", tenantId)
    .eq("connection_id", connectionId)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (derivationError) {
    throw new SemanticLayerServiceError(
      "semantic_graph_read_failed",
      "Lettura Queryability Graph fallita.",
      500
    );
  }
  if (!derivation) {
    if (!required) {
      return null;
    }
    throw new SemanticLayerServiceError(
      "semantic_graph_not_found",
      "Importa prima lo schema e il Queryability Graph.",
      404
    );
  }
  const { data, error } = await admin
    .from("queryability_graph_versions")
    .select("id,connection_id,version,graph_hash,graph")
    .eq("tenant_id", tenantId)
    .eq("connection_id", connectionId)
    .eq("id", derivation.graph_version_id)
    .maybeSingle();
  if (error || !data) {
    if (!required && !error) {
      return null;
    }
    throw new SemanticLayerServiceError(
      "semantic_graph_not_found",
      "Queryability Graph corrente non trovato.",
      error ? 500 : 404
    );
  }
  return {
    id: data.id as string,
    connection_id: data.connection_id as string,
    version: data.version as number,
    graph_hash: data.graph_hash as string,
    graph: QueryabilityGraphArtifactSchema.parse(data.graph)
  };
}

async function readCurrentSemanticPolicy(
  tenantId: string,
  connectionId: string,
  required: true
): Promise<SemanticPolicySnapshot>;
async function readCurrentSemanticPolicy(
  tenantId: string,
  connectionId: string,
  required: false
): Promise<SemanticPolicySnapshot | null>;
async function readCurrentSemanticPolicy(
  tenantId: string,
  connectionId: string,
  required: boolean
): Promise<SemanticPolicySnapshot | null> {
  const admin = createSupabaseAdminClient();
  const [{ data: tenant, error: tenantError }, { data: connection, error: connectionError }] =
    await Promise.all([
      admin
        .from("tenants")
        .select("default_currency")
        .eq("id", tenantId)
        .maybeSingle(),
      admin
        .from("db_connections")
        .select("default_currency,semantic_policy_config")
        .eq("tenant_id", tenantId)
        .eq("id", connectionId)
        .maybeSingle()
    ]);
  if (tenantError || connectionError) {
    throw new SemanticLayerServiceError(
      "semantic_policy_read_failed",
      "Lettura policy semantica fallita.",
      500
    );
  }
  if (!tenant || !connection) {
    if (!required) {
      return null;
    }
    throw new SemanticLayerServiceError(
      "semantic_policy_not_found",
      "Policy semantica della connessione non trovata.",
      404
    );
  }
  return resolveSemanticPolicy({
    connectionDefaultCurrency: z
      .string()
      .regex(/^[A-Z]{3}$/)
      .nullable()
      .parse(connection.default_currency),
    policyConfig: connection.semantic_policy_config,
    tenantDefaultCurrency: z
      .string()
      .regex(/^[A-Z]{3}$/)
      .nullable()
      .parse(tenant.default_currency)
  });
}

async function synchronizeSemanticPolicy({
  connectionId,
  context,
  policy
}: {
  connectionId: string;
  context: ActiveTenantContext;
  policy: SemanticPolicySnapshot;
}) {
  const { error } = await createSupabaseAdminClient().rpc(
    "save_resolved_semantic_policy",
    {
      actor_user_id: context.userId,
      target_connection_id: connectionId,
      target_policy: policy,
      target_tenant_id: context.tenantId
    }
  );
  if (error) {
    throw mapDatabaseError(error, "semantic_policy_save_failed");
  }
}

function parseSemanticVersionRow(row: Record<string, unknown>): SemanticVersionRow {
  const validation = z
    .strictObject({
      status: z.enum([
        "not_validated",
        "valid",
        "valid_with_warnings",
        "blocked"
      ])
    })
    .passthrough()
    .parse(row.validation_report);
  return {
    id: z.string().uuid().parse(row.id),
    connection_id: z.string().uuid().parse(row.connection_id),
    queryability_graph_version_id: z
      .string()
      .uuid()
      .parse(row.queryability_graph_version_id),
    base_graph_hash: z.string().regex(/^[0-9a-f]{64}$/).parse(row.base_graph_hash),
    base_policy_hash: z.string().regex(/^[0-9a-f]{64}$/).parse(row.base_policy_hash),
    version: z.number().int().positive().parse(row.version),
    status: z
      .enum(["draft", "proposed", "active", "archived"])
      .parse(row.status),
    freshness: z.enum(["fresh", "stale"]).parse(row.freshness),
    revision: z.number().int().positive().parse(row.revision),
    semantic_hash: z.string().regex(/^[0-9a-f]{64}$/).parse(row.semantic_hash),
    validation_status: validation.status,
    activation_policy: z
      .enum(["auto_validated", "manual_review"])
      .parse(row.activation_policy),
    artifact: row.artifact,
    rebased_from_version_id: z.string().uuid().nullable().parse(
      row.rebased_from_version_id
    ),
    created_at: z.string().parse(row.created_at),
    updated_at: z.string().parse(row.updated_at),
    activated_at: z.string().nullable().parse(row.activated_at),
    archived_at: z.string().nullable().parse(row.archived_at)
  };
}

function toVersionSummary(
  row: SemanticVersionRow,
  currentGraphHash: string | undefined,
  currentPolicyHash: string | undefined
): SemanticVersionSummary {
  const artifactCompatibility = semanticArtifactCompatibility(row.artifact);
  return {
    id: row.id,
    connection_id: row.connection_id,
    queryability_graph_version_id: row.queryability_graph_version_id,
    version: row.version,
    status: row.status,
    freshness: row.freshness,
    revision: row.revision,
    semantic_hash: row.semantic_hash,
    validation_status: row.validation_status,
    activation_policy: row.activation_policy,
    created_at: row.created_at,
    updated_at: row.updated_at,
    activated_at: row.activated_at,
    archived_at: row.archived_at,
    artifact_status: artifactCompatibility.status,
    artifact_error: artifactCompatibility.error,
    effective_freshness:
      currentGraphHash &&
      currentPolicyHash &&
      row.base_graph_hash === currentGraphHash &&
      row.base_policy_hash === currentPolicyHash
        ? "fresh"
        : "stale"
  };
}

function parseSemanticLayerArtifact(
  artifact: unknown,
  semanticVersionId?: string
): SemanticLayer {
  const parsed = SemanticLayerSchema.safeParse(artifact);
  if (!parsed.success) {
    const firstIssue = parsed.error.issues[0];
    const detail = firstIssue
      ? `${firstIssue.path.join(".") || "<root>"}: ${firstIssue.message}`
      : "unknown schema mismatch";
    throw new SemanticLayerServiceError(
      "semantic_artifact_incompatible",
      `Semantic Layer artifact incompatible: ${detail}`,
      422,
      semanticVersionId
    );
  }
  return parsed.data;
}

function semanticArtifactCompatibility(artifact: unknown): {
  status: "compatible" | "incompatible";
  error: string | null;
} {
  const parsed = SemanticLayerSchema.safeParse(artifact);
  if (parsed.success) {
    return { status: "compatible", error: null };
  }
  const firstIssue = parsed.error.issues[0];
  return {
    status: "incompatible",
    error: firstIssue
      ? `${firstIssue.path.join(".") || "<root>"}: ${firstIssue.message}`
      : "unknown schema mismatch"
  };
}

function assertVersionTargetsCurrentContext(
  row: SemanticVersionRow,
  graph: GraphRow,
  policy: SemanticPolicySnapshot
) {
  if (!versionTargetsCurrentContext(row, graph, policy)) {
    throw new SemanticLayerServiceError(
      "semantic_version_stale",
      "La versione Semantic Layer è stale e deve essere ribasata.",
      409
    );
  }
}

function versionTargetsCurrentContext(
  row: SemanticVersionRow,
  graph: GraphRow,
  policy: SemanticPolicySnapshot
) {
  return (
    row.queryability_graph_version_id === graph.id &&
    row.base_graph_hash === graph.graph_hash &&
    row.base_policy_hash === policy.policy_hash
  );
}

function assertSemanticAdmin(context: ActiveTenantContext) {
  if (!canManageSemanticLayer(context.role)) {
    throw new SemanticLayerServiceError(
      "semantic_forbidden",
      "Solo owner e admin possono modificare il Semantic Layer.",
      403
    );
  }
}

function isSemanticRevisionConflict(
  error: unknown
): error is SemanticLayerServiceError {
  return (
    error instanceof SemanticLayerServiceError &&
    error.code === "semantic_revision_conflict"
  );
}

function mapDatabaseError(
  error: { code?: string; message?: string } | null,
  fallbackCode: string
) {
  const message = error?.message ?? "Semantic Layer operation failed.";
  if (
    error?.code === "40001" ||
    error?.code === "55000" ||
    message.includes("revision conflict") ||
    message.includes("allocation mismatch")
  ) {
    return new SemanticLayerServiceError(
      "semantic_revision_conflict",
      "La versione è cambiata durante l'operazione.",
      409
    );
  }
  if (error?.code === "42501" || message.includes("owner or admin")) {
    return new SemanticLayerServiceError(
      "semantic_forbidden",
      "Solo owner e admin possono modificare il Semantic Layer.",
      403
    );
  }
  if (error?.code === "P0002" || message.includes("not found")) {
    return new SemanticLayerServiceError(
      "semantic_version_not_found",
      "Versione Semantic Layer non trovata.",
      404
    );
  }
  if (error?.code === "22023") {
    return new SemanticLayerServiceError(
      "semantic_invalid_artifact",
      "L'artifact Semantic Layer non rispetta gli invarianti richiesti.",
      422
    );
  }
  return new SemanticLayerServiceError(
    fallbackCode,
    "Operazione Semantic Layer non completata.",
    400
  );
}

function mapQueryEngineError(error: unknown, fallbackCode: string) {
  if (error instanceof QueryEngineRequestError) {
    if (
      error.status === 424 &&
      fallbackCode === "semantic_generation_failed"
    ) {
      if (error.message.includes("credentials were rejected")) {
        return new SemanticLayerServiceError(
          "semantic_ai_credentials_rejected",
          "Il provider AI ha rifiutato la API key configurata.",
          424
        );
      }
      if (error.message.includes("model is unavailable")) {
        return new SemanticLayerServiceError(
          "semantic_ai_model_unavailable",
          "Il modello AI configurato non e disponibile per questa API key.",
          424
        );
      }
      if (error.message.includes("configuration is invalid")) {
        return new SemanticLayerServiceError(
          "semantic_ai_provider_request_invalid",
          "La configurazione della richiesta AI non e accettata dal provider.",
          424
        );
      }
    }
    if (
      error.status === 429 &&
      fallbackCode === "semantic_generation_failed"
    ) {
      return new SemanticLayerServiceError(
        "semantic_generation_rate_limited",
        "Il provider AI ha applicato un limite temporaneo alla richiesta.",
        429
      );
    }
    if (
      error.status === 503 &&
      fallbackCode === "semantic_generation_failed"
    ) {
      return new SemanticLayerServiceError(
        "semantic_ai_secret_unavailable",
        "Le credenziali del provider AI non sono leggibili dal query-engine.",
        503
      );
    }
    if (error.status === 422) {
      const isGeneration = fallbackCode === "semantic_generation_failed";
      return new SemanticLayerServiceError(
        isGeneration
          ? "semantic_proposal_invalid"
          : "semantic_review_invalid",
        isGeneration
          ? "La proposta AI non rispetta i vincoli tecnici."
          : "La modifica semantica non rispetta i vincoli tecnici.",
        422
      );
    }
    if (error.status === 409) {
      return new SemanticLayerServiceError(
        "semantic_revision_conflict",
        "La versione e cambiata durante l'operazione.",
        409
      );
    }
  }
  return new SemanticLayerServiceError(
    fallbackCode,
    fallbackCode === "semantic_generation_failed"
      ? "Generazione Semantic Layer fallita."
      : "Operazione Semantic Layer fallita.",
    502
  );
}

export function semanticServiceResponse(error: unknown) {
  if (error instanceof SemanticLayerServiceError) {
    return {
      code: error.code,
      message: error.message,
      status: error.status
    };
  }
  return {
    code: "semantic_internal_error",
    message: "Operazione Semantic Layer fallita.",
    status: 500
  };
}

export function semanticArtifactForApi(layer: SemanticLayer) {
  return SemanticLayerSchema.parse(layer);
}

export function graphForSemanticService(graph: unknown): QueryabilityGraphArtifact {
  return QueryabilityGraphArtifactSchema.parse(graph);
}
