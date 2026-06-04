import "server-only";

import {
  ConnectionMetadataSchema,
  SchemaIntrospectionResponseSchema,
  type ConnectionMetadata,
  type SchemaColumnMetadata,
  type SchemaIntrospectionResponse
} from "@atlantebi/contracts";
import { GoogleAuth } from "google-auth-library";

import type { ActiveTenantContext } from "../tenant";
import { canManageConnections } from "../tenant";
import { createSupabaseAdminClient } from "../supabase/admin";

type IntrospectionResult =
  | {
      ok: true;
      schemaSnapshotId: string;
      semanticVersionId: string;
      tableCount: number;
      columnCount: number;
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

type SemanticTableInsert = {
  tenant_id: string;
  semantic_version_id: string;
  physical_schema: string;
  physical_name: string;
  active: boolean;
  metadata: Record<string, string | number | boolean>;
};

type SemanticTableRow = {
  id: string;
  physical_schema: string;
  physical_name: string;
};

type SemanticColumnInsert = {
  tenant_id: string;
  semantic_table_id: string;
  physical_name: string;
  data_type: string;
  role: "dimension" | "measure" | "date" | "identifier" | "unknown";
  pii: boolean;
  metadata: Record<string, string | number | boolean>;
};

type SemanticRelationshipInsert = {
  tenant_id: string;
  semantic_version_id: string;
  from_table_id: string;
  from_columns: string[];
  to_table_id: string;
  to_columns: string[];
  cardinality: "many_to_one";
  semantic_status: "confirmed";
  source: "database_fk";
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

  const schema = await runSchemaIntrospection(metadata, timeoutMs);
  return persistSchemaIntrospection({
    connection,
    context,
    schema
  });
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
  schema
}: {
  connection: ConnectionSecretRow;
  context: ActiveTenantContext;
  schema: SchemaIntrospectionResponse;
}): Promise<IntrospectionResult> {
  const { supabase, tenantId, userId } = context;

  const { data: snapshot, error: snapshotError } = await supabase
    .from("schema_snapshots")
    .insert({
      tenant_id: tenantId,
      connection_id: connection.id,
      engine: schema.engine ?? connection.engine,
      snapshot: schema,
      snapshot_version: 1,
      table_count: schema.tables.length,
      column_count: countColumns(schema),
      introspected_at: schema.introspected_at,
      created_by: userId
    })
    .select("id")
    .single();

  if (snapshotError || !snapshot) {
    return {
      ok: false,
      code: "schema_snapshot_save_failed",
      message: "Snapshot schema non salvato."
    };
  }

  const version = await nextSemanticVersion({
    connectionId: connection.id,
    context
  });

  const { data: semanticVersion, error: versionError } = await supabase
    .from("semantic_versions")
    .insert({
      tenant_id: tenantId,
      connection_id: connection.id,
      schema_snapshot_id: (snapshot as { id: string }).id,
      version,
      status: "draft",
      created_by: userId
    })
    .select("id")
    .single();

  if (versionError || !semanticVersion) {
    return {
      ok: false,
      code: "semantic_version_save_failed",
      message: "Versione semantica non salvata."
    };
  }

  const semanticVersionId = (semanticVersion as { id: string }).id;
  const tableRows = await insertSemanticTables({
    context,
    schema,
    semanticVersionId
  });

  if (!tableRows.ok) {
    return tableRows;
  }

  const columnsResult = await insertSemanticColumns({
    context,
    schema,
    tableRows: tableRows.tables
  });

  if (!columnsResult.ok) {
    return columnsResult;
  }

  const relationshipsResult = await insertSemanticRelationships({
    context,
    relationships: schema.foreign_keys,
    semanticVersionId,
    tableRows: tableRows.tables
  });

  if (!relationshipsResult.ok) {
    return relationshipsResult;
  }

  await supabase.from("audit_logs").insert({
    tenant_id: tenantId,
    actor_user_id: userId,
    action: "schema.introspected",
    subject_type: "db_connection",
    subject_id: connection.id,
    metadata: {
      schema_snapshot_id: (snapshot as { id: string }).id,
      semantic_version_id: semanticVersionId,
      table_count: schema.tables.length,
      column_count: countColumns(schema)
    }
  });

  return {
    ok: true,
    schemaSnapshotId: (snapshot as { id: string }).id,
    semanticVersionId,
    tableCount: schema.tables.length,
    columnCount: countColumns(schema)
  };
}

