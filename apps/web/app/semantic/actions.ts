"use server";

import { redirect } from "next/navigation";
import { z } from "zod";

import {
  introspectConnection,
  rebuildQueryabilityGraph
} from "../../lib/schema-introspection/service";
import {
  createNorthStarBenchmark,
  deleteNorthStarBenchmark,
  northStarServiceResponse,
  updateNorthStarBenchmark
} from "../../lib/north-star-benchmarks/service";
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

const NullableUuidFormSchema = z.preprocess(
  (value) => (value === "" ? null : value),
  z.string().uuid().nullable()
);

const NullableDateFormSchema = z.preprocess(
  (value) => (value === "" ? null : value),
  z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/)
    .nullable()
);

const NullableNumberFormSchema = z.preprocess(
  (value) => (value === "" ? null : value),
  z.coerce.number().finite().nullable()
);

const NorthStarFormSchema = z
  .strictObject({
    tenant_id: z.string().uuid(),
    connection_id: z.string().uuid(),
    benchmark_key: NullableUuidFormSchema.optional(),
    dashboard_id: NullableUuidFormSchema.optional(),
    semantic_version_id: NullableUuidFormSchema.optional(),
    metric_key: NullableUuidFormSchema.optional(),
    name: z.string().trim().min(1).max(255),
    description: z.preprocess(
      (value) => (value === "" ? null : value),
      z.string().trim().max(2_000).nullable()
    ),
    expected_value: z.coerce.number().finite(),
    value_type: z.enum(["currency", "number", "percentage", "count"]),
    currency: z.preprocess(
      (value) => (value === "" ? null : value),
      z.string().trim().regex(/^[A-Z]{3}$/).nullable()
    ),
    period_type: z.enum([
      "day",
      "week",
      "month",
      "quarter",
      "year",
      "rolling_12_months",
      "custom"
    ]),
    period_start: NullableDateFormSchema,
    period_end: NullableDateFormSchema,
    tolerance_mode: z.enum(["percentage", "absolute", "range"]),
    tolerance_percentage: NullableNumberFormSchema,
    min_value: NullableNumberFormSchema,
    max_value: NullableNumberFormSchema,
    severity: z.enum(["low", "medium", "high", "critical"]),
    enabled: z.preprocess((value) => value === "on", z.boolean())
  })
  .superRefine((input, context) => {
    if ((input.metric_key === null) !== (input.semantic_version_id === null)) {
      context.addIssue({
        code: "custom",
        path: ["metric_key"],
        message: "metric_key and semantic_version_id must be provided together"
      });
    }
    if (input.value_type === "currency" && !input.currency) {
      context.addIssue({
        code: "custom",
        path: ["currency"],
        message: "currency is required for currency benchmarks"
      });
    }
    if (
      input.period_type === "custom" &&
      (!input.period_start || !input.period_end)
    ) {
      context.addIssue({
        code: "custom",
        path: ["period_start"],
        message: "custom periods require start and end dates"
      });
    }
    if (
      input.period_start &&
      input.period_end &&
      input.period_start > input.period_end
    ) {
      context.addIssue({
        code: "custom",
        path: ["period_end"],
        message: "period_end must be on or after period_start"
      });
    }
    if (
      input.tolerance_mode === "percentage" &&
      (input.tolerance_percentage === null ||
        input.tolerance_percentage <= 0 ||
        input.min_value !== null ||
        input.max_value !== null)
    ) {
      context.addIssue({
        code: "custom",
        path: ["tolerance_percentage"],
        message: "percentage tolerance requires only tolerance_percentage"
      });
    }
    if (
      input.tolerance_mode !== "percentage" &&
      (input.tolerance_percentage !== null ||
        input.min_value === null ||
        input.max_value === null ||
        input.min_value > input.max_value)
    ) {
      context.addIssue({
        code: "custom",
        path: ["min_value"],
        message: "range tolerance requires min_value and max_value"
      });
    }
  });

const NorthStarDeleteFormSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid(),
  benchmark_key: z.string().uuid()
});

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

