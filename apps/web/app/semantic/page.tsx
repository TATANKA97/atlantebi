import Link from "next/link";
import {
  QueryabilityGraphArtifactSchema,
  SchemaImportSummarySchema,
  SchemaIntrospectionResponseSchema,
  type QueryabilityForeignKeyEdge,
  type QueryabilityGraphArtifact,
  type SchemaColumnMetadata,
  type SchemaImportSummary
} from "@atlantebi/contracts";

import {
  introspectConnectionAction,
  rebuildQueryabilityGraphAction
} from "./actions";
import { PathInspector } from "./path-inspector";
import { coverageWarningsLabel } from "../../lib/semantic/summary";
import { createSupabaseAdminClient } from "../../lib/supabase/admin";
import {
  canManageConnections,
  getActiveTenantContext
} from "../../lib/tenant";

type ConnectionRow = {
  id: string;
  name: string;
  engine: "sqlserver" | "mysql";
  database_name: string;
  status: string;
};

type GraphVersionRow = {
  id: string;
  connection_id: string;
  schema_snapshot_id: string;
  version: number;
  status: "complete" | "partial";
  graph_hash: string;
  graph_input_hash: string;
  builder_version: string;
  policy_version: string;
  node_count: number;
  column_count: number;
  edge_count: number;
  graph: unknown;
  created_at: string;
};

type SnapshotSummaryRow = {
  id: string;
  summary: unknown;
  snapshot: unknown;
};

const MESSAGE_COPY: Record<string, string> = {
  connection_not_found: "Connessione non trovata.",
  connection_not_ready: "La connessione deve essere ready prima dell'import schema.",
  invalid_introspection: "Richiesta introspection non valida.",
  queryability_graph_blocked: "Il Queryability Graph non è utilizzabile.",
  schema_forbidden: "Il tuo ruolo non consente di importare lo schema.",
  schema_import_save_failed: "Import schema e graph non salvati.",
  invalid_rebuild_request: "Richiesta di rigenerazione non valida.",
  queryability_rebuild_failed: "Rigenerazione Queryability Graph fallita.",
  queryability_rebuild_forbidden: "Il tuo ruolo non consente la rigenerazione.",
  queryability_rebuild_save_failed: "Queryability Graph rigenerato ma non salvato.",
  schema_snapshot_not_found: "Snapshot tecnico non trovato."
};

export const dynamic = "force-dynamic";

