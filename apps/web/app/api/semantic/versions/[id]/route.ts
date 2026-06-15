import { z } from "zod";

import {
  semanticErrorResponse,
  semanticSuccessResponse
} from "../../../../../lib/semantic-layer/api";
import { readSemanticLayerVersion } from "../../../../../lib/semantic-layer/service";
import { getActiveTenantContextForApi } from "../../../../../lib/tenant";

const QuerySchema = z.strictObject({ tenant_id: z.string().uuid() });
const IdSchema = z.string().uuid();

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const id = IdSchema.safeParse((await params).id);
  const query = QuerySchema.safeParse(
    Object.fromEntries(new URL(request.url).searchParams)
  );
  if (!id.success || !query.success) {
    return semanticSuccessResponse({ error: "invalid_semantic_request" }, 400);
  }
  const tenant = await getActiveTenantContextForApi(query.data.tenant_id);
  if (!tenant.ok) {
    return semanticSuccessResponse({ error: tenant.code }, tenant.status);
  }
  try {
    return semanticSuccessResponse(
      await readSemanticLayerVersion({
        context: tenant.context,
        semanticVersionId: id.data
      })
    );
  } catch (error) {
    return semanticErrorResponse(error);
  }
}
