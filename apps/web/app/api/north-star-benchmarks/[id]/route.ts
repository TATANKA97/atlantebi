import { NorthStarBenchmarkInputSchema } from "@atlantebi/contracts";
import { z } from "zod";

import {
  deleteNorthStarBenchmark,
  northStarServiceResponse,
  updateNorthStarBenchmark
} from "../../../../lib/north-star-benchmarks/service";
import {
  readJson,
  semanticMutationRequestError,
  semanticSuccessResponse
} from "../../../../lib/semantic-layer/api";
import { getActiveTenantContextForApi } from "../../../../lib/tenant";

export const dynamic = "force-dynamic";

const RouteParamsSchema = z.strictObject({
  id: z.string().uuid()
});

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const mutationError = semanticMutationRequestError(request);
  if (mutationError) {
    return mutationError;
  }

  const body = await readJson(request);
  const parsed = NorthStarBenchmarkInputSchema.safeParse(body);
  if (!parsed.success) {
    return semanticSuccessResponse(
      { error: "north_star_invalid", issues: parsed.error.issues },
      400
    );
  }

  const tenantResult = await getActiveTenantContextForApi();
  if (!tenantResult.ok) {
    return semanticSuccessResponse(
      { error: tenantResult.code },
      tenantResult.status
    );
  }

  try {
    const parsedParams = RouteParamsSchema.safeParse(await params);
    if (!parsedParams.success) {
      return semanticSuccessResponse({ error: "north_star_invalid_id" }, 400);
    }
    const benchmarkKey = await updateNorthStarBenchmark({
      benchmarkKey: parsedParams.data.id,
      context: tenantResult.context,
      input: parsed.data
    });
    return semanticSuccessResponse({ benchmark_key: benchmarkKey });
  } catch (error) {
    return northStarErrorResponse(error, "north_star_update_failed");
  }
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const mutationError = northStarMutationRequestError(request);
  if (mutationError) {
    return mutationError;
  }

  const tenantResult = await getActiveTenantContextForApi();
  if (!tenantResult.ok) {
    return semanticSuccessResponse(
      { error: tenantResult.code },
      tenantResult.status
    );
  }

  try {
    const parsedParams = RouteParamsSchema.safeParse(await params);
    if (!parsedParams.success) {
      return semanticSuccessResponse({ error: "north_star_invalid_id" }, 400);
    }
    const benchmarkKey = await deleteNorthStarBenchmark({
      benchmarkKey: parsedParams.data.id,
      context: tenantResult.context
    });
    return semanticSuccessResponse({ benchmark_key: benchmarkKey });
  } catch (error) {
    return northStarErrorResponse(error, "north_star_delete_failed");
  }
}

function northStarErrorResponse(error: unknown, fallbackCode: string) {
  const mapped = northStarServiceResponse(error, fallbackCode);
  return semanticSuccessResponse({ error: mapped.code }, mapped.status);
}

function northStarMutationRequestError(request: Request) {
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite === "cross-site") {
    return semanticSuccessResponse(
      { error: "north_star_cross_site_request_rejected" },
      403
    );
  }

  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin) {
    return semanticSuccessResponse(
      { error: "north_star_origin_rejected" },
      403
    );
  }

  return null;
}
