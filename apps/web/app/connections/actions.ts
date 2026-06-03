"use server";

import { redirect } from "next/navigation";

import {
  ConnectionFormInputSchema,
  createAndTestConnection
} from "../../lib/connections/service";
import {
  assertCanManageConnections,
  getActiveTenantContext
} from "../../lib/tenant";

export async function createConnection(formData: FormData) {
  const tenantId = formData.get("tenant_id")?.toString();
  const context = await getActiveTenantContext(tenantId);
  assertCanManageConnections(context.role);

  const parsed = ConnectionFormInputSchema.safeParse({
    tenant_id: context.tenantId,
    name: formData.get("name"),
    engine: formData.get("engine"),
    network_mode: formData.get("network_mode"),
    host: formData.get("host"),
    port: formData.get("port"),
    database_name: formData.get("database_name"),
    username: formData.get("username"),
    password: formData.get("password"),
    tls_required: formData.get("tls_required") === "on",
    trust_server_certificate: formData.get("trust_server_certificate") === "on",
    tls_server_name: formData.get("tls_server_name"),
    timeout_ms: formData.get("timeout_ms") ?? "30000"
  });

  if (!parsed.success) {
    redirect("/connections/new?message=invalid_connection");
  }

  const result = await createAndTestConnection({
    input: parsed.data,
    supabase: context.supabase,
    userId: context.userId
  });

  if (!result.ok) {
    redirect(`/connections/new?message=${result.code}`);
  }

  redirect(`/connections?created=${result.connectionId}`);
}
