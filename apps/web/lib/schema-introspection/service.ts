import "server-only";

import { randomUUID } from "node:crypto";
import {
  ConnectionMetadataSchema,
  QueryabilityGraphArtifactSchema,
  SchemaImportSummarySchema,
  SchemaIntrospectionResponseSchema,
  type ConnectionMetadata,
  type QueryabilityGraphArtifact,
  type SchemaImportSummary,
  type SchemaIntrospectionResponse
} from "@atlantebi/contracts";
import { GoogleAuth } from "google-auth-library";

import type { ActiveTenantContext } from "../tenant";
import { canManageConnections } from "../tenant";
import {
  isSecurityOperationLimitError,
  withSecurityOperationLease
} from "../security/operation-lease";
import { createSupabaseAdminClient } from "../supabase/admin";

type IntrospectionResult =
  | {
      ok: true;
      schemaSnapshotId: string;
      queryabilityGraphId: string;
      queryabilityGraphVersion: number;
      queryabilityGraphStatus: "complete" | "partial";
      semanticStatus: "not_initialized";
      deduplicated: boolean;
      tableCount: number;
      columnCount: number;
    }
  | { ok: false; code: string; message: string };

export type QueryabilityRebuildResult =
  | {
      ok: true;
      schemaSnapshotId: string;
      queryabilityGraphId: string;
      queryabilityGraphVersion: number;
      queryabilityGraphStatus: "complete" | "partial";
      semanticStatus: "not_initialized";
      deduplicated: boolean;
    }
  | { ok: false; code: string; message: string };

type ConnectionSecretRow = {
  id: string;
  tenant_id: string;
  name: string;
  engine: "sqlserver" | "mysql";
  network_mode: "public_allowlist" | "vpn";
  host: string;
  port: number;
  database_name: string;
  username: string;
  tls_required: boolean;
  trust_server_certificate: boolean;
  tls_server_name: string | null;
  secret_ref: string | null;
  status: "draft" | "ready" | "failed" | "disabled";
};

type PersistableQueryabilityGraph = QueryabilityGraphArtifact & {
  status: "complete" | "partial";
};

export async function introspectConnection({
  connectionId,
  context,
  timeoutMs
}: {
  connectionId: string;
  context: ActiveTenantContext;
  timeoutMs: number;
}): Promise<IntrospectionResult> {
  if (!canManageConnections(context.role)) {
    return {
      ok: false,
      code: "schema_forbidden",
      message: "Il tuo ruolo non consente di importare lo schema."
    };
  }

  const connection = await readConnectionForEngine({
    connectionId,
    tenantId: context.tenantId
  });

  if (!connection) {
    return {
      ok: false,
      code: "connection_not_found",
      message: "Connessione non trovata."
    };
  }

  if (connection.status !== "ready" || !connection.secret_ref) {
    return {
      ok: false,
      code: "connection_not_ready",
      message: "La connessione deve essere ready prima dell'introspection."
    };
  }

  const metadata = ConnectionMetadataSchema.parse({
    tenant_id: connection.tenant_id,
    connection_id: connection.id,
    name: connection.name,
    engine: connection.engine,
    network_mode: connection.network_mode,
    host: connection.host,
    port: connection.port,
    database_name: connection.database_name,
    username: connection.username,
    tls_required: connection.tls_required,
    trust_server_certificate: connection.trust_server_certificate,
    tls_server_name: connection.tls_server_name,
    secret_ref: connection.secret_ref,
    status: connection.status
  });

  try {
    return await withSecurityOperationLease({
      actorUserId: context.userId,
      operation: "schema_introspection",
      resourceKey: connection.id,
      run: async () => {
        const schema = await runSchemaIntrospection(metadata, timeoutMs);
        const schemaSnapshotId = randomUUID();
        const graph = await runQueryabilityCompilation({
          connectionId: connection.id,
          schema,
          schemaSnapshotId,
          tenantId: context.tenantId,
          timeoutMs
        });
        if (graph.status === "blocked") {
          return {
            ok: false,
            code: "queryability_graph_blocked",
            message: "Il Queryability Graph non è utilizzabile."
          };
        }
        const persistableGraph: PersistableQueryabilityGraph = {
          ...graph,
          status: graph.status
        };
        return persistSchemaIntrospection({
          connection,
          context,
          graph: persistableGraph,
          schemaSnapshotId,
          schema
        });
      },
      tenantId: context.tenantId
    });
  } catch (error) {
    if (isSecurityOperationLimitError(error)) {
      return {
        ok: false,
        code: "schema_rate_limited",
        message: "Un import schema è già in corso o il limite è stato superato."
      };
    }
    throw error;
  }
}

