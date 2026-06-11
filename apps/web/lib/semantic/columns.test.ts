import { describe, expect, it } from "vitest";

import {
  isSemanticColumnQueryable,
  semanticColumnAtlanteFlags,
  semanticColumnDatabaseFlags,
  semanticColumnTypeLabel,
  splitSemanticColumns,
  type SemanticColumnDisplay
} from "./columns";

const baseColumn: SemanticColumnDisplay = {
  data_type: "nvarchar",
  id: "column-id",
  metadata: {
    is_nullable: false,
    is_primary_key: false,
    declared_type_available: true,
    is_sensitive: false,
    queryable: true,
    technical_role: "text"
  },
  physical_name: "Name",
  pii: false,
  role: "dimension",
  semantic_table_id: "table-id"
};

describe("semantic column display helpers", () => {
  it("excludes non-queryable sensitive columns from the queryable list", () => {
    const passwordHash: SemanticColumnDisplay = {
      ...baseColumn,
      metadata: {
        ...baseColumn.metadata,
        is_sensitive: true,
        queryable: false,
        sensitive_reason: "credential_name"
      },
      physical_name: "PasswordHash",
      pii: false,
      role: "unknown"
    };

    expect(isSemanticColumnQueryable(passwordHash)).toBe(false);
    expect(splitSemanticColumns([baseColumn, passwordHash])).toEqual({
      excludedColumns: [passwordHash],
      queryableColumns: [baseColumn]
    });
  });

  it("keeps PII business columns visible while flagging them", () => {
    const emailAddress: SemanticColumnDisplay = {
      ...baseColumn,
      metadata: {
        ...baseColumn.metadata,
        is_nullable: true,
        pii_reason: "contact_identifier"
      },
      physical_name: "EmailAddress",
      pii: true
    };

    expect(isSemanticColumnQueryable(emailAddress)).toBe(true);
    expect(semanticColumnDatabaseFlags(emailAddress)).toEqual(["nullable"]);
    expect(semanticColumnAtlanteFlags(emailAddress)).toEqual([
      "queryable",
      "PII"
    ]);
  });

  it("does not derive queryability from the semantic role", () => {
    const technicalImport: SemanticColumnDisplay = {
      ...baseColumn,
      role: "unknown"
    };
    const missingExplicitQueryability: SemanticColumnDisplay = {
      ...baseColumn,
      metadata: {
        ...baseColumn.metadata,
        is_nullable: false,
        queryable: undefined as never
      }
    };

    expect(isSemanticColumnQueryable(technicalImport)).toBe(true);
    expect(isSemanticColumnQueryable(missingExplicitQueryability)).toBe(false);
  });

  it("shows declared SQL Server alias types without replacing base type", () => {
    const phone: SemanticColumnDisplay = {
      ...baseColumn,
      data_type: "nvarchar",
      metadata: {
        ...baseColumn.metadata,
        declared_type: "Phone",
        declared_type_name: "Phone",
        declared_type_schema: "SalesLT",
        is_nullable: true
      },
      physical_name: "Phone"
    };

    expect(semanticColumnTypeLabel(phone)).toBe("nvarchar (SalesLT.Phone)");
    expect(semanticColumnTypeLabel(baseColumn)).toBe("nvarchar");
  });
});
