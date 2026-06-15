import { NextResponse } from "next/server";

import {
  semanticServiceResponse,
  type SemanticLayerServiceError
} from "./service";

export async function readJson(request: Request): Promise<unknown> {
  try {
    return await request.json();
  } catch {
    return null;
  }
}

export function semanticMutationRequestError(request: Request) {
  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().startsWith("application/json")) {
    return semanticSuccessResponse(
      { error: "semantic_json_required" },
      415
    );
  }

  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite === "cross-site") {
    return semanticSuccessResponse(
      { error: "semantic_cross_site_request_rejected" },
      403
    );
  }

  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin) {
    return semanticSuccessResponse(
      { error: "semantic_origin_rejected" },
      403
    );
  }

  return null;
}

export function semanticErrorResponse(error: unknown) {
  const mapped = semanticServiceResponse(error);
  return NextResponse.json(
    { error: mapped.code, message: mapped.message },
    {
      status: mapped.status,
      headers: { "cache-control": "private, no-store" }
    }
  );
}

export function semanticSuccessResponse(
  payload: Record<string, unknown>,
  status = 200
) {
  return NextResponse.json(payload, {
    status,
    headers: { "cache-control": "private, no-store" }
  });
}

export function isSemanticServiceError(
  error: unknown
): error is SemanticLayerServiceError {
  return (
    error instanceof Error &&
    error.name === "SemanticLayerServiceError" &&
    "code" in error &&
    "status" in error
  );
}
