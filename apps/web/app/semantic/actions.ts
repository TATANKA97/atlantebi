"use server";

import { redirect } from "next/navigation";
import { z } from "zod";

import { introspectConnection } from "../../lib/schema-introspection/service";
import { getActiveTenantContext } from "../../lib/tenant";

const IntrospectionFormSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid(),
  timeout_ms: z.coerce.number().int().min(1000).max(120000).default(120000)
});

export async function introspectConnectionAction(formData: FormData) {
  const parsed = IntrospectionFormSchema.safeParse({
    tenant_id: formData.get("tenant_id"),
    connection_id: formData.get("connection_id"),
    timeout_ms: formData.get("timeout_ms") ?? "120000"
  });

  if (!parsed.success) {
    redirect("/semantic?message=invalid_introspection");
  }

  const context = await getActiveTenantContext(parsed.data.tenant_id);
  const result = await introspectConnection({
    connectionId: parsed.data.connection_id,
    context,
    timeoutMs: parsed.data.timeout_ms
  });

  if (!result.ok) {
    redirect(`/semantic?message=${result.code}`);
  }

  redirect(
    `/semantic?version=${result.semanticVersionId}&snapshot=${result.schemaSnapshotId}`
  );
}
