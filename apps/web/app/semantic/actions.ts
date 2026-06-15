"use server";

import { redirect } from "next/navigation";
import { z } from "zod";

import {
  introspectConnection,
  rebuildQueryabilityGraph
} from "../../lib/schema-introspection/service";
import {
  activateSemanticVersion,
  archiveSemanticVersion,
  createSemanticDraft,
  generateSemanticDraft,
  patchSemanticDraft,
  rebaseSemanticVersion,
  semanticServiceResponse,
  validateSemanticDraft
} from "../../lib/semantic-layer/service";
import { getActiveTenantContext } from "../../lib/tenant";

const IntrospectionFormSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid(),
  timeout_ms: z.coerce.number().int().min(1000).max(120000).default(120000)
});

export async function introspectConnectionAction(formData: FormData) {
  const parsed = IntrospectionFormSchema.safeParse({
    tenant_id: formData.get("tenant_id"),
    connection_id: formData.get("connection_id"),
    timeout_ms: formData.get("timeout_ms") ?? "120000"
  });

  if (!parsed.success) {
    redirect("/semantic?tab=technical&message=invalid_introspection");
  }

  const context = await getActiveTenantContext(parsed.data.tenant_id);
  const result = await introspectConnection({
    connectionId: parsed.data.connection_id,
    context,
    timeoutMs: parsed.data.timeout_ms
  });

  if (!result.ok) {
    redirect(
      `/semantic?tab=technical&connection=${parsed.data.connection_id}&message=${result.code}`
    );
  }

  redirect(
    `/semantic?tab=technical&connection=${parsed.data.connection_id}&graph=${result.queryabilityGraphId}&snapshot=${result.schemaSnapshotId}`
  );
}

const RebuildFormSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid(),
  schema_snapshot_id: z.string().uuid()
});

export async function rebuildQueryabilityGraphAction(formData: FormData) {
  const parsed = RebuildFormSchema.safeParse({
    tenant_id: formData.get("tenant_id"),
    connection_id: formData.get("connection_id"),
    schema_snapshot_id: formData.get("schema_snapshot_id")
  });
  if (!parsed.success) {
    redirect("/semantic?tab=technical&message=invalid_rebuild_request");
  }

  const context = await getActiveTenantContext(parsed.data.tenant_id);
  const result = await rebuildQueryabilityGraph({
    context,
    schemaSnapshotId: parsed.data.schema_snapshot_id,
    timeoutMs: 30000
  });
  if (!result.ok) {
    redirect(
      `/semantic?tab=technical&connection=${parsed.data.connection_id}&message=${result.code}`
    );
  }

  redirect(
    `/semantic?tab=technical&connection=${parsed.data.connection_id}&graph=${result.queryabilityGraphId}&snapshot=${result.schemaSnapshotId}`
  );
}

const SemanticConnectionFormSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid()
});

const SemanticVersionFormSchema = SemanticConnectionFormSchema.extend({
  semantic_version_id: z.string().uuid(),
  expected_revision: z.coerce.number().int().positive().optional()
}).strict();

const SemanticMetricFormSchema = SemanticVersionFormSchema.extend({
  metric_key: z.string().uuid(),
  return_page: z.coerce.number().int().positive().max(100_000).optional()
}).strict();

const SemanticMetricCorrectionFormSchema = SemanticMetricFormSchema.extend({
  name: z.string().trim().min(1).max(255),
  description: z.string().trim().max(2_000)
}).strict();

export async function createAndGenerateSemanticDraftAction(formData: FormData) {
  const parsed = SemanticConnectionFormSchema.safeParse({
    tenant_id: formData.get("tenant_id"),
    connection_id: formData.get("connection_id")
  });
  if (!parsed.success) {
    redirectSemantic({ message: "invalid_semantic_draft" });
  }

  const context = await getActiveTenantContext(parsed.data.tenant_id);
  let semanticVersionId: string;
  try {
    const draft = await createSemanticDraft({
      activationPolicy: "auto_validated",
      connectionId: parsed.data.connection_id,
      context
    });
    const generated = await generateSemanticDraft({
      context,
      semanticVersionId: draft.artifact.semantic_version_id
    });
    semanticVersionId = generated.artifact.semantic_version_id;
  } catch (error) {
    redirectSemanticError(error, parsed.data.connection_id);
  }
  redirectSemantic({
    connectionId: parsed.data.connection_id,
    message: "semantic_proposal_generated",
    semanticVersionId
  });
}

