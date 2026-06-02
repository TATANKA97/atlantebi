import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const migrationPath = resolve(
  import.meta.dirname,
  "../../../supabase/migrations/20260602201234_init_app_metadata.sql"
);
const migration = readFileSync(migrationPath, "utf8");

const tenantScopedTables = [
  "tenants",
  "tenant_memberships",
  "db_connections",
  "schema_snapshots",
  "semantic_versions",
  "semantic_tables",
  "semantic_columns",
  "semantic_relationships",
  "semantic_metrics",
  "business_anchors",
  "dashboards",
  "widgets",
  "dashboard_widgets",
  "query_history",
  "audit_logs"
];

describe("Supabase metadata migration", () => {
  it("does not define customer database credential columns", () => {
    const forbiddenColumnPattern =
      /\b(password|db_password|connection_string|dsn|secret_value|private_key)\b/i;

    expect(migration).not.toMatch(forbiddenColumnPattern);
    expect(migration).toMatch(/\bsecret_ref\b/);
  });

  it("enables RLS on every tenant-scoped table", () => {
    for (const table of tenantScopedTables) {
      expect(migration).toContain(
        `alter table public.${table} enable row level security;`
      );
    }
  });

  it("uses a private helper schema for membership checks", () => {
    expect(migration).toContain("create schema if not exists app_private;");
    expect(migration).toContain("app_private.is_tenant_member");
    expect(migration).toContain("security definer");
  });
});