export async function rebuildQueryabilityGraph({
  context,
  schemaSnapshotId,
  timeoutMs
}: {
  context: ActiveTenantContext;
  schemaSnapshotId: string;
  timeoutMs: number;
}): Promise<QueryabilityRebuildResult> {
  if (!canManageConnections(context.role)) {
    return {
      ok: false,
      code: "queryability_rebuild_forbidden",
      message: "Il tuo ruolo non consente di rigenerare il graph."
    };
  }

  const admin = createSupabaseAdminClient();
  const { data, error } = await admin
    .from("schema_snapshots")
    .select(
      "id,connection_id,engine,snapshot,summary,table_count,column_count,introspected_at"
    )
    .eq("tenant_id", context.tenantId)
    .eq("id", schemaSnapshotId)
    .single();
  if (error || !data) {
    return {
      ok: false,
      code: "schema_snapshot_not_found",
      message: "Snapshot tecnico non trovato."
    };
  }

  try {
    const schema = SchemaIntrospectionResponseSchema.parse(data.snapshot);
    const summary = SchemaImportSummarySchema.parse(data.summary);
    const graph = await runQueryabilityCompilation({
      connectionId: data.connection_id as string,
      schema,
      schemaSnapshotId,
      tenantId: context.tenantId,
      timeoutMs
    });
    if (graph.status === "blocked") {
      return {
        ok: false,
        code: "queryability_graph_blocked",
        message: "Il Queryability Graph non è utilizzabile."
      };
    }

    const { data: persistedData, error: persistError } = await admin.rpc(
      "persist_queryability_graph_import",
      {
        actor_user_id: context.userId,
        queryability_graph: graph,
        reuse_existing_snapshot: true,
        target_column_count: data.column_count as number,
        target_connection_id: data.connection_id as string,
        target_engine: data.engine as "sqlserver",
        target_introspected_at: data.introspected_at as string,
        target_snapshot_id: schemaSnapshotId,
        target_summary: summary,
        target_table_count: data.table_count as number,
        target_tenant_id: context.tenantId,
        technical_snapshot: schema
      }
    );
    const persisted = Array.isArray(persistedData)
      ? persistedData[0]
      : persistedData;
    if (persistError || !persisted) {
      return {
        ok: false,
        code: "queryability_rebuild_save_failed",
        message: "Rigenerazione Queryability Graph non salvata."
      };
    }

    const result = persisted as {
      schema_snapshot_id: string;
      queryability_graph_id: string;
      queryability_graph_version: number;
      deduplicated: boolean;
      semantic_status: "not_initialized";
    };
    return {
      ok: true,
      schemaSnapshotId: result.schema_snapshot_id,
      queryabilityGraphId: result.queryability_graph_id,
      queryabilityGraphVersion: result.queryability_graph_version,
      queryabilityGraphStatus: graph.status,
      semanticStatus: result.semantic_status,
      deduplicated: result.deduplicated
    };
  } catch {
    return {
      ok: false,
      code: "queryability_rebuild_failed",
      message: "Rigenerazione Queryability Graph fallita."
    };
  }
}

async function readConnectionForEngine({
  connectionId,
  tenantId
}: {
  connectionId: string;
  tenantId: string;
}) {
  const admin = createSupabaseAdminClient();
  const { data, error } = await admin
    .from("db_connections")
    .select(
      "id,tenant_id,name,engine,network_mode,host,port,database_name,username,tls_required,trust_server_certificate,tls_server_name,secret_ref,status"
    )
    .eq("tenant_id", tenantId)
    .eq("id", connectionId)
    .single();

  if (error || !data) {
    return null;
  }

  return data as ConnectionSecretRow;
}

async function runSchemaIntrospection(
  connection: ConnectionMetadata,
  timeoutMs: number
) {
  const queryEngineUrl = process.env.QUERY_ENGINE_URL;

  if (!queryEngineUrl) {
    throw new Error("QUERY_ENGINE_URL is required.");
  }

  const headers: Record<string, string> = {
    "content-type": "application/json"
  };
  const token = process.env.QUERY_ENGINE_API_TOKEN;
  if (token) {
    headers["x-atlante-query-engine-token"] = token;
  }

  const url = new URL("/schema/introspect", queryEngineUrl).toString();
  const body = JSON.stringify({ connection, timeout_ms: timeoutMs });

  if (process.env.QUERY_ENGINE_AUTH_MODE === "google_id_token") {
    const client = await new GoogleAuth().getIdTokenClient(queryEngineUrl);
    const response = await client.request({
      data: body,
      headers,
      method: "POST",
      timeout: timeoutMs + 5000,
      url,
      validateStatus: () => true
    });

    if (response.status < 200 || response.status >= 300) {
      throw new Error("Schema introspection failed.");
    }

    return validatedIntrospectionResponse(response.data);
  }

  const response = await fetch(url, {
    body,
    headers,
    method: "POST",
    signal: AbortSignal.timeout(timeoutMs + 5000)
  });

  if (!response.ok) {
    throw new Error("Schema introspection failed.");
  }

  return validatedIntrospectionResponse(await response.json());
}

