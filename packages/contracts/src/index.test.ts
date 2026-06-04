import { describe, expect, it } from "vitest";
import {
  ChartSpecSchema,
  ConnectionMetadataSchema,
  ConnectionTestRequestSchema,
  ConnectionTestResponseSchema,
  DatabaseCredentialsSchema,
  EngineSchema,
  QueryResponseSchema,
  QueryRequestSchema,
  RelationshipSchema,
  SchemaIntrospectionRequestSchema,
  SchemaIntrospectionResponseSchema,
  VerificationSummarySchema
} from "./index";

const tenantId = "11111111-1111-4111-8111-111111111111";
const versionId = "22222222-2222-4222-8222-222222222222";
const connectionId = "33333333-3333-4333-8333-333333333333";
const userId = "44444444-4444-4444-8444-444444444444";
const relationshipId = "55555555-5555-4555-8555-555555555555";
const metricId = "66666666-6666-4666-8666-666666666666";
const anchorId = "77777777-7777-4777-8777-777777777777";

describe("contracts", () => {
  it("accepts only V1 database engines", () => {
    expect(EngineSchema.parse("sqlserver")).toBe("sqlserver");
    expect(EngineSchema.parse("mysql")).toBe("mysql");
    expect(() => EngineSchema.parse("postgres")).toThrow();
  });

  it("validates connection metadata without storing database passwords", () => {
    const metadata = ConnectionMetadataSchema.parse({
      tenant_id: tenantId,
      connection_id: connectionId,
      name: "Azure SQL demo",
      engine: "sqlserver",
      network_mode: "public_allowlist",
      host: "demo.database.windows.net",
      port: 1433,
      database_name: "SalesLT",
      username: "readonly_user",
      tls_required: true,
      trust_server_certificate: false,
      secret_ref: "gcp-secret-manager://projects/atlantebi/secrets/demo-sql-password",
      status: "draft"
    });

    expect(metadata.username).toBe("readonly_user");
    expect(() =>
      ConnectionMetadataSchema.parse({
        ...metadata,
        password: "must-not-be-here"
      })
    ).toThrow();
  });

  it("keeps database secret payload minimal and strict", () => {
    expect(DatabaseCredentialsSchema.parse({ password: "secret" }).password).toBe("secret");
    expect(() => DatabaseCredentialsSchema.parse({ username: "u", password: "p" })).toThrow();
  });

  it("validates connection test request and response contracts", () => {
    const request = ConnectionTestRequestSchema.parse({
      connection: {
        tenant_id: tenantId,
        connection_id: connectionId,
        name: "MySQL demo",
        engine: "mysql",
        network_mode: "public_allowlist",
        host: "mysql.example.com",
        port: 3306,
        database_name: "demo",
        username: "readonly_user",
        tls_required: true,
        secret_ref: "gcp-secret-manager://projects/atlantebi/secrets/demo-mysql-password",
        status: "draft"
      },
      timeout_ms: 30000
    });

    expect(request.connection.trust_server_certificate).toBe(false);

    const response = ConnectionTestResponseSchema.parse({
      status: "failed",
      message: "MySQL connection failed.",
      checked_at: "2026-06-03T12:00:00.000Z",
      duration_ms: 42,
      sanitized_error: "MySQL connection failed."
    });

    expect(response.status).toBe("failed");
  });

  it("validates strict schema introspection metadata without raw data", () => {
    const request = SchemaIntrospectionRequestSchema.parse({
      connection: {
        tenant_id: tenantId,
        connection_id: connectionId,
        name: "Azure SQL demo",
        engine: "sqlserver",
        network_mode: "public_allowlist",
        host: "136.111.143.3",
        port: 10002,
        database_name: "AdventureWorksLT",
        username: "readonly_user",
        tls_required: true,
        tls_server_name: "atlanteadmin.database.windows.net",
        secret_ref: "gcp-secret-manager://projects/atlantebi/secrets/demo-sql-password",
        status: "ready"
      },
      timeout_ms: 120000
    });
    expect(request.timeout_ms).toBe(120000);

    const response = SchemaIntrospectionResponseSchema.parse({
      status: "ok",
      message: "Schema introspection completed.",
      introspected_at: "2026-06-03T12:00:00.000Z",
      duration_ms: 1000,
      engine: "sqlserver",
      tables: [
        {
          schema: "SalesLT",
          name: "Customer",
          table_type: "base_table",
          columns: [
            {
              name: "CustomerID",
              data_type: "int",
              ordinal_position: 1,
              is_nullable: false,
              is_identity: true,
              is_computed: false
            },
            {
              name: "FirstName",
              data_type: "nvarchar",
              declared_type: "Name",
              ordinal_position: 2,
              is_nullable: false,
              max_length: 50,
              is_identity: false,
              is_computed: false
            }
          ],
          primary_key: {
            name: "PK_Customer_CustomerID",
            columns: ["CustomerID"]
          }
        }
      ],
      foreign_keys: []
    });

    expect(response.tables[0]?.primary_key?.columns).toEqual(["CustomerID"]);
    expect(response.tables[0]?.columns[1]?.declared_type).toBe("Name");
    expect(() =>
      SchemaIntrospectionResponseSchema.parse({
        ...response,
        sample_rows: [{ CustomerID: 1 }]
      })
    ).toThrow();
    expect(() =>
      SchemaIntrospectionResponseSchema.parse({
        ...response,
        duration_ms: "1000"
      })
    ).toThrow();
  });

  it("keeps chart specs deterministic and strict", () => {
    const parsed = ChartSpecSchema.parse({
      type: "bar",
      title: "Fatturato per mese",
      x: "mese",
      y: ["fatturato"],
      formatting: {
        fatturato: { type: "currency", currency: "EUR", decimals: 2 }
      }
    });

    expect(parsed.display.limit).toBe(20);
    expect(() =>
      ChartSpecSchema.parse({
        type: "bar",
        title: "Fatturato",
        unexpected: true
      })
    ).toThrow();
  });

  it("uses non-numeric semantic relationship confidence", () => {
    const parsed = RelationshipSchema.parse({
      id: relationshipId,
      from_table: "SalesOrderHeader",
      from_columns: ["CustomerID"],
      to_table: "Customer",
      to_columns: ["CustomerID"],
      cardinality: "many_to_one",
      semantic_status: "confirmed",
      source: "database_fk"
    });

    expect(parsed.semantic_status).toBe("confirmed");
    expect(() =>
      RelationshipSchema.parse({
        ...parsed,
        semantic_status: 0.92
      })
    ).toThrow();
  });

  it("represents verification states without treating skipped checks as failure", () => {
    const parsed = VerificationSummarySchema.parse({
      status: "pass",
      confidence_label: "high",
      result_visible: true,
      checks: [
        {
          type: "historical_plausibility",
          status: "skip",
          message: "Baseline storica non disponibile",
          evidence: {}
        }
      ]
    });

    expect(parsed.result_visible).toBe(true);
  });

  it("validates a full query request with semantic layer context", () => {
    const parsed = QueryRequestSchema.parse({
      tenant_id: tenantId,
      connection_id: connectionId,
      user_id: userId,
      question: "Fatturato 2025 per mese",
      semantic_layer: {
        tenant_id: tenantId,
        version_id: versionId,
        version: 1,
        status: "active",
        engine: "sqlserver",
        tables: [
          {
            name: "SalesOrderHeader",
            schema: "SalesLT",
            business_name: "Ordini vendita",
            active: true,
            columns: [
              {
                name: "OrderDate",
                data_type: "datetime",
                role: "date",
                pii: false
              },
              {
                name: "SubTotal",
                data_type: "money",
                role: "measure",
                format: { type: "currency", currency: "EUR", decimals: 2 },
                pii: false
              }
            ]
          }
        ],
        relationships: [],
        metrics: [
          {
            id: metricId,
            name: "fatturato",
            expression: "sum(SalesOrderHeader.SubTotal)",
            grain: ["month"],
            format: { type: "currency", currency: "EUR", decimals: 2 }
          }
        ],
        business_anchors: [
          {
            id: anchorId,
            name: "Fatturato mensile atteso",
            metric_id: metricId,
            expected_range: { min: 0 },
            period: "monthly"
          }
        ]
      },
      permissions: {
        can_view_sql: false,
        can_save_widget: true
      },
      execution: {
        mode: "run",
        row_limit: 500,
        timeout_ms: 30000
      }
    });

    expect(parsed.semantic_layer.tables[0]?.columns).toHaveLength(2);
  });

  it("rejects null for optional query response fields", () => {
    expect(() =>
      QueryResponseSchema.parse({
        query_id: "88888888-8888-4888-8888-888888888888",
        status: "failed",
        sql: null,
        result_metadata: {
          columns: [],
          row_count: 0,
          truncated: false
        },
        chart: null,
        verification: {
          status: "engine_error",
          confidence_label: "blocked",
          result_visible: false,
          checks: [
            {
              type: "dry_run",
              status: "engine_error",
              message: "Query execution is not implemented.",
              evidence: {}
            }
          ]
        },
        sanitized_error: "Query execution is not implemented."
      })
    ).toThrow();
  });
});
