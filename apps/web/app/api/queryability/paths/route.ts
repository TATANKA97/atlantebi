import {
  QueryabilityGraphArtifactSchema,
  QueryabilityPathResultSchema
} from "@atlantebi/contracts";
import { GoogleAuth } from "google-auth-library";
import { NextResponse } from "next/server";
import { z } from "zod";

import { createSupabaseAdminClient } from "../../../../lib/supabase/admin";
import {
  canManageConnections,
  getActiveTenantContextForApi
} from "../../../../lib/tenant";

const RequestSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  graph_id: z.string().uuid(),
  from_node_key: z.string().regex(/^[0-9a-f]{64}$/),
  to_node_key: z.string().regex(/^[0-9a-f]{64}$/)
});

export async function POST(request: Request) {
  const parsed = RequestSchema.safeParse(await readJson(request));
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid_path_request" }, { status: 400 });
  }

  const tenant = await getActiveTenantContextForApi(parsed.data.tenant_id);
  if (!tenant.ok) {
    return NextResponse.json({ error: tenant.code }, { status: tenant.status });
  }
  if (!canManageConnections(tenant.context.role)) {
    return NextResponse.json({ error: "path_forbidden" }, { status: 403 });
  }

  const admin = createSupabaseAdminClient();
  const { data, error } = await admin
    .from("queryability_graph_versions")
    .select("graph")
    .eq("tenant_id", tenant.context.tenantId)
    .eq("id", parsed.data.graph_id)
    .single();
  if (error || !data) {
    return NextResponse.json({ error: "graph_not_found" }, { status: 404 });
  }

  const graph = QueryabilityGraphArtifactSchema.parse(data.graph);
  const result = await runPathSearch({
    fromNodeKey: parsed.data.from_node_key,
    graph,
    toNodeKey: parsed.data.to_node_key
  });
  return NextResponse.json(result);
}

async function runPathSearch({
  fromNodeKey,
  graph,
  toNodeKey
}: {
  fromNodeKey: string;
  graph: z.infer<typeof QueryabilityGraphArtifactSchema>;
  toNodeKey: string;
}) {
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
  const url = new URL("/queryability/paths", queryEngineUrl).toString();
  const body = JSON.stringify({
    graph,
    from_node_key: fromNodeKey,
    to_node_key: toNodeKey,
    max_hops: 4
  });

  if (process.env.QUERY_ENGINE_AUTH_MODE === "google_id_token") {
    const client = await new GoogleAuth().getIdTokenClient(queryEngineUrl);
    const response = await client.request({
      data: body,
      headers,
      method: "POST",
      timeout: 30000,
      url,
      validateStatus: () => true
    });
    if (response.status < 200 || response.status >= 300) {
      throw new Error("Queryability path search failed.");
    }
    return QueryabilityPathResultSchema.parse(response.data);
  }

  const response = await fetch(url, {
    body,
    headers,
    method: "POST",
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) {
    throw new Error("Queryability path search failed.");
  }
  return QueryabilityPathResultSchema.parse(await response.json());
}

async function readJson(request: Request): Promise<unknown> {
  try {
    return await request.json();
  } catch {
    return null;
  }
}
