"use server";

import { redirect } from "next/navigation";
import { z } from "zod";

import { createSupabaseServerClient } from "../../lib/supabase/server";

const AuthFormSchema = z.strictObject({
  email: z.string().email().max(320),
  password: z.string().min(8).max(200)
});

function parseAuthForm(formData: FormData) {
  return AuthFormSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password")
  });
}

export async function signIn(formData: FormData) {
  const parsed = parseAuthForm(formData);

  if (!parsed.success) {
    redirect("/login?message=invalid_credentials");
  }

  const supabase = await createSupabaseServerClient();

  if (!supabase) {
    redirect("/login?message=supabase_not_configured");
  }

  const { error } = await supabase.auth.signInWithPassword(parsed.data);

  if (error) {
    redirect("/login?message=signin_failed");
  }

  redirect("/setup");
}

export async function signUp(formData: FormData) {
  const parsed = parseAuthForm(formData);

  if (!parsed.success) {
    redirect("/login?message=invalid_credentials");
  }

  const supabase = await createSupabaseServerClient();

  if (!supabase) {
    redirect("/login?message=supabase_not_configured");
  }

  const { error } = await supabase.auth.signUp(parsed.data);

  if (error) {
    redirect("/login?message=signup_failed");
  }

  redirect("/setup");
}

export async function signOut() {
  const supabase = await createSupabaseServerClient();

  if (!supabase) {
    redirect("/setup?message=supabase_not_configured");
  }

  const { error } = await supabase.auth.signOut();
  if (error) {
    redirect("/setup?message=signout_failed");
  }

  redirect("/login");
}
