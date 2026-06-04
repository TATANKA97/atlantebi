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
      /\b(add column|,\s*)\s+(password|db_password|connection_string|dsn|secret_value|private_key)\s+/i;

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
    expect(migration).toContain(
      "grant insert, update, delete on table public.db_connections to authenticated;"
    );
    expect(migration).toContain("revoke all privileges on table public.db_connections from anon;");
    expect(migration).toContain(
      "revoke all privileges on table public.db_connections from authenticated;"
    );
  });

  it("keeps connection secret references out of broad authenticated selects", () => {
    expect(migration).toContain("create or replace view public.db_connection_summaries");
    expect(migration).not.toContain(
      "grant select on table public.db_connections to authenticated;"
    );
    expect(migration).toContain(") on table public.db_connections to authenticated;");
    expect(migration).toContain("grant select on table public.db_connection_summaries to authenticated;");
    expect(migration).toContain(
      "revoke all privileges on table public.db_connection_summaries from authenticated;"
    );
    expect(migration).toContain("username,");
    const summaryViews =
      migration.match(
        /create(?: or replace)? view public\.db_connection_summaries[\s\S]*?from public\.db_connections;/gi
      ) ?? [];
    expect(summaryViews.length).toBeGreaterThan(0);
    for (const summaryView of summaryViews) {
      expect(summaryView).not.toContain("secret_ref");
    }
  });

  it("stores connection test metadata without customer result data", () => {
    expect(migration).toContain("create type public.connection_test_status");
    expect(migration).toContain("add column username text not null");
    expect(migration).toContain("add column trust_server_certificate boolean not null default false");
    expect(migration).toContain("add column last_test_status public.connection_test_status");
    expect(migration).toContain("add column last_test_error text");
    expect(migration).toContain("alter column secret_ref drop not null");
    expect(migration).toContain("db_connections_ready_requires_secret_ref");
    expect(migration).toContain("check (status <> 'ready' or secret_ref is not null)");
    expect(migration).not.toMatch(/\b(add column|,\s*)\s+(sample_rows|preview_rows|result_rows|data_cache|raw_rows|cached_result)\s+/i);
  });

  it("keeps schema introspection snapshots metadata-only", () => {
    expect(migration).toContain("app_private.jsonb_has_forbidden_metadata_key");
    expect(migration).toContain("schema_snapshots_snapshot_metadata_only");
    expect(migration).toContain("snapshot ? 'tables'");
    expect(migration).toContain("snapshot ? 'foreign_keys'");
    expect(migration).toContain("'secret_ref'");
    expect(migration).toContain("'sample_rows'");
    expect(migration).toContain("'result_rows'");
    expect(migration).toContain("create or replace view public.schema_snapshot_summaries");
    expect(migration).toContain(
      "grant select on table public.schema_snapshot_summaries to authenticated;"
    );
    expect(migration).not.toMatch(
      /\b(customer_rows|customer_values|raw_result|query_result_cache)\b/i
    );
  });

  it("marks imported credential metadata as sensitive and non-queryable", () => {
    expect(migration).toContain("mark_sensitive_semantic_columns");
    expect(migration).toContain("fix_sensitive_semantic_column_tokenization");
    expect(migration).toContain("sensitive_reason");
    expect(migration).toContain("'queryable', false");
    expect(migration).toContain("'credential_name'");
    expect(migration).toContain("'credential_derivative_name'");
    expect(migration).toContain("'secret_key_name'");
    expect(migration).toContain("'contact_identifier'");
    expect(migration).toContain("'direct_person_identifier'");
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

  it("exposes tenant bootstrap through an invoker RPC wrapper only", () => {
    expect(migration).toContain(
      "create or replace function public.create_tenant_with_owner"
    );
    expect(migration).toContain("security invoker");
    expect(migration).toContain(
      "select app_private.create_tenant_with_owner(tenant_slug, tenant_name, tenant_plan);"
    );
    expect(migration).toContain(
      "grant execute on function public.create_tenant_with_owner(text, text, text) to authenticated;"
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
