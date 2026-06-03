import "server-only";

import { redirect } from "next/navigation";

import { createSupabaseServerClient } from "./supabase/server";

export type ActiveTenantContext = {
  supabase: NonNullable<Awaited<ReturnType<typeof createSupabaseServerClient>>>;
  tenantId: string;
  userId: string;
  role: "owner" | "admin" | "editor" | "viewer";
};

type MembershipRow = {
  role: ActiveTenantContext["role"];
  tenant_id: string;
};

export async function getActiveTenantContext(
  requestedTenantId?: string | null
): Promise<ActiveTenantContext> {
  const supabase = await createSupabaseServerClient();

  if (!supabase) {
    redirect("/setup?message=supabase_not_configured");
  }

  const {
    data: { user }
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  let query = supabase
    .from("tenant_memberships")
    .select("tenant_id,role")
    .eq("user_id", user.id)
    .eq("status", "active")
    .order("created_at", { ascending: true })
    .limit(1);

  if (requestedTenantId) {
    query = query.eq("tenant_id", requestedTenantId);
  }

  const { data, error } = await query;

  if (error || !data?.[0]) {
    redirect("/setup");
  }

  const membership = data[0] as MembershipRow;

  return {
    supabase,
    tenantId: membership.tenant_id,
    userId: user.id,
    role: membership.role
  };
}

export function assertCanManageConnections(role: ActiveTenantContext["role"]) {
  if (!canManageConnections(role)) {
    redirect("/connections?message=connection_forbidden");
  }
}

export type ActiveTenantApiResult =
  | { ok: true; context: ActiveTenantContext }
  | { ok: false; status: number; code: string };

export async function getActiveTenantContextForApi(
  requestedTenantId?: string | null
): Promise<ActiveTenantApiResult> {
  const supabase = await createSupabaseServerClient();

  if (!supabase) {
    return { ok: false, status: 503, code: "supabase_not_configured" };
  }

  const {
    data: { user }
  } = await supabase.auth.getUser();

  if (!user) {
    return { ok: false, status: 401, code: "unauthorized" };
  }

  let query = supabase
    .from("tenant_memberships")
    .select("tenant_id,role")
    .eq("user_id", user.id)
    .eq("status", "active")
    .order("created_at", { ascending: true })
    .limit(1);

  if (requestedTenantId) {
    query = query.eq("tenant_id", requestedTenantId);
  }

  const { data, error } = await query;

  if (error || !data?.[0]) {
    return { ok: false, status: 403, code: "tenant_forbidden" };
  }

  const membership = data[0] as MembershipRow;

  return {
    ok: true,
    context: {
      supabase,
      tenantId: membership.tenant_id,
      userId: user.id,
      role: membership.role
    }
  };
}

export function canManageConnections(role: ActiveTenantContext["role"]) {
  return ["owner", "admin", "editor"].includes(role);
}
