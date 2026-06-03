"use server";

import { redirect } from "next/navigation";
import { z } from "zod";

import { createSupabaseServerClient } from "../../lib/supabase/server";

const TenantFormSchema = z.strictObject({
  name: z.string().trim().min(2).max(160),
  slug: z
    .string()
    .trim()
    .toLowerCase()
    .regex(/^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/)
});

export async function createTenant(formData: FormData) {
  const parsed = TenantFormSchema.safeParse({
    name: formData.get("name"),
    slug: formData.get("slug")
  });

  if (!parsed.success) {
    redirect("/setup?message=invalid_tenant");
  }

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

  const { error } = await supabase.rpc("create_tenant_with_owner", {
    tenant_name: parsed.data.name,
    tenant_plan: "pilot",
    tenant_slug: parsed.data.slug
  });

  if (error) {
    redirect("/setup?message=tenant_create_failed");
  }

  redirect("/setup?created=1");
}
