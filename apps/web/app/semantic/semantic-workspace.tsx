import Link from "next/link";
import type {
  SemanticLayer,
  SemanticMetric,
  SemanticValidationIssue
} from "@atlantebi/contracts";

import {
  activateSemanticVersionAction,
  archiveSemanticVersionAction,
  confirmSemanticMetricAction,
  correctSemanticMetricAction,
  createAndGenerateSemanticDraftAction,
  disableSemanticMetricAction,
  generateSemanticDraftAction,
  rebaseSemanticVersionAction,
  validateSemanticDraftAction
} from "./actions";
import {
  listSemanticVersions,
  readSemanticLayerVersion,
  type SemanticVersionSummary
} from "../../lib/semantic-layer/service";
import {
  buildSemanticIndexes,
  confidenceLabel,
  metricConceptLabel,
  metricFormulaLabel,
  metricGrainLabel,
  paginateItems,
  semanticLayerCounts,
  validationIssueCounts
} from "../../lib/semantic-layer/presentation";
import {
  canManageSemanticLayer,
  getActiveTenantContext
} from "../../lib/tenant";
import { SubmitButton } from "./submit-button";

type ConnectionRow = {
  id: string;
  name: string;
  engine: "sqlserver" | "mysql";
  database_name: string;
  status: string;
};

type SemanticWorkspaceParams = {
  ambiguities_page?: string;
  catalog_page?: string;
  connection?: string;
  issues_page?: string;
  message?: string;
  metrics_page?: string;
  semantic?: string;
};

const MESSAGE_COPY: Record<string, string> = {
  invalid_semantic_activation: "Richiesta di attivazione non valida.",
  invalid_semantic_archive: "Richiesta di archiviazione non valida.",
  invalid_semantic_draft: "Richiesta di creazione proposta non valida.",
  invalid_semantic_generation: "Richiesta di generazione non valida.",
  invalid_semantic_metric_update: "Aggiornamento metrica non valido.",
  invalid_semantic_rebase: "Richiesta di rebase non valida.",
  invalid_semantic_validation: "Richiesta di validazione non valida.",
  semantic_activation_failed: "Attivazione Semantic Layer fallita.",
  semantic_ai_not_configured:
    "La generazione AI non e configurata nel query-engine.",
  semantic_ai_provider_not_configured:
    "Configura un provider AI prima di generare una proposta.",
  semantic_archive_failed: "Archiviazione Semantic Layer fallita.",
  semantic_forbidden:
    "Solo owner e admin possono modificare il Semantic Layer.",
  semantic_generation_failed: "Generazione AI della proposta fallita.",
  semantic_generation_rate_limited:
    "Una generazione e gia in corso o il limite temporale e stato raggiunto.",
  semantic_internal_error: "Operazione Semantic Layer fallita.",
  semantic_metric_confirmed: "Metrica confermata e proposta rivalidata.",
  semantic_metric_corrected: "Metrica corretta e proposta rivalidata.",
  semantic_metric_disabled: "Metrica disabilitata e proposta rivalidata.",
  semantic_proposal_generated: "Proposta semantica generata e validata.",
  semantic_proposal_invalid: "La proposta AI non rispetta i vincoli tecnici.",
  semantic_proposal_validated: "Proposta semantica validata.",
  semantic_rebase_failed: "Rebase Semantic Layer fallito.",
  semantic_review_invalid:
    "La correzione non rispetta i vincoli tecnici del Semantic Layer.",
  semantic_revision_conflict:
    "La proposta è cambiata in un'altra sessione. Ricarica prima di riprovare.",
  semantic_version_activated: "Versione Semantic Layer attivata.",
  semantic_version_archived: "Versione Semantic Layer archiviata.",
  semantic_version_rebased: "Nuova draft creata sul graph corrente.",
  semantic_version_stale:
    "La versione si basa su un graph precedente e deve essere ribasata."
};

