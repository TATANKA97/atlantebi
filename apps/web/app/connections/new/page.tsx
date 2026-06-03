import Link from "next/link";

import { createConnection } from "../actions";
import { getActiveTenantContext } from "../../../lib/tenant";

const MESSAGE_COPY: Record<string, string> = {
  connection_create_failed: "Creazione connessione non riuscita.",
  connection_save_failed: "Connessione verificata ma salvataggio metadata non riuscito.",
  connection_test_failed: "Test connessione non riuscito.",
  invalid_connection: "Dati connessione non validi."
};

export const dynamic = "force-dynamic";

export default async function NewConnectionPage({
  searchParams
}: {
  searchParams: Promise<{ message?: string }>;
}) {
  const params = await searchParams;
  const { tenantId } = await getActiveTenantContext();
  const message = params.message ? MESSAGE_COPY[params.message] : undefined;

  return (
    <main className="min-h-screen px-8 py-10">
      <section className="mx-auto flex max-w-3xl flex-col gap-7">
        <header>
          <Link className="text-sm text-[color:var(--muted)]" href="/connections">
            Connessioni
          </Link>
          <h1 className="mt-3 text-3xl font-semibold tracking-normal">
            Nuova connessione SQL Server
          </h1>
          <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">
            La password viene inviata solo al server e salvata in GCP Secret Manager.
          </p>
        </header>

        {message ? (
          <p className="border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--muted)]">
            {message}
          </p>
        ) : null}

        <form className="grid gap-5 border-t border-[color:var(--border)] pt-6">
          <input name="tenant_id" type="hidden" value={tenantId} />
          <input name="engine" type="hidden" value="sqlserver" />
          <input name="network_mode" type="hidden" value="public_allowlist" />

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm">
              Nome
              <input
                className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
                maxLength={160}
                minLength={2}
                name="name"
                required
              />
            </label>
            <label className="flex flex-col gap-2 text-sm">
              Timeout ms
              <input
                className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
                defaultValue="15000"
                max="120000"
                min="1000"
                name="timeout_ms"
                required
                type="number"
              />
            </label>
          </div>

          <div className="grid gap-4 sm:grid-cols-[1fr_9rem]">
            <label className="flex flex-col gap-2 text-sm">
              Host
              <input
                className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
                maxLength={255}
                name="host"
                required
              />
            </label>
            <label className="flex flex-col gap-2 text-sm">
              Porta
              <input
                className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
                max="65535"
                min="1"
                name="port"
                required
                type="number"
              />
            </label>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm">
              Database
              <input
                className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
                maxLength={255}
                name="database_name"
                required
              />
            </label>
            <label className="flex flex-col gap-2 text-sm">
              Username
              <input
                className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
                maxLength={255}
                name="username"
                required
              />
            </label>
          </div>

          <label className="flex flex-col gap-2 text-sm">
            Password
            <input
              autoComplete="off"
              className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
              name="password"
              required
              type="password"
            />
          </label>

          <label className="flex flex-col gap-2 text-sm">
            TLS server name
            <input
              className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
              maxLength={255}
              name="tls_server_name"
              required
            />
          </label>

          <div className="flex flex-wrap gap-5 border-t border-[color:var(--border)] pt-5 text-sm">
            <label className="flex items-center gap-2">
              <input defaultChecked name="tls_required" type="checkbox" />
              TLS
            </label>
            <label className="flex items-center gap-2">
              <input name="trust_server_certificate" type="checkbox" />
              Trust server certificate
            </label>
          </div>

          <button
            className="w-fit border border-[color:var(--accent)] px-4 py-2 text-sm font-medium"
            formAction={createConnection}
          >
            Salva e testa
          </button>
        </form>
      </section>
    </main>
  );
}