export default async function QueryabilityPage({
  searchParams
}: {
  searchParams: Promise<{ graph?: string; message?: string; snapshot?: string }>;
}) {
  const params = await searchParams;
  const context = await getActiveTenantContext();
  const canManage = canManageConnections(context.role);
  const admin = createSupabaseAdminClient();
  const [connectionsResult, graphsResult] = await Promise.all([
    context.supabase
      .from("db_connection_summaries")
      .select("id,name,engine,database_name,status")
      .eq("tenant_id", context.tenantId)
      .eq("status", "ready")
      .order("created_at", { ascending: false }),
    canManage
      ? admin
          .from("queryability_graph_versions")
          .select(
            "id,connection_id,schema_snapshot_id,version,status,graph_hash,graph_input_hash,builder_version,policy_version,node_count,column_count,edge_count,graph,created_at"
          )
          .eq("tenant_id", context.tenantId)
          .order("created_at", { ascending: false })
          .limit(20)
      : Promise.resolve({ data: [], error: null })
  ]);

  const connections = (connectionsResult.data ?? []) as ConnectionRow[];
  const graphVersions = (graphsResult.data ?? []) as GraphVersionRow[];
  const selectedGraphRow =
    graphVersions.find((graph) => graph.id === params.graph) ?? graphVersions[0];
  const selectedGraph = selectedGraphRow
    ? QueryabilityGraphArtifactSchema.parse(selectedGraphRow.graph)
    : null;
  const snapshot = selectedGraphRow
    ? await readSnapshotSummary({
        admin,
        snapshotId: selectedGraphRow.schema_snapshot_id,
        tenantId: context.tenantId
      })
    : null;
  const message = params.message ? MESSAGE_COPY[params.message] : undefined;

  return (
    <main className="min-h-screen px-8 py-10">
      <section className="mx-auto flex max-w-7xl flex-col gap-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-normal">
              Schema e Queryability Graph
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--muted)]">
              Snapshot SQL Server deterministico e grafo tecnico per join,
              cardinalità e routing. Il Semantic Layer resta separato.
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
            Snapshot e Queryability Graph salvati. Semantic Layer: non inizializzato.
          </p>
        ) : null}

        {canManage ? (
          <ImportSection connections={connections} tenantId={context.tenantId} />
        ) : (
          <p className="border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--muted)]">
            Il tuo ruolo non consente di leggere o rigenerare il Queryability Graph.
          </p>
        )}

        {canManage ? (
          <section className="border-t border-[color:var(--border)] pt-6">
            <h2 className="text-base font-semibold">Versioni graph</h2>
            {graphVersions.length === 0 ? (
              <p className="mt-3 text-sm text-[color:var(--muted)]">
                Nessun Queryability Graph importato.
              </p>
            ) : (
              <div className="mt-4 flex flex-wrap gap-2">
                {graphVersions.map((graph) => (
                  <Link
                    className={`border px-3 py-1.5 text-sm ${
                      graph.id === selectedGraphRow?.id
                        ? "border-[color:var(--accent)]"
                        : "border-[color:var(--border)]"
                    }`}
                    href={`/semantic?graph=${graph.id}`}
                    key={graph.id}
                  >
                    v{graph.version} {graph.status}
                  </Link>
                ))}
              </div>
            )}
          </section>
        ) : null}

        {selectedGraph && selectedGraphRow ? (
          <>
            <GraphHeader graph={selectedGraph} row={selectedGraphRow} />
            <form action={rebuildQueryabilityGraphAction}>
              <input name="tenant_id" type="hidden" value={context.tenantId} />
              <input
                name="schema_snapshot_id"
                type="hidden"
                value={selectedGraphRow.schema_snapshot_id}
              />
              <button
                className="border border-[color:var(--border)] px-4 py-2 text-sm font-medium"
                type="submit"
              >
                Rigenera graph
              </button>
            </form>
            {snapshot ? (
              <>
                <ImportSummary summary={snapshot.summary} />
                <SnapshotObjects graph={selectedGraph} schema={snapshot.snapshot} />
              </>
            ) : null}
            <GraphMetrics graph={selectedGraph} />
            <PathInspector
              graphId={selectedGraphRow.id}
              nodes={selectedGraph.nodes.map((node) => ({
                key: node.node_key,
                label: `${node.schema_name}.${node.object_name}`
              }))}
              tenantId={context.tenantId}
            />
            <NodeTable graph={selectedGraph} />
            <EdgeTable graph={selectedGraph} />
          </>
        ) : null}
      </section>
    </main>
  );
}

