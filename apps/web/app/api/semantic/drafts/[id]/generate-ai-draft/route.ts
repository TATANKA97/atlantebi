import { z } from "zod";

import {
  readJson,
  semanticMutationRequestError,
  semanticErrorResponse,
  semanticSuccessResponse
} from "../../../../../../lib/semantic-layer/api";
import { generateSemanticDraft } from "../../../../../../lib/semantic-layer/service";
import { getActiveTenantContextForApi } from "../../../../../../lib/tenant";

const RequestSchema = z.strictObject({ tenant_id: z.string().uuid() });
const IdSchema = z.string().uuid();

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const requestError = semanticMutationRequestError(request);
  if (requestError) {
    return requestError;
  }
  const id = IdSchema.safeParse((await params).id);
  const body = RequestSchema.safeParse(await readJson(request));
  if (!id.success || !body.success) {
    return semanticSuccessResponse({ error: "invalid_semantic_generate" }, 400);
  }
  const tenant = await getActiveTenantContextForApi(body.data.tenant_id);
  if (!tenant.ok) {
    return semanticSuccessResponse({ error: tenant.code }, tenant.status);
  }
  try {
    return semanticSuccessResponse(
      await generateSemanticDraft({
        context: tenant.context,
        semanticVersionId: id.data
      })
    );
  } catch (error) {
    return semanticErrorResponse(error);
  }
}
