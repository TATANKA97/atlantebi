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

import { createSupabaseAdminClient } from "../supabase/admin";

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
  userId
}: {
  input: ConnectionInput;
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

    const { error } = await createSupabaseAdminClient().rpc(
      "save_connection_test_result",
      {
        actor_user_id: userId,
        connection_payload: connectionPersistencePayload({
          connectionId,
          expectedSecretRef: null,
          input,
          secretRef: savedSecretRef,
          test
        })
      }
    );

    if (error) {
      const persisted = await readExistingConnection(input.tenant_id, connectionId);
      if (
        persisted &&
        connectionMatchesInput(persisted, input) &&
        persisted.secret_ref === savedSecretRef
      ) {
        if (test.status !== "ok") {
          await deleteSecretIfPresent(secretId);
        }
        return { ok: true, connectionId, testStatus: test.status };
      }
      await deleteSecretIfPresent(secretId);
      return {
        ok: false,
        code: "connection_save_failed",
        message: "Connection metadata could not be saved."
      };
    }

    if (test.status !== "ok") {
      await deleteSecretIfPresent(secretId);
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

type ExistingConnection = {
  id: string;
  tenant_id: string;
  name: string;
  engine: "sqlserver";
  network_mode: "public_allowlist";
  host: string;
  port: number;
  database_name: string;
  username: string;
  tls_required: boolean;
  trust_server_certificate: boolean;
  tls_server_name: string | null;
  secret_ref: string | null;
};

async function readExistingConnection(
  tenantId: string,
  connectionId: string
) {
  const { data, error } = await createSupabaseAdminClient()
    .from("db_connections")
    .select(
      "id,tenant_id,name,engine,network_mode,host,port,database_name,username,tls_required,trust_server_certificate,tls_server_name,secret_ref"
    )
    .eq("tenant_id", tenantId)
    .eq("id", connectionId)
    .single();

  if (error || !data) {
    return null;
  }

  return data as ExistingConnection;
}

function connectionPersistencePayload({
  connectionId,
  expectedSecretRef,
  input,
  secretRef,
  test
}: {
  connectionId: string;
  expectedSecretRef: string | null;
  input: ConnectionInput | ConnectionUpdateInput;
  secretRef: string | null;
  test: Awaited<ReturnType<typeof runConnectionTest>>;
}) {
  return {
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
    expected_secret_ref: expectedSecretRef,
    secret_ref: secretRef,
    status: test.status === "ok" ? "ready" : "failed",
    last_test_status: test.status,
    last_test_error: test.status === "ok" ? null : sanitizeTestError(test),
    last_tested_at: test.checked_at
  };
}

export function connectionIdentityChanged(
  existing: ExistingConnection,
  input: ConnectionUpdateInput
) {
  return (
    existing.host !== input.host ||
    existing.port !== input.port ||
    existing.database_name !== input.database_name ||
    existing.username !== input.username ||
    existing.tls_server_name !== (input.tls_server_name ?? null)
  );
}

function connectionMatchesInput(
  existing: ExistingConnection,
  input: ConnectionInput | ConnectionUpdateInput
) {
  return (
    existing.name === input.name &&
    existing.engine === input.engine &&
    existing.network_mode === input.network_mode &&
    existing.host === input.host &&
    existing.port === input.port &&
    existing.database_name === input.database_name &&
    existing.username === input.username &&
    existing.tls_required === input.tls_required &&
    existing.trust_server_certificate === input.trust_server_certificate &&
    existing.tls_server_name === (input.tls_server_name ?? null)
  );
}

export function secretRefAfterTest({
  existingSecretRef,
  candidateSecretRef,
  identityChanged,
  testStatus
}: {
  existingSecretRef: string | null;
  candidateSecretRef: string;
  identityChanged: boolean;
  testStatus: ConnectionTestStatus;
}) {
  if (testStatus === "ok") {
    return candidateSecretRef;
  }
  return identityChanged ? null : existingSecretRef;
}

export function shouldDeletePreviousSecret({
  identityChanged,
  passwordProvided,
  testStatus
}: {
  identityChanged: boolean;
  passwordProvided: boolean;
  testStatus: ConnectionTestStatus;
}) {
  return identityChanged || (passwordProvided && testStatus === "ok");
}

async function persistUpdatedConnection({
  input,
  userId,
  expectedSecretRef,
  secretRef,
  test
}: {
  input: ConnectionUpdateInput;
  userId: string;
  expectedSecretRef: string | null;
  secretRef: string | null;
  test: Awaited<ReturnType<typeof runConnectionTest>>;
}) {
  return createSupabaseAdminClient().rpc("save_connection_test_result", {
    actor_user_id: userId,
    connection_payload: connectionPersistencePayload({
      connectionId: input.connection_id,
      expectedSecretRef,
      input,
      secretRef,
      test
    })
  });
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
  userId
}: {
  input: ConnectionUpdateInput;
  userId: string;
}): Promise<CreateConnectionResult> {
  const stagedSecretId = input.password
    ? `atlantebi-${input.tenant_id}-${input.connection_id}-${randomUUID()}-db-password`
    : null;

  try {
    const existing = await readExistingConnection(
      input.tenant_id,
      input.connection_id
    );
    if (!existing) {
      return {
        ok: false,
        code: "connection_not_found",
        message: "Connection metadata could not be found."
      };
    }

    const identityChanged = connectionIdentityChanged(existing, input);
    if (!input.password && (identityChanged || !existing.secret_ref)) {
      const passwordRequiredTest = {
        status: "engine_error" as const,
        message: "A new password is required before this connection can be ready.",
        checked_at: new Date().toISOString(),
        duration_ms: 0,
        sanitized_error:
          "A new password is required before this connection can be ready."
      };
      const { error } = await persistUpdatedConnection({
        input,
        userId,
        expectedSecretRef: existing.secret_ref,
        secretRef: null,
        test: passwordRequiredTest
      });
      if (error) {
        return {
          ok: false,
          code: "connection_save_failed",
          message: "Connection metadata could not be saved."
        };
      }
      if (identityChanged) {
        await deleteSecretRefIfPresent(existing.secret_ref);
      }
      return {
        ok: true,
        connectionId: input.connection_id,
        testStatus: "engine_error"
      };
    }

    if (input.password && stagedSecretId) {
      await setDatabasePasswordSecret(stagedSecretId, input.password);
    }
    const candidateSecretRef = stagedSecretId
      ? gcpSecretRef(stagedSecretId)
      : existing.secret_ref;
    if (!candidateSecretRef) {
      return {
        ok: false,
        code: "connection_password_required",
        message: "A password is required to test this connection."
      };
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
      secret_ref: candidateSecretRef,
      status: "draft"
    });
    const test = await runConnectionTest(connection, input.timeout_ms);
    const persistedSecretRef = secretRefAfterTest({
      existingSecretRef: existing.secret_ref,
      candidateSecretRef,
      identityChanged,
      testStatus: test.status
    });
    const deletePreviousSecret = shouldDeletePreviousSecret({
      identityChanged,
      passwordProvided: Boolean(input.password),
      testStatus: test.status
    });
    const { error } = await persistUpdatedConnection({
      input,
      userId,
      expectedSecretRef: existing.secret_ref,
      secretRef: persistedSecretRef,
      test
    });

    if (error) {
      const persisted = await readExistingConnection(
        input.tenant_id,
        input.connection_id
      );
      if (
        persisted &&
        connectionMatchesInput(persisted, input) &&
        persisted.secret_ref === persistedSecretRef
      ) {
        if (deletePreviousSecret) {
          await deleteSecretRefIfPresent(existing.secret_ref);
        }
        if (test.status !== "ok" && stagedSecretId) {
          await deleteSecretIfPresent(stagedSecretId);
        }
        return {
          ok: true,
          connectionId: input.connection_id,
          testStatus: test.status
        };
      }
      if (stagedSecretId) {
        await deleteSecretIfPresent(stagedSecretId);
      }
      return {
        ok: false,
        code: "connection_save_failed",
        message: "Connection metadata could not be saved."
      };
    }

    if (deletePreviousSecret) {
      await deleteSecretRefIfPresent(existing.secret_ref);
    }
    if (test.status !== "ok" && stagedSecretId) {
      await deleteSecretIfPresent(stagedSecretId);
    }

    return { ok: true, connectionId: input.connection_id, testStatus: test.status };
  } catch {
    if (stagedSecretId) {
      await deleteSecretIfPresent(stagedSecretId);
    }
    return {
      ok: false,
      code: "connection_update_failed",
      message: "Connection could not be updated."
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

async function deleteSecretRefIfPresent(secretRef: string | null) {
  if (!secretRef) {
    return;
  }
  const match = /^gcp-secret-manager:\/\/projects\/[^/]+\/secrets\/([^/]+)/.exec(
    secretRef
  );
  if (match?.[1]) {
    await deleteSecretIfPresent(match[1]);
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
