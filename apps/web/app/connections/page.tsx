import Link from "next/link";

import { getActiveTenantContext } from "../../lib/tenant";

type ConnectionSummaryRow = {
  id: string;
  name: string;
  engine: string;
  network_mode: string;
  host: string;
  port: number;
  database_name: string;
  username: string;
  tls_required: boolean;
  tls_server_name: string | null;
  trust_server_certificate: boolean;
  status: string;
  last_test_status: string | null;
  last_test_error: string | null;
  last_tested_at: string | null;
};

const MESSAGE_COPY: Record<string, string> = {
  connection_forbidden: "Il tuo ruolo non consente di gestire connessioni.",
  connection_saved_test_failed:
    "Connessione salvata, ma il test e fallito. Correggi i metadata e riprova."
};

export const dynamic = "force-dynamic";

export default async function ConnectionsPage({
  searchParams
}: {
  searchParams: Promise<{ created?: string; updated?: string; message?: string }>;
}) {
  const params = await searchParams;
  const { supabase, tenantId } = await getActiveTenantContext();
  const { data } = await supabase
    .from("db_connection_summaries")
    .select(
      "id,name,engine,network_mode,host,port,database_name,username,tls_required,tls_server_name,trust_server_certificate,status,last_test_status,last_test_error,last_tested_at"
    )
    .eq("tenant_id", tenantId)
    .order("created_at", { ascending: false })
    .limit(50);
  const connections = (data ?? []) as ConnectionSummaryRow[];
  const message = params.message ? MESSAGE_COPY[params.message] : undefined;

  return (
    <main className="min-h-screen px-8 py-10">
      <section className="mx-auto flex max-w-5xl flex-col gap-7">
        <header className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-normal">Connessioni</h1>
            <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">
              Metadata connessioni tenant. Le password restano in GCP Secret Manager.
            </p>
          </div>
          <div className="flex gap-3">
            <Link
              className="border border-[color:var(--border)] px-4 py-2 text-sm font-medium"
              href="/semantic"
            >
              Semantic layer
            </Link>
            <Link
              className="border border-[color:var(--accent)] px-4 py-2 text-sm font-medium"
              href="/connections/new"
            >
              Nuova connessione
            </Link>
          </div>
        </header>

        {params.created ? (
          <p className="border border-[color:var(--accent)] px-4 py-3 text-sm">
            Connessione salvata.
          </p>
        ) : null}
        {params.updated ? (
          <p className="border border-[color:var(--accent)] px-4 py-3 text-sm">
            Connessione aggiornata.
          </p>
        ) : null}
        {message ? (
          <p className="border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--muted)]">
            {message}
          </p>
        ) : null}

        {connections.length === 0 ? (
          <section className="border-t border-[color:var(--border)] pt-6">
            <p className="text-sm text-[color:var(--muted)]">
              Nessuna connessione configurata.
            </p>
          </section>
        ) : (
          <div className="overflow-x-auto border-t border-[color:var(--border)] pt-6">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="text-[color:var(--muted)]">
                <tr>
                  <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                    Nome
                  </th>
                  <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                    Engine
                  </th>
                  <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                    Host
                  </th>
                  <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                    Database
                  </th>
                  <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                    Stato
                  </th>
                  <th className="border-b border-[color:var(--border)] py-2 font-medium">
                    Ultimo test
                  </th>
                  <th className="border-b border-[color:var(--border)] py-2 font-medium">
                    Azioni
                  </th>
                </tr>
              </thead>
              <tbody>
                {connections.map((connection) => (
                  <tr key={connection.id}>
                    <td className="border-b border-[color:var(--border)] py-3 pr-4">
                      <div className="font-medium">{connection.name}</div>
                      <div className="text-xs text-[color:var(--muted)]">
                        {connection.username}
                      </div>
                    </td>
                    <td className="border-b border-[color:var(--border)] py-3 pr-4">
                      {connection.engine}
                    </td>
                    <td className="border-b border-[color:var(--border)] py-3 pr-4">
                      {connection.host}:{connection.port}
                    </td>
                    <td className="border-b border-[color:var(--border)] py-3 pr-4">
                      {connection.database_name}
                    </td>
                    <td className="border-b border-[color:var(--border)] py-3 pr-4">
                      {connection.status}
                    </td>
                    <td className="border-b border-[color:var(--border)] py-3">
                      <div>{connection.last_test_status ?? "mai"}</div>
                      {connection.last_test_error ? (
                        <div className="mt-1 max-w-xs text-xs text-[color:var(--muted)]">
                          {connection.last_test_error}
                        </div>
                      ) : null}
                    </td>
                    <td className="border-b border-[color:var(--border)] py-3">
                      <Link
                        className="text-sm text-[color:var(--accent)]"
                        href={`/connections/${connection.id}/edit`}
                      >
                        Modifica
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
