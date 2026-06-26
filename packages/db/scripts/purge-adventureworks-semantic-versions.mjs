/* global console, fetch, process */

const DATABASE_NAME = "AdventureWorksLT";
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function parseArguments(argv) {
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(
        "Usage: --tenant-id <uuid> --connection-id <uuid> --actor-user-id <uuid> --confirm AdventureWorksLT"
      );
    }
    values.set(key.slice(2), value);
  }
  return values;
}

function required(values, name) {
  const value = values.get(name);
  if (!value) throw new Error(`Missing required argument --${name}.`);
  return value;
}

function environment(name, fallback) {
  const value = process.env[name] ?? process.env[fallback];
  if (!value) throw new Error(`Missing ${name} or ${fallback}.`);
  return value;
}

function isDemoTenant(tenant) {
  const marker = /(^|[-_\s])(demo|test)([-_\s]|$)/i;
  return (
    ["demo", "test"].includes(tenant.settings?.environment?.toLowerCase()) ||
    marker.test(tenant.slug) ||
    marker.test(tenant.name)
  );
}

async function main() {
  const values = parseArguments(process.argv.slice(2));
  const tenantId = required(values, "tenant-id");
  const connectionId = required(values, "connection-id");
  const actorUserId = required(values, "actor-user-id");
  if (
    !UUID_PATTERN.test(tenantId) ||
    !UUID_PATTERN.test(connectionId) ||
    !UUID_PATTERN.test(actorUserId)
  ) {
    throw new Error("Tenant, connection, and actor IDs must be UUIDs.");
  }
  if (required(values, "confirm") !== DATABASE_NAME) {
    throw new Error(`--confirm must be exactly ${DATABASE_NAME}.`);
  }

  const baseUrl = environment("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL").replace(
    /\/+$/,
    ""
  );
  const serviceKey = environment(
    "SUPABASE_SECRET_KEY",
    "SUPABASE_SERVICE_ROLE_KEY"
  );
  const headers = {
    apikey: serviceKey,
    "content-type": "application/json"
  };
  if (serviceKey.split(".").length === 3) {
    headers.authorization = `Bearer ${serviceKey}`;
  }
  const request = async (path, options = {}) => {
    const response = await fetch(`${baseUrl}/rest/v1/${path}`, {
      ...options,
      headers: { ...headers, ...options.headers }
    });
    const body = await response.text();
    if (!response.ok) {
      throw new Error(`Supabase request failed (${response.status}): ${body}`);
    }
    return body ? JSON.parse(body) : null;
  };
  const eq = (value) => encodeURIComponent(`eq.${value}`);

  const [tenant] = await request(
    `tenants?select=id,slug,name,settings&id=${eq(tenantId)}`
  );
  if (!tenant || !isDemoTenant(tenant)) {
    throw new Error("Semantic purge is restricted to demo/test tenants.");
  }
  const [connection] = await request(
    `db_connections?select=id,database_name&id=${eq(connectionId)}&tenant_id=${eq(tenantId)}`
  );
  if (!connection || connection.database_name !== DATABASE_NAME) {
    throw new Error("Tenant-scoped AdventureWorksLT connection not found.");
  }

  await request("rpc/purge_demo_semantic_versions", {
    method: "POST",
    body: JSON.stringify({
      actor_user_id: actorUserId,
      confirmation: DATABASE_NAME,
      target_connection_id: connectionId,
      target_tenant_id: tenantId
    })
  });
  const remaining = await request(
    `semantic_layer_versions?select=id&tenant_id=${eq(tenantId)}&connection_id=${eq(connectionId)}&limit=1`
  );
  if (remaining.length > 0) {
    throw new Error("Semantic version purge verification failed.");
  }

  console.log(
    `Purged AdventureWorksLT semantic versions for connection ${connectionId}.`
  );
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
