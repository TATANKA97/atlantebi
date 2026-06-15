import "server-only";

import { GoogleAuth } from "google-auth-library";
import type { z } from "zod";

export class QueryEngineRequestError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message);
    this.name = "QueryEngineRequestError";
  }
}

export async function postQueryEngine<TSchema extends z.ZodType>(
  path: string,
  payload: unknown,
  schema: TSchema,
  timeoutMs = 120_000
): Promise<z.infer<TSchema>> {
  const queryEngineUrl = process.env.QUERY_ENGINE_URL;
  if (!queryEngineUrl) {
    throw new QueryEngineRequestError("QUERY_ENGINE_URL is required.", 503);
  }

  const headers: Record<string, string> = {
    "content-type": "application/json"
  };
  const authMode = process.env.QUERY_ENGINE_AUTH_MODE;

  const url = new URL(path, queryEngineUrl).toString();
  const body = JSON.stringify(payload);
  let status: number;
  let responseBody: unknown;

  if (authMode === "google_id_token") {
    const client = await new GoogleAuth().getIdTokenClient(queryEngineUrl);
    const response = await client.request({
      data: body,
      headers,
      method: "POST",
      timeout: timeoutMs,
      url,
      validateStatus: () => true
    });
    status = response.status;
    responseBody = response.data;
  } else if (authMode === "static_token") {
    const token = process.env.QUERY_ENGINE_API_TOKEN;
    if (!token) {
      throw new QueryEngineRequestError(
        "QUERY_ENGINE_API_TOKEN is required for static_token auth.",
        503
      );
    }
    headers["x-atlante-query-engine-token"] = token;
    const response = await fetch(url, {
      body,
      headers,
      method: "POST",
      signal: AbortSignal.timeout(timeoutMs)
    });
    status = response.status;
    responseBody = await readResponseBody(response);
  } else if (
    authMode === "local_insecure" &&
    process.env.NODE_ENV !== "production" &&
    isLoopbackUrl(queryEngineUrl)
  ) {
    const response = await fetch(url, {
      body,
      headers,
      method: "POST",
      signal: AbortSignal.timeout(timeoutMs)
    });
    status = response.status;
    responseBody = await readResponseBody(response);
  } else {
    throw new QueryEngineRequestError(
      "QUERY_ENGINE_AUTH_MODE must be google_id_token, static_token, or local_insecure on loopback outside production.",
      503
    );
  }

  if (status < 200 || status >= 300) {
    throw new QueryEngineRequestError(
      semanticEngineErrorMessage(responseBody),
      status
    );
  }

  return schema.parse(responseBody);
}

function isLoopbackUrl(value: string) {
  const hostname = new URL(value).hostname;
  return hostname === "127.0.0.1" || hostname === "localhost" || hostname === "::1";
}

async function readResponseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

function semanticEngineErrorMessage(payload: unknown) {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return "Query engine request failed.";
}
