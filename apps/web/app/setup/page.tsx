import { redirect } from "next/navigation";

import { createTenant } from "./actions";
import { signOut } from "../auth/actions";
import { createSupabaseServerClient } from "../../lib/supabase/server";

type MembershipQueryRow = {
  role: string;
  status: string;
  tenants:
    | {
        id: string;
        name: string;
        slug: string;
      }
    | {
        id: string;
        name: string;
        slug: string;
      }[]
    | null;
};

const MESSAGE_COPY: Record<string, string> = {
  invalid_tenant: "Nome o slug tenant non validi.",
  tenant_create_failed: "Creazione tenant non riuscita.",
  supabase_not_configured: "Supabase non e configurato per questa installazione."
};

export const dynamic = "force-dynamic";

export default async function SetupPage({
  searchParams
}: {
  searchParams: Promise<{ created?: string; message?: string }>;
}) {
  const supabase = await createSupabaseServerClient();
  const params = await searchParams;

  if (!supabase) {
    return (
      <main className="min-h-screen px-8 py-10">
        <section className="mx-auto max-w-xl">
          <h1 className="text-3xl font-semibold">Configurazione mancante</h1>
          <p className="mt-3 text-sm leading-6 text-[color:var(--muted)]">
            Imposta NEXT_PUBLIC_SUPABASE_URL e NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY.
          </p>
        </section>
      </main>
    );
  }

  const {
    data: { user }
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const { data } = await supabase
    .from("tenant_memberships")
    .select("role,status,tenants(id,name,slug)")
    .eq("user_id", user.id)
    .eq("status", "active")
    .limit(10);

  const memberships = ((data ?? []) as unknown as MembershipQueryRow[]).map(
    (membership) => ({
      role: membership.role,
      status: membership.status,
      tenants: Array.isArray(membership.tenants)
        ? (membership.tenants[0] ?? null)
        : membership.tenants
    })
  );
  const message = params.message ? MESSAGE_COPY[params.message] : undefined;

  return (
    <main className="min-h-screen px-8 py-10">
      <section className="mx-auto flex max-w-2xl flex-col gap-8">
        <header className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-4xl font-semibold tracking-normal">Setup tenant</h1>
            <p className="mt-3 text-sm leading-6 text-[color:var(--muted)]">
              Crea o verifica il workspace Atlante BI associato al tuo account.
            </p>
          </div>
          <form>
            <button
              className="border border-[color:var(--border)] px-3 py-2 text-sm"
              formAction={signOut}
            >
              Esci
            </button>
          </form>
        </header>

        {params.created ? (
          <p className="border border-[color:var(--accent)] px-4 py-3 text-sm">
            Tenant creato.
          </p>
        ) : null}
        {message ? (
          <p className="border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--muted)]">
            {message}
          </p>
        ) : null}

        <form className="grid gap-4 border-t border-[color:var(--border)] pt-6">
          <label className="flex flex-col gap-2 text-sm">
            Nome azienda
            <input
              className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
              maxLength={160}
              minLength={2}
              name="name"
              required
            />
          </label>
          <label className="flex flex-col gap-2 text-sm">
            Slug tenant
            <input
              className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
              name="slug"
              pattern="[a-z0-9][a-z0-9-]{1,62}[a-z0-9]"
              required
            />
          </label>
          <button
            className="w-fit border border-[color:var(--accent)] px-4 py-2 text-sm font-medium"
            formAction={createTenant}
          >
            Crea tenant
          </button>
        </form>

        <section className="border-t border-[color:var(--border)] pt-6">
          <h2 className="text-lg font-medium">Tenant attivi</h2>
          {memberships.length === 0 ? (
            <p className="mt-3 text-sm text-[color:var(--muted)]">
              Nessun tenant attivo per questo utente.
            </p>
          ) : (
            <ul className="mt-4 grid gap-3">
              {memberships.map((membership) =>
                membership.tenants ? (
                  <li
                    className="border border-[color:var(--border)] px-4 py-3 text-sm"
                    key={membership.tenants.id}
                  >
                    <span className="font-medium">{membership.tenants.name}</span>
                    <span className="ml-2 text-[color:var(--muted)]">
                      /{membership.tenants.slug} · {membership.role}
                    </span>
                  </li>
                ) : null
              )}
            </ul>
          )}
        </section>
      </section>
    </main>
  );
}
