import { z } from "zod";

import {
  readJson,
  semanticMutationRequestError,
  semanticErrorResponse,
  semanticSuccessResponse
} from "../../../../lib/semantic-layer/api";
import { createSemanticDraft } from "../../../../lib/semantic-layer/service";
import { getActiveTenantContextForApi } from "../../../../lib/tenant";

const RequestSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid(),
  activation_policy: z
    .enum(["auto_validated", "manual_review"])
    .default("auto_validated")
});

export async function POST(request: Request) {
  const requestError = semanticMutationRequestError(request);
  if (requestError) {
    return requestError;
  }
  const parsed = RequestSchema.safeParse(await readJson(request));
  if (!parsed.success) {
    return semanticSuccessResponse({ error: "invalid_semantic_draft" }, 400);
  }
  const tenant = await getActiveTenantContextForApi(parsed.data.tenant_id);
  if (!tenant.ok) {
    return semanticSuccessResponse({ error: tenant.code }, tenant.status);
  }
  try {
    return semanticSuccessResponse(
      await createSemanticDraft({
        activationPolicy: parsed.data.activation_policy,
        connectionId: parsed.data.connection_id,
        context: tenant.context
      }),
      201
    );
  } catch (error) {
    return semanticErrorResponse(error);
  }
}
