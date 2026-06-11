import { describe, expect, it, vi } from "vitest";
import type { SchemaIntrospectionResponse } from "@atlantebi/contracts";

vi.mock("server-only", () => ({}));

const service = await import("./service");

describe("semantic column sensitivity classification", () => {
  it("marks credential material as non-queryable sensitive metadata", () => {
    expect(service.classifyColumnSensitivity("PasswordHash")).toEqual({
      kind: "credential",
      reason: "credential_name"
    });
    expect(service.classifyColumnSensitivity("PasswordSalt")).toEqual({
      kind: "credential",
      reason: "credential_name"
    });
    expect(service.classifyColumnSensitivity("ApiKey")).toEqual({
      kind: "credential",
      reason: "secret_key_name"
    });
  });

  it("restricts payment authorization codes without classifying them as PII", () => {
    expect(service.classifyColumnSensitivity("CreditCardApprovalCode")).toEqual({
      kind: "sensitive",
      reason: "payment_authorization_code"
    });
    expect(service.classifyColumnSensitivity("AccountNumber")).toEqual({
      kind: "none"
    });
  });

  it("marks direct contact fields as PII", () => {
    expect(service.classifyColumnSensitivity("EmailAddress")).toEqual({
      kind: "pii",
      reason: "contact_identifier"
    });
    expect(service.classifyColumnSensitivity("Phone")).toEqual({
      kind: "pii",
      reason: "contact_identifier"
    });
    expect(service.classifyColumnSensitivity("FirstName")).toEqual({
      kind: "pii",
      reason: "direct_person_identifier"
    });
    expect(service.classifyColumnSensitivity("AddressLine1")).toEqual({
      kind: "pii",
      reason: "direct_person_identifier"
    });
  });

  it("does not classify ordinary BI identifiers as secrets", () => {
    expect(service.classifyColumnSensitivity("ProductCategoryID")).toEqual({
      kind: "none"
    });
    expect(service.classifyColumnSensitivity("CustomerID")).toEqual({
      kind: "none"
    });
  });
});

