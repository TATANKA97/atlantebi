/* global console, fetch, process */

const REQUIRED_CONFIRMATION = "AdventureWorksLT";

function readArguments(argv) {
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(
        "Usage: --tenant-id <uuid> --connection-id <uuid> --confirm AdventureWorksLT"
      );
    }
    values.set(key.slice(2), value);
  }
  return values;
}

function requiredArgument(argumentsMap, name) {
  const value = argumentsMap.get(name);
  if (!value) {
    throw new Error(`Missing required argument --${name}.`);
  }
  return value;
}

function requiredEnvironment(name, fallbackName) {
  const value = process.env[name] ?? process.env[fallbackName];
  if (!value) {
    throw new Error(
      `Missing ${name}${fallbackName ? ` or ${fallbackName}` : ""}.`
    );
  }
  return value;
}

function isDemoOrTestTenant(tenant) {
  const environment = tenant.settings?.environment?.toLowerCase();
  const marker = /(^|[-_\s])(demo|test)([-_\s]|$)/i;
  return (
    environment === "demo" ||
    environment === "test" ||
    marker.test(tenant.slug) ||
    marker.test(tenant.name)
  );
}

function encodeFilterValue(value) {
  return encodeURIComponent(`eq.${value}`);
}

function tablePath(table, filters) {
  return `${table}?${filters.join("&")}`;
}

async function main() {
  const argumentsMap = readArguments(process.argv.slice(2));
  const tenantId = requiredArgument(argumentsMap, "tenant-id");
  const connectionId = requiredArgument(argumentsMap, "connection-id");
  const confirmation = requiredArgument(argumentsMap, "confirm");
  const uuidPattern =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

  if (confirmation !== REQUIRED_CONFIRMATION) {
    throw new Error(
      `--confirm must be exactly ${REQUIRED_CONFIRMATION}.`
    );
  }
  if (!uuidPattern.test(tenantId) || !uuidPattern.test(connectionId)) {
    throw new Error("--tenant-id and --connection-id must be UUIDs.");
  }

  const supabaseUrl = requiredEnvironment(
    "SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_URL"
  ).replace(/\/+$/, "");
  const serviceRoleKey = requiredEnvironment(
    "SUPABASE_SECRET_KEY",
    "SUPABASE_SERVICE_ROLE_KEY"
  );
  const headers = {
    apikey: serviceRoleKey,
    "content-type": "application/json"
  };
  if (serviceRoleKey.split(".").length === 3) {
    headers.authorization = `Bearer ${serviceRoleKey}`;
  }

  async function request(path, options = {}) {
    const { allowMissingRelation = false, ...fetchOptions } = options;
    const response = await fetch(`${supabaseUrl}/rest/v1/${path}`, {
      ...fetchOptions,
      headers: {
        ...headers,
        ...fetchOptions.headers
      }
    });
    const body = await response.text();
    if (!response.ok && allowMissingRelation && response.status === 404) {
      return [];
    }
    if (!response.ok) {
      throw new Error(
        `Supabase request failed (${response.status}): ${body || path}`
      );
    }
    return body ? JSON.parse(body) : null;
  }

  const tenants = await request(
    `tenants?select=id,slug,name,settings&id=${encodeFilterValue(tenantId)}`
  );
  const tenant = tenants[0];
  if (!tenant || !isDemoOrTestTenant(tenant)) {
    throw new Error(
      "Purge is restricted to a tenant explicitly marked demo/test."
    );
  }

  const connections = await request(
    [
      "db_connections?select=id,tenant_id,database_name",
      `id=${encodeFilterValue(connectionId)}`,
      `tenant_id=${encodeFilterValue(tenantId)}`
    ].join("&")
  );
  const connection = connections[0];
  if (!connection) {
    throw new Error("Tenant-scoped connection not found.");
  }
  if (connection.database_name !== REQUIRED_CONFIRMATION) {
    throw new Error(
      "Connection database_name does not match AdventureWorksLT."
    );
  }

  const widgets = await request(
    [
      "widgets?select=id",
      `tenant_id=${encodeFilterValue(tenantId)}`,
      `connection_id=${encodeFilterValue(connectionId)}`
    ].join("&")
  );

  for (let offset = 0; offset < widgets.length; offset += 100) {
    const widgetIds = widgets
      .slice(offset, offset + 100)
      .map(({ id }) => `"${id}"`)
      .join(",");
    await request(
      tablePath("dashboard_widgets", [
        `tenant_id=${encodeFilterValue(tenantId)}`,
        `widget_id=${encodeURIComponent(`in.(${widgetIds})`)}`
      ]),
      { method: "DELETE" }
    );
  }

  const scopedDelete = async (table) =>
    request(
      tablePath(table, [
        `tenant_id=${encodeFilterValue(tenantId)}`,
        `connection_id=${encodeFilterValue(connectionId)}`
      ]),
      { method: "DELETE" }
    );

  await scopedDelete("widgets");
  await scopedDelete("query_history");
  await scopedDelete("semantic_layer_versions");
  await scopedDelete("schema_snapshots");
  await request(
    tablePath("audit_logs", [
      `tenant_id=${encodeFilterValue(tenantId)}`,
      `subject_type=${encodeFilterValue("db_connection")}`,
      `subject_id=${encodeFilterValue(connectionId)}`
    ]),
    { method: "DELETE" }
  );

  for (const table of [
    "widgets",
    "query_history",
    "semantic_layer_versions",
    "queryability_graph_versions",
    "schema_snapshots"
  ]) {
    const remaining = await request(
      [
        `${table}?select=id`,
        `tenant_id=${encodeFilterValue(tenantId)}`,
        `connection_id=${encodeFilterValue(connectionId)}`,
        "limit=1"
      ].join("&"),
      table === "queryability_graph_versions"
        ? { allowMissingRelation: true }
        : {}
    );
    if (remaining.length > 0) {
      throw new Error(`Purge verification failed for ${table}.`);
    }
  }

  console.log(
    `Purged AdventureWorksLT plan for tenant ${tenantId}, connection ${connectionId}.`
  );
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
