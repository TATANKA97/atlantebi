import "server-only";

import { createClient } from "@supabase/supabase-js";

import { getSupabasePublicConfig } from "./config";

export function createSupabaseAdminClient() {
  const config = getSupabasePublicConfig();
  const secretKey =
    process.env.SUPABASE_SECRET_KEY ?? process.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!config || !secretKey) {
    throw new Error("SUPABASE_SECRET_KEY is required for server-side metadata access.");
  }

  return createClient(config.url, secretKey, {
    auth: {
      autoRefreshToken: false,
      persistSession: false
    }
  });
}
