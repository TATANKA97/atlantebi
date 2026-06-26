/* global console, fetch, process */

const DATABASE_NAME = "AdventureWorksLT";

function argumentsMap(argv) {
  const result = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(
        "Usage: --tenant-id <uuid> --connection-id <uuid> --actor-user-id <uuid> --currency EUR --confirm AdventureWorksLT"
      );
    }
    result.set(key.slice(2), value);
  }
  return result;
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
  const values = argumentsMap(process.argv.slice(2));
  const tenantId = required(values, "tenant-id");
  const connectionId = required(values, "connection-id");
  const actorUserId = required(values, "actor-user-id");
  const currency = required(values, "currency").toUpperCase();
  if (required(values, "confirm") !== DATABASE_NAME) {
    throw new Error(`--confirm must be exactly ${DATABASE_NAME}.`);
  }
  if (!/^[A-Z]{3}$/.test(currency)) {
    throw new Error("--currency must be a three-letter ISO currency code.");
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
    throw new Error("Profile configuration is restricted to demo/test tenants.");
  }
  const [connection] = await request(
    `db_connections?select=id,database_name&id=${eq(connectionId)}&tenant_id=${eq(tenantId)}`
  );
  if (!connection || connection.database_name !== DATABASE_NAME) {
    throw new Error("Tenant-scoped AdventureWorksLT connection not found.");
  }
  const [derivation] = await request(
    `queryability_graph_derivations?select=graph_version_id&tenant_id=${eq(tenantId)}&connection_id=${eq(connectionId)}&order=created_at.desc&limit=1`
  );
  if (!derivation) throw new Error("Current Queryability Graph not found.");
  const [version] = await request(
    `queryability_graph_versions?select=graph&id=${eq(derivation.graph_version_id)}&tenant_id=${eq(tenantId)}&connection_id=${eq(connectionId)}`
  );
  if (!version?.graph) throw new Error("Queryability Graph artifact not found.");
  const graph = version.graph;
  const node = (name) => {
    const result = graph.nodes.find(
      (item) => item.schema_name === "SalesLT" && item.object_name === name
    );
    if (!result) throw new Error(`Graph node SalesLT.${name} not found.`);
    return result;
  };
  const column = (table, name) => {
    const result = node(table).columns.find((item) => item.name === name);
    if (!result) throw new Error(`Graph column SalesLT.${table}.${name} not found.`);
    return result.column_key;
  };

  const categoryDimension = {
    dimension_column_key: column("ProductCategory", "ProductCategoryID"),
    expected_safety: "safe"
  };
  const metricSpec = ({
    specKey,
    concept,
    variant,
    canonicalName,
    table,
    aggregation,
    measure,
    grain,
    date = null,
    valueType,
    defaultForConcept = false,
    requiredForActivation = false,
    dimensions = [],
    allowedEligibility = ["eligible", "eligible_with_disclosure"]
  }) => ({
    spec_key: specKey,
    intent_key: canonicalName,
    business_concept_ref: concept,
    expected_variant: variant,
    canonical_name: canonicalName,
    name: canonicalName.replaceAll("_", " "),
    description: null,
    source_table_key: node(table).node_key,
    aggregation,
    measure_column_key: column(table, measure),
    grain_column_keys: grain.map((name) => column(table, name)),
    default_date_column_key: date ? column(date[0], date[1]) : null,
    value_type: valueType,
    default_for_concept: defaultForConcept,
    required_for_activation: requiredForActivation,
    allowed_eligibility: allowedEligibility,
    dimension_expectations: dimensions,
    synonyms: []
  });
  const orderDate = ["SalesOrderHeader", "OrderDate"];
  const customerEligibility = [
    "eligible",
    "eligible_with_disclosure",
    "clarification_required"
  ];
  const policyConfig = {
    policy_version: "1.0.0",
    missing_currency_behavior: "clarification_required",
    activation_policy: "auto_validated",
    minimum_eligible_metrics: 4,
    required_concepts: [
      ["revenue", ["document_total", "line_detail", "net_header"], true],
      ["quantity_sold", ["line_quantity"], true],
      ["orders", ["header_count"], true],
      ["customers", ["customer_master", "order_customers"], false]
    ].map(([concept_ref, preferred_variants, required_for_activation]) => ({
      concept_ref,
      preferred_variants,
      required: true,
      required_for_activation
    })),
    required_metric_specs: [
      metricSpec({ specKey: "adventureworks.revenue.net_header", concept: "revenue", variant: "net_header", canonicalName: "fatturato_netto", table: "SalesOrderHeader", aggregation: "sum", measure: "SubTotal", grain: ["SalesOrderID"], date: orderDate, valueType: "currency", defaultForConcept: true, requiredForActivation: true, dimensions: [{ ...categoryDimension, expected_safety: "forbidden" }] }),
      metricSpec({ specKey: "adventureworks.revenue.document_total", concept: "revenue", variant: "document_total", canonicalName: "totale_documento", table: "SalesOrderHeader", aggregation: "sum", measure: "TotalDue", grain: ["SalesOrderID"], date: orderDate, valueType: "currency", requiredForActivation: true }),
      metricSpec({ specKey: "adventureworks.revenue.line_detail", concept: "revenue", variant: "line_detail", canonicalName: "fatturato_righe", table: "SalesOrderDetail", aggregation: "sum", measure: "LineTotal", grain: ["SalesOrderID", "SalesOrderDetailID"], date: orderDate, valueType: "currency", dimensions: [categoryDimension] }),
      metricSpec({ specKey: "adventureworks.quantity.line_quantity", concept: "quantity_sold", variant: "line_quantity", canonicalName: "quantita_venduta", table: "SalesOrderDetail", aggregation: "sum", measure: "OrderQty", grain: ["SalesOrderID", "SalesOrderDetailID"], date: orderDate, valueType: "number", requiredForActivation: true, dimensions: [categoryDimension] }),
      metricSpec({ specKey: "adventureworks.orders.header_count", concept: "orders", variant: "header_count", canonicalName: "ordini", table: "SalesOrderHeader", aggregation: "count", measure: "SalesOrderID", grain: ["SalesOrderID"], date: orderDate, valueType: "count", requiredForActivation: true }),
      metricSpec({ specKey: "adventureworks.customers.order_customers", concept: "customers", variant: "order_customers", canonicalName: "clienti_ordini", table: "SalesOrderHeader", aggregation: "count_distinct", measure: "CustomerID", grain: ["SalesOrderID"], date: orderDate, valueType: "count", allowedEligibility: customerEligibility }),
      metricSpec({ specKey: "adventureworks.customers.customer_master", concept: "customers", variant: "customer_master", canonicalName: "clienti_anagrafica", table: "Customer", aggregation: "count", measure: "CustomerID", grain: ["CustomerID"], valueType: "count", allowedEligibility: customerEligibility })
    ]
  };

  await request("rpc/update_semantic_policy_settings", {
    method: "POST",
    body: JSON.stringify({
      actor_user_id: actorUserId,
      target_tenant_id: tenantId,
      target_connection_id: connectionId,
      target_default_currency: currency,
      target_policy_config: policyConfig,
      update_policy_config: true
    })
  });
  console.log(`Configured AdventureWorks semantic profile for ${connectionId}.`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
