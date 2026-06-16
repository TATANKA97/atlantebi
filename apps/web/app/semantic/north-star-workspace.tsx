import Link from "next/link";
import type {
  NorthStarBenchmark,
  SemanticLayer,
  SemanticMetric
} from "@atlantebi/contracts";

import {
  deleteNorthStarBenchmarkAction,
  upsertNorthStarBenchmarkAction
} from "./actions";
import { WorkspaceTabs } from "./semantic-workspace";
import { listNorthStarBenchmarks } from "../../lib/north-star-benchmarks/service";
import {
  buildSemanticIndexes,
  metricFormulaLabel,
  metricGrainLabel
} from "../../lib/semantic-layer/presentation";
import { readCurrentSemanticLayer } from "../../lib/semantic-layer/service";
import {
  canManageSemanticLayer,
  getActiveTenantContext
} from "../../lib/tenant";

type ConnectionRow = {
  id: string;
  name: string;
  engine: "sqlserver" | "mysql";
  database_name: string;
  status: string;
};

type NorthStarWorkspaceParams = {
  connection?: string;
  message?: string;
};

const MESSAGE_COPY: Record<string, string> = {
  invalid_north_star: "Benchmark North Star non valido.",
  invalid_north_star_delete: "Eliminazione benchmark non valida.",
  north_star_created: "Benchmark North Star creato.",
  north_star_deleted: "Benchmark North Star eliminato.",
  north_star_failed: "Operazione North Star fallita.",
  north_star_forbidden:
    "Solo owner e admin possono modificare le North Star.",
  north_star_invalid: "Benchmark North Star non coerente.",
  north_star_not_found: "Benchmark North Star non trovato.",
  north_star_updated: "Benchmark North Star aggiornato."
};

export async function NorthStarWorkspace({
  searchParams
}: {
  searchParams: NorthStarWorkspaceParams;
}) {
  const context = await getActiveTenantContext();
  const canManage = canManageSemanticLayer(context.role);
  const { data } = await context.supabase
    .from("db_connection_summaries")
    .select("id,name,engine,database_name,status")
    .eq("tenant_id", context.tenantId)
    .eq("status", "ready")
    .order("created_at", { ascending: false });
  const connections = (data ?? []) as ConnectionRow[];
  const selectedConnection =
    connections.find((connection) => connection.id === searchParams.connection) ??
    connections[0] ??
    null;
  const currentSemantic = selectedConnection
    ? await readCurrentSemanticLayer({
        connectionId: selectedConnection.id,
        context
      })
    : null;
  const benchmarks = selectedConnection
    ? await listNorthStarBenchmarks({
        connectionId: selectedConnection.id,
        context
      })
    : [];
  const message = searchParams.message
    ? MESSAGE_COPY[searchParams.message] ?? searchParams.message
    : null;

  return (
    <main className="min-h-screen px-4 py-8 sm:px-8 sm:py-10">
      <div className="mx-auto flex max-w-7xl flex-col gap-7">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal sm:text-3xl">
              North Star Benchmarks
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--muted)]">
              Valori attesi per controlli di plausibilita futuri. Non cambiano
              formula, queryability o Semantic Layer.
            </p>
          </div>
          <Link
            className="border border-[color:var(--border)] px-4 py-2 text-sm font-medium"
            href="/connections"
          >
            Connessioni
          </Link>
        </header>

        <WorkspaceTabs
          active="north-stars"
          {...(selectedConnection
            ? { connectionId: selectedConnection.id }
            : {})}
        />

        {message ? (
          <p
            aria-live="polite"
            className="border-l-2 border-[color:var(--accent)] py-2 pl-4 text-sm"
            role="status"
          >
            {message}
          </p>
        ) : null}

        <ConnectionSelector
          connections={connections}
          {...(selectedConnection
            ? { selectedConnectionId: selectedConnection.id }
            : {})}
        />

        {!selectedConnection ? (
          <EmptyState
            detail="Collega e valida un database prima di definire benchmark."
            title="Nessuna connessione pronta"
          />
        ) : (
          <NorthStarContent
            benchmarks={benchmarks}
            canManage={canManage}
            connection={selectedConnection}
            currentSemantic={currentSemantic?.artifact ?? null}
            currentSemanticStatus={currentSemantic?.summary.status ?? null}
            currentSemanticVersionId={
              currentSemantic?.artifact.semantic_version_id ?? null
            }
            currentSemanticFreshness={
              currentSemantic?.summary.effective_freshness ?? null
            }
            tenantId={context.tenantId}
          />
        )}
      </div>
    </main>
  );
}

