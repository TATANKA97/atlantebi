import { NextResponse } from "next/server";

import {
  ConnectionInputSchema,
  createAndTestConnection
} from "../../../lib/connections/service";
import {
  canManageConnections,
  getActiveTenantContextForApi
} from "../../../lib/tenant";

export async function GET() {
  const tenant = await getActiveTenantContextForApi();
  if (!tenant.ok) {
    return NextResponse.json({ error: tenant.code }, { status: tenant.status });
  }

  const { supabase, tenantId } = tenant.context;
  const { data, error } = await supabase
    .from("db_connection_summaries")
    .select(
      "id,name,engine,network_mode,host,port,database_name,username,tls_required,tls_server_name,trust_server_certificate,status,last_test_status,last_test_error,last_tested_at"
    )
    .eq("tenant_id", tenantId)
    .order("created_at", { ascending: false })
    .limit(50);

  if (error) {
    return NextResponse.json({ error: "connections_read_failed" }, { status: 500 });
  }

  return NextResponse.json({ connections: data ?? [] });
}

export async function POST(request: Request) {
  const body = await readJson(request);

  if (!body.ok) {
    return NextResponse.json({ error: "invalid_connection" }, { status: 400 });
  }

  const parsed = ConnectionInputSchema.safeParse(body.value);
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid_connection" }, { status: 400 });
  }

  const tenant = await getActiveTenantContextForApi(parsed.data.tenant_id);
  if (!tenant.ok) {
    return NextResponse.json({ error: tenant.code }, { status: tenant.status });
  }
  if (!canManageConnections(tenant.context.role)) {
    return NextResponse.json({ error: "connection_forbidden" }, { status: 403 });
  }

  const result = await createAndTestConnection({
    input: { ...parsed.data, tenant_id: tenant.context.tenantId },
    userId: tenant.context.userId
  });

  if (!result.ok) {
    return NextResponse.json(
      { error: result.code, message: result.message },
      { status: 400 }
    );
  }

  return NextResponse.json(
    {
      connection_id: result.connectionId,
      status: result.testStatus === "ok" ? "ready" : "failed",
      test_status: result.testStatus
    },
    { status: 201 }
  );
}

async function readJson(
  request: Request
): Promise<{ ok: true; value: unknown } | { ok: false }> {
  try {
    return { ok: true, value: await request.json() };
  } catch {
    return { ok: false };
  }
}
