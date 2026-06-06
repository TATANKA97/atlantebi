import { NextResponse, type NextRequest } from "next/server";

import { createSupabaseServerClient } from "../../../lib/supabase/server";

export function safeNextPath(requestedNext: string | null) {
  const containsControlCharacter =
    requestedNext?.split("").some((character) => {
      const codePoint = character.charCodeAt(0);
      return codePoint <= 31 || codePoint === 127;
    }) ?? false;

  if (
    !requestedNext?.startsWith("/") ||
    requestedNext.startsWith("//") ||
    requestedNext.includes("\\") ||
    containsControlCharacter
  ) {
    return "/setup";
  }

  const trustedOrigin = "https://atlante.invalid";
  const resolved = new URL(requestedNext, trustedOrigin);
  return resolved.origin === trustedOrigin ? requestedNext : "/setup";
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