function NorthStarContent({
  benchmarks,
  canManage,
  connection,
  currentSemantic,
  currentSemanticFreshness,
  currentSemanticStatus,
  currentSemanticVersionId,
  tenantId
}: {
  benchmarks: NorthStarBenchmark[];
  canManage: boolean;
  connection: ConnectionRow;
  currentSemantic: SemanticLayer | null;
  currentSemanticFreshness: "fresh" | "stale" | null;
  currentSemanticStatus: "draft" | "proposed" | "active" | "archived" | null;
  currentSemanticVersionId: string | null;
  tenantId: string;
}) {
  const eligibleMetrics = currentSemantic
    ? currentSemantic.metrics.filter(
        (metric) =>
          metric.enabled &&
          ["eligible", "eligible_with_disclosure"].includes(
            metric.compiler_eligibility
          )
      )
    : [];
  const canAttachMetric =
    currentSemanticStatus === "active" &&
    currentSemanticFreshness === "fresh" &&
    Boolean(currentSemanticVersionId) &&
    eligibleMetrics.length > 0;

  return (
    <>
      <section className="grid gap-4 border border-[color:var(--border)] p-4 text-sm md:grid-cols-4">
        <SummaryItem label="Connessione" value={connection.name} />
        <SummaryItem
          label="Semantic Layer"
          value={
            currentSemantic
              ? `${currentSemanticStatus ?? "unknown"} / ${currentSemanticFreshness ?? "unknown"}`
              : "not initialized"
          }
        />
        <SummaryItem
          label="Metriche agganciabili"
          value={canAttachMetric ? String(eligibleMetrics.length) : "0"}
        />
        <SummaryItem label="Benchmark" value={String(benchmarks.length)} />
      </section>

      {canManage ? (
        canAttachMetric && currentSemantic && currentSemanticVersionId ? (
          <BenchmarkForm
            connectionId={connection.id}
            metrics={eligibleMetrics}
            semanticLayer={currentSemantic}
            semanticVersionId={currentSemanticVersionId}
            tenantId={tenantId}
          />
        ) : (
          <p className="border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--muted)]">
            Serve un Semantic Layer active e fresh con metriche eligible per
            collegare una North Star a una metrica.
          </p>
        )
      ) : (
        <p className="border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--muted)]">
          Il tuo ruolo consente solo la lettura dei benchmark.
        </p>
      )}

      <BenchmarkTable
        benchmarks={benchmarks}
        canManage={canManage}
        connectionId={connection.id}
        currentSemantic={currentSemantic}
        metrics={eligibleMetrics}
        semanticVersionId={canAttachMetric ? currentSemanticVersionId : null}
        tenantId={tenantId}
      />
    </>
  );
}

