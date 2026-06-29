import Link from "next/link";
import type { QueryIntentResult, SemanticLayer } from "@atlantebi/contracts";

import {
  QueryIntentServiceError,
  resolveQueryIntent
} from "../../lib/query-intent/service";
import {
  buildSemanticIndexes,
  metricFormulaLabel,
  semanticColumnLabel
} from "../../lib/semantic-layer/presentation";
import { getActiveTenantContext } from "../../lib/tenant";
import { WorkspaceTabs } from "../semantic/semantic-workspace";

type SearchParams = {
  connection?: string;
  question?: string;
};

type ConnectionRow = {
  id: string;
  name: string;
  engine: "sqlserver" | "mysql";
  database_name: string;
  status: string;
};

export const dynamic = "force-dynamic";

export default async function QueryIntentPage({
  searchParams
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const context = await getActiveTenantContext();
  const { data } = await context.supabase
    .from("db_connection_summaries")
    .select("id,name,engine,database_name,status")
    .eq("tenant_id", context.tenantId)
    .eq("status", "ready")
    .order("created_at", { ascending: false });
  const connections = (data ?? []) as ConnectionRow[];
  const selectedConnectionId = params.connection ?? connections[0]?.id ?? "";
  const question = params.question?.trim() ?? "";
  let result: QueryIntentResult | null = null;
  let semanticLayer: SemanticLayer | null = null;
  let error: string | null = null;

  if (selectedConnectionId && question) {
    try {
      const resolution = await resolveQueryIntent({
        connectionId: selectedConnectionId,
        context,
        question
      });
      result = resolution.result;
      semanticLayer = resolution.semanticLayer;
    } catch (caught) {
      error =
        caught instanceof QueryIntentServiceError
          ? caught.message
          : "Risoluzione intent fallita.";
    }
  }

  return (
    <main className="min-h-screen px-8 py-10">
      <section className="mx-auto flex max-w-6xl flex-col gap-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-normal">
              Query Intent Resolver
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--muted)]">
              Piano strutturato, senza SQL e senza esecuzione.
            </p>
          </div>
          <Link
            className="border border-[color:var(--border)] px-3 py-2 text-sm"
            href={
              selectedConnectionId
                ? `/semantic?connection=${selectedConnectionId}`
                : "/semantic"
            }
          >
            Semantic Layer
          </Link>
        </header>

        <WorkspaceTabs
          active="query-intent"
          {...(selectedConnectionId
            ? { connectionId: selectedConnectionId }
            : {})}
        />

        <form
          className="grid gap-4 border border-[color:var(--border)] p-4 md:grid-cols-[minmax(220px,320px)_1fr_auto]"
          method="get"
        >
          <label className="flex flex-col gap-2 text-sm">
            Connessione
            <select
              className="border border-[color:var(--border)] bg-transparent px-3 py-2"
              defaultValue={selectedConnectionId}
              name="connection"
            >
              {connections.map((connection) => (
                <option key={connection.id} value={connection.id}>
                  {connection.name} - {connection.database_name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-2 text-sm">
            Domanda
            <input
              className="border border-[color:var(--border)] bg-transparent px-3 py-2"
              defaultValue={question}
              name="question"
              placeholder="fatturato 2008"
              type="text"
            />
          </label>
          <button
            className="self-end border border-[color:var(--accent)] px-4 py-2 text-sm"
            type="submit"
          >
            Risolvi
          </button>
        </form>

        {error ? (
          <section className="border border-red-500/40 p-4">
            <h2 className="text-lg font-semibold">Errore</h2>
            <p className="mt-2 text-sm text-[color:var(--muted)]">{error}</p>
          </section>
        ) : null}

        {result ? (
          <IntentResult result={result} semanticLayer={semanticLayer} />
        ) : null}
      </section>
    </main>
  );
}

function IntentResult({
  result,
  semanticLayer
}: {
  result: QueryIntentResult;
  semanticLayer: SemanticLayer | null;
}) {
  const indexes = semanticLayer ? buildSemanticIndexes(semanticLayer) : null;
  const metric = result.plan
    ? semanticLayer?.metrics.find(
        (item) => item.metric_key === result.plan?.primary_metric_key
      )
    : undefined;
  const dateColumn =
    result.plan?.effective_date_column_key && indexes
      ? indexes.columns.get(result.plan.effective_date_column_key)
      : undefined;

  return (
    <section className="flex flex-col gap-4 border border-[color:var(--border)] p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">Risultato</h2>
        <span className="border border-[color:var(--border)] px-2 py-1 text-xs">
          {result.status}
        </span>
        {result.unsupported_reason ? (
          <span className="border border-red-500/40 px-2 py-1 text-xs">
            {result.unsupported_reason}
          </span>
        ) : null}
      </div>
      <p className="text-sm text-[color:var(--muted)]">{result.message}</p>

      {result.plan ? (
        <div className="grid gap-3 md:grid-cols-2">
          <SummaryRow label="Metric display name" value={metric?.name ?? "-"} />
          <SummaryRow
            label="Metric formula"
            value={metric && indexes ? metricFormulaLabel(metric, indexes) : "-"}
          />
          <SummaryRow
            label="Date display name"
            value={
              result.plan.effective_date_column_key && indexes
                ? semanticColumnLabel(dateColumn, indexes.tables)
                : "-"
            }
          />
          <SummaryRow
            label="Time range start"
            value={result.plan.time_range?.start_date ?? "-"}
          />
          <SummaryRow
            label="Time range end"
            value={result.plan.time_range?.end_date ?? "-"}
          />
          <SummaryRow label="Metric key" value={result.plan.primary_metric_key} />
          <SummaryRow
            label="Concept"
            value={`${result.plan.requested_concept_ref}/${result.plan.selected_variant}`}
          />
          <SummaryRow
            label="Date key"
            value={result.plan.effective_date_column_key ?? "-"}
          />
          <SummaryRow
            label="Time range"
            value={result.plan.time_range?.label ?? "-"}
          />
          <SummaryRow
            label="Group by"
            value={
              result.plan.group_by_dimensions
                .map((item) => item.column_key)
                .join(", ") || "-"
            }
          />
          <SummaryRow
            label="Edges"
            value={result.plan.required_edge_path_keys.join(", ") || "-"}
          />
        </div>
      ) : null}

      {result.clarification ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Chiarimento</h3>
          <p className="text-sm text-[color:var(--muted)]">
            {result.clarification.question}
          </p>
          <ul className="grid gap-2 md:grid-cols-2">
            {result.clarification.options.map((option) => (
              <li
                className="border border-[color:var(--border)] p-3 text-sm"
                key={option.value}
              >
                <div>{option.label}</div>
                <div className="mt-1 text-xs text-[color:var(--muted)]">
                  {option.business_concept_ref}/{option.metric_variant}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {result.plan?.disclosures.length ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Disclosure</h3>
          <ul className="list-disc pl-5 text-sm text-[color:var(--muted)]">
            {result.plan.disclosures.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {result.audit_trail.length ? (
        <details className="text-sm">
          <summary>Audit trail</summary>
          <pre className="mt-3 overflow-auto bg-black/20 p-3 text-xs">
            {JSON.stringify(result.audit_trail, null, 2)}
          </pre>
        </details>
      ) : null}
    </section>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-[color:var(--border)] p-3">
      <div className="text-xs uppercase text-[color:var(--muted)]">{label}</div>
      <div className="mt-1 break-all text-sm">{value}</div>
    </div>
  );
}
