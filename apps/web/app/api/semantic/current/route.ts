import { z } from "zod";

import {
  semanticErrorResponse,
  semanticSuccessResponse
} from "../../../../lib/semantic-layer/api";
import { readCurrentSemanticLayer } from "../../../../lib/semantic-layer/service";
import { getActiveTenantContextForApi } from "../../../../lib/tenant";

const QuerySchema = z.strictObject({
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid()
});

export async function GET(request: Request) {
  const parsed = QuerySchema.safeParse(
    Object.fromEntries(new URL(request.url).searchParams)
  );
  if (!parsed.success) {
    return semanticSuccessResponse({ error: "invalid_semantic_request" }, 400);
  }
  const tenant = await getActiveTenantContextForApi(parsed.data.tenant_id);
  if (!tenant.ok) {
    return semanticSuccessResponse({ error: tenant.code }, tenant.status);
  }
  try {
    const current = await readCurrentSemanticLayer({
      connectionId: parsed.data.connection_id,
      context: tenant.context
    });
    if (!current) {
      return semanticSuccessResponse(
        { error: "semantic_version_not_found" },
        404
      );
    }
    return semanticSuccessResponse(current);
  } catch (error) {
    return semanticErrorResponse(error);
  }
}
