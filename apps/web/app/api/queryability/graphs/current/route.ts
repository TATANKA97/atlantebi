import { QueryabilityGraphArtifactSchema } from "@atlantebi/contracts";
import { NextResponse } from "next/server";
import { z } from "zod";

import { createSupabaseAdminClient } from "../../../../../lib/supabase/admin";
import {
  canManageConnections,
  getActiveTenantContextForApi
} from "../../../../../lib/tenant";

const QuerySchema = z.strictObject({
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid()
});

export async function GET(request: Request) {
  const parsed = QuerySchema.safeParse(
    Object.fromEntries(new URL(request.url).searchParams)
  );
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid_graph_request" }, { status: 400 });
  }

  const tenant = await getActiveTenantContextForApi(parsed.data.tenant_id);
  if (!tenant.ok) {
    return NextResponse.json({ error: tenant.code }, { status: tenant.status });
  }
  if (!canManageConnections(tenant.context.role)) {
    return NextResponse.json({ error: "graph_forbidden" }, { status: 403 });
  }

  const { data, error } = await createSupabaseAdminClient()
    .from("queryability_graph_versions")
    .select("id,version,created_at,graph")
    .eq("tenant_id", tenant.context.tenantId)
    .eq("connection_id", parsed.data.connection_id)
    .order("version", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) {
    return NextResponse.json({ error: "graph_read_failed" }, { status: 500 });
  }
  if (!data) {
    return NextResponse.json({ error: "graph_not_found" }, { status: 404 });
  }

  return NextResponse.json({
    graph_version_id: data.id,
    graph_version: data.version,
    created_at: data.created_at,
    graph: QueryabilityGraphArtifactSchema.parse(data.graph)
  });
}
