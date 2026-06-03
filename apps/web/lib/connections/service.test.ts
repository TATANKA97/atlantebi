import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const service = await import("./service");

const baseInput = {
  tenant_id: "8a4a54cb-7bc4-4e8a-a951-8d386e1f2d07",
  name: "AdventureWorksLT Azure SQL",
  engine: "sqlserver",
  network_mode: "public_allowlist",
  host: "136.111.143.3",
  port: 10002,
  database_name: "AdventureWorksLT",
  username: "atlante_demo_ro",
  password: "not-a-real-password",
  tls_required: true,
  trust_server_certificate: false,
  tls_server_name: "atlanteadmin.database.windows.net",
  timeout_ms: 30000
} as const;

describe("connection input boundary", () => {
  it("rejects API JSON numbers encoded as strings", () => {
    const parsed = service.ConnectionInputSchema.safeParse({
      ...baseInput,
      port: "10002",
      timeout_ms: "500"
    });

    expect(parsed.success).toBe(false);
  });

  it("rejects API JSON booleans encoded as strings", () => {
    const parsed = service.ConnectionInputSchema.safeParse({
      ...baseInput,
      tls_required: "false",
      trust_server_certificate: "false"
    });

    expect(parsed.success).toBe(false);
  });

  it("accepts form encoded numeric strings only through the form schema", () => {
    const parsed = service.ConnectionFormInputSchema.parse({
      ...baseInput,
      port: "10002",
      timeout_ms: "30000"
    });

    expect(parsed.port).toBe(10002);
    expect(parsed.timeout_ms).toBe(30000);
  });
});
