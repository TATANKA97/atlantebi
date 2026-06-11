import Link from "next/link";
import {
  SchemaImportSummarySchema,
  type SchemaImportSummary
} from "@atlantebi/contracts";

import { introspectConnectionAction } from "./actions";
import {
  semanticColumnAtlanteFlags,
  semanticColumnDatabaseFlags,
  semanticColumnTypeLabel,
  splitSemanticColumns,
  type SemanticColumnDisplay
} from "../../lib/semantic/columns";
import { getActiveTenantContext } from "../../lib/tenant";

type ConnectionRow = {
  id: string;
  name: string;
  engine: "sqlserver" | "mysql";
  database_name: string;
  status: string;
};

type SemanticVersionRow = {
  id: string;
  connection_id: string;
  schema_snapshot_id: string | null;
  version: number;
  status: "draft" | "active" | "archived";
  created_at: string;
};

type SemanticTableRow = {
  id: string;
  physical_schema: string;
  physical_name: string;
  active: boolean;
  metadata: {
    table_type?: string;
    column_count?: number;
    primary_key_count?: number;
    row_count_estimate?: number;
    view_definition_available?: boolean;
    lineage_available?: boolean;
    view_lineage_count?: number;
    has_definition_hash?: boolean;
  };
};

type SnapshotSummaryRow = {
  id: string;
  summary: unknown;
};

type SemanticColumnRow = SemanticColumnDisplay & {
  metadata: SemanticColumnDisplay["metadata"] & {
    ordinal_position?: number;
  };
};

const MESSAGE_COPY: Record<string, string> = {
  connection_not_found: "Connessione non trovata.",
  connection_not_ready: "La connessione deve essere ready prima dell'import schema.",
  invalid_introspection: "Richiesta introspection non valida.",
  schema_forbidden: "Il tuo ruolo non consente di importare lo schema.",
  schema_snapshot_save_failed: "Snapshot schema non salvato.",
  schema_import_save_failed: "Import schema non salvato.",
  semantic_columns_save_failed: "Colonne semantiche non salvate.",
  semantic_relationships_save_failed: "Relazioni semantiche non salvate.",
  semantic_tables_save_failed: "Tabelle semantiche non salvate.",
  semantic_version_save_failed: "Versione semantica non salvata."
};

export const dynamic = "force-dynamic";

