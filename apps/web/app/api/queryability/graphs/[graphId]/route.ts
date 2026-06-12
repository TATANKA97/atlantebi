import { QueryabilityGraphArtifactSchema } from "@atlantebi/contracts";
import { NextResponse } from "next/server";
import { z } from "zod";

import { createSupabaseAdminClient } from "../../../../../lib/supabase/admin";
import {
  canManageConnections,
  getActiveTenantContextForApi
} from "../../../../../lib/tenant";

const TenantSchema = z.string().uuid();
const GraphIdSchema = z.string().uuid();

export async function GET(
  request: Request,
  { params }: { params: Promise<{ graphId: string }> }
) {
  const graphId = GraphIdSchema.safeParse((await params).graphId);
  const tenantId = TenantSchema.safeParse(
    new URL(request.url).searchParams.get("tenant_id")
  );
  if (!graphId.success || !tenantId.success) {
    return NextResponse.json({ error: "invalid_graph_request" }, { status: 400 });
  }

  const tenant = await getActiveTenantContextForApi(tenantId.data);
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
    .eq("id", graphId.data)
    .single();
  if (error || !data) {
    return NextResponse.json({ error: "graph_not_found" }, { status: 404 });
  }

  return NextResponse.json({
    graph_version_id: data.id,
    graph_version: data.version,
    created_at: data.created_at,
    graph: QueryabilityGraphArtifactSchema.parse(data.graph)
  });
}
