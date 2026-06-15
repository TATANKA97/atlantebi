import { z } from "zod";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const googleAuth = vi.hoisted(() => ({
  getIdTokenClient: vi.fn(),
  request: vi.fn()
}));

vi.mock("google-auth-library", () => ({
  GoogleAuth: class {
    getIdTokenClient = googleAuth.getIdTokenClient;
  }
}));

const { postQueryEngine, QueryEngineRequestError } = await import("./client");

const ResponseSchema = z.strictObject({
  status: z.literal("ok"),
  request_id: z.string().uuid()
});

describe("query-engine API client", () => {
  beforeEach(() => {
    vi.stubEnv("QUERY_ENGINE_URL", "https://query-engine.example.test/base/");
    vi.stubEnv("QUERY_ENGINE_API_TOKEN", "server-token");
    vi.stubEnv("QUERY_ENGINE_AUTH_MODE", "static_token");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("fails with a service-unavailable error when the engine URL is missing", async () => {
    vi.stubEnv("QUERY_ENGINE_URL", "");

    await expect(
      postQueryEngine("/query", {}, ResponseSchema)
    ).rejects.toMatchObject({
      name: "QueryEngineRequestError",
      status: 503,
      message: "QUERY_ENGINE_URL is required."
    });
  });

  it("posts JSON with the server token and validates the successful response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "ok",
          request_id: "88888888-8888-4888-8888-888888888888"
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" }
        }
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const result = await postQueryEngine(
      "/query",
      { question: "Fatturato 2008" },
      ResponseSchema,
      5_000
    );

    expect(result.request_id).toBe("88888888-8888-4888-8888-888888888888");
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://query-engine.example.test/query");
    expect(init).toMatchObject({
      method: "POST",
      body: JSON.stringify({ question: "Fatturato 2008" }),
      headers: {
        "content-type": "application/json",
        "x-atlante-query-engine-token": "server-token"
      }
    });
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("fails closed when static token auth has no token", async () => {
    vi.stubEnv("QUERY_ENGINE_API_TOKEN", "");

    await expect(
      postQueryEngine("/query", {}, ResponseSchema)
    ).rejects.toMatchObject({
      status: 503,
      message: "QUERY_ENGINE_API_TOKEN is required for static_token auth."
    });
  });

  it("fails closed for an unknown authentication mode", async () => {
    vi.stubEnv("QUERY_ENGINE_AUTH_MODE", "typo");

    await expect(
      postQueryEngine("/query", {}, ResponseSchema)
    ).rejects.toMatchObject({ status: 503 });
  });

  it("allows insecure transport only for loopback outside production", async () => {
    vi.stubEnv("QUERY_ENGINE_AUTH_MODE", "local_insecure");
    vi.stubEnv("QUERY_ENGINE_URL", "http://127.0.0.1:8080");
    vi.stubEnv("NODE_ENV", "development");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: "ok",
            request_id: "88888888-8888-4888-8888-888888888888"
          }),
          {
            status: 200,
            headers: { "content-type": "application/json" }
          }
        )
      )
    );

    await expect(
      postQueryEngine("/query", {}, ResponseSchema)
    ).resolves.toMatchObject({ status: "ok" });

    vi.stubEnv("NODE_ENV", "production");
    await expect(
      postQueryEngine("/query", {}, ResponseSchema)
    ).rejects.toMatchObject({ status: 503 });
  });

  it("maps a structured engine error to a typed status-bearing error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Semantic layer is stale." }), {
          status: 409,
          headers: { "content-type": "application/json" }
        })
      )
    );

    const error = await postQueryEngine("/query", {}, ResponseSchema).catch(
      (caught) => caught
    );

    expect(error).toBeInstanceOf(QueryEngineRequestError);
    expect(error).toMatchObject({
      status: 409,
      message: "Semantic layer is stale."
    });
  });

  it("uses a sanitized fallback for non-JSON engine errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("upstream stack trace", { status: 502 })
        )
    );

    await expect(
      postQueryEngine("/query", {}, ResponseSchema)
    ).rejects.toMatchObject({
      status: 502,
      message: "Query engine request failed."
    });
  });

  it("rejects successful responses that do not match the expected API schema", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: "ok", request_id: "invalid" }), {
          status: 200,
          headers: { "content-type": "application/json" }
        })
      )
    );

    await expect(
      postQueryEngine("/query", {}, ResponseSchema)
    ).rejects.toBeInstanceOf(z.ZodError);
  });

  it("uses Google ID token transport without falling back to fetch", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("QUERY_ENGINE_AUTH_MODE", "google_id_token");
    googleAuth.getIdTokenClient.mockResolvedValue({
      request: googleAuth.request
    });
    googleAuth.request.mockResolvedValue({
      status: 200,
      data: {
        status: "ok",
        request_id: "88888888-8888-4888-8888-888888888888"
      }
    });

    await expect(
      postQueryEngine("/query", { question: "Ordini 2008" }, ResponseSchema, 7_000)
    ).resolves.toMatchObject({ status: "ok" });

    expect(googleAuth.getIdTokenClient).toHaveBeenCalledWith(
      "https://query-engine.example.test/base/"
    );
    expect(googleAuth.request).toHaveBeenCalledWith({
      data: JSON.stringify({ question: "Ordini 2008" }),
      headers: { "content-type": "application/json" },
      method: "POST",
      timeout: 7_000,
      url: "https://query-engine.example.test/query",
      validateStatus: expect.any(Function)
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
