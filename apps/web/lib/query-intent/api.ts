import { NextResponse } from "next/server";

export async function readQueryIntentJson(request: Request): Promise<unknown> {
  try {
    return await request.json();
  } catch {
    return null;
  }
}

export function queryIntentJsonPostRequestError(request: Request) {
  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().startsWith("application/json")) {
    return queryIntentApiResponse(
      { error: "query_intent_json_required" },
      415
    );
  }

  if (request.headers.get("sec-fetch-site") === "cross-site") {
    return queryIntentApiResponse(
      { error: "query_intent_cross_site_request_rejected" },
      403
    );
  }

  return null;
}

export function queryIntentApiResponse(
  payload: Record<string, unknown>,
  status = 200
) {
  return NextResponse.json(payload, {
    status,
    headers: { "cache-control": "private, no-store" }
  });
}
