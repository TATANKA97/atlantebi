import { describe, expect, it } from "vitest";

import graphFixture from "../../../../packages/contracts/src/fixtures/queryability-graph-v1.json";
import {
  QueryabilityForeignKeyEdgeSchema,
  QueryabilityGraphArtifactSchema,
  SchemaColumnMetadataSchema
} from "@atlantebi/contracts";

import {
  foreignKeyEdgeDetail,
  graphLineageCounts,
  schemaColumnFlags,
  viewLineageLabel
} from "./presentation";

describe("queryability presentation", () => {
  it("distinguishes foreign keys that connect the same objects", () => {
    const edge = QueryabilityForeignKeyEdgeSchema.parse({
      edge_key: "1".repeat(64),
      edge_type: "fk_join",
      constraint_name: "FK_Order_Address_ShipTo",
      from_node_key: "2".repeat(64),
      to_node_key: "3".repeat(64),
      column_pairs: [
        {
          ordinal_position: 1,
          from_column: "ShipToAddressID",
          from_column_key: "4".repeat(64),
          to_column: "AddressID",
          to_column_key: "5".repeat(64)
        }
      ],
      relationship_shape: "many_to_one",
      child_to_parent: "zero_or_one",
      parent_to_child: "zero_or_many",
      nullable_fk: true,
      self_reference: false,
      verified_by_db: true,
      enforcement_status: "enabled",
      validation_status: "trusted",
      automatic_join_allowed: true,
      reason_codes: []
    });

    expect(foreignKeyEdgeDetail(edge, "SalesLT.Address")).toBe(
      "FK_Order_Address_ShipTo: ShipToAddressID → SalesLT.Address.AddressID"
    );
  });

  it("labels composite key membership without claiming column uniqueness", () => {
    const column = SchemaColumnMetadataSchema.parse({
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
    });

    expect(
      schemaColumnFlags({
        column,
        primaryKeyColumnCount: 2,
        tableType: "base_table"
      })
    ).toEqual([
      "part_of_composite_pk",
      "FK",
      "part_of_composite_unique",
      "not null"
    ]);
  });

  it("separates object lineage from column lineage coverage", () => {
    const graph = QueryabilityGraphArtifactSchema.parse(graphFixture);
    const view = graph.nodes.find((node) => node.object_type === "view");

    expect(graphLineageCounts(graph)).toEqual({
      objectEdges: 1,
      columnEdges: 1
    });
    expect(viewLineageLabel(view)).toBe("object partial, columns complete");
  });
});