export async function upsertNorthStarBenchmarkAction(formData: FormData) {
  const parsed = NorthStarFormSchema.safeParse({
    tenant_id: formData.get("tenant_id"),
    connection_id: formData.get("connection_id"),
    benchmark_key: formData.get("benchmark_key") || undefined,
    dashboard_id: formData.get("dashboard_id") || null,
    semantic_version_id: formData.get("semantic_version_id") || null,
    metric_key: formData.get("metric_key") || null,
    name: formData.get("name"),
    description: formData.get("description") ?? "",
    expected_value: formData.get("expected_value"),
    value_type: formData.get("value_type"),
    currency: formData.get("currency") ?? "",
    period_type: formData.get("period_type"),
    period_start: formData.get("period_start") ?? "",
    period_end: formData.get("period_end") ?? "",
    tolerance_mode: formData.get("tolerance_mode"),
    tolerance_percentage: formData.get("tolerance_percentage") ?? "",
    min_value: formData.get("min_value") ?? "",
    max_value: formData.get("max_value") ?? "",
    severity: formData.get("severity"),
    enabled: formData.get("enabled")
  });
  if (!parsed.success) {
    redirectNorthStar({
      connectionId: String(formData.get("connection_id") ?? ""),
      message: "invalid_north_star"
    });
  }

  const context = await getActiveTenantContext(parsed.data.tenant_id);
  let message = "north_star_created";
  try {
    const input = {
      connection_id: parsed.data.connection_id,
      dashboard_id: parsed.data.dashboard_id ?? null,
      semantic_version_id: parsed.data.semantic_version_id ?? null,
      metric_key: parsed.data.metric_key ?? null,
      name: parsed.data.name,
      description: parsed.data.description,
      expected_value: parsed.data.expected_value,
      value_type: parsed.data.value_type,
      currency:
        parsed.data.value_type === "currency" ? parsed.data.currency : null,
      period_type: parsed.data.period_type,
      period_start: parsed.data.period_start,
      period_end: parsed.data.period_end,
      tolerance_mode: parsed.data.tolerance_mode,
      tolerance_percentage: parsed.data.tolerance_percentage,
      min_value: parsed.data.min_value,
      max_value: parsed.data.max_value,
      severity: parsed.data.severity,
      enabled: parsed.data.enabled
    };
    if (parsed.data.benchmark_key) {
      await updateNorthStarBenchmark({
        benchmarkKey: parsed.data.benchmark_key,
        context,
        input
      });
      message = "north_star_updated";
    } else {
      await createNorthStarBenchmark({
        context,
        input
      });
    }
  } catch (error) {
    redirectNorthStarError(error, parsed.data.connection_id);
  }

  redirectNorthStar({
    connectionId: parsed.data.connection_id,
    message
  });
}

export async function deleteNorthStarBenchmarkAction(formData: FormData) {
  const parsed = NorthStarDeleteFormSchema.safeParse({
    tenant_id: formData.get("tenant_id"),
    connection_id: formData.get("connection_id"),
    benchmark_key: formData.get("benchmark_key")
  });
  if (!parsed.success) {
    redirectNorthStar({ message: "invalid_north_star_delete" });
  }

  const context = await getActiveTenantContext(parsed.data.tenant_id);
  try {
    await deleteNorthStarBenchmark({
      benchmarkKey: parsed.data.benchmark_key,
      context
    });
  } catch (error) {
    redirectNorthStarError(error, parsed.data.connection_id);
  }

  redirectNorthStar({
    connectionId: parsed.data.connection_id,
    message: "north_star_deleted"
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

function redirectNorthStar({
  connectionId,
  message
}: {
  connectionId?: string;
  message: string;
}): never {
  const query = new URLSearchParams({
    message,
    tab: "north-stars"
  });
  if (connectionId) {
    query.set("connection", connectionId);
  }
  redirect(`/semantic?${query.toString()}`);
}

function redirectNorthStarError(error: unknown, connectionId?: string): never {
  const response = northStarServiceResponse(error, "north_star_failed");
  redirectNorthStar({
    message: response.code,
    ...(connectionId ? { connectionId } : {})
  });
}
