import "server-only";

import { SecretManagerServiceClient } from "@google-cloud/secret-manager";
import {
  AIProviderSettingSummarySchema,
  AISemanticProviderConfigSchema,
  AnthropicThinkingConfigSchema,
  OpenAIThinkingConfigSchema,
  type AIProviderSettingSummary,
  type AISemanticProviderConfig
} from "@atlantebi/contracts";
import { createHash, randomUUID } from "node:crypto";
import { z } from "zod";

import {
  isSecurityOperationLimitError,
  withSecurityOperationLease
} from "../security/operation-lease";
import { createSupabaseAdminClient } from "../supabase/admin";
import {
  canManageSemanticLayer,
  type ActiveTenantContext
} from "../tenant";

const secretClient = new SecretManagerServiceClient();

const BaseAIProviderSettingInputSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  display_name: z.string().trim().min(1).max(160),
  api_key: z.string().trim().min(1).max(10_000),
  is_default: z.boolean().default(true)
});

export const AIProviderSettingInputSchema = z.discriminatedUnion("provider", [
  BaseAIProviderSettingInputSchema.extend({
    provider: z.literal("openai"),
    model_id: z.literal("gpt-5.5"),
    thinking: OpenAIThinkingConfigSchema
  }).strict(),
  BaseAIProviderSettingInputSchema.extend({
    provider: z.literal("anthropic"),
    model_id: z.enum(["claude-sonnet-4-6", "claude-opus-4-8"]),
    thinking: AnthropicThinkingConfigSchema
  })
    .strict()
    .superRefine((value, context) => {
      if (
        value.model_id === "claude-sonnet-4-6" &&
        value.thinking.effort === "xhigh"
      ) {
        context.addIssue({
          code: "custom",
          message: "Claude Sonnet 4.6 does not support xhigh effort."
        });
      }
    })
]);

export type AIProviderSettingInput = z.infer<
  typeof AIProviderSettingInputSchema
>;

export class AIProviderSettingsError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status = 400
  ) {
    super(message);
    this.name = "AIProviderSettingsError";
  }
}

export async function listAIProviderSettings({
  context
}: {
  context: ActiveTenantContext;
}): Promise<AIProviderSettingSummary[]> {
  const { data, error } = await createSupabaseAdminClient()
    .from("ai_provider_setting_summaries")
    .select(
      "id,tenant_id,provider,model_id,display_name,thinking,status,is_default,last_test_status,last_tested_at,created_at,updated_at"
    )
    .eq("tenant_id", context.tenantId)
    .order("is_default", { ascending: false })
    .order("updated_at", { ascending: false });

  if (error) {
    throw new AIProviderSettingsError(
      "ai_provider_settings_read_failed",
      "Configurazioni AI non leggibili.",
      500
    );
  }

  return (data ?? []).map((row) => AIProviderSettingSummarySchema.parse(row));
}

export async function readDefaultAIProviderConfig({
  context
}: {
  context: ActiveTenantContext;
}): Promise<AISemanticProviderConfig | null> {
  const { data, error } = await createSupabaseAdminClient()
    .from("ai_provider_settings")
    .select("id,provider,model_id,thinking,secret_ref")
    .eq("tenant_id", context.tenantId)
    .eq("status", "ready")
    .eq("is_default", true)
    .order("updated_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) {
    throw new AIProviderSettingsError(
      "ai_provider_settings_read_failed",
      "Configurazione AI non leggibile.",
      500
    );
  }
  if (!data) {
    return null;
  }

  return AISemanticProviderConfigSchema.parse({
    provider: data.provider,
    setting_id: data.id,
    model_id: data.model_id,
    thinking: data.thinking,
    secret_ref: data.secret_ref
  });
}

export async function createAIProviderSetting({
  context,
  input
}: {
  context: ActiveTenantContext;
  input: AIProviderSettingInput;
}): Promise<string> {
  assertCanManageAIProviderSettings(context);
  try {
    return await withSecurityOperationLease({
      actorUserId: context.userId,
      operation: "ai_provider_setting",
      resourceKey: input.provider,
      tenantId: context.tenantId,
      run: () => createAIProviderSettingWithLease({ context, input })
    });
  } catch (error) {
    if (isSecurityOperationLimitError(error)) {
      throw new AIProviderSettingsError(
        "ai_provider_rate_limited",
        "Troppe operazioni AI provider in corso. Riprova tra poco.",
        429
      );
    }
    if (error instanceof AIProviderSettingsError) {
      throw error;
    }
    throw new AIProviderSettingsError(
      "ai_provider_save_failed",
      "Configurazione AI non salvata.",
      500
    );
  }
}