async function persistSchemaIntrospection({
  connection,
  context,
  graph,
  schemaSnapshotId,
  schema
}: {
  connection: ConnectionSecretRow;
  context: ActiveTenantContext;
  graph: PersistableQueryabilityGraph;
  schemaSnapshotId: string;
  schema: SchemaIntrospectionResponse;
}): Promise<IntrospectionResult> {
  const summary = buildSchemaImportSummary(schema, graph);
  const admin = createSupabaseAdminClient();
  const { data, error } = await admin.rpc("persist_queryability_graph_import", {
    actor_user_id: context.userId,
    queryability_graph: graph,
    reuse_existing_snapshot: false,
    target_column_count: countColumns(schema),
    target_connection_id: connection.id,
    target_engine: schema.engine ?? connection.engine,
    target_introspected_at: schema.introspected_at,
    target_snapshot_id: schemaSnapshotId,
    target_summary: summary,
    target_table_count: summary.total_tables,
    target_tenant_id: context.tenantId,
    technical_snapshot: schema
  });

  const result = Array.isArray(data) ? data[0] : data;
  if (error || !result) {
    return {
      ok: false,
      code: "schema_import_save_failed",
      message: "Import schema non salvato."
    };
  }

  const persisted = result as {
    schema_snapshot_id: string;
    queryability_graph_id: string;
    queryability_graph_version: number;
    deduplicated: boolean;
    semantic_status: "not_initialized";
  };
  return {
    ok: true,
    schemaSnapshotId: persisted.schema_snapshot_id,
    queryabilityGraphId: persisted.queryability_graph_id,
    queryabilityGraphVersion: persisted.queryability_graph_version,
    queryabilityGraphStatus: graph.status,
    semanticStatus: persisted.semantic_status,
    deduplicated: persisted.deduplicated,
    tableCount: summary.total_tables,
    columnCount: summary.total_columns
  };
}