function BenchmarkForm({
  benchmark,
  connectionId,
  metrics,
  semanticLayer,
  semanticVersionId,
  tenantId
}: {
  benchmark?: NorthStarBenchmark;
  connectionId: string;
  metrics: SemanticMetric[];
  semanticLayer?: SemanticLayer;
  semanticVersionId?: string;
  tenantId: string;
}) {
  const indexes = semanticLayer ? buildSemanticIndexes(semanticLayer) : null;
  const isConnectionBenchmark = benchmark?.metric_key === null;
  const selectedMetricKey = isConnectionBenchmark
    ? undefined
    : benchmark?.metric_key &&
        metrics.some((metric) => metric.metric_key === benchmark.metric_key)
      ? benchmark.metric_key
      : metrics[0]?.metric_key;
  const selectedMetric = selectedMetricKey
    ? metrics.find((metric) => metric.metric_key === selectedMetricKey)
    : undefined;
  return (
    <form
      action={upsertNorthStarBenchmarkAction}
      className="grid gap-4 border border-[color:var(--border)] p-4 text-sm md:grid-cols-4"
    >
      <input name="tenant_id" type="hidden" value={tenantId} />
      <input name="connection_id" type="hidden" value={connectionId} />
      <input
        name="semantic_version_id"
        type="hidden"
        value={isConnectionBenchmark ? "" : (semanticVersionId ?? "")}
      />
      {isConnectionBenchmark ? (
        <input name="metric_key" type="hidden" value="" />
      ) : null}
      {benchmark ? (
        <input
          name="benchmark_key"
          type="hidden"
          value={benchmark.benchmark_key}
        />
      ) : null}

      {!isConnectionBenchmark && indexes ? (
        <label className="flex flex-col gap-1 md:col-span-2">
          <span className="text-xs text-[color:var(--muted)]">Metrica</span>
          <select
            className="border border-[color:var(--border)] bg-transparent px-3 py-2"
            defaultValue={selectedMetricKey}
            name="metric_key"
            required
          >
            {metrics.map((metric) => (
              <option key={metric.metric_key} value={metric.metric_key}>
                {metric.name} - {metricFormulaLabel(metric, indexes)}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <label className="flex flex-col gap-1 md:col-span-2">
        <span className="text-xs text-[color:var(--muted)]">Nome</span>
        <input
          className="border border-[color:var(--border)] bg-transparent px-3 py-2"
          defaultValue={benchmark?.name ?? ""}
          maxLength={255}
          name="name"
          required
        />
      </label>

      <label className="flex flex-col gap-1 md:col-span-2">
        <span className="text-xs text-[color:var(--muted)]">Descrizione</span>
        <input
          className="border border-[color:var(--border)] bg-transparent px-3 py-2"
          defaultValue={benchmark?.description ?? ""}
          maxLength={2000}
          name="description"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[color:var(--muted)]">Valore atteso</span>
        <input
          className="border border-[color:var(--border)] bg-transparent px-3 py-2"
          defaultValue={benchmark?.expected_value ?? ""}
          name="expected_value"
          required
          step="any"
          type="number"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[color:var(--muted)]">Tipo valore</span>
        <select
          className="border border-[color:var(--border)] bg-transparent px-3 py-2"
          defaultValue={benchmark?.value_type ?? "currency"}
          name="value_type"
        >
          <option value="currency">currency</option>
          <option value="number">number</option>
          <option value="percentage">percentage</option>
          <option value="count">count</option>
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[color:var(--muted)]">Currency</span>
        <input
          className="border border-[color:var(--border)] bg-transparent px-3 py-2"
          defaultValue={benchmark?.currency ?? "EUR"}
          maxLength={3}
          name="currency"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[color:var(--muted)]">Periodo</span>
        <select
          className="border border-[color:var(--border)] bg-transparent px-3 py-2"
          defaultValue={benchmark?.period_type ?? "year"}
          name="period_type"
        >
          <option value="day">day</option>
          <option value="week">week</option>
          <option value="month">month</option>
          <option value="quarter">quarter</option>
          <option value="year">year</option>
          <option value="rolling_12_months">rolling_12_months</option>
          <option value="custom">custom</option>
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[color:var(--muted)]">Dal</span>
        <input
          className="border border-[color:var(--border)] bg-transparent px-3 py-2"
          defaultValue={benchmark?.period_start ?? ""}
          name="period_start"
          type="date"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[color:var(--muted)]">Al</span>
        <input
          className="border border-[color:var(--border)] bg-transparent px-3 py-2"
          defaultValue={benchmark?.period_end ?? ""}
          name="period_end"
          type="date"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[color:var(--muted)]">Tolleranza</span>
        <select
          className="border border-[color:var(--border)] bg-transparent px-3 py-2"
          defaultValue={benchmark?.tolerance_mode ?? "percentage"}
          name="tolerance_mode"
        >
          <option value="percentage">percentage</option>
          <option value="absolute">absolute</option>
          <option value="range">range</option>
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[color:var(--muted)]">Tolleranza %</span>
        <input
          className="border border-[color:var(--border)] bg-transparent px-3 py-2"
          defaultValue={
            !benchmark || benchmark.tolerance_mode === "percentage"
              ? benchmark?.tolerance_percentage ?? 10
              : ""
          }
          name="tolerance_percentage"
          step="any"
          type="number"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[color:var(--muted)]">Min</span>
        <input
          className="border border-[color:var(--border)] bg-transparent px-3 py-2"
          defaultValue={benchmark?.min_value ?? ""}
          name="min_value"
          step="any"
          type="number"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[color:var(--muted)]">Max</span>
        <input
          className="border border-[color:var(--border)] bg-transparent px-3 py-2"
          defaultValue={benchmark?.max_value ?? ""}
          name="max_value"
          step="any"
          type="number"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[color:var(--muted)]">Severity</span>
        <select
          className="border border-[color:var(--border)] bg-transparent px-3 py-2"
          defaultValue={benchmark?.severity ?? "medium"}
          name="severity"
        >
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
          <option value="critical">critical</option>
        </select>
      </label>

      <label className="flex items-center gap-2">
        <input
          defaultChecked={benchmark?.enabled ?? true}
          name="enabled"
          type="checkbox"
        />
        <span>Enabled</span>
      </label>

      <div className="md:col-span-4">
        <button
          className="border border-[color:var(--accent)] px-4 py-2 text-sm font-medium"
          type="submit"
        >
          {benchmark ? "Salva benchmark" : "Crea benchmark"}
        </button>
      </div>

      {selectedMetric && indexes ? (
        <p className="md:col-span-4 text-xs text-[color:var(--muted)]">
          Grain metrica: {metricGrainLabel(selectedMetric, indexes)}
        </p>
      ) : null}
    </form>
  );
}

function BenchmarkTable({
  benchmarks,
  canManage,
  connectionId,
  currentSemantic,
  metrics,
  semanticVersionId,
  tenantId
}: {
  benchmarks: NorthStarBenchmark[];
  canManage: boolean;
  connectionId: string;
  currentSemantic: SemanticLayer | null;
  metrics: SemanticMetric[];
  semanticVersionId: string | null;
  tenantId: string;
}) {
  const metricMap = new Map(metrics.map((metric) => [metric.metric_key, metric]));
  return (
    <section className="border-t border-[color:var(--border)] pt-6">
      <h2 className="text-base font-semibold">Benchmark salvati</h2>
      {benchmarks.length === 0 ? (
        <p className="mt-3 text-sm text-[color:var(--muted)]">
          Nessuna North Star salvata per questa connessione.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[1050px] border-collapse text-left text-xs">
            <thead className="text-[color:var(--muted)]">
              <tr>
                {[
                  "Benchmark",
                  "Metrica",
                  "Valore",
                  "Periodo",
                  "Tolleranza",
                  "Severity",
                  "Stato",
                  "Azioni"
                ].map((label) => (
                  <th
                    className="border-b border-[color:var(--border)] py-2 pr-4 font-medium"
                    key={label}
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {benchmarks.map((benchmark) => {
                const metric = benchmark.metric_key
                  ? metricMap.get(benchmark.metric_key)
                  : undefined;
                const canEditBenchmark =
                  benchmark.metric_key === null ||
                  Boolean(currentSemantic && semanticVersionId && metric);
                return (
                  <tr key={benchmark.benchmark_key}>
                    <th className="border-b border-[color:var(--border)] py-3 pr-4 text-left align-top font-normal">
                      <div className="font-medium">{benchmark.name}</div>
                      {benchmark.description ? (
                        <div className="mt-1 max-w-64 text-[color:var(--muted)]">
                          {benchmark.description}
                        </div>
                      ) : null}
                    </th>
                    <td className="border-b border-[color:var(--border)] py-3 pr-4 align-top">
                      {metric ? (
                        <>
                          <div>{metric.name}</div>
                          <div className="mt-1 font-mono text-[color:var(--muted)]">
                            {metric.canonical_name}
                          </div>
                        </>
                      ) : benchmark.metric_key ? (
                        <span className="text-[color:var(--muted)]">
                          metrica non presente nella versione corrente
                        </span>
                      ) : (
                        "connection benchmark"
                      )}
                    </td>
                    <td className="border-b border-[color:var(--border)] py-3 pr-4 align-top">
                      {formatExpectedValue(benchmark)}
                    </td>
                    <td className="border-b border-[color:var(--border)] py-3 pr-4 align-top">
                      <div>{benchmark.period_type}</div>
                      {benchmark.period_start || benchmark.period_end ? (
                        <div className="mt-1 text-[color:var(--muted)]">
                          {benchmark.period_start ?? "..."} -{" "}
                          {benchmark.period_end ?? "..."}
                        </div>
                      ) : null}
                    </td>
                    <td className="border-b border-[color:var(--border)] py-3 pr-4 align-top">
                      {formatTolerance(benchmark)}
                    </td>
                    <td className="border-b border-[color:var(--border)] py-3 pr-4 align-top">
                      {benchmark.severity}
                    </td>
                    <td className="border-b border-[color:var(--border)] py-3 pr-4 align-top">
                      {benchmark.enabled ? "enabled" : "disabled"}
                    </td>
                    <td className="border-b border-[color:var(--border)] py-3 align-top">
                      {canManage ? (
                        <div className="flex flex-col gap-3">
                          {canEditBenchmark ? (
                            <details>
                              <summary className="cursor-pointer text-[color:var(--accent)]">
                                Modifica
                              </summary>
                              <div className="mt-3 min-w-[900px]">
                                <BenchmarkForm
                                  benchmark={benchmark}
                                  connectionId={connectionId}
                                  metrics={metrics}
                                  {...(currentSemantic
                                    ? { semanticLayer: currentSemantic }
                                    : {})}
                                  {...(semanticVersionId
                                    ? { semanticVersionId }
                                    : {})}
                                  tenantId={tenantId}
                                />
                              </div>
                            </details>
                          ) : (
                            <span className="text-[color:var(--muted)]">
                              Modifica non disponibile: metrica non eligible
                              nella versione active/fresh corrente.
                            </span>
                          )}
                          <form action={deleteNorthStarBenchmarkAction}>
                            <input name="tenant_id" type="hidden" value={tenantId} />
                            <input
                              name="connection_id"
                              type="hidden"
                              value={connectionId}
                            />
                            <input
                              name="benchmark_key"
                              type="hidden"
                              value={benchmark.benchmark_key}
                            />
                            <button
                              className="text-xs text-[color:var(--danger)]"
                              type="submit"
                            >
                              Elimina
                            </button>
                          </form>
                        </div>
                      ) : (
                        <span className="text-[color:var(--muted)]">
                          Sola lettura
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ConnectionSelector({
  connections,
  selectedConnectionId
}: {
  connections: ConnectionRow[];
  selectedConnectionId?: string;
}) {
  if (connections.length === 0) {
    return null;
  }
  return (
    <section>
      <h2 className="text-xs font-medium uppercase text-[color:var(--muted)]">
        Connessione
      </h2>
      <div className="mt-3 flex flex-wrap gap-2">
        {connections.map((connection) => (
          <Link
            className={`border px-3 py-1.5 text-sm ${
              connection.id === selectedConnectionId
                ? "border-[color:var(--accent)]"
                : "border-[color:var(--border)] text-[color:var(--muted)]"
            }`}
            href={`/semantic?tab=north-stars&connection=${connection.id}`}
            key={connection.id}
          >
            {connection.name}
          </Link>
        ))}
      </div>
    </section>
  );
}

function EmptyState({ detail, title }: { detail: string; title: string }) {
  return (
    <section className="border border-dashed border-[color:var(--border)] p-6">
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mt-2 text-sm text-[color:var(--muted)]">{detail}</p>
    </section>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase text-[color:var(--muted)]">{label}</div>
      <div className="mt-1 font-medium">{value}</div>
    </div>
  );
}

function formatExpectedValue(benchmark: NorthStarBenchmark) {
  const value = new Intl.NumberFormat("it-IT", {
    maximumFractionDigits: 2
  }).format(benchmark.expected_value);
  if (benchmark.value_type === "currency") {
    return `${value} ${benchmark.currency ?? ""}`.trim();
  }
  if (benchmark.value_type === "percentage") {
    return `${value}%`;
  }
  return value;
}

function formatTolerance(benchmark: NorthStarBenchmark) {
  if (benchmark.tolerance_mode === "percentage") {
    return `+/- ${benchmark.tolerance_percentage}%`;
  }
  return `${benchmark.min_value} - ${benchmark.max_value}`;
}
