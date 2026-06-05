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

  it("requires credential rebinding when endpoint identity changes", () => {
    const existing = {
      id: "33333333-3333-4333-8333-333333333333",
      tenant_id: baseInput.tenant_id,
      name: baseInput.name,
      engine: "sqlserver" as const,
      network_mode: "public_allowlist" as const,
      host: baseInput.host,
      port: baseInput.port,
      database_name: baseInput.database_name,
      username: baseInput.username,
      tls_required: baseInput.tls_required,
      trust_server_certificate: baseInput.trust_server_certificate,
      tls_server_name: baseInput.tls_server_name,
      secret_ref: "gcp-secret-manager://projects/demo/secrets/customer-db"
    };
    const unchanged = service.ConnectionUpdateInputSchema.parse({
      ...baseInput,
      connection_id: existing.id,
      password: undefined
    });

    expect(service.connectionIdentityChanged(existing, unchanged)).toBe(false);
    expect(
      service.connectionIdentityChanged(existing, {
        ...unchanged,
        host: "different.example.com"
      })
    ).toBe(true);
    expect(
      service.connectionIdentityChanged(existing, {
        ...unchanged,
        database_name: "different"
      })
    ).toBe(true);
  });

  it("preserves the current secret when a same-endpoint rotation fails", () => {
    const existingSecretRef =
      "gcp-secret-manager://projects/demo/secrets/current-password";
    const stagedSecretRef =
      "gcp-secret-manager://projects/demo/secrets/staged-password";

    expect(
      service.secretRefAfterTest({
        existingSecretRef,
        candidateSecretRef: stagedSecretRef,
        identityChanged: false,
        testStatus: "failed"
      })
    ).toBe(existingSecretRef);
    expect(
      service.shouldDeletePreviousSecret({
        identityChanged: false,
        passwordProvided: true,
        testStatus: "failed"
      })
    ).toBe(false);
  });

  it("does not reuse a secret after the connection identity changes", () => {
    expect(
      service.secretRefAfterTest({
        existingSecretRef:
          "gcp-secret-manager://projects/demo/secrets/current-password",
        candidateSecretRef:
          "gcp-secret-manager://projects/demo/secrets/staged-password",
        identityChanged: true,
        testStatus: "failed"
      })
    ).toBeNull();
    expect(
      service.shouldDeletePreviousSecret({
        identityChanged: true,
        passwordProvided: true,
        testStatus: "failed"
      })
    ).toBe(true);
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
