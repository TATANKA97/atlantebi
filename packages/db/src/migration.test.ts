import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const migrationsDirectory = resolve(
  import.meta.dirname,
  "../../../supabase/migrations"
);
const migration = readdirSync(migrationsDirectory)
  .filter((fileName) => fileName.endsWith(".sql"))
  .sort()
  .map((fileName) => readFileSync(resolve(migrationsDirectory, fileName), "utf8"))
  .join("\n");
const supabaseConfig = readFileSync(
  resolve(import.meta.dirname, "../../../supabase/config.toml"),
  "utf8"
);

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

  it("grants authenticated API access explicitly instead of relying on auto exposure", () => {
    expect(supabaseConfig).toContain("auto_expose_new_tables = false");
    expect(migration).toContain("grant usage on schema public to authenticated;");
    expect(migration).toContain(
      "grant select, insert, update, delete on table public.widgets to authenticated;"
    );
    expect(migration).toContain(
      "grant select, insert on table public.query_history to authenticated;"
    );
  });

  it("keeps connection secret references out of broad authenticated selects", () => {
    expect(migration).toContain("create or replace view public.db_connection_summaries");
    expect(migration).not.toContain(
      "grant select on table public.db_connections to authenticated;"
    );
    expect(migration).toContain(") on table public.db_connections to authenticated;");
  });

  it("uses a non-circular tenant bootstrap function", () => {
    expect(migration).toContain("app_private.create_tenant_with_owner");
    expect(migration).toContain(
      'drop policy if exists "authenticated users can create tenants" on public.tenants;'
    );
    expect(migration).toContain(
      'drop policy if exists "creator can add initial owner membership" on public.tenant_memberships;'
    );
  });

  it("enforces tenant consistency with composite foreign keys", () => {
    expect(migration).toContain("db_connections_tenant_id_id_unique");
    expect(migration).toContain("widgets_connection_tenant_fk");
    expect(migration).toContain("query_history_connection_tenant_fk");
    expect(migration).toContain("dashboard_widgets_widget_tenant_fk");
  });

  it("guards owner membership changes", () => {
    expect(migration).toContain("app_private.has_other_active_owner");
    expect(migration).toContain('create policy "owners can update memberships"');
    expect(migration).toContain('create policy "admins can update non-owner memberships"');
    expect(migration).toContain('create policy "owners can delete memberships"');
  });
});
