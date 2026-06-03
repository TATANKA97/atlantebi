import { ENGINE_VALUES } from "@atlantebi/contracts";
import { redirect } from "next/navigation";

import { createSupabaseServerClient } from "../lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function Home() {
  const supabase = await createSupabaseServerClient();

  if (supabase) {
    const {
      data: { user }
    } = await supabase.auth.getUser();

    if (user) {
      redirect("/setup");
    }
  }

  return (
    <main className="min-h-screen px-8 py-10">
      <section className="mx-auto flex max-w-3xl flex-col gap-6">
        <div>
          <h1 className="text-4xl font-semibold tracking-normal">Atlante BI</h1>
          <p className="mt-3 text-base leading-7 text-[color:var(--muted)]">
            Fondazione tecnica attiva. Questo step espone solo confini di
            prodotto, contract e healthcheck.
          </p>
        </div>
        <div className="flex gap-3">
          <a
            className="border border-[color:var(--accent)] px-4 py-2 text-sm font-medium"
            href="/login"
          >
            Accedi
          </a>
          <a
            className="border border-[color:var(--border)] px-4 py-2 text-sm font-medium"
            href="/setup"
          >
            Setup tenant
          </a>
        </div>
        <dl className="grid gap-3 border-t border-[color:var(--border)] pt-6 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-[color:var(--muted)]">Customer DB engines</dt>
            <dd className="mt-1 font-medium">{ENGINE_VALUES.join(", ")}</dd>
          </div>
          <div>
            <dt className="text-[color:var(--muted)]">Customer secrets</dt>
            <dd className="mt-1 font-medium">GCP Secret Manager reference only</dd>
          </div>
        </dl>
      </section>
    </main>
  );
}
