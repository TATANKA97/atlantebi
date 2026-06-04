import { NextResponse } from "next/server";
import { z } from "zod";

import { introspectConnection } from "../../../../lib/schema-introspection/service";
import { getActiveTenantContextForApi } from "../../../../lib/tenant";

const IntrospectionRequestSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid(),
  timeout_ms: z.number().int().min(1000).max(120000).default(120000)
});

export async function POST(request: Request) {
  const body = await readJson(request);

  if (!body.ok) {
    return NextResponse.json({ error: "invalid_introspection" }, { status: 400 });
  }

  const parsed = IntrospectionRequestSchema.safeParse(body.value);
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid_introspection" }, { status: 400 });
  }

  const tenant = await getActiveTenantContextForApi(parsed.data.tenant_id);
  if (!tenant.ok) {
    return NextResponse.json({ error: tenant.code }, { status: tenant.status });
  }

  const result = await introspectConnection({
    connectionId: parsed.data.connection_id,
    context: tenant.context,
    timeoutMs: parsed.data.timeout_ms
  });

  if (!result.ok) {
    return NextResponse.json(
      { error: result.code, message: result.message },
      { status: 400 }
    );
  }

  return NextResponse.json({
    schema_snapshot_id: result.schemaSnapshotId,
    semantic_version_id: result.semanticVersionId,
    table_count: result.tableCount,
    column_count: result.columnCount
  });
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
