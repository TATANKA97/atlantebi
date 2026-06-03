import "server-only";

import { SecretManagerServiceClient } from "@google-cloud/secret-manager";
import {
  ConnectionMetadataSchema,
  ConnectionTestResponseSchema,
  DatabaseCredentialsSchema
} from "@atlantebi/contracts";
import { GoogleAuth } from "google-auth-library";
import { randomUUID } from "node:crypto";
import { z } from "zod";

import type { createSupabaseServerClient } from "../supabase/server";

type SupabaseClient = Awaited<ReturnType<typeof createSupabaseServerClient>>;
type ConnectionTestStatus = "ok" | "failed" | "engine_error";

const BooleanInputSchema = z
  .union([z.boolean(), z.enum(["on", "true", "false"])])
  .transform((value) => value === true || value === "on" || value === "true");

export const ConnectionInputSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  name: z.string().trim().min(2).max(160),
  engine: z.literal("sqlserver"),
  network_mode: z.literal("public_allowlist"),
  host: z.string().trim().min(1).max(255),
  port: z.number().int().min(1).max(65535),
  database_name: z.string().trim().min(1).max(255),
  username: z.string().trim().min(1).max(255),
  password: z.string().min(1),
  tls_required: z.boolean(),
  trust_server_certificate: z.boolean().default(false),
  tls_server_name: z
    .string()
    .trim()
    .min(1)
    .max(255)
    .optional()
    .or(z.literal("").transform(() => undefined)),
  timeout_ms: z.number().int().min(1000).max(120000).default(30000)
});

export type ConnectionInput = z.infer<typeof ConnectionInputSchema>;

export const ConnectionFormInputSchema = ConnectionInputSchema.extend({
  port: z.coerce.number().int().min(1).max(65535),
  tls_required: BooleanInputSchema,
  trust_server_certificate: BooleanInputSchema.default(false),
  timeout_ms: z.coerce.number().int().min(1000).max(120000).default(30000)
});

export type CreateConnectionResult =
  | {
      ok: true;
      connectionId: string;
      testStatus: ConnectionTestStatus;
    }
  | { ok: false; code: string; message: string };

const secretClient = new SecretManagerServiceClient();

export async function createAndTestConnection({
  input,
  supabase,
  userId
}: {
  input: ConnectionInput;
  supabase: NonNullable<SupabaseClient>;
  userId: string;
}): Promise<CreateConnectionResult> {
  const connectionId = randomUUID();
  const secretId = `atlantebi-${input.tenant_id}-${connectionId}-db-password`;
  const secretRef = gcpSecretRef(secretId);

  try {
    await setDatabasePasswordSecret(secretId, input.password);

    const connection = ConnectionMetadataSchema.parse({
      tenant_id: input.tenant_id,
      connection_id: connectionId,
      name: input.name,
      engine: input.engine,
      network_mode: input.network_mode,
      host: input.host,
      port: input.port,
      database_name: input.database_name,
      username: input.username,
      tls_required: input.tls_required,
      trust_server_certificate: input.trust_server_certificate,
      tls_server_name: input.tls_server_name ?? null,
      secret_ref: secretRef,
      status: "draft"
    });
    const test = await runConnectionTest(connection, input.timeout_ms);
    const savedSecretRef = test.status === "ok" ? secretRef : null;

    if (test.status !== "ok") {
      await deleteSecretIfPresent(secretId);
    }

    const { error } = await supabase.from("db_connections").insert({
      id: connectionId,
      tenant_id: input.tenant_id,
      name: input.name,
      engine: input.engine,
      network_mode: input.network_mode,
      host: input.host,
      port: input.port,
      database_name: input.database_name,
      username: input.username,
      tls_required: input.tls_required,
      tls_server_name: input.tls_server_name ?? null,
      trust_server_certificate: input.trust_server_certificate,
      secret_ref: savedSecretRef,
      status: test.status === "ok" ? "ready" : "failed",
      last_test_status: test.status,
      last_test_error: test.status === "ok" ? null : sanitizeTestError(test),
      last_tested_at: test.checked_at,
      created_by: userId
    });

    if (error) {
      await deleteSecretIfPresent(secretId);
      return {
        ok: false,
        code: "connection_save_failed",
        message: "Connection metadata could not be saved."
      };
    }

    return { ok: true, connectionId, testStatus: test.status };
  } catch {
    await deleteSecretIfPresent(secretId);
    return {
      ok: false,
      code: "connection_create_failed",
      message: "Connection could not be created."
    };
  }
}

