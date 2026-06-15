import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const { semanticMutationRequestError } = await import("./api");

describe("semantic API mutation guard", () => {
  it("accepts same-origin JSON requests", () => {
    const request = new Request("https://atlante.example/api/semantic/drafts", {
      headers: {
        "content-type": "application/json",
        origin: "https://atlante.example",
        "sec-fetch-site": "same-origin"
      },
      method: "POST"
    });

    expect(semanticMutationRequestError(request)).toBeNull();
  });

  it("rejects non-JSON mutation requests", async () => {
    const response = semanticMutationRequestError(
      new Request("https://atlante.example/api/semantic/drafts", {
        headers: { "content-type": "text/plain" },
        method: "POST"
      })
    );

    expect(response?.status).toBe(415);
    await expect(response?.json()).resolves.toMatchObject({
      error: "semantic_json_required"
    });
  });

  it("rejects cross-origin and cross-site mutation requests", () => {
    const crossOrigin = semanticMutationRequestError(
      new Request("https://atlante.example/api/semantic/drafts", {
        headers: {
          "content-type": "application/json",
          origin: "https://attacker.example"
        },
        method: "POST"
      })
    );
    const crossSite = semanticMutationRequestError(
      new Request("https://atlante.example/api/semantic/drafts", {
        headers: {
          "content-type": "application/json",
          "sec-fetch-site": "cross-site"
        },
        method: "POST"
      })
    );

    expect(crossOrigin?.status).toBe(403);
    expect(crossSite?.status).toBe(403);
  });
});
