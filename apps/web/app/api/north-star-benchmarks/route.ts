import { NorthStarBenchmarkInputSchema } from "@atlantebi/contracts";

import {
  createNorthStarBenchmark,
  listNorthStarBenchmarks,
  northStarServiceResponse
} from "../../../lib/north-star-benchmarks/service";
import {
  readJson,
  semanticMutationRequestError,
  semanticSuccessResponse
} from "../../../lib/semantic-layer/api";
import { getActiveTenantContextForApi } from "../../../lib/tenant";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const tenantResult = await getActiveTenantContextForApi(
    url.searchParams.get("tenant_id")
  );
  if (!tenantResult.ok) {
    return semanticSuccessResponse(
      { error: tenantResult.code },
      tenantResult.status
    );
  }

  const connectionId = url.searchParams.get("connection_id");
  if (!connectionId) {
    return semanticSuccessResponse(
      { error: "north_star_connection_required" },
      400
    );
  }

  try {
    const benchmarks = await listNorthStarBenchmarks({
      connectionId,
      context: tenantResult.context
    });
    return semanticSuccessResponse({ benchmarks });
  } catch (error) {
    return northStarErrorResponse(error, "north_star_read_failed");
  }
}

export async function POST(request: Request) {
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
    const benchmarkKey = await createNorthStarBenchmark({
      context: tenantResult.context,
      input: parsed.data
    });
    return semanticSuccessResponse({ benchmark_key: benchmarkKey }, 201);
  } catch (error) {
    return northStarErrorResponse(error, "north_star_create_failed");
  }
}

function northStarErrorResponse(error: unknown, fallbackCode: string) {
  const mapped = northStarServiceResponse(error, fallbackCode);
  return semanticSuccessResponse({ error: mapped.code }, mapped.status);
}