describe("technical schema projection", () => {
  const schema: SchemaIntrospectionResponse = {
    status: "ok",
    message: "Schema introspection completed.",
    introspected_at: "2026-06-11T12:00:00.000Z",
    duration_ms: 1200,
    engine: "sqlserver",
    database_name: "AdventureWorksLT",
    engine_version: "12.0.2000.8",
    schema_hash: "b".repeat(64),
    coverage_status: "partial",
    tables: [
      {
        schema: "SalesLT",
        name: "SalesOrderDetail",
        table_type: "base_table",
        columns: [
          {
            name: "OrderQty",
            data_type: "smallint",
            declared_type_available: true,
            technical_role: "quantity_candidate",
            ordinal_position: 1,
            is_nullable: false,
            is_identity: false,
            is_computed: false,
            is_primary_key: false,
            is_foreign_key: false,
            is_unique_member: false
          },
          {
            name: "EmailAddress",
            data_type: "nvarchar",
            declared_type_available: true,
            technical_role: "text",
            ordinal_position: 2,
            is_nullable: true,
            is_identity: false,
            is_computed: false,
            is_primary_key: false,
            is_foreign_key: false,
            is_unique_member: false
          },
          {
            name: "PasswordHash",
            data_type: "varchar",
            declared_type_available: true,
            technical_role: "binary",
            ordinal_position: 3,
            is_nullable: false,
            is_identity: false,
            is_computed: false,
            is_primary_key: false,
            is_foreign_key: false,
            is_unique_member: false
          },
          {
            name: "CatalogDescription",
            data_type: "xml",
            declared_type_available: true,
            technical_role: "xml",
            ordinal_position: 4,
            is_nullable: true,
            is_identity: false,
            is_computed: false,
            is_primary_key: false,
            is_foreign_key: false,
            is_unique_member: false
          },
          {
            name: "CreditCardApprovalCode",
            data_type: "varchar",
            declared_type_available: true,
            technical_role: "text",
            ordinal_position: 5,
            is_nullable: true,
            is_identity: false,
            is_computed: false,
            is_primary_key: false,
            is_foreign_key: false,
            is_unique_member: false
          }
        ],
        is_system_object: false,
        view_lineage: []
      },
      {
        schema: "SalesLT",
        name: "SalesSummary",
        table_type: "view",
        columns: [],
        is_system_object: false,
        view_definition_available: true,
        lineage_available: true,
        view_lineage: []
      }
    ],
    foreign_keys: [],
    unique_constraints: [],
    check_constraints: [],
    default_constraints: [],
    indexes: [
      {
        name: "IX_OrderQty",
        schema_name: "SalesLT",
        table_name: "SalesOrderDetail",
        object_type: "table",
        is_unique: false,
        is_primary_key: false,
        index_type: "NONCLUSTERED",
        key_columns: [],
        included_columns: [],
        is_disabled: false
      },
      {
        name: "IX_SalesSummary",
        schema_name: "SalesLT",
        table_name: "SalesSummary",
        object_type: "view",
        is_unique: true,
        is_primary_key: false,
        index_type: "CLUSTERED",
        key_columns: [],
        included_columns: [],
        is_disabled: false
      }
    ],
    coverage_warnings: [
      {
        code: "VIEW_LINEAGE_PARTIAL",
        severity: "warning",
        message: "Lineage incomplete.",
        object_schema: "SalesLT",
        object_name: "SalesSummary"
      }
    ]
  };

  it("preserves conservative technical roles and leaves semantic roles unknown", () => {
    const projection = service.buildSemanticTableProjection(schema);
    const projectedTable = projection[0];
    expect(projectedTable).toBeDefined();
    if (!projectedTable) {
      throw new Error("Expected a projected table.");
    }
    const [
      orderQty,
      emailAddress,
      passwordHash,
      catalogDescription,
      creditCardApprovalCode
    ] =
      projectedTable.columns;

    expect(orderQty).toMatchObject({
      role: "unknown",
      pii: false,
      metadata: {
        technical_role: "quantity_candidate",
        queryable: true,
        is_sensitive: false
      }
    });
    expect(emailAddress).toMatchObject({
      role: "unknown",
      pii: true,
      metadata: { queryable: true, is_sensitive: false }
    });
    expect(passwordHash).toMatchObject({
      role: "unknown",
      pii: false,
      metadata: {
        queryable: false,
        is_sensitive: true,
        exclusion_reason: "unsupported_binary_type"
      }
    });
    expect(catalogDescription).toMatchObject({
      role: "unknown",
      pii: false,
      metadata: {
        queryable: false,
        is_sensitive: false,
        exclusion_reason: "unsupported_complex_type"
      }
    });
    expect(creditCardApprovalCode).toMatchObject({
      role: "unknown",
      pii: false,
      metadata: {
        technical_role: "text",
        queryable: false,
        is_sensitive: true,
        sensitive_reason: "payment_authorization_code"
      }
    });
  });

  it("builds the complete persisted summary from explicit projection fields", () => {
    expect(service.buildSchemaImportSummary(schema)).toMatchObject({
      coverage_status: "partial",
      total_objects: 2,
      total_tables: 1,
      total_views: 1,
      total_columns: 5,
      queryable_objects: 1,
      non_queryable_objects: 1,
      queryable_columns: 2,
      non_queryable_columns: 3,
      indexes_total_count: 2,
      table_indexes_count: 1,
      view_indexes_count: 1,
      views_total: 1,
      views_with_definition_count: 1,
      views_with_lineage_count: 1,
      views_with_partial_lineage_count: 1,
      pii_columns_count: 1,
      excluded_columns_count: 3,
      sensitive_columns_count: 2,
      coverage_warnings_count: 1,
      coverage_warnings_by_code: { VIEW_LINEAGE_PARTIAL: 1 }
    });
  });
});
