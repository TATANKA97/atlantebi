import { redirect } from "next/navigation";

import { signIn, signUp } from "../auth/actions";
import { createSupabaseServerClient } from "../../lib/supabase/server";

const MESSAGE_COPY: Record<string, string> = {
  invalid_credentials: "Email o password non valide.",
  signin_failed: "Accesso non riuscito.",
  signup_failed: "Registrazione non riuscita.",
  supabase_not_configured: "Supabase non e configurato per questa installazione."
};

export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams
}: {
  searchParams: Promise<{ message?: string }>;
}) {
  const supabase = await createSupabaseServerClient();
  const params = await searchParams;

  if (supabase) {
    const {
      data: { user }
    } = await supabase.auth.getUser();

    if (user) {
      redirect("/setup");
    }
  }

  const message = params.message ? MESSAGE_COPY[params.message] : undefined;

  return (
    <main className="min-h-screen px-8 py-10">
      <section className="mx-auto flex max-w-sm flex-col gap-8">
        <div>
          <h1 className="text-4xl font-semibold tracking-normal">Atlante BI</h1>
          <p className="mt-3 text-sm leading-6 text-[color:var(--muted)]">
            Accedi per configurare il tenant e collegare i metadata applicativi.
          </p>
        </div>

        {message ? (
          <p className="border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--muted)]">
            {message}
          </p>
        ) : null}

        <form className="flex flex-col gap-4">
          <label className="flex flex-col gap-2 text-sm">
            Email
            <input
              className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
              name="email"
              required
              type="email"
            />
          </label>
          <label className="flex flex-col gap-2 text-sm">
            Password
            <input
              className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
              minLength={8}
              name="password"
              required
              type="password"
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <button
              className="border border-[color:var(--accent)] px-4 py-2 text-sm font-medium"
              formAction={signIn}
            >
              Accedi
            </button>
            <button
              className="border border-[color:var(--border)] px-4 py-2 text-sm font-medium"
              formAction={signUp}
            >
              Registrati
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
