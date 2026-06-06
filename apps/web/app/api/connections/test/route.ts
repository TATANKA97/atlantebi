import { NextResponse } from "next/server";

import {
  ConnectionInputSchema,
  testConnectionWithoutSaving
} from "../../../../lib/connections/service";
import {
  canManageConnections,
  getActiveTenantContextForApi
} from "../../../../lib/tenant";

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

  const result = await testConnectionWithoutSaving(
    {
      ...parsed.data,
      tenant_id: tenant.context.tenantId
    },
    tenant.context.userId
  );

  if (!result.ok) {
    return NextResponse.json(
      { error: result.code, message: result.message },
      { status: result.code === "connection_rate_limited" ? 429 : 400 }
    );
  }

  return NextResponse.json({ ok: true });
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
