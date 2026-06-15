import { z } from "zod";

import {
  readJson,
  semanticMutationRequestError,
  semanticErrorResponse,
  semanticSuccessResponse
} from "../../../../../lib/semantic-layer/api";
import {
  patchSemanticDraft,
  SemanticDraftPatchSchema
} from "../../../../../lib/semantic-layer/service";
import { getActiveTenantContextForApi } from "../../../../../lib/tenant";

const IdSchema = z.string().uuid();

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const requestError = semanticMutationRequestError(request);
  if (requestError) {
    return requestError;
  }
  const id = IdSchema.safeParse((await params).id);
  const patch = SemanticDraftPatchSchema.safeParse(await readJson(request));
  if (!id.success || !patch.success) {
    return semanticSuccessResponse({ error: "invalid_semantic_patch" }, 400);
  }
  const tenant = await getActiveTenantContextForApi(patch.data.tenant_id);
  if (!tenant.ok) {
    return semanticSuccessResponse({ error: tenant.code }, tenant.status);
  }
  try {
    return semanticSuccessResponse(
      await patchSemanticDraft({
        context: tenant.context,
        patch: patch.data,
        semanticVersionId: id.data
      })
    );
  } catch (error) {
    return semanticErrorResponse(error);
  }
}