const METRICS_PAGE_SIZE = 50;
const AMBIGUITIES_PAGE_SIZE = 50;
const VALIDATION_ISSUES_PAGE_SIZE = 100;
const CATALOG_TABLES_PAGE_SIZE = 50;

export async function SemanticWorkspace({
  searchParams
}: {
  searchParams: SemanticWorkspaceParams;
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
  const versions = selectedConnection
    ? await listSemanticVersions({
        connectionId: selectedConnection.id,
        context
      })
    : [];
  const selectedSummary = selectVersion(versions, searchParams.semantic);
  const selected = selectedSummary
    ? await readSemanticLayerVersion({
        context,
        semanticVersionId: selectedSummary.id
      })
    : null;
  const message = searchParams.message
    ? MESSAGE_COPY[searchParams.message] ?? searchParams.message
    : null;

  return (
    <main className="min-h-screen px-4 py-8 sm:px-8 sm:py-10">
      <div className="mx-auto flex max-w-7xl flex-col gap-7">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal sm:text-3xl">
              Semantic Workspace
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--muted)]">
              Proposte business generate da Atlante, validate contro il
              Queryability Graph e governate per versione.
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
          active="semantic"
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
            detail="Collega e valida un database prima di generare una proposta semantica."
            title="Nessuna connessione pronta"
          />
        ) : (
          <>
            <VersionToolbar
              canManage={canManage}
              connection={selectedConnection}
              selected={selected?.summary ?? null}
              tenantId={context.tenantId}
              versions={versions}
            />
            {selected ? (
              <SemanticLayerDetail
                canManage={canManage}
                connectionId={selectedConnection.id}
                layer={selected.artifact}
                searchParams={searchParams}
                summary={selected.summary}
                tenantId={context.tenantId}
              />
            ) : (
              <EmptyState
                detail={
                  canManage
                    ? "Crea la prima proposta: Atlante costruirà seed, proposta AI e validazione."
                    : "Un owner o admin deve generare la prima proposta."
                }
                title="Semantic Layer non inizializzato"
              />
            )}
          </>
        )}
      </div>
    </main>
  );
}

