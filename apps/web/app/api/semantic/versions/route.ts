import { z } from "zod";

import {
  semanticErrorResponse,
  semanticSuccessResponse
} from "../../../../lib/semantic-layer/api";
import { listSemanticVersions } from "../../../../lib/semantic-layer/service";
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
    return semanticSuccessResponse({
      versions: await listSemanticVersions({
        connectionId: parsed.data.connection_id,
        context: tenant.context
      })
    });
  } catch (error) {
    return semanticErrorResponse(error);
  }
}
