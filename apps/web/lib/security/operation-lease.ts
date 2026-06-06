import "server-only";

import { createSupabaseAdminClient } from "../supabase/admin";

export type SecurityOperation =
  | "connection_test"
  | "schema_introspection";

export class SecurityOperationLimitError extends Error {
  constructor() {
    super("Security operation rate or concurrency limit exceeded.");
    this.name = "SecurityOperationLimitError";
  }
}

export async function withSecurityOperationLease<T>({
  actorUserId,
  operation,
  resourceKey,
  run,
  tenantId
}: {
  actorUserId: string;
  operation: SecurityOperation;
  resourceKey: string;
  run: () => Promise<T>;
  tenantId: string;
}): Promise<T> {
  const admin = createSupabaseAdminClient();
  const { data, error } = await admin.rpc(
    "acquire_security_operation_lease",
    {
      target_actor_user_id: actorUserId,
      target_operation: operation,
      target_resource_key: resourceKey,
      target_tenant_id: tenantId
    }
  );

  if (error || typeof data !== "string") {
    if (
      error?.message.includes("rate limit") ||
      error?.message.includes("concurrency limit") ||
      error?.message.includes("already busy")
    ) {
      throw new SecurityOperationLimitError();
    }
    throw new Error("Security operation lease could not be acquired.");
  }

  try {
    return await run();
  } finally {
    await admin.rpc("release_security_operation_lease", {
      target_lease_id: data
    });
  }
}

export function isSecurityOperationLimitError(
  error: unknown
): error is SecurityOperationLimitError {
  return error instanceof SecurityOperationLimitError;
}