export function buildSchemaImportSummary(
  schema: SchemaIntrospectionResponse,
  graph: QueryabilityGraphArtifact
): SchemaImportSummary {
  const allColumns = graph.nodes.flatMap((node) => node.columns);
  const views = schema.tables.filter((table) => table.table_type === "view");
  const warningCounts = schema.coverage_warnings.reduce<Record<string, number>>(
    (counts, warning) => {
      counts[warning.code] = (counts[warning.code] ?? 0) + 1;
      return counts;
    },
    {}
  );
  const viewHasPartialLineage = (schemaName: string, objectName: string) =>
    schema.coverage_warnings.some(
      (warning) =>
        ["VIEW_LINEAGE_PARTIAL", "VIEW_LINEAGE_UNRESOLVED_REFERENCE"].includes(
          warning.code
        ) &&
        warning.object_schema === schemaName &&
        warning.object_name === objectName
    );

  return SchemaImportSummarySchema.parse({
    database_name: schema.database_name,
    engine: schema.engine,
    engine_version: schema.engine_version,
    schema_hash: schema.schema_hash,
    coverage_status: schema.coverage_status,
    captured_at: schema.introspected_at,
    duration_ms: schema.duration_ms,
    total_objects: schema.tables.length,
    total_tables: schema.tables.filter(
      (table) => table.table_type === "base_table"
    ).length,
    total_views: views.length,
    total_columns: allColumns.length,
    queryable_objects: graph.nodes.filter(
      (node) => node.queryability_status === "queryable"
    ).length,
    non_queryable_objects: graph.nodes.filter(
      (node) => node.queryability_status !== "queryable"
    ).length,
    queryable_columns: allColumns.filter(
      (column) => column.queryability_status === "queryable"
    ).length,
    non_queryable_columns: allColumns.filter(
      (column) => column.queryability_status !== "queryable"
    ).length,
    primary_keys_count: schema.tables.filter((table) => table.primary_key).length,
    foreign_keys_count: schema.foreign_keys.length,
    unique_constraints_count: schema.unique_constraints.length,
    check_constraints_count: schema.check_constraints.length,
    default_constraints_count: schema.default_constraints.length,
    indexes_total_count: schema.indexes.length,
    table_indexes_count: schema.indexes.filter(
      (index) => index.object_type === "table"
    ).length,
    view_indexes_count: schema.indexes.filter(
      (index) => index.object_type === "view"
    ).length,
    unique_indexes_count: schema.indexes.filter((index) => index.is_unique).length,
    filtered_indexes_count: schema.indexes.filter(
      (index) => index.filter_definition !== undefined
    ).length,
    included_columns_indexes_count: schema.indexes.filter(
      (index) => index.included_columns.length > 0
    ).length,
    views_total: views.length,
    views_with_definition_count: views.filter(
      (view) => view.view_definition_available === true
    ).length,
    views_without_definition_count: views.filter(
      (view) => view.view_definition_available !== true
    ).length,
    views_with_lineage_count: views.filter(
      (view) => view.lineage_available === true
    ).length,
    views_with_partial_lineage_count: views.filter((view) =>
      viewHasPartialLineage(view.schema, view.name)
    ).length,
    views_without_lineage_count: views.filter(
      (view) => view.lineage_available !== true
    ).length,
    view_lineage_dependencies_count: views.reduce(
      (count, view) => count + view.view_lineage.length,
      0
    ),
    columns_with_declared_type_count: schema.tables.reduce(
      (count, table) =>
        count +
        table.columns.filter((column) => column.declared_type_available).length,
      0
    ),
    columns_without_declared_type_count: schema.tables.reduce(
      (count, table) =>
        count +
        table.columns.filter((column) => !column.declared_type_available).length,
      0
    ),
    columns_with_default_count: schema.tables.reduce(
      (count, table) =>
        count +
        table.columns.filter((column) => column.default_value !== undefined).length,
      0
    ),
    computed_columns_count: schema.tables.reduce(
      (count, table) =>
        count + table.columns.filter((column) => column.is_computed).length,
      0
    ),
    identity_columns_count: schema.tables.reduce(
      (count, table) =>
        count + table.columns.filter((column) => column.is_identity).length,
      0
    ),
    pii_columns_count: allColumns.filter(
      (column) => column.sensitivity === "pii"
    ).length,
    excluded_columns_count: allColumns.filter(
      (column) => column.queryability_status === "excluded"
    ).length,
    sensitive_columns_count: allColumns.filter(
      (column) => column.sensitivity === "sensitive"
    ).length,
    coverage_warnings_count: schema.coverage_warnings.length,
    coverage_warnings_by_code: warningCounts
  });
}

async function runQueryabilityCompilation({
  connectionId,
  schema,
  schemaSnapshotId,
  tenantId,
  timeoutMs
}: {
  connectionId: string;
  schema: SchemaIntrospectionResponse;
  schemaSnapshotId: string;
  tenantId: string;
  timeoutMs: number;
}) {
  const queryEngineUrl = process.env.QUERY_ENGINE_URL;
  if (!queryEngineUrl) {
    throw new Error("QUERY_ENGINE_URL is required.");
  }

  const headers: Record<string, string> = {
    "content-type": "application/json"
  };
  const token = process.env.QUERY_ENGINE_API_TOKEN;
  if (token) {
    headers["x-atlante-query-engine-token"] = token;
  }
  const url = new URL("/queryability/compile", queryEngineUrl).toString();
  const body = JSON.stringify({
    tenant_id: tenantId,
    connection_id: connectionId,
    schema_snapshot_id: schemaSnapshotId,
    snapshot: schema
  });

  if (process.env.QUERY_ENGINE_AUTH_MODE === "google_id_token") {
    const client = await new GoogleAuth().getIdTokenClient(queryEngineUrl);
    const response = await client.request({
      data: body,
      headers,
      method: "POST",
      timeout: timeoutMs + 5000,
      url,
      validateStatus: () => true
    });
    if (response.status < 200 || response.status >= 300) {
      throw new Error("Queryability graph compilation failed.");
    }
    return QueryabilityGraphArtifactSchema.parse(response.data);
  }

  const response = await fetch(url, {
    body,
    headers,
    method: "POST",
    signal: AbortSignal.timeout(timeoutMs + 5000)
  });
  if (!response.ok) {
    throw new Error("Queryability graph compilation failed.");
  }
  return QueryabilityGraphArtifactSchema.parse(await response.json());
}

function validatedIntrospectionResponse(payload: unknown) {
  const schema = SchemaIntrospectionResponseSchema.parse(payload);

  if (
    schema.status !== "ok" ||
    !schema.engine ||
    !schema.schema_hash ||
    !schema.snapshot_hash
  ) {
    throw new Error(schema.sanitized_error ?? schema.message);
  }

  return schema;
}

function countColumns(schema: SchemaIntrospectionResponse) {
  return schema.tables.reduce((count, table) => count + table.columns.length, 0);
}