export async function generateSemanticDraftAction(formData: FormData) {
  const parsed = parseSemanticVersionForm(formData);
  if (!parsed) {
    redirectSemantic({ message: "invalid_semantic_generation" });
  }
  const context = await getActiveTenantContext(parsed.tenant_id);
  let semanticVersionId: string;
  try {
    const generated = await generateSemanticDraft({
      context,
      semanticVersionId: parsed.semantic_version_id
    });
    semanticVersionId = generated.artifact.semantic_version_id;
  } catch (error) {
    redirectSemanticError(
      error,
      parsed.connection_id,
      parsed.semantic_version_id
    );
  }
  redirectSemantic({
    connectionId: parsed.connection_id,
    message: "semantic_proposal_generated",
    semanticVersionId
  });
}

export async function validateSemanticDraftAction(formData: FormData) {
  const parsed = parseSemanticVersionForm(formData, true);
  if (!parsed?.expected_revision) {
    redirectSemantic({ message: "invalid_semantic_validation" });
  }
  const context = await getActiveTenantContext(parsed.tenant_id);
  let semanticVersionId: string;
  try {
    const validated = await validateSemanticDraft({
      context,
      expectedRevision: parsed.expected_revision,
      semanticVersionId: parsed.semantic_version_id
    });
    semanticVersionId = validated.artifact.semantic_version_id;
  } catch (error) {
    redirectSemanticError(
      error,
      parsed.connection_id,
      parsed.semantic_version_id
    );
  }
  redirectSemantic({
    connectionId: parsed.connection_id,
    message: "semantic_proposal_validated",
    semanticVersionId
  });
}

export async function activateSemanticVersionAction(formData: FormData) {
  const parsed = parseSemanticVersionForm(formData, true);
  if (!parsed?.expected_revision) {
    redirectSemantic({ message: "invalid_semantic_activation" });
  }
  const context = await getActiveTenantContext(parsed.tenant_id);
  let semanticVersionId: string;
  try {
    const activated = await activateSemanticVersion({
      context,
      expectedRevision: parsed.expected_revision,
      semanticVersionId: parsed.semantic_version_id
    });
    semanticVersionId = activated.artifact.semantic_version_id;
  } catch (error) {
    redirectSemanticError(
      error,
      parsed.connection_id,
      parsed.semantic_version_id
    );
  }
  redirectSemantic({
    connectionId: parsed.connection_id,
    message: "semantic_version_activated",
    semanticVersionId
  });
}

export async function rebaseSemanticVersionAction(formData: FormData) {
  const parsed = parseSemanticVersionForm(formData);
  if (!parsed) {
    redirectSemantic({ message: "invalid_semantic_rebase" });
  }
  const context = await getActiveTenantContext(parsed.tenant_id);
  let semanticVersionId: string;
  try {
    const rebased = await rebaseSemanticVersion({
      context,
      semanticVersionId: parsed.semantic_version_id
    });
    semanticVersionId = rebased.artifact.semantic_version_id;
  } catch (error) {
    redirectSemanticError(
      error,
      parsed.connection_id,
      parsed.semantic_version_id
    );
  }
  redirectSemantic({
    connectionId: parsed.connection_id,
    message: "semantic_version_rebased",
    semanticVersionId
  });
}

export async function archiveSemanticVersionAction(formData: FormData) {
  const parsed = parseSemanticVersionForm(formData);
  if (!parsed) {
    redirectSemantic({ message: "invalid_semantic_archive" });
  }
  const context = await getActiveTenantContext(parsed.tenant_id);
  try {
    await archiveSemanticVersion({
      context,
      semanticVersionId: parsed.semantic_version_id
    });
  } catch (error) {
    redirectSemanticError(
      error,
      parsed.connection_id,
      parsed.semantic_version_id
    );
  }
  redirectSemantic({
    connectionId: parsed.connection_id,
    message: "semantic_version_archived"
  });
}

export async function confirmSemanticMetricAction(formData: FormData) {
  await updateSemanticMetric(formData, {
    enabled: true,
    message: "semantic_metric_confirmed",
    status: "human_verified"
  });
}

export async function disableSemanticMetricAction(formData: FormData) {
  await updateSemanticMetric(formData, {
    enabled: false,
    message: "semantic_metric_disabled",
    status: "disabled"
  });
}