async function nextSemanticVersion({
  connectionId,
  context
}: {
  connectionId: string;
  context: ActiveTenantContext;
}) {
  const { data } = await context.supabase
    .from("semantic_versions")
    .select("version")
    .eq("tenant_id", context.tenantId)
    .eq("connection_id", connectionId)
    .order("version", { ascending: false })
    .limit(1);

  const latest = (data?.[0] as { version: number } | undefined)?.version ?? 0;
  return latest + 1;
}

async function insertSemanticTables({
  context,
  schema,
  semanticVersionId
}: {
  context: ActiveTenantContext;
  schema: SchemaIntrospectionResponse;
  semanticVersionId: string;
}): Promise<
  | { ok: true; tables: SemanticTableRow[] }
  | { ok: false; code: string; message: string }
> {
  const rows: SemanticTableInsert[] = schema.tables.map((table) => ({
    tenant_id: context.tenantId,
    semantic_version_id: semanticVersionId,
    physical_schema: table.schema,
    physical_name: table.name,
    active: false,
    metadata: {
      table_type: table.table_type,
      column_count: table.columns.length,
      primary_key_count: table.primary_key?.columns.length ?? 0
    }
  }));

  if (rows.length === 0) {
    return { ok: true, tables: [] };
  }

  const { data, error } = await context.supabase
    .from("semantic_tables")
    .insert(rows)
    .select("id,physical_schema,physical_name");

  if (error || !data) {
    return {
      ok: false,
      code: "semantic_tables_save_failed",
      message: "Tabelle semantiche non salvate."
    };
  }

  return { ok: true, tables: data as SemanticTableRow[] };
}

async function insertSemanticColumns({
  context,
  schema,
  tableRows
}: {
  context: ActiveTenantContext;
  schema: SchemaIntrospectionResponse;
  tableRows: SemanticTableRow[];
}): Promise<{ ok: true } | { ok: false; code: string; message: string }> {
  const tableIds = new Map(
    tableRows.map((table) => [
      physicalTableKey(table.physical_schema, table.physical_name),
      table.id
    ])
  );
  const rows = schema.tables.flatMap((table) =>
    table.columns.map((column) => {
      const tableId = tableIds.get(physicalTableKey(table.schema, table.name));
      if (!tableId) {
        throw new Error("Semantic table id missing.");
      }
      const primaryKeyColumns = new Set(
        (table.primary_key?.columns ?? []).map((name) => name.toLowerCase())
      );

      return toSemanticColumnInsert({
        column,
        primaryKeyColumns,
        tableId,
        tenantId: context.tenantId
      });
    })
  );

  if (rows.length === 0) {
    return { ok: true };
  }

  const { error } = await context.supabase.from("semantic_columns").insert(rows);

  if (error) {
    return {
      ok: false,
      code: "semantic_columns_save_failed",
      message: "Colonne semantiche non salvate."
    };
  }

  return { ok: true };
}

async function insertSemanticRelationships({
  context,
  relationships,
  semanticVersionId,
  tableRows
}: {
  context: ActiveTenantContext;
  relationships: SchemaIntrospectionResponse["foreign_keys"];
  semanticVersionId: string;
  tableRows: SemanticTableRow[];
}): Promise<{ ok: true } | { ok: false; code: string; message: string }> {
  const tableIds = new Map(
    tableRows.map((table) => [
      physicalTableKey(table.physical_schema, table.physical_name),
      table.id
    ])
  );
  const rows: SemanticRelationshipInsert[] = [];

  for (const relationship of relationships) {
    const fromTableId = tableIds.get(
      physicalTableKey(relationship.from_schema, relationship.from_table)
    );
    const toTableId = tableIds.get(
      physicalTableKey(relationship.to_schema, relationship.to_table)
    );

    if (!fromTableId || !toTableId) {
      continue;
    }

    rows.push({
      tenant_id: context.tenantId,
      semantic_version_id: semanticVersionId,
      from_table_id: fromTableId,
      from_columns: relationship.from_columns,
      to_table_id: toTableId,
      to_columns: relationship.to_columns,
      cardinality: "many_to_one",
      semantic_status: "confirmed",
      source: "database_fk"
    });
  }

  if (rows.length === 0) {
    return { ok: true };
  }

  const { error } = await context.supabase
    .from("semantic_relationships")
    .insert(rows);

  if (error) {
    return {
      ok: false,
      code: "semantic_relationships_save_failed",
      message: "Relazioni semantiche non salvate."
    };
  }

  return { ok: true };
}