export default async function SemanticPage({
  searchParams
}: {
  searchParams: Promise<{ message?: string; version?: string; snapshot?: string }>;
}) {
  const params = await searchParams;
  const { supabase, tenantId } = await getActiveTenantContext();
  const [connectionsResult, versionsResult] = await Promise.all([
    supabase
      .from("db_connection_summaries")
      .select("id,name,engine,database_name,status")
      .eq("tenant_id", tenantId)
      .eq("status", "ready")
      .order("created_at", { ascending: false }),
    supabase
      .from("semantic_versions")
      .select("id,connection_id,schema_snapshot_id,version,status,created_at")
      .eq("tenant_id", tenantId)
      .order("created_at", { ascending: false })
      .limit(20)
  ]);
  const connections = (connectionsResult.data ?? []) as ConnectionRow[];
  const versions = (versionsResult.data ?? []) as SemanticVersionRow[];
  const selectedVersionId = params.version ?? versions[0]?.id;
  const selectedVersion = versions.find((version) => version.id === selectedVersionId);
  const semanticData = selectedVersion
    ? await readSemanticVersionData({
        semanticVersionId: selectedVersion.id,
        snapshotId: selectedVersion.schema_snapshot_id,
        supabase,
        tenantId
      })
    : {
        columnsByTable: new Map<string, SemanticColumnRow[]>(),
        snapshot: null,
        tables: []
      };
  const message = params.message ? MESSAGE_COPY[params.message] : undefined;

  return (
    <main className="min-h-screen px-8 py-10">
      <section className="mx-auto flex max-w-6xl flex-col gap-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-normal">Semantic layer</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[color:var(--muted)]">
              Import schema deterministico da connessioni ready. Le tabelle partono
              inattive: l'attivazione business arriva dopo revisione.
            </p>
          </div>
          <Link
            className="border border-[color:var(--border)] px-4 py-2 text-sm font-medium"
            href="/connections"
          >
            Connessioni
          </Link>
        </header>

        {message ? (
          <p className="border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--muted)]">
            {message}
          </p>
        ) : null}
        {params.snapshot ? (
          <p className="border border-[color:var(--accent)] px-4 py-3 text-sm">
            Schema importato e versione semantica draft creata.
          </p>
        ) : null}

        <section className="border-t border-[color:var(--border)] pt-6">
          <h2 className="text-base font-semibold">Import schema</h2>
          {connections.length === 0 ? (
            <p className="mt-3 text-sm text-[color:var(--muted)]">
              Nessuna connessione ready. Crea e verifica una connessione prima.
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full border-collapse text-left text-sm">
                <thead className="text-[color:var(--muted)]">
                  <tr>
                    <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                      Connessione
                    </th>
                    <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                      Engine
                    </th>
                    <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                      Database
                    </th>
                    <th className="border-b border-[color:var(--border)] py-2 font-medium">
                      Azione
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {connections.map((connection) => (
                    <tr key={connection.id}>
                      <td className="border-b border-[color:var(--border)] py-3 pr-4">
                        {connection.name}
                      </td>
                      <td className="border-b border-[color:var(--border)] py-3 pr-4">
                        {connection.engine}
                      </td>
                      <td className="border-b border-[color:var(--border)] py-3 pr-4">
                        {connection.database_name}
                      </td>
                      <td className="border-b border-[color:var(--border)] py-3">
                        <form>
                          <input name="tenant_id" type="hidden" value={tenantId} />
                          <input
                            name="connection_id"
                            type="hidden"
                            value={connection.id}
                          />
                          <input name="timeout_ms" type="hidden" value="120000" />
                          <button
                            className="border border-[color:var(--accent)] px-3 py-1.5 text-sm"
                            formAction={introspectConnectionAction}
                          >
                            Importa schema
                          </button>
                        </form>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="border-t border-[color:var(--border)] pt-6">
          <h2 className="text-base font-semibold">Versioni draft</h2>
          {versions.length === 0 ? (
            <p className="mt-3 text-sm text-[color:var(--muted)]">
              Nessuna versione semantica importata.
            </p>
          ) : (
            <div className="mt-4 flex flex-wrap gap-2">
              {versions.map((version) => (
                <Link
                  className={`border px-3 py-1.5 text-sm ${
                    version.id === selectedVersionId
                      ? "border-[color:var(--accent)]"
                      : "border-[color:var(--border)]"
                  }`}
                  href={`/semantic?version=${version.id}`}
                  key={version.id}
                >
                  v{version.version} {version.status}
                </Link>
              ))}
            </div>
          )}
        </section>

        {selectedVersion ? (
          <section className="border-t border-[color:var(--border)] pt-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h2 className="text-base font-semibold">Schema importato</h2>
                <p className="mt-2 text-sm text-[color:var(--muted)]">
                  {semanticData.tables.length} oggetti nella versione v
                  {selectedVersion.version}.
                </p>
              </div>
            </div>

            {semanticData.snapshot ? (
              <ImportSummary summary={semanticData.snapshot.summary} />
            ) : null}

            <div className="mt-5 grid gap-6">
              {semanticData.tables.map((table) => {
                const columns = semanticData.columnsByTable.get(table.id) ?? [];
                const { excludedColumns, queryableColumns } =
                  splitSemanticColumns(columns);
                return (
                  <section className="border-t border-[color:var(--border)] pt-4" key={table.id}>
                    <div className="flex flex-wrap items-baseline justify-between gap-3">
                      <h3 className="text-sm font-semibold">
                        {table.physical_schema}.{table.physical_name}
                      </h3>
                      <p className="text-xs text-[color:var(--muted)]">
                        {table.metadata.table_type ?? "table"} -{" "}
                        {queryableColumns.length} colonne queryable
                        {excludedColumns.length > 0
                          ? `, ${excludedColumns.length} escluse`
                          : ""}
                        {table.metadata.row_count_estimate !== undefined
                          ? ` - row estimate ${table.metadata.row_count_estimate}`
                          : ""}
                        {table.metadata.table_type === "view"
                          ? ` - definition ${
                              table.metadata.view_definition_available
                                ? "available"
                                : "not available"
                            }`
                          : ""}
                        {table.metadata.table_type === "view"
                          ? ` - lineage ${
                              table.metadata.lineage_available
                                ? `available (${table.metadata.view_lineage_count ?? 0})`
                                : "not available"
                            }`
                          : ""}
                      </p>
                    </div>
                    <div className="mt-3 overflow-x-auto">
                      <table className="w-full border-collapse text-left text-xs">
                        <thead className="text-[color:var(--muted)]">
                          <tr>
                            <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                              Colonna
                            </th>
                            <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                              Tipo DB
                            </th>
                            <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                              Metadata DB
                            </th>
                            <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                              Ruolo tecnico
                            </th>
                            <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                              Ruolo Atlante
                            </th>
                            <th className="border-b border-[color:var(--border)] py-2 font-medium">
                              Classificazione Atlante
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {queryableColumns.map((column) => (
                            <tr key={column.id}>
                              <td className="border-b border-[color:var(--border)] py-2 pr-4">
                                {column.physical_name}
                              </td>
                              <td className="border-b border-[color:var(--border)] py-2 pr-4">
                                {semanticColumnTypeLabel(column)}
                              </td>
                              <td className="border-b border-[color:var(--border)] py-2 pr-4">
                                {semanticColumnDatabaseFlags(column).join(" ")}
                              </td>
                              <td className="border-b border-[color:var(--border)] py-2 pr-4">
                                {column.metadata.technical_role}
                              </td>
                              <td className="border-b border-[color:var(--border)] py-2 pr-4">
                                {column.role}
                              </td>
                              <td className="border-b border-[color:var(--border)] py-2 text-[color:var(--muted)]">
                                {semanticColumnAtlanteFlags(column).join(" ")}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {excludedColumns.length > 0 ? (
                      <div className="mt-3 overflow-x-auto">
                        <p className="mb-2 text-xs font-medium text-[color:var(--muted)]">
                          Colonne escluse
                        </p>
                        <table className="w-full border-collapse text-left text-xs">
                          <thead className="text-[color:var(--muted)]">
                            <tr>
                              <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                                Colonna
                              </th>
                              <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                                Tipo DB
                              </th>
                              <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                                Metadata DB
                              </th>
                              <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                                Ruolo tecnico
                              </th>
                              <th className="border-b border-[color:var(--border)] py-2 pr-4 font-medium">
                                Ruolo Atlante
                              </th>
                              <th className="border-b border-[color:var(--border)] py-2 font-medium">
                                Classificazione Atlante
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {excludedColumns.map((column) => (
                              <tr key={column.id}>
                                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                                  {column.physical_name}
                                </td>
                                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                                  {semanticColumnTypeLabel(column)}
                                </td>
                                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                                  {semanticColumnDatabaseFlags(column).join(" ")}
                                </td>
                                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                                  {column.metadata.technical_role}
                                </td>
                                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                                  {column.role}
                                </td>
                                <td className="border-b border-[color:var(--border)] py-2 text-[color:var(--muted)]">
                                  {semanticColumnAtlanteFlags(column).join(" ")}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : null}
                  </section>
                );
              })}
            </div>
          </section>
        ) : null}
      </section>
    </main>
  );
}

async function readSemanticVersionData({
  semanticVersionId,
  snapshotId,
  supabase,
  tenantId
}: {
  semanticVersionId: string;
  snapshotId: string | null;
  supabase: Awaited<ReturnType<typeof getActiveTenantContext>>["supabase"];
  tenantId: string;
}) {
  const { data: tableData } = await supabase
    .from("semantic_tables")
    .select("id,physical_schema,physical_name,active,metadata")
    .eq("tenant_id", tenantId)
    .eq("semantic_version_id", semanticVersionId)
    .order("physical_schema", { ascending: true })
    .order("physical_name", { ascending: true });
  const tables = (tableData ?? []) as SemanticTableRow[];
  const tableIds = tables.map((table) => table.id);

  if (tableIds.length === 0) {
    return {
      columnsByTable: new Map<string, SemanticColumnRow[]>(),
      snapshot: await readSnapshotSummary({
        resolvedSnapshotId: snapshotId,
        supabase,
        tenantId
      }),
      tables
    };
  }

  const { data: columnData } = await supabase
    .from("semantic_columns")
    .select("id,semantic_table_id,physical_name,data_type,role,pii,metadata")
    .eq("tenant_id", tenantId)
    .in("semantic_table_id", tableIds)
    .order("physical_name", { ascending: true });
  const columns = (columnData ?? []) as SemanticColumnRow[];
  const columnsByTable = new Map<string, SemanticColumnRow[]>();

  for (const column of columns) {
    const existing = columnsByTable.get(column.semantic_table_id) ?? [];
    existing.push(column);
    columnsByTable.set(column.semantic_table_id, existing);
  }

  for (const groupedColumns of columnsByTable.values()) {
    groupedColumns.sort(
      (left, right) =>
        (left.metadata.ordinal_position ?? 0) - (right.metadata.ordinal_position ?? 0)
    );
  }

  return {
    columnsByTable,
    snapshot: await readSnapshotSummary({
      resolvedSnapshotId: snapshotId,
      supabase,
      tenantId
    }),
    tables
  };
}

async function readSnapshotSummary({
  resolvedSnapshotId,
  supabase,
  tenantId
}: {
  resolvedSnapshotId: string | null;
  supabase: Awaited<ReturnType<typeof getActiveTenantContext>>["supabase"];
  tenantId: string;
}) {
  if (!resolvedSnapshotId) {
    return null;
  }

  const { data } = await supabase
    .from("schema_snapshot_summaries")
    .select("id,summary")
    .eq("tenant_id", tenantId)
    .eq("id", resolvedSnapshotId)
    .single();

  const snapshot = data as SnapshotSummaryRow | null;
  if (!snapshot) {
    return null;
  }

  return {
    id: snapshot.id,
    summary: SchemaImportSummarySchema.parse(snapshot.summary)
  };
}

function ImportSummary({ summary }: { summary: SchemaImportSummary }) {
  const overview = [
    ["Database", summary.database_name],
    ["Engine", `${summary.engine} ${summary.engine_version}`],
    ["Coverage", summary.coverage_status],
    ["Acquisito", new Date(summary.captured_at).toLocaleString("it-IT")],
    ["Durata", `${summary.duration_ms} ms`],
    ["Oggetti", summary.total_objects],
    ["Tabelle", summary.total_tables],
    ["View", summary.total_views],
    ["Colonne", summary.total_columns],
    ["Oggetti queryable", summary.queryable_objects],
    ["Oggetti non queryable", summary.non_queryable_objects],
    ["Colonne queryable", summary.queryable_columns],
    ["Colonne non queryable", summary.non_queryable_columns]
  ] as const;
  const constraints = [
    ["Primary key", summary.primary_keys_count],
    ["Foreign key", summary.foreign_keys_count],
    ["Unique constraint", summary.unique_constraints_count],
    ["Check constraint", summary.check_constraints_count],
    ["Default constraint", summary.default_constraints_count]
  ] as const;
  const indexes = [
    ["Indici totali", summary.indexes_total_count],
    ["Su tabelle", summary.table_indexes_count],
    ["Su view", summary.view_indexes_count],
    ["Unici", summary.unique_indexes_count],
    ["Filtrati", summary.filtered_indexes_count],
    ["Con colonne incluse", summary.included_columns_indexes_count]
  ] as const;
  const viewCoverage = [
    ["View totali", summary.views_total],
    ["Con definizione", summary.views_with_definition_count],
    ["Senza definizione", summary.views_without_definition_count],
    ["Con lineage", summary.views_with_lineage_count],
    ["Lineage parziale", summary.views_with_partial_lineage_count],
    ["Senza lineage", summary.views_without_lineage_count],
    ["Dipendenze lineage", summary.view_lineage_dependencies_count]
  ] as const;
  const columns = [
    ["Tipo dichiarato disponibile", summary.columns_with_declared_type_count],
    ["Tipo dichiarato assente", summary.columns_without_declared_type_count],
    ["Con default", summary.columns_with_default_count],
    ["Calcolate", summary.computed_columns_count],
    ["Identity", summary.identity_columns_count],
    ["PII", summary.pii_columns_count],
    ["Escluse", summary.excluded_columns_count],
    ["Sensitive", summary.sensitive_columns_count]
  ] as const;
  const warningEntries = Object.entries(summary.coverage_warnings_by_code).sort(
    ([left], [right]) => left.localeCompare(right)
  );

  return (
    <div className="mt-4 grid gap-5 border border-[color:var(--border)] p-4 text-sm">
      <SummaryValues title="Import" values={overview} />
      <div className="grid gap-5 md:grid-cols-2">
        <SummaryValues title="Vincoli" values={constraints} />
        <SummaryValues title="Indici" values={indexes} />
        <SummaryValues title="Copertura view" values={viewCoverage} />
        <SummaryValues title="Colonne" values={columns} />
      </div>
      <p className="break-all text-xs text-[color:var(--muted)]">
        Schema hash: {summary.schema_hash}
      </p>
      {warningEntries.length > 0 ? (
        <div>
          <p className="text-xs font-medium text-[color:var(--muted)]">
            Warning aggregati ({summary.coverage_warnings_count})
          </p>
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
            {warningEntries.map(([code, count]) => (
              <li key={code}>
                {code}:{" "}
                {code === "COLUMN_DECLARED_TYPE_UNAVAILABLE"
                  ? `${summary.columns_without_declared_type_count}/${summary.total_columns} colonne hanno declared type non visibile; usati native/base types.`
                  : count}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function SummaryValues({
  title,
  values
}: {
  title: string;
  values: ReadonlyArray<readonly [string, string | number]>;
}) {
  return (
    <div>
      <h3 className="text-xs font-medium text-[color:var(--muted)]">{title}</h3>
      <dl className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
        {values.map(([label, value]) => (
          <div className="flex justify-between gap-3" key={label}>
            <dt className="text-[color:var(--muted)]">{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