export async function correctSemanticMetricAction(formData: FormData) {
  const parsed = SemanticMetricCorrectionFormSchema.safeParse({
    tenant_id: formData.get("tenant_id"),
    connection_id: formData.get("connection_id"),
    semantic_version_id: formData.get("semantic_version_id"),
    expected_revision: formData.get("expected_revision"),
    metric_key: formData.get("metric_key"),
    return_page: formData.get("return_page") || undefined,
    name: formData.get("name"),
    description: formData.get("description") ?? ""
  });
  if (!parsed.success || !parsed.data.expected_revision) {
    redirectSemantic({ message: "invalid_semantic_metric_update" });
  }
  const context = await getActiveTenantContext(parsed.data.tenant_id);
  let semanticVersionId: string;
  try {
    const updated = await patchSemanticDraft({
      context,
      patch: {
        tenant_id: parsed.data.tenant_id,
        expected_revision: parsed.data.expected_revision,
        tables: [],
        columns: [],
        business_concepts: [],
        metrics: [
          {
            metric_key: parsed.data.metric_key,
            name: parsed.data.name,
            description: parsed.data.description || null
          }
        ],
        ambiguities: []
      },
      semanticVersionId: parsed.data.semantic_version_id
    });
    semanticVersionId = updated.artifact.semantic_version_id;
  } catch (error) {
    redirectSemanticError(
      error,
      parsed.data.connection_id,
      parsed.data.semantic_version_id,
      parsed.data.return_page
    );
  }
  redirectSemantic({
    connectionId: parsed.data.connection_id,
    message: "semantic_metric_corrected",
    ...(parsed.data.return_page
      ? { metricPage: parsed.data.return_page }
      : {}),
    semanticVersionId
  });
}

async function updateSemanticMetric(
  formData: FormData,
  update: {
    enabled: boolean;
    message: string;
    status: "human_verified" | "disabled";
  }
) {
  const parsed = SemanticMetricFormSchema.safeParse({
    tenant_id: formData.get("tenant_id"),
    connection_id: formData.get("connection_id"),
    semantic_version_id: formData.get("semantic_version_id"),
    expected_revision: formData.get("expected_revision"),
    metric_key: formData.get("metric_key"),
    return_page: formData.get("return_page") || undefined
  });
  if (!parsed.success || !parsed.data.expected_revision) {
    redirectSemantic({ message: "invalid_semantic_metric_update" });
  }
  const context = await getActiveTenantContext(parsed.data.tenant_id);
  let semanticVersionId: string;
  try {
    const updated = await patchSemanticDraft({
      context,
      patch: {
        tenant_id: parsed.data.tenant_id,
        expected_revision: parsed.data.expected_revision,
        tables: [],
        columns: [],
        business_concepts: [],
        metrics: [
          {
            metric_key: parsed.data.metric_key,
            enabled: update.enabled,
            status: update.status
          }
        ],
        ambiguities: []
      },
      semanticVersionId: parsed.data.semantic_version_id
    });
    semanticVersionId = updated.artifact.semantic_version_id;
  } catch (error) {
    redirectSemanticError(
      error,
      parsed.data.connection_id,
      parsed.data.semantic_version_id,
      parsed.data.return_page
    );
  }
  redirectSemantic({
    connectionId: parsed.data.connection_id,
    message: update.message,
    ...(parsed.data.return_page
      ? { metricPage: parsed.data.return_page }
      : {}),
    semanticVersionId
  });
}

function parseSemanticVersionForm(formData: FormData, revisionRequired = false) {
  const parsed = SemanticVersionFormSchema.safeParse({
    tenant_id: formData.get("tenant_id"),
    connection_id: formData.get("connection_id"),
    semantic_version_id: formData.get("semantic_version_id"),
    expected_revision: formData.get("expected_revision") || undefined
  });
  if (!parsed.success || (revisionRequired && !parsed.data.expected_revision)) {
    return null;
  }
  return parsed.data;
}

function redirectSemantic({
  connectionId,
  message,
  metricPage,
  semanticVersionId
}: {
  connectionId?: string;
  message: string;
  metricPage?: number;
  semanticVersionId?: string;
}): never {
  const query = new URLSearchParams({ message });
  if (connectionId) {
    query.set("connection", connectionId);
  }
  if (semanticVersionId) {
    query.set("semantic", semanticVersionId);
  }
  if (metricPage) {
    query.set("metrics_page", String(metricPage));
  }
  redirect(`/semantic?${query.toString()}${metricPage ? "#metrics" : ""}`);
}

function redirectSemanticError(
  error: unknown,
  connectionId?: string,
  semanticVersionId?: string,
  metricPage?: number
): never {
  const response = semanticServiceResponse(error);
  redirectSemantic({
    message: response.code,
    ...(connectionId ? { connectionId } : {}),
    ...(metricPage ? { metricPage } : {}),
    ...(semanticVersionId ? { semanticVersionId } : {})
  });
}