export const ConnectionUpdateInputSchema = ConnectionInputSchema.extend({
  connection_id: z.string().uuid(),
  password: z.string().optional()
});

export const ConnectionUpdateFormInputSchema = ConnectionFormInputSchema.extend({
  connection_id: z.string().uuid(),
  password: z
    .string()
    .transform((value) => (value.length === 0 ? undefined : value))
    .optional()
});

export type ConnectionUpdateInput = z.infer<typeof ConnectionUpdateInputSchema>;

export async function updateAndTestConnection({
  input,
  supabase
}: {
  input: ConnectionUpdateInput;
  supabase: NonNullable<SupabaseClient>;
}): Promise<CreateConnectionResult> {
  const secretId = `atlantebi-${input.tenant_id}-${input.connection_id}-db-password`;
  const secretRef = gcpSecretRef(secretId);
  const testSecretId = input.password
    ? `atlantebi-${input.tenant_id}-${input.connection_id}-${randomUUID()}-db-password-test`
    : secretId;
  const testSecretRef = gcpSecretRef(testSecretId);

  try {
    const { data: existing, error: existingError } = await supabase
      .from("db_connection_summaries")
      .select("id,status")
      .eq("tenant_id", input.tenant_id)
      .eq("id", input.connection_id)
      .single();

    if (existingError || !existing) {
      return {
        ok: false,
        code: "connection_not_found",
        message: "Connection metadata could not be found."
      };
    }

    if (input.password) {
      await setDatabasePasswordSecret(testSecretId, input.password);
    }

    const connection = ConnectionMetadataSchema.parse({
      tenant_id: input.tenant_id,
      connection_id: input.connection_id,
      name: input.name,
      engine: input.engine,
      network_mode: input.network_mode,
      host: input.host,
      port: input.port,
      database_name: input.database_name,
      username: input.username,
      tls_required: input.tls_required,
      trust_server_certificate: input.trust_server_certificate,
      tls_server_name: input.tls_server_name ?? null,
      secret_ref: testSecretRef,
      status: "draft"
    });
    const test = await runConnectionTest(connection, input.timeout_ms);
    const updatePayload: Record<string, unknown> = {
      name: input.name,
      engine: input.engine,
      network_mode: input.network_mode,
      host: input.host,
      port: input.port,
      database_name: input.database_name,
      username: input.username,
      tls_required: input.tls_required,
      tls_server_name: input.tls_server_name ?? null,
      trust_server_certificate: input.trust_server_certificate,
      status: test.status === "ok" ? "ready" : "failed",
      last_test_status: test.status,
      last_test_error: test.status === "ok" ? null : sanitizeTestError(test),
      last_tested_at: test.checked_at
    };

    if (test.status === "ok") {
      if (input.password) {
        await setDatabasePasswordSecret(secretId, input.password);
      }
      updatePayload.secret_ref = secretRef;
    }

    const { error } = await supabase
      .from("db_connections")
      .update(updatePayload)
      .eq("tenant_id", input.tenant_id)
      .eq("id", input.connection_id);

    if (error) {
      return {
        ok: false,
        code: "connection_save_failed",
        message: "Connection metadata could not be saved."
      };
    }

    return { ok: true, connectionId: input.connection_id, testStatus: test.status };
  } catch {
    return {
      ok: false,
      code: "connection_update_failed",
      message: "Connection could not be updated."
    };
  } finally {
    if (input.password) {
      await deleteSecretIfPresent(testSecretId);
    }
  }
}