async function createAIProviderSettingWithLease({
  context,
  input
}: {
  context: ActiveTenantContext;
  input: AIProviderSettingInput;
}) {
  if (input.tenant_id !== context.tenantId) {
    throw new AIProviderSettingsError(
      "ai_provider_forbidden",
      "Tenant AI provider non autorizzato.",
      403
    );
  }

  const settingId = randomUUID();
  const secretId = aiProviderSecretId({
    provider: input.provider,
    settingId,
    tenantId: context.tenantId
  });
  const secretRef = gcpSecretRef(secretId);

  try {
    await setAIProviderSecret(secretId, input.api_key, {
      provider: input.provider,
      settingId,
      tenantId: context.tenantId
    });

    const admin = createSupabaseAdminClient();
    const { error } = await admin.from("ai_provider_settings").insert({
      id: settingId,
      tenant_id: context.tenantId,
      provider: input.provider,
      model_id: input.model_id,
      display_name: input.display_name,
      thinking: input.thinking,
      secret_ref: secretRef,
      status: "ready",
      is_default: false,
      last_test_status: null,
      last_tested_at: null,
      created_by: context.userId,
      updated_by: context.userId
    });
    if (error) {
      throw error;
    }
    if (input.is_default) {
      const { error: defaultError } = await admin
        .from("ai_provider_settings")
        .update({ is_default: false, updated_by: context.userId })
        .eq("tenant_id", context.tenantId)
        .eq("is_default", true);
      if (defaultError) {
        throw defaultError;
      }
      const { error: promoteError } = await admin
        .from("ai_provider_settings")
        .update({ is_default: true, updated_by: context.userId })
        .eq("tenant_id", context.tenantId)
        .eq("id", settingId);
      if (promoteError) {
        throw promoteError;
      }
    }
    return settingId;
  } catch (error) {
    await deleteSecretIfPresent(secretId);
    if (error instanceof AIProviderSettingsError) {
      throw error;
    }
    throw new AIProviderSettingsError(
      "ai_provider_save_failed",
      "Configurazione AI non salvata.",
      500
    );
  }
}

async function setAIProviderSecret(
  secretId: string,
  apiKey: string,
  binding: AIProviderSecretBindingInput
) {
  const projectId = getGcpProjectId();
  const parent = `projects/${projectId}`;
  const name = `${parent}/secrets/${secretId}`;

  try {
    await secretClient.createSecret({
      parent,
      secretId,
      secret: {
        labels: aiSecretBindingLabels(binding),
        replication: {
          automatic: {}
        }
      }
    });
  } catch (error) {
    if (!isAlreadyExistsError(error)) {
      throw error;
    }
  }

  await secretClient.addSecretVersion({
    parent: name,
    payload: {
      data: Buffer.from(JSON.stringify({ api_key: apiKey }), "utf8")
    }
  });
}

type AIProviderSecretBindingInput = {
  provider: "openai" | "anthropic";
  settingId: string;
  tenantId: string;
};

function aiSecretBindingFingerprint(binding: AIProviderSecretBindingInput) {
  return createHash("sha256")
    .update(
      [
        binding.tenantId.toLowerCase(),
        binding.settingId.toLowerCase(),
        binding.provider.toLowerCase()
      ].join("\n"),
      "utf8"
    )
    .digest("hex")
    .slice(0, 32);
}

function aiSecretBindingLabels(binding: AIProviderSecretBindingInput) {
  return {
    atlantebi_ai_binding: aiSecretBindingFingerprint(binding),
    atlantebi_ai_provider: binding.provider.toLowerCase(),
    atlantebi_ai_setting: binding.settingId.toLowerCase(),
    atlantebi_tenant: binding.tenantId.toLowerCase()
  };
}

function aiProviderSecretId(binding: AIProviderSecretBindingInput) {
  return `atlantebi-${binding.tenantId}-${binding.settingId}-${binding.provider}-ai-key`;
}

function gcpSecretRef(secretId: string) {
  return `gcp-secret-manager://projects/${getGcpProjectId()}/secrets/${secretId}`;
}

function getGcpProjectId() {
  const projectId = process.env.GCP_PROJECT_ID ?? process.env.GOOGLE_CLOUD_PROJECT;
  if (!projectId) {
    throw new AIProviderSettingsError(
      "ai_provider_secret_manager_unconfigured",
      "GCP_PROJECT_ID richiesto per salvare API key AI.",
      503
    );
  }
  return projectId;
}

function isAlreadyExistsError(error: unknown) {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    error.code === 6
  );
}

async function deleteSecretIfPresent(secretId: string) {
  try {
    await secretClient.deleteSecret({
      name: `projects/${getGcpProjectId()}/secrets/${secretId}`
    });
  } catch {
    // Best effort cleanup only. The DB row is not saved if this path runs.
  }
}

function assertCanManageAIProviderSettings(context: ActiveTenantContext) {
  if (!canManageSemanticLayer(context.role)) {
    throw new AIProviderSettingsError(
      "ai_provider_forbidden",
      "Solo owner e admin possono configurare provider AI.",
      403
    );
  }
}

export function aiProviderSettingsResponse(error: unknown) {
  if (error instanceof AIProviderSettingsError) {
    return {
      code: error.code,
      message: error.message,
      status: error.status
    };
  }
  return {
    code: "ai_provider_internal_error",
    message: "Operazione provider AI fallita.",
    status: 500
  };
}
