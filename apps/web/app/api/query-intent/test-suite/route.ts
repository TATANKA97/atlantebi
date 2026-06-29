import { NextResponse } from "next/server";
import { z } from "zod";

import {
  readJson,
  semanticMutationRequestError
} from "../../../../lib/semantic-layer/api";
import {
  QueryIntentServiceError,
  runQueryIntentTestSuite
} from "../../../../lib/query-intent/service";
import {
  canManageSemanticLayer,
  getActiveTenantContextForApi,
  type ActiveTenantContext
} from "../../../../lib/tenant";

const RequestSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid(),
  suite_id: z.enum(["adventureworks_v1"]).default("adventureworks_v1"),
  ai_mode: z.enum(["disabled", "advisory"]).default("disabled")
});

export async function POST(request: Request) {
  const requestError = semanticMutationRequestError(request);
  if (requestError) {
    return requestError;
  }

  const parsed = RequestSchema.safeParse(await readJson(request));
  if (!parsed.success) {
    return json({ error: "invalid_query_intent_test_suite_request" }, 400);
  }

  const tenant = await getActiveTenantContextForApi(parsed.data.tenant_id);
  if (!tenant.ok) {
    return json({ error: tenant.code }, tenant.status);
  }
  if (!canManageSemanticLayer(tenant.context.role)) {
    return json({ error: "query_intent_test_suite_forbidden" }, 403);
  }

  const connectionName = await readConnectionName({
    connectionId: parsed.data.connection_id,
    context: tenant.context
  });
  if (!connectionName) {
    return json({ error: "connection_not_found" }, 404);
  }

  try {
    const report = await runQueryIntentTestSuite({
      aiMode: parsed.data.ai_mode,
      connectionId: parsed.data.connection_id,
      connectionName,
      context: tenant.context,
      suiteId: parsed.data.suite_id
    });
    return json(report, 200);
  } catch (error) {
    if (error instanceof QueryIntentServiceError) {
      return json(
        { error: error.code, message: error.message },
        error.status
      );
    }
    return json(
      {
        error: "query_intent_test_suite_failed",
        message: "Query Intent test suite failed."
      },
      500
    );
  }
}

async function readConnectionName({
  connectionId,
  context
}: {
  connectionId: string;
  context: ActiveTenantContext;
}) {
  const { data, error } = await context.supabase
    .from("db_connection_summaries")
    .select("name,database_name")
    .eq("tenant_id", context.tenantId)
    .eq("id", connectionId)
    .maybeSingle();
  if (error || !data) {
    return null;
  }
  const row = data as { database_name: string; name: string };
  return `${row.name} - ${row.database_name}`;
}

function json(payload: Record<string, unknown>, status: number) {
  return NextResponse.json(payload, {
    status,
    headers: { "cache-control": "private, no-store" }
  });
}