export async function testConnectionWithoutSaving(
  input: ConnectionInput
): Promise<CreateConnectionResult> {
  const connectionId = randomUUID();
  const secretId = `atlantebi-${input.tenant_id}-${connectionId}-db-password-test`;
  const secretRef = gcpSecretRef(secretId);

  try {
    await setDatabasePasswordSecret(secretId, input.password);
    const connection = ConnectionMetadataSchema.parse({
      tenant_id: input.tenant_id,
      connection_id: connectionId,
      name: input.name,
      engine: input.engine,
      network_mode: input.network_mode,
      host: input.host,
      port: input.port,
      database_name: input.database_name,
      username: input.username,
      tls_required: input.tls_required,
      trust_server_certificate: input.trust_server_certificate,
      tls_server_name: input.tls_server_name ?? null,
      secret_ref: secretRef,
      status: "draft"
    });
    const test = await testConnectionViaQueryEngine(connection, input.timeout_ms);

    if (test.status !== "ok") {
      return {
        ok: false,
        code: "connection_test_failed",
        message: test.sanitized_error ?? test.message
      };
    }

    return { ok: true, connectionId, testStatus: "ok" };
  } catch {
    return {
      ok: false,
      code: "connection_test_failed",
      message: "Connection test could not run."
    };
  } finally {
    await deleteSecretIfPresent(secretId);
  }
}

async function setDatabasePasswordSecret(secretId: string, password: string) {
  const projectId = getGcpProjectId();
  const parent = `projects/${projectId}`;
  const name = `${parent}/secrets/${secretId}`;
  const payload = DatabaseCredentialsSchema.parse({ password });

  try {
    await secretClient.createSecret({
      parent,
      secretId,
      secret: {
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
      data: Buffer.from(JSON.stringify(payload), "utf8")
    }
  });
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
    // Cleanup is best effort: failed connection metadata is not saved.
  }
}

function gcpSecretRef(secretId: string) {
  return `gcp-secret-manager://projects/${getGcpProjectId()}/secrets/${secretId}`;
}

function getGcpProjectId() {
  const projectId = process.env.GCP_PROJECT_ID ?? process.env.GOOGLE_CLOUD_PROJECT;

  if (!projectId) {
    throw new Error("GCP_PROJECT_ID is required.");
  }

  return projectId;
}

async function testConnectionViaQueryEngine(
  connection: z.infer<typeof ConnectionMetadataSchema>,
  timeoutMs: number
) {
  const queryEngineUrl = process.env.QUERY_ENGINE_URL;

  if (!queryEngineUrl) {
    throw new Error("QUERY_ENGINE_URL is required.");
  }

  const headers: Record<string, string> = {
    "content-type": "application/json"
  };
  const token = process.env.QUERY_ENGINE_API_TOKEN;
  if (token) {
    headers["x-atlante-query-engine-token"] = token;
  }
  const url = new URL("/connections/test", queryEngineUrl).toString();
  const body = JSON.stringify({ connection, timeout_ms: timeoutMs });

  if (process.env.QUERY_ENGINE_AUTH_MODE === "google_id_token") {
    const client = await new GoogleAuth().getIdTokenClient(queryEngineUrl);
    const response = await client.request({
      data: body,
      headers,
      method: "POST",
      timeout: timeoutMs + 5000,
      url,
      validateStatus: () => true
    });

    if (response.status < 200 || response.status >= 300) {
      throw new Error("Query engine connection test failed.");
    }

    return ConnectionTestResponseSchema.parse(response.data);
  }

  const response = await fetch(url, {
    body,
    headers,
    method: "POST",
    signal: AbortSignal.timeout(timeoutMs + 5000)
  });

  if (!response.ok) {
    throw new Error("Query engine connection test failed.");
  }

  return ConnectionTestResponseSchema.parse(await response.json());
}

async function runConnectionTest(
  connection: z.infer<typeof ConnectionMetadataSchema>,
  timeoutMs: number
) {
  try {
    return await testConnectionViaQueryEngine(connection, timeoutMs);
  } catch {
    return {
      status: "engine_error" as const,
      message: "Connection test could not run.",
      checked_at: new Date().toISOString(),
      duration_ms: 0,
      sanitized_error: "Connection test could not run."
    };
  }
}

function sanitizeTestError(test: {
  sanitized_error?: string | undefined;
  message: string;
}) {
  return (test.sanitized_error ?? test.message).slice(0, 500);
}
