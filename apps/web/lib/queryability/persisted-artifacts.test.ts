import { describe, expect, it } from "vitest";

import graphFixture from "../../../../packages/contracts/src/fixtures/queryability-graph-v1.json";

import {
  parsePersistedQueryabilityGraph,
  parsePersistedTechnicalSnapshot
} from "./persisted-artifacts";

const technicalSnapshot = {
  status: "ok",
  message: "Schema introspection completed.",
  introspected_at: "2026-06-13T00:00:00.000Z",
  duration_ms: 1,
  engine: "sqlserver",
  database_name: "AdventureWorksLT",
  engine_version: "12.0.2000.8",
  schema_hash: "a".repeat(64),
  snapshot_hash: "b".repeat(64),
  coverage_status: "partial",
  tables: [
    {
      schema: "SalesLT",
      name: "CustomerAddress",
      table_type: "base_table",
      columns: [
        {
          name: "CustomerID",
          data_type: "int",
          declared_type_available: true,
          technical_role: "identifier",
          ordinal_position: 1,
          is_nullable: false,
          is_primary_key: true,
          is_foreign_key: true,
          is_single_column_unique: false,
          is_composite_unique_member: true
        }
      ],
      is_system_object: false,
      view_lineage: []
    }
  ],
  foreign_keys: [],
  unique_constraints: [],
  check_constraints: [],
  default_constraints: [],
  indexes: [],
  coverage_warnings: []
};

describe("persisted queryability artifacts", () => {
  it("accepts artifacts that match the current strict contracts", () => {
    expect(parsePersistedQueryabilityGraph(graphFixture)).not.toBeNull();
    expect(parsePersistedTechnicalSnapshot(technicalSnapshot)).not.toBeNull();
  });

  it("rejects legacy snapshots without throwing during page rendering", () => {
    const legacySnapshot = structuredClone(technicalSnapshot);
    const legacyColumn = legacySnapshot.tables[0]!.columns[0]! as Record<
      string,
      unknown
    >;
    delete legacyColumn.is_single_column_unique;
    delete legacyColumn.is_composite_unique_member;
    legacyColumn.is_unique_member = true;

    expect(parsePersistedTechnicalSnapshot(legacySnapshot)).toBeNull();
  });
});
