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
import {
  isSecurityOperationLimitError,
  withSecurityOperationLease
} from "../security/operation-lease";
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

type SemanticTableProjection = {
  physical_schema: string;
  physical_name: string;
  metadata: Record<string, string | number | boolean>;
  columns: SemanticColumnProjection[];
};

type SemanticColumnProjection = {
  physical_name: string;
  data_type: string;
  role: "dimension" | "measure" | "date" | "identifier" | "unknown";
  pii: boolean;
  metadata: Record<string, string | number | boolean>;
};

type SemanticRelationshipProjection = {
  from_schema: string;
  from_table: string;
  from_columns: string[];
  to_schema: string;
  to_table: string;
  to_columns: string[];
  cardinality: "one_to_one" | "many_to_one";
  constraint_name: string;
  update_rule: string;
  delete_rule: string;
  is_disabled: boolean;
  is_not_trusted: boolean;
  verified_by_db: boolean;
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
        return persistSchemaIntrospection({
          connection,
          context,
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
  const tableProjection = buildSemanticTableProjection(schema);
  const relationshipProjection = buildRelationshipProjection(schema);
  const admin = createSupabaseAdminClient();
  const { data, error } = await admin.rpc("persist_technical_schema_import", {
    actor_user_id: context.userId,
    relationship_projection: relationshipProjection,
    semantic_table_projection: tableProjection,
    target_column_count: countColumns(schema),
    target_connection_id: connection.id,
    target_engine: schema.engine ?? connection.engine,
    target_introspected_at: schema.introspected_at,
    target_table_count: schema.tables.length,
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
    semantic_version_id: string;
  };
  return {
    ok: true,
    schemaSnapshotId: persisted.schema_snapshot_id,
    semanticVersionId: persisted.semantic_version_id,
    tableCount: schema.tables.length,
    columnCount: countColumns(schema)
  };
}

function toSemanticColumnProjection({
  column,
  primaryKeyColumns
}: {
  column: SchemaColumnMetadata;
  primaryKeyColumns: Set<string>;
}): SemanticColumnProjection {
  const metadata: Record<string, string | number | boolean> = {
    ordinal_position: column.ordinal_position,
    is_nullable: column.is_nullable,
    is_primary_key: primaryKeyColumns.has(column.name.toLowerCase()),
    is_foreign_key: column.is_foreign_key,
    is_unique_member: column.is_unique_member,
    is_identity: column.is_identity,
    is_computed: column.is_computed
  };

  if (column.declared_type !== undefined) {
    metadata.declared_type = column.declared_type;
  }
  if (column.declared_type_schema !== undefined) {
    metadata.declared_type_schema = column.declared_type_schema;
  }
  if (column.declared_type_name !== undefined) {
    metadata.declared_type_name = column.declared_type_name;
  }
  if (column.declared_type_is_user_defined !== undefined) {
    metadata.declared_type_is_user_defined = column.declared_type_is_user_defined;
  }
  if (column.declared_type_is_assembly !== undefined) {
    metadata.declared_type_is_assembly = column.declared_type_is_assembly;
  }
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
  if (column.native_type !== undefined) {
    metadata.native_type = column.native_type;
  }
  if (column.normalized_type !== undefined) {
    metadata.normalized_type = column.normalized_type;
  }
  if (column.default_value !== undefined) {
    metadata.has_default = true;
  }
  if (column.collation !== undefined) {
    metadata.collation = column.collation;
  }
  if (column.identity_seed !== undefined) {
    metadata.identity_seed = column.identity_seed;
  }
  if (column.identity_increment !== undefined) {
    metadata.identity_increment = column.identity_increment;
  }
  if (column.computed_expression !== undefined) {
    metadata.has_computed_expression = true;
  }
  if (column.comment !== undefined) {
    metadata.has_comment = true;
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

function buildSemanticTableProjection(
  schema: SchemaIntrospectionResponse
): SemanticTableProjection[] {
  return schema.tables.map((table) => {
    const metadata: SemanticTableProjection["metadata"] = {
      table_type: table.table_type,
      column_count: table.columns.length,
      primary_key_count: table.primary_key?.columns.length ?? 0,
      has_definition_hash: table.definition_hash !== undefined
    };
    if (table.row_count_estimate !== undefined) {
      metadata.row_count_estimate = table.row_count_estimate;
    }
    if (table.view_definition_available !== undefined) {
      metadata.view_definition_available = table.view_definition_available;
    }
    if (table.lineage_available !== undefined) {
      metadata.lineage_available = table.lineage_available;
    }
    if (table.table_type === "view") {
      metadata.view_lineage_count = table.view_lineage.length;
    }

    const primaryKeyColumns = new Set(
      (table.primary_key?.columns ?? []).map((name) => name.toLowerCase())
    );
    return {
      physical_schema: table.schema,
      physical_name: table.name,
      metadata,
      columns: table.columns.map((column) =>
        toSemanticColumnProjection({ column, primaryKeyColumns })
      )
    };
  });
}

function buildRelationshipProjection(
  schema: SchemaIntrospectionResponse
): SemanticRelationshipProjection[] {
  return schema.foreign_keys.map((relationship) => ({
    from_schema: relationship.from_schema,
    from_table: relationship.from_table,
    from_columns: relationship.from_columns,
    to_schema: relationship.to_schema,
    to_table: relationship.to_table,
    to_columns: relationship.to_columns,
    cardinality: isUniqueSourceColumns(schema, relationship)
      ? "one_to_one"
      : "many_to_one",
    constraint_name: relationship.name,
    update_rule: relationship.on_update,
    delete_rule: relationship.on_delete,
    is_disabled: relationship.is_disabled,
    is_not_trusted: relationship.is_not_trusted,
    verified_by_db: relationship.verified_by_db
  }));
}

function isUniqueSourceColumns(
  schema: SchemaIntrospectionResponse,
  relationship: SchemaIntrospectionResponse["foreign_keys"][number]
) {
  const expected = normalizedColumnSet(relationship.from_columns);
  const uniqueConstraintMatch = schema.unique_constraints.some(
    (constraint) =>
      physicalTableKey(constraint.schema_name, constraint.table_name) ===
        physicalTableKey(relationship.from_schema, relationship.from_table) &&
      normalizedColumnSet(constraint.columns) === expected
  );
  if (uniqueConstraintMatch) {
    return true;
  }

  return schema.indexes.some(
    (index) =>
      index.is_unique &&
      physicalTableKey(index.schema_name, index.table_name) ===
        physicalTableKey(relationship.from_schema, relationship.from_table) &&
      normalizedColumnSet(index.key_columns.map((column) => column.name)) ===
        expected
  );
}

function normalizedColumnSet(columns: string[]) {
  return columns.map((column) => column.toLowerCase()).sort().join("\u0000");
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
): SemanticColumnProjection["role"] {
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
