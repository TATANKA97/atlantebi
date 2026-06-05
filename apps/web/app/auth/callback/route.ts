import { NextResponse, type NextRequest } from "next/server";

import { createSupabaseServerClient } from "../../../lib/supabase/server";

export function safeNextPath(requestedNext: string | null) {
  return requestedNext?.startsWith("/") &&
    !requestedNext.startsWith("//") &&
    !requestedNext.includes("\\")
    ? requestedNext
    : "/setup";
}

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const next = safeNextPath(url.searchParams.get("next"));

  if (code) {
    const supabase = await createSupabaseServerClient();
    await supabase?.auth.exchangeCodeForSession(code);
  }

  return NextResponse.redirect(new URL(next, request.url));
}