function ImportSection({
  connections,
  tenantId
}: {
  connections: ConnectionRow[];
  tenantId: string;
}) {
  return (
    <section className="border-t border-[color:var(--border)] pt-6">
      <h2 className="text-base font-semibold">Import schema</h2>
      {connections.length === 0 ? (
        <p className="mt-3 text-sm text-[color:var(--muted)]">
          Nessuna connessione ready.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="text-[color:var(--muted)]">
              <tr>
                {["Connessione", "Engine", "Database", "Azione"].map((label) => (
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
                        Importa
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
  );
}

function GraphHeader({
  graph,
  row
}: {
  graph: QueryabilityGraphArtifact;
  row: GraphVersionRow;
}) {
  return (
    <section className="border-t border-[color:var(--border)] pt-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Graph status" value={graph.status} />
        <Stat label="Semantic Layer" value="not initialized" />
        <Stat label="Builder" value={row.builder_version} />
        <Stat label="Policy" value={row.policy_version} />
      </div>
      <dl className="mt-5 grid gap-3 text-xs text-[color:var(--muted)]">
        <div>
          <dt className="font-medium">Schema hash</dt>
          <dd className="break-all">{graph.schema_hash}</dd>
        </div>
        <div>
          <dt className="font-medium">Graph hash</dt>
          <dd className="break-all">{graph.graph_hash}</dd>
        </div>
        <div>
          <dt className="font-medium">Snapshot hash</dt>
          <dd className="break-all">{graph.snapshot_hash}</dd>
        </div>
        <div>
          <dt className="font-medium">Graph input hash</dt>
          <dd className="break-all">{graph.graph_input_hash}</dd>
        </div>
      </dl>
    </section>
  );
}

function GraphMetrics({ graph }: { graph: QueryabilityGraphArtifact }) {
  const fkEdges = graph.edges.filter(
    (edge): edge is QueryabilityForeignKeyEdge => edge.edge_type === "fk_join"
  );
  const metrics = [
    ["Nodi", graph.nodes.length],
    ["Colonne", graph.nodes.reduce((count, node) => count + node.columns.length, 0)],
    ["FK", fkEdges.length],
    ["Join automatici", fkEdges.filter((edge) => edge.automatic_join_allowed).length],
    ["FK untrusted", fkEdges.filter((edge) => edge.validation_status === "untrusted").length],
    ["FK disabled", fkEdges.filter((edge) => edge.enforcement_status === "disabled").length],
    ["Self reference", fkEdges.filter((edge) => edge.self_reference).length],
    ["Bridge candidate", graph.nodes.filter((node) => node.bridge_candidate).length],
    ["Lineage edge", graph.edges.filter((edge) => edge.edge_type !== "fk_join").length]
  ] as const;

  return (
    <section className="border-t border-[color:var(--border)] pt-6">
      <h2 className="text-base font-semibold">Recap graph</h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {metrics.map(([label, value]) => (
          <Stat key={label} label={label} value={String(value)} />
        ))}
      </div>
    </section>
  );
}

function NodeTable({ graph }: { graph: QueryabilityGraphArtifact }) {
  return (
    <section className="border-t border-[color:var(--border)] pt-6">
      <h2 className="text-base font-semibold">Nodi</h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs">
          <thead className="text-[color:var(--muted)]">
            <tr>
              {["Oggetto", "Tipo", "Stato", "Colonne", "Chiavi", "Trait"].map(
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
            {graph.nodes.map((node) => (
              <tr key={node.node_key}>
                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                  {node.schema_name}.{node.object_name}
                </td>
                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                  {node.object_type}
                </td>
                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                  {node.queryability_status}
                </td>
                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                  {node.columns.length}
                </td>
                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                  {node.candidate_keys.filter((key) => key.eligible_for_cardinality).length}
                </td>
                <td className="border-b border-[color:var(--border)] py-2 text-[color:var(--muted)]">
                  {[
                    node.bridge_candidate ? "bridge candidate" : null,
                    node.view_lineage_status
                      ? `lineage ${node.view_lineage_status}`
                      : null
                  ]
                    .filter(Boolean)
                    .join(", ") || "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function EdgeTable({ graph }: { graph: QueryabilityGraphArtifact }) {
  const nodes = new Map(
    graph.nodes.map((node) => [
      node.node_key,
      `${node.schema_name}.${node.object_name}`
    ])
  );
  return (
    <section className="border-t border-[color:var(--border)] pt-6">
      <h2 className="text-base font-semibold">Edge</h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs">
          <thead className="text-[color:var(--muted)]">
            <tr>
              {["Tipo", "Da", "A", "Cardinalità", "Routing", "Stato"].map(
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
            {graph.edges.map((edge) => (
              <tr key={edge.edge_key}>
                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                  {edge.edge_type}
                </td>
                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                  {nodes.get(edge.from_node_key) ?? edge.from_node_key}
                </td>
                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                  {edge.to_node_key
                    ? nodes.get(edge.to_node_key) ?? edge.to_node_key
                    : "external/unresolved"}
                </td>
                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                  {edge.edge_type === "fk_join"
                    ? `${edge.relationship_shape}, ${edge.child_to_parent}`
                    : "provenance only"}
                </td>
                <td className="border-b border-[color:var(--border)] py-2 pr-4">
                  {edge.automatic_join_allowed ? "automatic" : "excluded"}
                </td>
                <td className="border-b border-[color:var(--border)] py-2 text-[color:var(--muted)]">
                  {edge.edge_type === "fk_join"
                    ? `${edge.enforcement_status}, ${edge.validation_status}`
                    : edge.resolution_status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ImportSummary({ summary }: { summary: unknown }) {
  const parsed = SchemaImportSummarySchema.safeParse(summary);
  if (!parsed.success) {
    return null;
  }
  const value: SchemaImportSummary = parsed.data;
  const overview = [
    ["Database", value.database_name],
    ["Engine", `${value.engine} ${value.engine_version}`],
    ["Coverage", value.coverage_status],
    ["Acquisito", new Date(value.captured_at).toLocaleString("it-IT")],
    ["Durata", `${value.duration_ms} ms`],
    ["Oggetti", value.total_objects],
    ["Tabelle", value.total_tables],
    ["View", value.total_views],
    ["Colonne", value.total_columns],
    ["Oggetti queryable", value.queryable_objects],
    ["Oggetti non queryable", value.non_queryable_objects],
    ["Colonne queryable", value.queryable_columns],
    ["Colonne non queryable", value.non_queryable_columns]
  ] as const;
  const constraints = [
    ["Primary key", value.primary_keys_count],
    ["Foreign key", value.foreign_keys_count],
    ["Unique constraint", value.unique_constraints_count],
    ["Check constraint", value.check_constraints_count],
    ["Default constraint", value.default_constraints_count]
  ] as const;
  const indexes = [
    ["Indici totali", value.indexes_total_count],
    ["Su tabelle", value.table_indexes_count],
    ["Su view", value.view_indexes_count],
    ["Unici", value.unique_indexes_count],
    ["Filtrati", value.filtered_indexes_count],
    ["Con colonne incluse", value.included_columns_indexes_count]
  ] as const;
  const viewCoverage = [
    ["View totali", value.views_total],
    ["Con definizione", value.views_with_definition_count],
    ["Senza definizione", value.views_without_definition_count],
    ["Con lineage", value.views_with_lineage_count],
    ["Lineage parziale", value.views_with_partial_lineage_count],
    ["Senza lineage", value.views_without_lineage_count],
    ["Dipendenze lineage", value.view_lineage_dependencies_count]
  ] as const;
  const columns = [
    ["Tipo dichiarato disponibile", value.columns_with_declared_type_count],
    ["Tipo dichiarato assente", value.columns_without_declared_type_count],
    ["Con default", value.columns_with_default_count],
    ["Calcolate", value.computed_columns_count],
    ["Identity", value.identity_columns_count],
    ["PII", value.pii_columns_count],
    ["Escluse", value.excluded_columns_count],
    ["Sensitive", value.sensitive_columns_count]
  ] as const;
  const warningEntries = Object.entries(value.coverage_warnings_by_code).sort(
    ([left], [right]) => left.localeCompare(right)
  );
  return (
    <section className="border-t border-[color:var(--border)] pt-6">
      <h2 className="text-base font-semibold">Technical Snapshot</h2>
      <div className="mt-4 grid gap-5 border border-[color:var(--border)] p-4 text-sm">
        <SummaryValues title="Import" values={overview} />
        <div className="grid gap-5 md:grid-cols-2">
          <SummaryValues title="Vincoli" values={constraints} />
          <SummaryValues title="Indici" values={indexes} />
          <SummaryValues title="Copertura view" values={viewCoverage} />
          <SummaryValues title="Colonne" values={columns} />
        </div>
        <p className="break-all text-xs text-[color:var(--muted)]">
          Schema hash: {value.schema_hash}
        </p>
        {warningEntries.length > 0 ? (
          <div>
            <p className="text-xs font-medium text-[color:var(--muted)]">
              {coverageWarningsLabel(
                value.coverage_warnings_count,
                warningEntries.length
              )}
            </p>
            <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {warningEntries.map(([code, count]) => (
                <li key={code}>
                  {code}:{" "}
                  {code === "COLUMN_DECLARED_TYPE_UNAVAILABLE"
                    ? `${value.columns_without_declared_type_count}/${value.total_columns} colonne hanno declared type non visibile; usati native/base types.`
                    : count}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </section>
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

function SnapshotObjects({
  graph,
  schema
}: {
  graph: QueryabilityGraphArtifact;
  schema: unknown;
}) {
  const parsed = SchemaIntrospectionResponseSchema.safeParse(schema);
  if (!parsed.success) {
    return null;
  }
  const graphNodes = new Map(
    graph.nodes.map((node) => [`${node.schema_name}.${node.object_name}`, node])
  );
  return (
    <section className="border-t border-[color:var(--border)] pt-6">
      <h2 className="text-base font-semibold">Oggetti importati</h2>
      <div className="mt-5 grid gap-6">
        {parsed.data.tables.map((table) => {
          const graphNode = graphNodes.get(`${table.schema}.${table.name}`);
          const graphColumns = new Map(
            graphNode?.columns.map((column) => [column.name, column]) ?? []
          );
          return (
            <section
              className="border-t border-[color:var(--border)] pt-4"
              key={`${table.schema}.${table.name}`}
            >
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <h3 className="text-sm font-semibold">
                  {table.schema}.{table.name}
                </h3>
                <p className="text-xs text-[color:var(--muted)]">
                  {table.table_type} - {table.columns.length} colonne
                  {table.row_count_estimate !== undefined
                    ? ` - row estimate ${table.row_count_estimate}`
                    : ""}
                  {table.table_type === "view"
                    ? ` - definition ${
                        table.view_definition_available
                          ? "available"
                          : "not available"
                      } - lineage ${
                        graphNode?.view_lineage_status ?? "unavailable"
                      }`
                    : ""}
                </p>
              </div>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full border-collapse text-left text-xs">
                  <thead className="text-[color:var(--muted)]">
                    <tr>
                      {[
                        "Colonna",
                        "Tipo DB",
                        "Metadata DB",
                        "Ruolo tecnico",
                        "Queryability",
                        "Sensitivity"
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
                    {table.columns.map((column) => {
                      const graphColumn = graphColumns.get(column.name);
                      return (
                        <tr key={column.name}>
                          <td className="border-b border-[color:var(--border)] py-2 pr-4">
                            {column.name}
                          </td>
                          <td className="border-b border-[color:var(--border)] py-2 pr-4">
                            {schemaColumnTypeLabel(column)}
                          </td>
                          <td className="border-b border-[color:var(--border)] py-2 pr-4">
                            {schemaColumnFlags(column).join(" ") || "-"}
                          </td>
                          <td className="border-b border-[color:var(--border)] py-2 pr-4">
                            {column.technical_role}
                          </td>
                          <td className="border-b border-[color:var(--border)] py-2 pr-4">
                            {graphColumn?.queryability_status ?? "excluded"}
                          </td>
                          <td className="border-b border-[color:var(--border)] py-2 text-[color:var(--muted)]">
                            {graphColumn?.sensitivity ?? "none"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })}
      </div>
    </section>
  );
}

function schemaColumnTypeLabel(column: SchemaColumnMetadata) {
  const nativeType = column.native_type ?? column.data_type;
  if (
    column.declared_type_available &&
    column.declared_type &&
    column.declared_type !== nativeType
  ) {
    return `${nativeType} (${column.declared_type})`;
  }
  return nativeType;
}

function schemaColumnFlags(column: SchemaColumnMetadata) {
  return [
    column.is_primary_key ? "PK" : null,
    column.is_foreign_key ? "FK" : null,
    column.is_unique_member ? "unique" : null,
    column.is_identity ? "identity" : null,
    column.is_computed ? "computed" : null,
    column.default_value !== undefined ? "default" : null,
    column.is_nullable ? "nullable" : "not null",
    column.collation ? `collation ${column.collation}` : null
  ].filter((value): value is string => value !== null);
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-l-2 border-[color:var(--border)] pl-3">
      <div className="text-xs text-[color:var(--muted)]">{label}</div>
      <div className="mt-1 text-sm font-medium">{value}</div>
    </div>
  );
}

async function readSnapshotSummary({
  admin,
  snapshotId,
  tenantId
}: {
  admin: ReturnType<typeof createSupabaseAdminClient>;
  snapshotId: string;
  tenantId: string;
}) {
  const { data } = await admin
    .from("schema_snapshots")
    .select("id,summary,snapshot")
    .eq("tenant_id", tenantId)
    .eq("id", snapshotId)
    .single();
  if (!data) {
    return null;
  }
  return {
    id: data.id as string,
    summary: SchemaImportSummarySchema.parse(data.summary),
    snapshot: SchemaIntrospectionResponseSchema.parse(data.snapshot)
  } satisfies SnapshotSummaryRow;
}
