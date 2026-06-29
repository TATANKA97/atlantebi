import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const { queryIntentJsonPostRequestError } = await import("./api");

describe("query intent API request guard", () => {
  it("accepts JSON requests from the app even when the proxy rewrites request.url", () => {
    const request = new Request(
      "https://internal-cloud-run.example/api/query-intent/test-suite",
      {
        headers: {
          "content-type": "application/json",
          origin: "https://web-3zsxzvizgq-uc.a.run.app",
          "sec-fetch-site": "same-origin"
        },
        method: "POST"
      }
    );

    expect(queryIntentJsonPostRequestError(request)).toBeNull();
  });

  it("rejects non-JSON requests", async () => {
    const response = queryIntentJsonPostRequestError(
      new Request("https://atlante.example/api/query-intent/test-suite", {
        headers: { "content-type": "text/plain" },
        method: "POST"
      })
    );

    expect(response?.status).toBe(415);
    await expect(response?.json()).resolves.toMatchObject({
      error: "query_intent_json_required"
    });
  });

  it("rejects browser cross-site requests", async () => {
    const response = queryIntentJsonPostRequestError(
      new Request("https://atlante.example/api/query-intent/test-suite", {
        headers: {
          "content-type": "application/json",
          "sec-fetch-site": "cross-site"
        },
        method: "POST"
      })
    );

    expect(response?.status).toBe(403);
    await expect(response?.json()).resolves.toMatchObject({
      error: "query_intent_cross_site_request_rejected"
    });
  });
});