export function WorkspaceTabs({
  active,
  connectionId
}: {
  active: "semantic" | "technical" | "north-stars" | "ai-provider";
  connectionId?: string;
}) {
  const semanticHref = connectionId
    ? `/semantic?connection=${connectionId}`
    : "/semantic";
  const technicalHref = connectionId
    ? `/semantic?tab=technical&connection=${connectionId}`
    : "/semantic?tab=technical";
  const northStarsHref = connectionId
    ? `/semantic?tab=north-stars&connection=${connectionId}`
    : "/semantic?tab=north-stars";
  const aiProviderHref = connectionId
    ? `/semantic?tab=ai-provider&connection=${connectionId}`
    : "/semantic?tab=ai-provider";
  return (
    <nav
      aria-label="Workspace schema"
      className="flex gap-6 border-b border-[color:var(--border)] text-sm"
    >
      <Link
        className={`pb-3 ${
          active === "semantic"
            ? "border-b-2 border-[color:var(--accent)] font-medium"
            : "text-[color:var(--muted)]"
        }`}
        aria-current={active === "semantic" ? "page" : undefined}
        href={semanticHref}
      >
        Semantic Layer
      </Link>
      <Link
        className={`pb-3 ${
          active === "technical"
            ? "border-b-2 border-[color:var(--accent)] font-medium"
            : "text-[color:var(--muted)]"
        }`}
        aria-current={active === "technical" ? "page" : undefined}
        href={technicalHref}
      >
        Technical Snapshot &amp; Graph
      </Link>
      <Link
        className={`pb-3 ${
          active === "north-stars"
            ? "border-b-2 border-[color:var(--accent)] font-medium"
            : "text-[color:var(--muted)]"
        }`}
        aria-current={active === "north-stars" ? "page" : undefined}
        href={northStarsHref}
      >
        North Star Benchmarks
      </Link>
      <Link
        className={`pb-3 ${
          active === "ai-provider"
            ? "border-b-2 border-[color:var(--accent)] font-medium"
            : "text-[color:var(--muted)]"
        }`}
        aria-current={active === "ai-provider" ? "page" : undefined}
        href={aiProviderHref}
      >
        AI Provider
      </Link>
    </nav>
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
            className={`border px-3 py-2 text-sm ${
              connection.id === selectedConnectionId
                ? "border-[color:var(--accent)]"
                : "border-[color:var(--border)]"
            }`}
            href={`/semantic?connection=${connection.id}`}
            key={connection.id}
          >
            {connection.name}
            <span className="ml-2 text-xs text-[color:var(--muted)]">
              {connection.database_name}
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}

function VersionToolbar({
  canManage,
  connection,
  selected,
  tenantId,
  versions
}: {
  canManage: boolean;
  connection: ConnectionRow;
  selected: SemanticVersionSummary | null;
  tenantId: string;
  versions: SemanticVersionSummary[];
}) {
  return (
    <section className="border-t border-[color:var(--border)] pt-6">
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div>
          <h2 className="text-base font-semibold">Versioni semantiche</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {versions.length === 0 ? (
              <span className="text-sm text-[color:var(--muted)]">
                Nessuna versione
              </span>
            ) : (
              versions.map((version) => (
                <Link
                  className={`border px-3 py-1.5 text-sm ${
                    version.id === selected?.id
                      ? "border-[color:var(--accent)]"
                      : "border-[color:var(--border)]"
                  }`}
                  href={`/semantic?connection=${connection.id}&semantic=${version.id}`}
                  key={version.id}
                >
                  v{version.version} {version.status}
                </Link>
              ))
            )}
          </div>
        </div>
        {canManage ? (
          <form action={createAndGenerateSemanticDraftAction}>
            <input name="tenant_id" type="hidden" value={tenantId} />
            <input name="connection_id" type="hidden" value={connection.id} />
            <SubmitButton
              className="border border-[color:var(--accent)] px-4 py-2 text-sm font-medium disabled:cursor-wait disabled:opacity-60"
              idleLabel="Nuova proposta AI"
              pendingLabel="Generazione..."
            />
          </form>
        ) : null}
      </div>
    </section>
  );
}

function SemanticLayerDetail({
  canManage,
  connectionId,
  layer,
  searchParams,
  summary,
  tenantId
}: {
  canManage: boolean;
  connectionId: string;
  layer: SemanticLayer;
  searchParams: SemanticWorkspaceParams;
  summary: SemanticVersionSummary;
  tenantId: string;
}) {
  const indexes = buildSemanticIndexes(layer);
  const counts = semanticLayerCounts(layer);
  const issueCounts = validationIssueCounts(layer.validation_report);
  const mutable =
    ["draft", "proposed"].includes(summary.status) &&
    summary.effective_freshness === "fresh";

  return (
    <>
      <section className="border-t border-[color:var(--border)] pt-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Stat label="Versione" value={`v${summary.version}`} />
          <Stat label="Stato" value={summary.status} />
          <Stat label="Freshness" value={summary.effective_freshness} />
          <Stat label="Revisione" value={String(summary.revision)} />
          <Stat label="Validazione" value={summary.validation_status} />
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          {canManage && mutable ? (
            <>
              <VersionActionForm
                action={generateSemanticDraftAction}
                connectionId={connectionId}
                label="Rigenera proposta"
                revision={summary.revision}
                semanticVersionId={summary.id}
                tenantId={tenantId}
              />
              <VersionActionForm
                action={validateSemanticDraftAction}
                connectionId={connectionId}
                label="Valida"
                revision={summary.revision}
                semanticVersionId={summary.id}
                tenantId={tenantId}
              />
            </>
          ) : null}
          {canManage &&
          summary.status === "proposed" &&
          summary.effective_freshness === "fresh" ? (
            <VersionActionForm
              action={activateSemanticVersionAction}
              connectionId={connectionId}
              emphasized
              label="Attiva"
              revision={summary.revision}
              semanticVersionId={summary.id}
              tenantId={tenantId}
            />
          ) : null}
          {canManage && ["active", "archived"].includes(summary.status) ? (
            <VersionActionForm
              action={rebaseSemanticVersionAction}
              connectionId={connectionId}
              label={
                summary.effective_freshness === "stale"
                  ? "Rebase su graph corrente"
                  : "Crea draft di revisione"
              }
              semanticVersionId={summary.id}
              tenantId={tenantId}
            />
          ) : null}
          {canManage &&
          ["draft", "proposed"].includes(summary.status) &&
          summary.effective_freshness === "stale" ? (
            <p className="text-sm text-[color:var(--muted)]">
              Questa versione e stale. Crea una nuova proposta sul graph corrente.
            </p>
          ) : null}
          {canManage && summary.status === "active" ? (
            <VersionActionForm
              action={archiveSemanticVersionAction}
              connectionId={connectionId}
              label="Archivia"
              semanticVersionId={summary.id}
              tenantId={tenantId}
            />
          ) : null}
        </div>
        <dl className="mt-5 grid gap-2 text-xs text-[color:var(--muted)]">
          <div>
            <dt className="font-medium">Semantic hash</dt>
            <dd className="break-all">{summary.semantic_hash}</dd>
          </div>
          <div>
            <dt className="font-medium">Base graph hash</dt>
            <dd className="break-all">{layer.base_graph_hash}</dd>
          </div>
        </dl>
      </section>

      <section className="border-t border-[color:var(--border)] pt-6">
        <h2 className="text-base font-semibold">Recap</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Tabelle" value={String(counts.tables)} />
          <Stat label="Colonne" value={String(counts.columns)} />
          <Stat label="Concept" value={String(counts.concepts)} />
          <Stat label="Metriche" value={String(counts.metrics)} />
          <Stat label="Compiler eligible" value={String(counts.eligibleMetrics)} />
          <Stat label="Ambiguità aperte" value={String(counts.ambiguitiesOpen)} />
        </div>
      </section>

      <MetricTable
        canManage={canManage && mutable}
        connectionId={connectionId}
        indexes={indexes}
        metrics={layer.metrics}
        requestedPage={searchParams.metrics_page}
        revision={summary.revision}
        searchParams={searchParams}
        semanticVersionId={summary.id}
        tenantId={tenantId}
      />

      <AmbiguitySection
        layer={layer}
        requestedPage={searchParams.ambiguities_page}
        searchParams={searchParams}
      />

      <ValidationSection
        counts={issueCounts}
        requestedPage={searchParams.issues_page}
        report={layer.validation_report}
        searchParams={searchParams}
      />

      <CatalogSection
        layer={layer}
        requestedPage={searchParams.catalog_page}
        searchParams={searchParams}
      />
    </>
  );
}

function MetricTable({
  canManage,
  connectionId,
  indexes,
  metrics,
  requestedPage,
  revision,
  searchParams,
  semanticVersionId,
  tenantId
}: {
  canManage: boolean;
  connectionId: string;
  indexes: ReturnType<typeof buildSemanticIndexes>;
  metrics: SemanticMetric[];
  requestedPage: string | undefined;
  revision: number;
  searchParams: SemanticWorkspaceParams;
  semanticVersionId: string;
  tenantId: string;
}) {
  const pagination = paginateItems(
    metrics,
    requestedPage,
    METRICS_PAGE_SIZE
  );
  return (
    <section className="border-t border-[color:var(--border)] pt-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Metriche proposte</h2>
          <p className="mt-1 text-xs text-[color:var(--muted)]">
            Formula, grain e eligibility sono artifact strutturati. Nessun SQL
            libero.
          </p>
        </div>
        <a className="text-xs text-[color:var(--accent)]" href="#validation">
          Vedi validazione
        </a>
      </div>
      {metrics.length === 0 ? (
        <p className="mt-4 text-sm text-[color:var(--muted)]">
          Nessuna metrica proposta in questa versione.
        </p>
      ) : (
        <>
          <Pagination
            anchor="metrics"
            pageParam="metrics_page"
            pagination={pagination}
            searchParams={searchParams}
          />
          <div className="mt-4 overflow-x-auto" id="metrics">
            <table className="w-full min-w-[1100px] border-collapse text-left text-xs">
            <thead className="text-[color:var(--muted)]">
              <tr>
                {[
                  "Metrica",
                  "Concept / variant",
                  "Formula",
                  "Grain",
                  "Eligibility",
                  "Confidence",
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
                {pagination.items.map((metric) => (
                <tr key={metric.metric_key}>
                  <th
                    className="border-b border-[color:var(--border)] py-3 pr-4 text-left align-top font-normal"
                    scope="row"
                  >
                    <div className="font-medium">{metric.name}</div>
                    <div className="mt-1 text-[color:var(--muted)]">
                      {metric.canonical_name}
                    </div>
                  </th>
                  <td className="border-b border-[color:var(--border)] py-3 pr-4 align-top">
                    {metricConceptLabel(metric, indexes.concepts)}
                  </td>
                  <td className="border-b border-[color:var(--border)] py-3 pr-4 align-top font-mono">
                    {metricFormulaLabel(metric, indexes)}
                  </td>
                  <td className="border-b border-[color:var(--border)] py-3 pr-4 align-top">
                    {metricGrainLabel(metric, indexes)}
                  </td>
                  <td className="border-b border-[color:var(--border)] py-3 pr-4 align-top">
                    <div>{metric.compiler_eligibility}</div>
                    {metric.eligibility_reasons.length > 0 ? (
                      <div className="mt-1 max-w-56 text-[color:var(--muted)]">
                        {metric.eligibility_reasons.join(", ")}
                      </div>
                    ) : null}
                  </td>
                  <td className="border-b border-[color:var(--border)] py-3 pr-4 align-top">
                    {confidenceLabel(metric)}
                  </td>
                  <td className="border-b border-[color:var(--border)] py-3 pr-4 align-top">
                    {metric.status}
                    {!metric.enabled ? " · disabled" : ""}
                  </td>
                  <td className="border-b border-[color:var(--border)] py-3 align-top">
                    {canManage ? (
                      <div className="flex gap-2">
                        {metric.status !== "human_verified" && metric.enabled ? (
                          <MetricActionForm
                            action={confirmSemanticMetricAction}
                            connectionId={connectionId}
                            label="Conferma"
                            metricLabel={metric.name}
                            metricKey={metric.metric_key}
                            returnPage={pagination.page}
                            revision={revision}
                            semanticVersionId={semanticVersionId}
                            tenantId={tenantId}
                          />
                        ) : null}
                        {metric.enabled ? (
                          <MetricActionForm
                            action={disableSemanticMetricAction}
                            connectionId={connectionId}
                            label="Disabilita"
                            metricLabel={metric.name}
                            metricKey={metric.metric_key}
                            returnPage={pagination.page}
                            revision={revision}
                            semanticVersionId={semanticVersionId}
                            tenantId={tenantId}
                          />
                        ) : null}
                        <MetricCorrectionForm
                          connectionId={connectionId}
                          metric={metric}
                          returnPage={pagination.page}
                          revision={revision}
                          semanticVersionId={semanticVersionId}
                          tenantId={tenantId}
                        />
                      </div>
                    ) : (
                      <span className="text-[color:var(--muted)]">Sola lettura</span>
                    )}
                  </td>
                </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function AmbiguitySection({
  layer,
  requestedPage,
  searchParams
}: {
  layer: SemanticLayer;
  requestedPage: string | undefined;
  searchParams: SemanticWorkspaceParams;
}) {
  const pagination = paginateItems(
    layer.ambiguities,
    requestedPage,
    AMBIGUITIES_PAGE_SIZE
  );
  return (
    <section
      className="border-t border-[color:var(--border)] pt-6"
      id="ambiguities"
    >
      <h2 className="text-base font-semibold">Ambiguità</h2>
      {layer.ambiguities.length === 0 ? (
        <p className="mt-3 text-sm text-[color:var(--muted)]">
          Nessuna ambiguità registrata.
        </p>
      ) : (
        <>
          <Pagination
            anchor="ambiguities"
            pageParam="ambiguities_page"
            pagination={pagination}
            searchParams={searchParams}
          />
          <div className="mt-4 divide-y divide-[color:var(--border)] border-y border-[color:var(--border)]">
            {pagination.items.map((ambiguity) => (
            <div className="grid gap-2 py-4 md:grid-cols-[160px_1fr]" key={ambiguity.ambiguity_key}>
              <div className="text-xs">
                <div className="font-medium">{ambiguity.code}</div>
                <div className="mt-1 text-[color:var(--muted)]">
                  {ambiguity.status}
                </div>
              </div>
              <div className="text-sm">
                <p>{ambiguity.summary}</p>
                <p className="mt-1 text-[color:var(--muted)]">
                  {ambiguity.clarification_question}
                </p>
              </div>
            </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function ValidationSection({
  counts,
  requestedPage,
  searchParams,
  report
}: {
  counts: ReturnType<typeof validationIssueCounts>;
  requestedPage: string | undefined;
  searchParams: SemanticWorkspaceParams;
  report: SemanticLayer["validation_report"];
}) {
  const issues = [
    ...report.blocking_errors,
    ...report.warnings,
    ...report.info
  ];
  const pagination = paginateItems(
    issues,
    requestedPage,
    VALIDATION_ISSUES_PAGE_SIZE
  );
  return (
    <section
      className="border-t border-[color:var(--border)] pt-6"
      id="validation"
    >
      <h2 className="text-base font-semibold">Validazione deterministica</h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-4">
        <Stat label="Stato" value={report.status} />
        <Stat label="Blocking" value={String(counts.blocking)} />
        <Stat label="Warning" value={String(counts.warnings)} />
        <Stat label="Info" value={String(counts.info)} />
      </div>
      {issues.length > 0 ? (
        <>
          <Pagination
            anchor="validation"
            pageParam="issues_page"
            pagination={pagination}
            searchParams={searchParams}
          />
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-left text-xs">
            <thead className="text-[color:var(--muted)]">
              <tr>
                {["Severità", "Codice", "Target", "Messaggio"].map((label) => (
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
                {pagination.items.map((issue, index) => (
                <ValidationIssueRow
                  issue={issue}
                  key={`${issue.code}-${issue.target_key}-${index}`}
                />
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p className="mt-4 text-sm text-[color:var(--muted)]">
          Nessun issue nella revisione validata.
        </p>
      )}
    </section>
  );
}

function ValidationIssueRow({ issue }: { issue: SemanticValidationIssue }) {
  return (
    <tr>
      <td className="border-b border-[color:var(--border)] py-3 pr-4">
        {issue.severity}
      </td>
      <td className="border-b border-[color:var(--border)] py-3 pr-4">
        {issue.code}
      </td>
      <td className="border-b border-[color:var(--border)] py-3 pr-4 text-[color:var(--muted)]">
        {issue.target_type}
      </td>
      <td className="border-b border-[color:var(--border)] py-3">
        {issue.message}
      </td>
    </tr>
  );
}

function CatalogSection({
  layer,
  requestedPage,
  searchParams
}: {
  layer: SemanticLayer;
  requestedPage: string | undefined;
  searchParams: SemanticWorkspaceParams;
}) {
  const includedTables = layer.tables.filter((table) => table.included);
  const pagination = paginateItems(
    includedTables,
    requestedPage,
    CATALOG_TABLES_PAGE_SIZE
  );
  const includedColumnCounts = new Map<string, number>();
  for (const column of layer.columns) {
    if (!column.included) {
      continue;
    }
    includedColumnCounts.set(
      column.node_key,
      (includedColumnCounts.get(column.node_key) ?? 0) + 1
    );
  }
  return (
    <section
      className="border-t border-[color:var(--border)] pt-6"
      id="catalog"
    >
      <h2 className="text-base font-semibold">Catalogo semantico</h2>
      <Pagination
        anchor="catalog"
        pageParam="catalog_page"
        pagination={pagination}
        searchParams={searchParams}
      />
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-left text-xs">
          <thead className="text-[color:var(--muted)]">
            <tr>
              {["Oggetto", "Nome business", "Dominio", "Stato", "Colonne incluse"].map(
                (label) => (
                  <th
                    className="border-b border-[color:var(--border)] py-2 pr-4 font-medium"
                    key={label}
                  >
                    {label}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody>
            {pagination.items.map((table) => (
              <tr key={table.node_key}>
                <td className="border-b border-[color:var(--border)] py-3 pr-4">
                  {table.schema_name}.{table.object_name}
                </td>
                <td className="border-b border-[color:var(--border)] py-3 pr-4">
                  {table.display_name ?? "-"}
                </td>
                <td className="border-b border-[color:var(--border)] py-3 pr-4">
                  {table.business_domain ?? "-"}
                </td>
                <td className="border-b border-[color:var(--border)] py-3 pr-4">
                  {table.status}
                </td>
                <td className="border-b border-[color:var(--border)] py-3">
                  {includedColumnCounts.get(table.node_key) ?? 0}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function VersionActionForm({
  action,
  connectionId,
  emphasized = false,
  label,
  revision,
  semanticVersionId,
  tenantId
}: {
  action: (formData: FormData) => Promise<void>;
  connectionId: string;
  emphasized?: boolean;
  label: string;
  revision?: number;
  semanticVersionId: string;
  tenantId: string;
}) {
  return (
    <form action={action}>
      <input name="tenant_id" type="hidden" value={tenantId} />
      <input name="connection_id" type="hidden" value={connectionId} />
      <input
        name="semantic_version_id"
        type="hidden"
        value={semanticVersionId}
      />
      {revision ? (
        <input name="expected_revision" type="hidden" value={revision} />
      ) : null}
      <SubmitButton
        className={`border px-3 py-1.5 text-sm disabled:cursor-wait disabled:opacity-60 ${
          emphasized
            ? "border-[color:var(--accent)]"
            : "border-[color:var(--border)]"
        }`}
        idleLabel={label}
        pendingLabel="Attendi..."
      />
    </form>
  );
}

function MetricActionForm({
  action,
  connectionId,
  label,
  metricLabel,
  metricKey,
  returnPage,
  revision,
  semanticVersionId,
  tenantId
}: {
  action: (formData: FormData) => Promise<void>;
  connectionId: string;
  label: string;
  metricLabel: string;
  metricKey: string;
  returnPage: number;
  revision: number;
  semanticVersionId: string;
  tenantId: string;
}) {
  return (
    <form action={action}>
      <input name="tenant_id" type="hidden" value={tenantId} />
      <input name="connection_id" type="hidden" value={connectionId} />
      <input
        name="semantic_version_id"
        type="hidden"
        value={semanticVersionId}
      />
      <input name="expected_revision" type="hidden" value={revision} />
      <input name="metric_key" type="hidden" value={metricKey} />
      <input name="return_page" type="hidden" value={returnPage} />
      <SubmitButton
        ariaLabel={`${label} ${metricLabel}`}
        className="border border-[color:var(--border)] px-2 py-1 disabled:cursor-wait disabled:opacity-60"
        idleLabel={label}
        pendingLabel="Attendi..."
      />
    </form>
  );
}

function MetricCorrectionForm({
  connectionId,
  metric,
  returnPage,
  revision,
  semanticVersionId,
  tenantId
}: {
  connectionId: string;
  metric: SemanticMetric;
  returnPage: number;
  revision: number;
  semanticVersionId: string;
  tenantId: string;
}) {
  return (
    <details>
      <summary
        aria-label={`Correggi ${metric.name}`}
        className="cursor-pointer border border-[color:var(--border)] px-2 py-1"
      >
        Correggi
      </summary>
      <form
        action={correctSemanticMetricAction}
        className="mt-2 grid w-72 gap-3 border border-[color:var(--border)] bg-[color:var(--background)] p-3"
      >
        <input name="tenant_id" type="hidden" value={tenantId} />
        <input name="connection_id" type="hidden" value={connectionId} />
        <input
          name="semantic_version_id"
          type="hidden"
          value={semanticVersionId}
        />
        <input name="expected_revision" type="hidden" value={revision} />
        <input name="metric_key" type="hidden" value={metric.metric_key} />
        <input name="return_page" type="hidden" value={returnPage} />
        <label className="grid gap-1 text-xs">
          Nome
          <input
            className="min-w-0 border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
            defaultValue={metric.name}
            maxLength={255}
            name="name"
            required
          />
        </label>
        <label className="grid gap-1 text-xs">
          Descrizione
          <textarea
            className="min-h-20 min-w-0 resize-y border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
            defaultValue={metric.description ?? ""}
            maxLength={2_000}
            name="description"
          />
        </label>
        <SubmitButton
          className="justify-self-start border border-[color:var(--accent)] px-3 py-1.5 text-xs font-medium disabled:cursor-wait disabled:opacity-60"
          idleLabel="Salva e valida"
          pendingLabel="Salvataggio..."
        />
      </form>
    </details>
  );
}

function EmptyState({ detail, title }: { detail: string; title: string }) {
  return (
    <section className="border-y border-[color:var(--border)] py-10">
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mt-2 max-w-2xl text-sm text-[color:var(--muted)]">
        {detail}
      </p>
    </section>
  );
}

function Pagination({
  anchor,
  pageParam,
  pagination,
  searchParams
}: {
  anchor: string;
  pageParam:
    | "ambiguities_page"
    | "catalog_page"
    | "issues_page"
    | "metrics_page";
  pagination: {
    page: number;
    pageCount: number;
    total: number;
  };
  searchParams: SemanticWorkspaceParams;
}) {
  if (pagination.pageCount === 1) {
    return null;
  }

  const pageHref = (page: number) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(searchParams)) {
      if (value && key !== "message") {
        params.set(key, value);
      }
    }
    params.set(pageParam, String(page));
    return `/semantic?${params.toString()}#${anchor}`;
  };

  return (
    <nav
      aria-label={`Paginazione ${anchor}`}
      className="mt-3 flex items-center gap-3 text-xs"
    >
      {pagination.page > 1 ? (
        <Link
          className="text-[color:var(--accent)]"
          href={pageHref(pagination.page - 1)}
        >
          Precedente
        </Link>
      ) : null}
      <span className="text-[color:var(--muted)]">
        Pagina {pagination.page} di {pagination.pageCount} · {pagination.total} totali
      </span>
      {pagination.page < pagination.pageCount ? (
        <Link
          className="text-[color:var(--accent)]"
          href={pageHref(pagination.page + 1)}
        >
          Successiva
        </Link>
      ) : null}
    </nav>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-l-2 border-[color:var(--border)] pl-3">
      <div className="text-xs text-[color:var(--muted)]">{label}</div>
      <div className="mt-1 text-sm font-medium">{value}</div>
    </div>
  );
}

function selectVersion(
  versions: SemanticVersionSummary[],
  requestedVersionId?: string
) {
  if (requestedVersionId) {
    const requested = versions.find(
      (version) => version.id === requestedVersionId
    );
    if (requested) {
      return requested;
    }
  }
  return (
    versions.find((version) => version.status === "active") ??
    versions.find((version) => version.status === "proposed") ??
    versions.find((version) => version.status === "draft") ??
    versions[0] ??
    null
  );
}
