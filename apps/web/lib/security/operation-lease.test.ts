import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const rpc = vi.fn();
vi.mock("../supabase/admin", () => ({
  createSupabaseAdminClient: () => ({ rpc })
}));

const lease = await import("./operation-lease");

describe("security operation leases", () => {
  beforeEach(() => {
    rpc.mockReset();
  });

  it("releases the distributed lease after successful work", async () => {
    rpc
      .mockResolvedValueOnce({
        data: "30000000-0000-4000-8000-000000000001",
        error: null
      })
      .mockResolvedValueOnce({ data: null, error: null });

    const result = await lease.withSecurityOperationLease({
      actorUserId: "10000000-0000-4000-8000-000000000001",
      operation: "schema_introspection",
      resourceKey: "connection-id",
      run: async () => "ok",
      tenantId: "20000000-0000-4000-8000-000000000001"
    });

    expect(result).toBe("ok");
    expect(rpc).toHaveBeenLastCalledWith(
      "release_security_operation_lease",
      {
        target_lease_id: "30000000-0000-4000-8000-000000000001"
      }
    );
  });

  it("maps database rate limits to a typed application error", async () => {
    rpc.mockResolvedValueOnce({
      data: null,
      error: { message: "security operation rate limit exceeded" }
    });

    await expect(
      lease.withSecurityOperationLease({
        actorUserId: "10000000-0000-4000-8000-000000000001",
        operation: "connection_test",
        resourceKey: "sql.example.com:1433",
        run: async () => "unreachable",
        tenantId: "20000000-0000-4000-8000-000000000001"
      })
    ).rejects.toBeInstanceOf(lease.SecurityOperationLimitError);
  });

  it("passes semantic generation leases to the database unchanged", async () => {
    rpc
      .mockResolvedValueOnce({
        data: "30000000-0000-4000-8000-000000000009",
        error: null
      })
      .mockResolvedValueOnce({ data: null, error: null });

    await lease.withSecurityOperationLease({
      actorUserId: "10000000-0000-4000-8000-000000000001",
      operation: "semantic_generation",
      resourceKey: "connection-id",
      run: async () => "generated",
      tenantId: "20000000-0000-4000-8000-000000000001"
    });

    expect(rpc).toHaveBeenNthCalledWith(
      1,
      "acquire_security_operation_lease",
      {
        target_actor_user_id: "10000000-0000-4000-8000-000000000001",
        target_operation: "semantic_generation",
        target_resource_key: "connection-id",
        target_tenant_id: "20000000-0000-4000-8000-000000000001"
      }
    );
  });

  it("passes AI provider setting leases to the database unchanged", async () => {
    rpc
      .mockResolvedValueOnce({
        data: "30000000-0000-4000-8000-000000000010",
        error: null
      })
      .mockResolvedValueOnce({ data: null, error: null });

    await lease.withSecurityOperationLease({
      actorUserId: "10000000-0000-4000-8000-000000000001",
      operation: "ai_provider_setting",
      resourceKey: "openai:gpt-5.5",
      run: async () => "saved",
      tenantId: "20000000-0000-4000-8000-000000000001"
    });

    expect(rpc).toHaveBeenNthCalledWith(
      1,
      "acquire_security_operation_lease",
      {
        target_actor_user_id: "10000000-0000-4000-8000-000000000001",
        target_operation: "ai_provider_setting",
        target_resource_key: "openai:gpt-5.5",
        target_tenant_id: "20000000-0000-4000-8000-000000000001"
      }
    );
  });
});