function toSemanticColumnInsert({
  column,
  primaryKeyColumns,
  tableId,
  tenantId
}: {
  column: SchemaColumnMetadata;
  primaryKeyColumns: Set<string>;
  tableId: string;
  tenantId: string;
}): SemanticColumnInsert {
  const metadata: Record<string, string | number | boolean> = {
    ordinal_position: column.ordinal_position,
    is_nullable: column.is_nullable,
    is_primary_key: primaryKeyColumns.has(column.name.toLowerCase()),
    is_identity: column.is_identity,
    is_computed: column.is_computed
  };

  if (column.max_length !== undefined) {
    metadata.max_length = column.max_length;
  }
  if (column.numeric_precision !== undefined) {
    metadata.numeric_precision = column.numeric_precision;
  }
  if (column.numeric_scale !== undefined) {
    metadata.numeric_scale = column.numeric_scale;
  }
  if (column.datetime_precision !== undefined) {
    metadata.datetime_precision = column.datetime_precision;
  }

  const sensitivity = classifyColumnSensitivity(column.name);
  if (sensitivity.kind === "credential") {
    metadata.is_sensitive = true;
    metadata.queryable = false;
    metadata.sensitive_reason = sensitivity.reason;
  } else if (sensitivity.kind === "pii") {
    metadata.pii_reason = sensitivity.reason;
  }

  return {
    tenant_id: tenantId,
    semantic_table_id: tableId,
    physical_name: column.name,
    data_type: column.data_type,
    role:
      sensitivity.kind === "credential"
        ? "unknown"
        : inferColumnRole(column, primaryKeyColumns),
    pii: sensitivity.kind !== "none",
    metadata
  };
}

export type ColumnSensitivity =
  | { kind: "none" }
  | { kind: "pii"; reason: "direct_person_identifier" | "contact_identifier" }
  | {
      kind: "credential";
      reason:
        | "credential_name"
        | "credential_derivative_name"
        | "secret_name"
        | "secret_key_name";
    };

export function classifyColumnSensitivity(columnName: string): ColumnSensitivity {
  const tokens = columnNameTokens(columnName);
  const tokenSet = new Set(tokens);

  if (tokens.some((token) => ["password", "passwd", "pwd"].includes(token))) {
    return { kind: "credential", reason: "credential_name" };
  }

  if (tokens.some((token) => ["hash", "salt"].includes(token))) {
    return { kind: "credential", reason: "credential_derivative_name" };
  }

  if (
    tokens.some((token) =>
      ["secret", "token", "credential", "credentials"].includes(token)
    )
  ) {
    return { kind: "credential", reason: "secret_name" };
  }

  if (
    tokenSet.has("key") &&
    ["api", "access", "private", "secret"].some((token) =>
      tokenSet.has(token)
    )
  ) {
    return { kind: "credential", reason: "secret_key_name" };
  }

  if (tokens.some((token) => ["email", "phone"].includes(token))) {
    return { kind: "pii", reason: "contact_identifier" };
  }

  const compactName = tokens.join("");
  if (
    compactName === "firstname" ||
    compactName === "middlename" ||
    compactName === "lastname" ||
    compactName === "fullname" ||
    compactName === "addressline" ||
    compactName === "addressline1" ||
    compactName === "addressline2"
  ) {
    return { kind: "pii", reason: "direct_person_identifier" };
  }

  return { kind: "none" };
}

function columnNameTokens(columnName: string) {
  return columnName
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((token) => token.length > 0);
}

function inferColumnRole(
  column: SchemaColumnMetadata,
  primaryKeyColumns: Set<string>
): SemanticColumnInsert["role"] {
  const name = column.name.toLowerCase();
  const dataType = column.data_type.toLowerCase();

  if (primaryKeyColumns.has(name) || name === "id" || name.endsWith("id")) {
    return "identifier";
  }

  if (dataType.includes("date") || dataType.includes("time")) {
    return "date";
  }

  if (
    ["money", "decimal", "numeric", "float", "real"].some((type) =>
      dataType.includes(type)
    )
  ) {
    return "measure";
  }

  if (["int", "bit", "char", "text", "uniqueidentifier"].some((type) =>
    dataType.includes(type)
  )) {
    return "dimension";
  }

  return "unknown";
}

function physicalTableKey(schema: string, table: string) {
  return `${schema}.${table}`.toLowerCase();
}

function validatedIntrospectionResponse(payload: unknown) {
  const schema = SchemaIntrospectionResponseSchema.parse(payload);

  if (schema.status !== "ok" || !schema.engine) {
    throw new Error(schema.sanitized_error ?? schema.message);
  }

  return schema;
}

function countColumns(schema: SchemaIntrospectionResponse) {
  return schema.tables.reduce((count, table) => count + table.columns.length, 0);
}
