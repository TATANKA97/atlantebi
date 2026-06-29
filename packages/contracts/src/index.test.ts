import { describe, expect, it } from "vitest";
import connectionNullTls from "./fixtures/connection-null-tls.json";
import semanticLayerFixture from "./fixtures/semantic-layer-v1.json";
import {
  ChartSpecSchema,
  ConnectionMetadataSchema,
  ConnectionTestRequestSchema,
  ConnectionTestResponseSchema,
  DatabaseCredentialsSchema,
  EngineSchema,
  QueryIntentRequestSchema,
  QueryIntentResultSchema,
  QueryIntentTestSuiteReportSchema,
  QueryIntentTestSuiteRunRequestSchema,
  QueryResponseSchema,
  QueryRequestSchema,
  SemanticRelationshipSchema,
  SchemaImportSummarySchema,
  SchemaIntrospectionRequestSchema,
  SchemaIntrospectionResponseSchema,
  VerificationSummarySchema
} from "./index";

const tenantId = "11111111-1111-4111-8111-111111111111";
const connectionId = "33333333-3333-4333-8333-333333333333";
const userId = "44444444-4444-4444-8444-444444444444";

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

  it("accepts the shared nullable TLS fixture", () => {
    expect(ConnectionMetadataSchema.parse(connectionNullTls).tls_server_name).toBeNull();
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
      database_name: "AdventureWorksLT",
      engine_version: "12.0.2000.8",
      schema_hash: "a".repeat(64),
      coverage_status: "partial",
      tables: [
        {
          schema: "SalesLT",
          name: "Customer",
          table_type: "base_table",
          database_name: "AdventureWorksLT",
          object_id: 12345,
          is_system_object: false,
          row_count_estimate: 847,
          columns: [
            {
              name: "CustomerID",
              data_type: "int",
              native_type: "int",
              normalized_type: "int",
              declared_type_available: false,
              technical_role: "identifier",
              ordinal_position: 1,
              is_nullable: false,
              is_identity: true,
              is_computed: false,
              is_primary_key: true
            },
            {
              name: "FirstName",
              data_type: "nvarchar",
              declared_type: "Name",
              declared_type_schema: "SalesLT",
              declared_type_name: "Name",
              declared_type_is_user_defined: true,
              declared_type_is_assembly: false,
              declared_type_available: true,
              technical_role: "text",
              native_type: "nvarchar",
              normalized_type: "nvarchar",
              ordinal_position: 2,
              is_nullable: false,
              max_length: 50,
              is_identity: false,
              is_computed: false,
              collation: "SQL_Latin1_General_CP1_CI_AS"
            }
          ],
          primary_key: {
            name: "PK_Customer_CustomerID",
            columns: ["CustomerID"]
          }
        },
        {
          schema: "SalesLT",
          name: "vCustomer",
          table_type: "view",
          columns: [],
          lineage_available: true,
          view_lineage: [
            {
              source: "dm_sql_referenced_entities",
              referencing_column: "CustomerID",
              referenced_schema_name: "SalesLT",
              referenced_entity_name: "Customer",
              referenced_column_name: "CustomerID",
              referenced_class: "OBJECT_OR_COLUMN",
              is_selected: true,
              is_updated: false,
              is_select_all: false,
              is_all_columns_found: true,
              is_caller_dependent: false,
              is_ambiguous: false,
              is_incomplete: false
            }
          ]
        }
      ],
      foreign_keys: [
        {
          constraint_name: "FK_Order_Customer",
          from_schema: "SalesLT",
          from_table: "SalesOrderHeader",
          from_columns: ["CustomerID"],
          to_schema: "SalesLT",
          to_table: "Customer",
          to_columns: ["CustomerID"],
          delete_rule: "no_action",
          update_rule: "no_action",
          is_disabled: false,
          is_not_trusted: false,
          source: "db_fk",
          verified_by_db: true
        }
      ],
      unique_constraints: [],
      check_constraints: [
        {
          name: "CK_Demo",
          schema_name: "SalesLT",
          table_name: "Customer",
          definition: "([CustomerID]>(0))"
        }
      ],
      default_constraints: [
        {
          name: "DF_Demo",
          schema_name: "SalesLT",
          table_name: "Customer",
          column_name: "CustomerID",
          definition: "((0))"
        }
      ],
      indexes: [
        {
          name: "IX_Customer_Email",
          schema_name: "SalesLT",
          table_name: "Customer",
          object_type: "table",
          is_unique: true,
          is_primary_key: false,
          index_type: "nonclustered",
          key_columns: [
            {
              name: "EmailAddress",
              ordinal_position: 1,
              is_descending: false
            }
          ],
          included_columns: []
        }
      ],
      coverage_warnings: [
        {
          code: "VIEW_LINEAGE_PARTIAL",
          severity: "warning",
          message: "SQL Server returned partial view lineage metadata for this view."
        }
      ]
    });

    expect(response.tables[0]?.primary_key?.columns).toEqual(["CustomerID"]);
    expect(response.tables[0]?.columns[1]?.declared_type).toBe("Name");
    expect(response.tables[0]?.columns[1]?.declared_type_schema).toBe("SalesLT");
    expect(response.tables[1]?.view_lineage[0]?.referenced_entity_name).toBe(
      "Customer"
    );
    expect(response.foreign_keys[0]?.source).toBe("db_fk");
    expect(response.foreign_keys[0]?.constraint_name).toBe(
      "FK_Order_Customer"
    );
    expect(() =>
      SchemaIntrospectionResponseSchema.parse({
        ...response,
        foreign_keys: [
          {
            ...response.foreign_keys[0],
            constraint_name: undefined,
            name: "FK_Order_Customer"
          }
        ]
      })
    ).toThrow();
    expect(response.indexes[0]?.is_unique).toBe(true);
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

  it("validates the persisted import summary without legacy coverage fields", () => {
    const summary = SchemaImportSummarySchema.parse({
      database_name: "AdventureWorksLT",
      engine: "sqlserver",
      engine_version: "12.0.2000.8",
      schema_hash: "b".repeat(64),
      coverage_status: "partial",
      captured_at: "2026-06-11T12:00:00.000Z",
      duration_ms: 1200,
      total_objects: 13,
      total_tables: 10,
      total_views: 3,
      total_columns: 129,
      queryable_objects: 13,
      non_queryable_objects: 0,
      queryable_columns: 125,
      non_queryable_columns: 4,
      primary_keys_count: 10,
      foreign_keys_count: 12,
      unique_constraints_count: 3,
      check_constraints_count: 2,
      default_constraints_count: 8,
      indexes_total_count: 31,
      table_indexes_count: 30,
      view_indexes_count: 1,
      unique_indexes_count: 12,
      filtered_indexes_count: 0,
      included_columns_indexes_count: 1,
      views_total: 3,
      views_with_definition_count: 3,
      views_without_definition_count: 0,
      views_with_lineage_count: 3,
      views_with_partial_lineage_count: 1,
      views_without_lineage_count: 0,
      view_lineage_dependencies_count: 25,
      columns_with_declared_type_count: 110,
      columns_without_declared_type_count: 19,
      columns_with_default_count: 8,
      computed_columns_count: 4,
      identity_columns_count: 5,
      pii_columns_count: 8,
      excluded_columns_count: 4,
      sensitive_columns_count: 2,
      coverage_warnings_count: 3,
      coverage_warnings_by_code: {
        ROW_COUNT_ESTIMATE_UNAVAILABLE: 1,
        COLUMN_DECLARED_TYPE_UNAVAILABLE: 19,
        VIEW_LINEAGE_PARTIAL: 1
      }
    });

    expect(summary.indexes_total_count).toBe(31);
    expect(() =>
      SchemaImportSummarySchema.parse({
        ...summary,
        coverage_state: "partial"
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

  it("requires semantic relationships to reference graph stable keys", () => {
    const parsed = SemanticRelationshipSchema.parse({
      edge_key: "a".repeat(64),
      from_node_key: "b".repeat(64),
      to_node_key: "c".repeat(64),
      status: "system_seeded",
      enabled: true,
      relationship_shape: "many_to_one",
      child_to_parent: "exactly_one",
      parent_to_child: "zero_or_many",
      nullable_fk: false,
      self_reference: false
    });

    expect(parsed.status).toBe("system_seeded");
    expect(() =>
      SemanticRelationshipSchema.parse({
        ...parsed,
        edge_key: "FK_SalesOrder_Customer"
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
      tenant_id: semanticLayerFixture.tenant_id,
      connection_id: semanticLayerFixture.connection_id,
      user_id: userId,
      question: "Fatturato 2025 per mese",
      semantic_layer: semanticLayerFixture,
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

    expect(parsed.semantic_layer.columns).toHaveLength(5);
  });

  it("rejects query requests with mismatched or unusable semantic layers", () => {
    const baseRequest = {
      tenant_id: semanticLayerFixture.tenant_id,
      connection_id: semanticLayerFixture.connection_id,
      user_id: userId,
      question: "Fatturato 2025 per mese",
      semantic_layer: semanticLayerFixture,
      permissions: {
        can_view_sql: false,
        can_save_widget: true
      },
      execution: {
        mode: "plan_only" as const,
        row_limit: 500,
        timeout_ms: 30000
      }
    };

    expect(() =>
      QueryRequestSchema.parse({
        ...baseRequest,
        connection_id: connectionId
      })
    ).toThrow();
    expect(() =>
      QueryRequestSchema.parse({
        ...baseRequest,
        semantic_layer: {
          ...semanticLayerFixture,
          status: "draft"
        }
      })
    ).toThrow();
    expect(() =>
      QueryRequestSchema.parse({
        ...baseRequest,
        semantic_layer: {
          ...semanticLayerFixture,
          freshness: "stale"
        }
      })
    ).toThrow();
    expect(() =>
      QueryRequestSchema.parse({
        ...baseRequest,
        semantic_layer: {
          ...semanticLayerFixture,
          revision: semanticLayerFixture.revision + 1
        }
      })
    ).toThrow();
  });

  const queryabilityGraphFixture = {
    contract_version: "queryability_graph.v1",
    tenant_id: semanticLayerFixture.tenant_id,
    connection_id: semanticLayerFixture.connection_id,
    schema_snapshot_id: "33333333-3333-4333-8333-333333333333",
    engine: "sqlserver",
    schema_hash: "a".repeat(64),
    snapshot_hash: "b".repeat(64),
    graph_input_hash: "c".repeat(64),
    derivation_key: "d".repeat(64),
    graph_hash: semanticLayerFixture.base_graph_hash,
    builder_version: "1.0.0",
    policy_version: "1.0.0",
    status: "complete",
    status_reasons: [],
    semantic_status: "not_initialized",
    nodes: semanticLayerFixture.tables.map((table) => ({
      node_key: table.node_key,
      database_name: "AdventureWorksLT",
      schema_name: table.schema_name,
      object_name: table.object_name,
      object_type: table.object_type,
      queryability_status: table.queryability_status,
      reason_codes: [],
      bridge_candidate: false,
      candidate_keys: [],
      columns: semanticLayerFixture.columns
        .filter((column) => column.node_key === table.node_key)
        .map((column, index) => ({
          column_key: column.column_key,
          name: column.physical_name,
          ordinal_position: index + 1,
          native_type: column.native_type,
          normalized_type: column.normalized_type,
          technical_role: column.technical_role,
          nullable: column.nullable,
          queryability_status: column.queryability_status,
          sensitivity: column.sensitivity,
          reason_codes: []
        }))
    })),
    edges: []
  };

  it("validates query intent requests with semantic layer and graph context", () => {
    const parsed = QueryIntentRequestSchema.parse({
      tenant_id: semanticLayerFixture.tenant_id,
      connection_id: semanticLayerFixture.connection_id,
      user_id: userId,
      question: "fatturato 2008",
      semantic_layer: semanticLayerFixture,
      graph: queryabilityGraphFixture,
      ai_enabled: false
    });

    expect(parsed.policy.order_status_scope).toBe("all_statuses_with_disclosure");
  });

  it("keeps query intent plans strict and SQL-free", () => {
    const metric = semanticLayerFixture.metrics[0];
    if (!metric) {
      throw new Error("semantic fixture must include at least one metric");
    }
    const parsed = QueryIntentResultSchema.parse({
      status: "ready",
      plan: {
        primary_metric_key: metric.metric_key,
        requested_concept_ref: "records",
        selected_variant: metric.metric_variant,
        time_range: {
          kind: "year",
          start_date: "2008-01-01",
          end_date: "2008-12-31",
          label: "2008"
        },
        group_by_dimensions: [],
        required_edge_path_keys: [],
        grain_safety_decision: "safe",
        filters: [],
        rejected_alternatives: [],
        disclosures: ["Order status scope defaults to all statuses in V1."],
        audit_trail: []
      },
      audit_trail: [],
      message: "Query intent resolved without SQL generation."
    });

    expect(parsed.plan?.selected_variant).toBe(metric.metric_variant);
    expect(() =>
      QueryIntentResultSchema.parse({
        ...parsed,
        sql: "select 1"
      })
    ).toThrow();
  });

  it("requires structured unsupported reasons for blocked query intents", () => {
    expect(
      QueryIntentResultSchema.parse({
        status: "blocked",
        unsupported_reason: "destructive_request_not_allowed",
        audit_trail: [],
        message: "Destructive operations are outside Query Intent Resolver V1."
      }).unsupported_reason
    ).toBe("destructive_request_not_allowed");

    expect(() =>
      QueryIntentResultSchema.parse({
        status: "blocked",
        audit_trail: [],
        message: "Missing reason."
      })
    ).toThrow();
  });

  it("validates query intent bulk test suite reports", () => {
    const parsedRequest = QueryIntentTestSuiteRunRequestSchema.parse({
      tenant_id: semanticLayerFixture.tenant_id,
      connection_id: semanticLayerFixture.connection_id,
      user_id: userId,
      connection_name: "TEST - AdventureWorksLT",
      environment: "test",
      suite_id: "adventureworks_v1",
      ai_mode: "disabled",
      semantic_layer: semanticLayerFixture,
      graph: queryabilityGraphFixture
    });

    expect(parsedRequest.ai_mode).toBe("disabled");

    const parsedReport = QueryIntentTestSuiteReportSchema.parse({
      run_id: "99999999-9999-4999-8999-999999999999",
      created_at: "2026-06-29T10:00:00.000Z",
      environment: "test",
      suite_id: "adventureworks_v1",
      ai_mode: "disabled",
      connection: {
        id: semanticLayerFixture.connection_id,
        name: "TEST - AdventureWorksLT"
      },
      semantic_layer: {
        version: `v${semanticLayerFixture.version}`,
        status: semanticLayerFixture.status,
        freshness: semanticLayerFixture.freshness,
        semantic_hash: semanticLayerFixture.semantic_hash,
        base_graph_hash: semanticLayerFixture.base_graph_hash,
        base_policy_hash: semanticLayerFixture.base_policy_hash
      },
      summary: {
        total: 1,
        passed: 1,
        failed: 0,
        skipped: 0
      },
      results: [
        {
          id: "core_fatturato_2008",
          question: "fatturato 2008",
          passed: true,
          expected: {
            description: {
              result_status_equals: "ready"
            }
          },
          actual: {
            status: "ready"
          },
          diffs: [],
          duration_ms: 1
        }
      ]
    });

    expect(parsedReport.results[0]?.passed).toBe(true);
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

  it("rejects schema responses above the V1 object cardinality limit", () => {
    expect(() =>
      SchemaIntrospectionResponseSchema.parse({
        status: "ok",
        message: "Schema introspection completed.",
        introspected_at: "2026-06-06T12:00:00.000Z",
        duration_ms: 10,
        engine: "sqlserver",
        coverage_status: "ok",
        tables: Array.from({ length: 5_001 }, (_, index) => ({
          schema: "dbo",
          name: `Table${index}`,
          table_type: "base_table",
          columns: []
        }))
      })
    ).toThrow();
  });
});
