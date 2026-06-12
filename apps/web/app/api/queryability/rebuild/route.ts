import { NextResponse } from "next/server";
import { z } from "zod";

import { rebuildQueryabilityGraph } from "../../../../lib/schema-introspection/service";
import { getActiveTenantContextForApi } from "../../../../lib/tenant";

const RequestSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  schema_snapshot_id: z.string().uuid(),
  timeout_ms: z.number().int().min(1000).max(120000).default(30000)
});

export async function POST(request: Request) {
  const parsed = RequestSchema.safeParse(await readJson(request));
  if (!parsed.success) {
    return NextResponse.json(
      { error: "invalid_rebuild_request" },
      { status: 400 }
    );
  }

  const tenant = await getActiveTenantContextForApi(parsed.data.tenant_id);
  if (!tenant.ok) {
    return NextResponse.json({ error: tenant.code }, { status: tenant.status });
  }

  const result = await rebuildQueryabilityGraph({
    context: tenant.context,
    schemaSnapshotId: parsed.data.schema_snapshot_id,
    timeoutMs: parsed.data.timeout_ms
  });
  if (!result.ok) {
    return NextResponse.json(
      { error: result.code, message: result.message },
      { status: result.code.endsWith("_forbidden") ? 403 : 400 }
    );
  }

  return NextResponse.json({
    schema_snapshot_id: result.schemaSnapshotId,
    queryability_graph_id: result.queryabilityGraphId,
    queryability_graph_version: result.queryabilityGraphVersion,
    queryability_graph_status: result.queryabilityGraphStatus,
    semantic_status: result.semanticStatus,
    deduplicated: result.deduplicated
  });
}

async function readJson(request: Request): Promise<unknown> {
  try {
    return await request.json();
  } catch {
    return null;
  }
}
