import Link from "next/link";
import { notFound } from "next/navigation";

import { updateConnection } from "../../actions";
import { getActiveTenantContext } from "../../../../lib/tenant";

type ConnectionRow = {
  id: string;
  name: string;
  engine: "sqlserver";
  network_mode: "public_allowlist";
  host: string;
  port: number;
  database_name: string;
  username: string;
  tls_required: boolean;
  tls_server_name: string | null;
  trust_server_certificate: boolean;
  last_test_error: string | null;
};

const MESSAGE_COPY: Record<string, string> = {
  connection_save_failed: "Metadata connessione non salvati.",
  connection_update_failed: "Aggiornamento connessione non riuscito.",
  invalid_connection: "Dati connessione non validi."
};

export const dynamic = "force-dynamic";

export default async function EditConnectionPage({
  params,
  searchParams
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ message?: string }>;
}) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const { supabase, tenantId } = await getActiveTenantContext();
  const { data } = await supabase
    .from("db_connection_summaries")
    .select(
      "id,name,engine,network_mode,host,port,database_name,username,tls_required,tls_server_name,trust_server_certificate,last_test_error"
    )
    .eq("tenant_id", tenantId)
    .eq("id", id)
    .single();

  if (!data) {
    notFound();
  }

  const connection = data as ConnectionRow;
  const message = query.message ? MESSAGE_COPY[query.message] : undefined;

  return (
    <main className="min-h-screen px-8 py-10">
      <section className="mx-auto flex max-w-3xl flex-col gap-7">
        <header>
          <Link className="text-sm text-[color:var(--muted)]" href="/connections">
            Connessioni
          </Link>
          <h1 className="mt-3 text-3xl font-semibold tracking-normal">
            Modifica connessione SQL Server
          </h1>
          <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">
            I metadata sono salvati in Supabase. La password resta in GCP Secret
            Manager e viene aggiornata solo se ne inserisci una nuova.
          </p>
        </header>

        {message ? (
          <p className="border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--muted)]">
            {message}
          </p>
        ) : null}
        {connection.last_test_error ? (
          <p className="border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--muted)]">
            Ultimo errore test: {connection.last_test_error}
          </p>
        ) : null}

        <form className="grid gap-5 border-t border-[color:var(--border)] pt-6">
          <input name="tenant_id" type="hidden" value={tenantId} />
          <input name="connection_id" type="hidden" value={connection.id} />
          <input name="engine" type="hidden" value={connection.engine} />
          <input name="network_mode" type="hidden" value={connection.network_mode} />

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm">
              Nome
              <input
                className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
                defaultValue={connection.name}
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
                defaultValue="120000"
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
                defaultValue={connection.host}
                maxLength={255}
                name="host"
                required
              />
            </label>
            <label className="flex flex-col gap-2 text-sm">
              Porta
              <input
                className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
                defaultValue={connection.port}
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
                defaultValue={connection.database_name}
                maxLength={255}
                name="database_name"
                required
              />
            </label>
            <label className="flex flex-col gap-2 text-sm">
              Username
              <input
                className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
                defaultValue={connection.username}
                maxLength={255}
                name="username"
                required
              />
            </label>
          </div>

          <label className="flex flex-col gap-2 text-sm">
            Nuova password
            <input
              autoComplete="off"
              className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
              name="password"
              type="password"
            />
          </label>

          <label className="flex flex-col gap-2 text-sm">
            TLS server name
            <input
              className="border border-[color:var(--border)] bg-transparent px-3 py-2 text-base"
              defaultValue={connection.tls_server_name ?? ""}
              maxLength={255}
              name="tls_server_name"
              required
            />
          </label>

          <div className="flex flex-wrap gap-5 border-t border-[color:var(--border)] pt-5 text-sm">
            <label className="flex items-center gap-2">
              <input
                defaultChecked={connection.tls_required}
                name="tls_required"
                type="checkbox"
              />
              TLS
            </label>
            <label className="flex items-center gap-2">
              <input
                defaultChecked={connection.trust_server_certificate}
                name="trust_server_certificate"
                type="checkbox"
              />
              Trust server certificate
            </label>
          </div>

          <button
            className="w-fit border border-[color:var(--accent)] px-4 py-2 text-sm font-medium"
            formAction={updateConnection}
          >
            Salva e ritesta
          </button>
        </form>
      </section>
    </main>
  );
}
