import "server-only";

import {
  NorthStarBenchmarkInputSchema,
  NorthStarBenchmarkSchema,
  type NorthStarBenchmark,
  type NorthStarBenchmarkInput
} from "@atlantebi/contracts";

import { createSupabaseAdminClient } from "../supabase/admin";
import {
  canManageSemanticLayer,
  type ActiveTenantContext
} from "../tenant";

export class NorthStarServiceError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status = 500) {
    super(message);
    this.name = "NorthStarServiceError";
    this.code = code;
    this.status = status;
  }
}

type NorthStarBenchmarkRow = {
  benchmark_key: string;
  tenant_id: string;
  connection_id: string;
  dashboard_id: string | null;
  semantic_version_id: string | null;
  metric_key: string | null;
  name: string;
  description: string | null;
  expected_value: string | number;
  value_type: "currency" | "number" | "percentage" | "count";
  currency: string | null;
  period_type:
    | "day"
    | "week"
    | "month"
    | "quarter"
    | "year"
    | "rolling_12_months"
    | "custom";
  period_start: string | null;
  period_end: string | null;
  tolerance_mode: "percentage" | "absolute" | "range";
  tolerance_percentage: string | number | null;
  min_value: string | number | null;
  max_value: string | number | null;
  severity: "low" | "medium" | "high" | "critical";
  enabled: boolean;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export async function listNorthStarBenchmarks({
  connectionId,
  context
}: {
  connectionId: string;
  context: ActiveTenantContext;
}): Promise<NorthStarBenchmark[]> {
  const admin = createSupabaseAdminClient();
  const { data, error } = await admin
    .from("north_star_benchmarks")
    .select(
      [
        "benchmark_key",
        "tenant_id",
        "connection_id",
        "dashboard_id",
        "semantic_version_id",
        "metric_key",
        "name",
        "description",
        "expected_value",
        "value_type",
        "currency",
        "period_type",
        "period_start",
        "period_end",
        "tolerance_mode",
        "tolerance_percentage",
        "min_value",
        "max_value",
        "severity",
        "enabled",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at"
      ].join(",")
    )
    .eq("tenant_id", context.tenantId)
    .eq("connection_id", connectionId)
    .order("enabled", { ascending: false })
    .order("created_at", { ascending: false });

  if (error) {
    throw new NorthStarServiceError(
      "north_star_read_failed",
      error.message,
      500
    );
  }

  return ((data ?? []) as unknown as NorthStarBenchmarkRow[]).map(
    parseBenchmarkRow
  );
}

export async function createNorthStarBenchmark({
  context,
  input
}: {
  context: ActiveTenantContext;
  input: NorthStarBenchmarkInput;
}) {
  assertNorthStarAdmin(context);
  const payload = NorthStarBenchmarkInputSchema.parse(input);
  const admin = createSupabaseAdminClient();
  const { data, error } = await admin.rpc("create_north_star_benchmark", {
    actor_user_id: context.userId,
    target_tenant_id: context.tenantId,
    target_connection_id: payload.connection_id,
    benchmark_payload: payload
  });

  if (error) {
    throw mapNorthStarRpcError(error, "north_star_create_failed");
  }

  return String(data);
}

export async function updateNorthStarBenchmark({
  benchmarkKey,
  context,
  input
}: {
  benchmarkKey: string;
  context: ActiveTenantContext;
  input: NorthStarBenchmarkInput;
}) {
  assertNorthStarAdmin(context);
  const payload = NorthStarBenchmarkInputSchema.parse(input);
  const admin = createSupabaseAdminClient();
  const { data, error } = await admin.rpc("update_north_star_benchmark", {
    actor_user_id: context.userId,
    target_tenant_id: context.tenantId,
    target_benchmark_key: benchmarkKey,
    benchmark_payload: payload
  });

  if (error) {
    throw mapNorthStarRpcError(error, "north_star_update_failed");
  }

  return String(data);
}

export async function deleteNorthStarBenchmark({
  benchmarkKey,
  context
}: {
  benchmarkKey: string;
  context: ActiveTenantContext;
}) {
  assertNorthStarAdmin(context);
  const admin = createSupabaseAdminClient();
  const { data, error } = await admin.rpc("delete_north_star_benchmark", {
    actor_user_id: context.userId,
    target_tenant_id: context.tenantId,
    target_benchmark_key: benchmarkKey
  });

  if (error) {
    throw mapNorthStarRpcError(error, "north_star_delete_failed");
  }

  return String(data);
}

export function northStarServiceResponse(
  error: unknown,
  fallbackCode: string
) {
  if (error instanceof NorthStarServiceError) {
    return {
      code: error.code,
      status: error.status
    };
  }

  return {
    code: fallbackCode,
    status: 500
  };
}

function assertNorthStarAdmin(context: ActiveTenantContext) {
  if (!canManageSemanticLayer(context.role)) {
    throw new NorthStarServiceError(
      "north_star_forbidden",
      "Only tenant owners and admins can manage North Star benchmarks.",
      403
    );
  }
}

function parseBenchmarkRow(row: NorthStarBenchmarkRow): NorthStarBenchmark {
  return NorthStarBenchmarkSchema.parse({
    ...row,
    expected_value: Number(row.expected_value),
    tolerance_percentage:
      row.tolerance_percentage === null
        ? null
        : Number(row.tolerance_percentage),
    min_value: row.min_value === null ? null : Number(row.min_value),
    max_value: row.max_value === null ? null : Number(row.max_value)
  });
}

function mapNorthStarRpcError(
  error: { code?: string; message: string },
  fallbackCode: string
) {
  if (error.code === "42501") {
    return new NorthStarServiceError(
      "north_star_forbidden",
      error.message,
      403
    );
  }
  if (error.code === "P0002") {
    return new NorthStarServiceError(
      "north_star_not_found",
      error.message,
      404
    );
  }
  if (
    error.code === "22023" ||
    error.code === "23503" ||
    error.code === "23514" ||
    error.code === "23505"
  ) {
    return new NorthStarServiceError(
      "north_star_invalid",
      error.message,
      400
    );
  }

  return new NorthStarServiceError(fallbackCode, error.message, 500);
}
