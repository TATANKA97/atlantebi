import { describe, expect, it } from "vitest";

import {
  isSemanticColumnQueryable,
  semanticColumnFlags,
  semanticColumnTypeLabel,
  splitSemanticColumns,
  type SemanticColumnDisplay
} from "./columns";

const baseColumn: SemanticColumnDisplay = {
  data_type: "nvarchar",
  id: "column-id",
  metadata: {
    is_nullable: false,
    is_primary_key: false
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
        is_sensitive: true,
        queryable: false,
        sensitive_reason: "credential_name"
      },
      physical_name: "PasswordHash",
      pii: true,
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
        is_nullable: true,
        pii_reason: "contact_identifier"
      },
      physical_name: "EmailAddress",
      pii: true
    };

    expect(isSemanticColumnQueryable(emailAddress)).toBe(true);
    expect(semanticColumnFlags(emailAddress)).toEqual(["nullable", "PII"]);
  });

  it("shows declared SQL Server alias types without replacing base type", () => {
    const phone: SemanticColumnDisplay = {
      ...baseColumn,
      data_type: "nvarchar",
      metadata: {
        declared_type: "Phone",
        is_nullable: true
      },
      physical_name: "Phone"
    };

    expect(semanticColumnTypeLabel(phone)).toBe("nvarchar (Phone)");
    expect(semanticColumnTypeLabel(baseColumn)).toBe("nvarchar");
  });
});
