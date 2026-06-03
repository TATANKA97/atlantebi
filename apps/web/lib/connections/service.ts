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
  | { ok: true; connectionId: string }
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
    await createDatabasePasswordSecret(secretId, input.password);

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
      await deleteSecretIfPresent(secretId);
      return {
        ok: false,
        code: "connection_test_failed",
        message: test.sanitized_error ?? test.message
      };
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
      secret_ref: secretRef,
      status: "ready",
      last_test_status: "ok",
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

    return { ok: true, connectionId };
  } catch {
    await deleteSecretIfPresent(secretId);
    return {
      ok: false,
      code: "connection_create_failed",
      message: "Connection could not be created."
    };
  }
}

export async function testConnectionWithoutSaving(
  input: ConnectionInput
): Promise<CreateConnectionResult> {
  const connectionId = randomUUID();
  const secretId = `atlantebi-${input.tenant_id}-${connectionId}-db-password-test`;
  const secretRef = gcpSecretRef(secretId);

  try {
    await createDatabasePasswordSecret(secretId, input.password);
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

    return { ok: true, connectionId };
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

async function createDatabasePasswordSecret(secretId: string, password: string) {
  const projectId = getGcpProjectId();
  const parent = `projects/${projectId}`;
  const name = `${parent}/secrets/${secretId}`;
  const payload = DatabaseCredentialsSchema.parse({ password });

  await secretClient.createSecret({
    parent,
    secretId,
    secret: {
      replication: {
        automatic: {}
      }
    }
  });
  await secretClient.addSecretVersion({
    parent: name,
    payload: {
      data: Buffer.from(JSON.stringify(payload), "utf8")
    }
  });
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
