import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const migrationsDirectory = resolve(
  import.meta.dirname,
  "../../../supabase/migrations"
);
const migrationFileNames = readdirSync(migrationsDirectory)
  .filter((fileName) => fileName.endsWith(".sql"))
  .sort();
const migration = migrationFileNames
  .map((fileName) => readFileSync(resolve(migrationsDirectory, fileName), "utf8"))
  .join("\n");
const schemaImportSummaryMigration = readFileSync(
  resolve(
    migrationsDirectory,
    "20260611120000_persist_schema_import_summary.sql"
  ),
  "utf8"
);
const schemaImportSummaryGrantsMigration = readFileSync(
  resolve(
    migrationsDirectory,
    "20260611140354_grant_schema_import_summary_helpers_to_service_role.sql"
  ),
  "utf8"
);
const queryabilityGraphMigration = readFileSync(
  resolve(
    migrationsDirectory,
    "20260612010000_queryability_graph_v1.sql"
  ),
  "utf8"
);
const purgeAdventureWorksPlanScript = readFileSync(
  resolve(
    import.meta.dirname,
    "../scripts/purge-adventureworkslt-plan.mjs"
  ),
  "utf8"
);
const supabaseConfig = readFileSync(
  resolve(import.meta.dirname, "../../../supabase/config.toml"),
  "utf8"
);
const workflows = readdirSync(
  resolve(import.meta.dirname, "../../../.github/workflows")
)
  .filter((fileName) => fileName.endsWith(".yml"))
  .map((fileName) =>
    readFileSync(
      resolve(import.meta.dirname, "../../../.github/workflows", fileName),
      "utf8"
    )
  )
  .join("\n");
const dockerIgnore = readFileSync(
  resolve(import.meta.dirname, "../../../.dockerignore"),
  "utf8"
);
const queryEngineDockerfile = readFileSync(
  resolve(import.meta.dirname, "../../../services/query-engine/Dockerfile"),
  "utf8"
);
const concurrentSchemaImportsFixture = readFileSync(
  resolve(
    import.meta.dirname,
    "../../../.github/fixtures/concurrent-schema-imports.sql"
  ),
  "utf8"
);

const tenantScopedTables = [
  "tenants",
  "tenant_memberships",
  "db_connections",
  "schema_snapshots",
  "queryability_graph_versions",
  "queryability_graph_nodes",
  "queryability_graph_columns",
  "queryability_graph_edges",
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
  it("pins every GitHub Action to an immutable commit SHA", () => {
    expect(workflows).not.toMatch(/uses:\s*[^\s#]+@v\d+/);
    const pinnedActions = [
      ...workflows.matchAll(/uses:\s*[^\s#]+@([0-9a-f]{40})/g)
    ];
    expect(pinnedActions.length).toBeGreaterThan(0);
    for (const match of pinnedActions) {
      expect(match[1]).toHaveLength(40);
    }
  });

  it("keeps local Auth password controls aligned with the application", () => {
    expect(supabaseConfig).toContain("minimum_password_length = 8");
    expect(supabaseConfig).toContain("secure_password_change = true");
  });

  it("keeps CI credentials out of Docker contexts and runs query-engine unprivileged", () => {
    expect(dockerIgnore).toContain("gha-creds-*.json");
    expect(queryEngineDockerfile).toContain("USER atlante");
  });

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
      "revoke insert, update, delete on table public.db_connections from authenticated;"
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

  it("moves audit writes and membership mutations behind server controls", () => {
    expect(migration).toContain(
      "revoke insert on table public.audit_logs from anon, authenticated;"
    );
    expect(migration).toContain(
      'drop policy if exists "members can create audit logs" on public.audit_logs;'
    );
    expect(migration).toContain(
      "revoke update, delete on table public.tenant_memberships from authenticated;"
    );
    expect(migration).toContain(
      "app_private.acquire_security_operation_lease"
    );
    expect(migration).toContain(
      "grant execute on function public.acquire_security_operation_lease"
    );
  });

  it("stores technical FK metadata for SQL Server snapshots without raw data", () => {
    expect(migration).toContain("add column if not exists constraint_name text");
    expect(migration).toContain("add column if not exists update_rule text");
    expect(migration).toContain("add column if not exists delete_rule text");
    expect(migration).toContain("add column if not exists is_disabled boolean not null default false");
    expect(migration).toContain("add column if not exists is_not_trusted boolean not null default false");
    expect(migration).toContain("add column if not exists verified_by_db boolean not null default false");
    expect(migration).toContain("db_fk maps to database_fk");
  });

  it("exposes only safe technical snapshot summary fields to authenticated users", () => {
    expect(migration).toContain("snapshot->>'engine_version' as engine_version");
    expect(migration).toContain("snapshot->>'schema_hash' as schema_hash");
    expect(migration).toContain("snapshot->'coverage_warnings'");
    const summaryViews =
      migration.match(
        /create(?: or replace)? view public\.schema_snapshot_summaries[\s\S]*?from public\.schema_snapshots;/gi
      ) ?? [];
    expect(summaryViews.length).toBeGreaterThan(0);
    const latestSummaryView = summaryViews.at(-1) ?? "";
    expect(latestSummaryView).not.toContain("view_definition");
    expect(latestSummaryView).not.toContain("extended_properties");
  });

  it("requires a pre-migration purge before replacing legacy coverage state", () => {
    expect(schemaImportSummaryMigration).toContain(
      "legacy schema snapshots must be purged before this migration"
    );
    expect(schemaImportSummaryMigration).toContain("drop column coverage_state");
    expect(schemaImportSummaryMigration).toContain(
      "add column coverage_status public.schema_coverage_status not null"
    );
    expect(schemaImportSummaryMigration).toContain(
      "add column summary jsonb not null"
    );
    expect(schemaImportSummaryMigration).not.toContain(
      "technical_snapshot->>'coverage_state'"
    );
  });

  it("persists a strict sanitized import summary through the service-role RPC", () => {
    expect(schemaImportSummaryMigration).toContain(
      "target_summary jsonb"
    );
    expect(schemaImportSummaryMigration).toContain(
      "app_private.sanitize_schema_import_summary"
    );
    expect(schemaImportSummaryMigration).toContain(
      "schema_snapshots_summary_strict"
    );
    expect(schemaImportSummaryMigration).toContain(
      "target_summary - allowed_keys <> '{}'::jsonb"
    );
    expect(schemaImportSummaryMigration).toContain(
      "technical_snapshot ? 'coverage_state'"
    );
    expect(schemaImportSummaryMigration).toContain(
      "grant execute on function public.persist_technical_schema_import("
    );
    expect(schemaImportSummaryMigration).toContain(") to service_role;");
    expect(schemaImportSummaryMigration).toContain("coverage_status,");
    expect(schemaImportSummaryMigration).toContain("summary,");
    expect(schemaImportSummaryGrantsMigration).toContain(
      "grant execute on function app_private.sanitize_schema_import_summary(jsonb)"
    );
    expect(schemaImportSummaryGrantsMigration).toContain(
      "grant execute on function app_private.is_valid_schema_import_summary(jsonb)"
    );
    expect(schemaImportSummaryGrantsMigration).not.toContain(
      "to anon"
    );
    expect(schemaImportSummaryGrantsMigration).not.toContain(
      "to authenticated"
    );
  });

  it("provides a guarded pre-migration AdventureWorksLT purge command", () => {
    expect(purgeAdventureWorksPlanScript).toContain(
      'const REQUIRED_CONFIRMATION = "AdventureWorksLT"'
    );
    expect(purgeAdventureWorksPlanScript).toContain(
      "SUPABASE_SERVICE_ROLE_KEY"
    );
    expect(purgeAdventureWorksPlanScript).toContain(
      "isDemoOrTestTenant"
    );
    expect(purgeAdventureWorksPlanScript).toContain(
      'await scopedDelete("semantic_versions")'
    );
    expect(purgeAdventureWorksPlanScript).toContain(
      'await scopedDelete("schema_snapshots")'
    );
    expect(purgeAdventureWorksPlanScript).not.toContain(
      ".rpc("
    );
  });

  it("moves privileged connection and schema writes behind service-role RPCs", () => {
    expect(migration).toContain("app_private.save_connection_test_result");
    expect(migration).toContain("public.save_connection_test_result");
    expect(migration).toContain(
      "grant execute on function public.save_connection_test_result(uuid, jsonb) to service_role;"
    );
    expect(migration).toContain("app_private.persist_technical_schema_import");
    expect(migration).toContain("pg_advisory_xact_lock");
    expect(migration).toContain(
      "revoke insert, update, delete on table public.schema_snapshots from authenticated;"
    );
    expect(migration).toContain(
      "revoke insert, update, delete on table public.semantic_relationships from authenticated;"
    );
    expect(migration).toContain("semantic_relationships_from_table_version_fk");
    expect(migration).toContain("semantic_relationships_to_table_version_fk");
    expect(migration).toContain(
      "semantic_versions_schema_snapshot_connection_fk"
    );
    expect(migration).toContain(
      "references public.schema_snapshots(tenant_id, connection_id, id)"
    );
    expect(migration).toContain(
      "semantic_relationships_tenant_version_from_table_idx"
    );
    expect(migration).toContain(
      "semantic_relationships_tenant_version_to_table_idx"
    );
    expect(migration).toContain(
      "semantic_versions_tenant_connection_snapshot_idx"
    );
  });

  it("persists immutable queryability graphs without creating semantic drafts", () => {
    for (const table of [
      "queryability_graph_versions",
      "queryability_graph_nodes",
      "queryability_graph_columns",
      "queryability_graph_edges"
    ]) {
      expect(queryabilityGraphMigration).toContain(
        `create table public.${table}`
      );
      expect(queryabilityGraphMigration).toContain(
        `alter table public.${table} enable row level security;`
      );
      expect(queryabilityGraphMigration).toContain(
        `revoke all privileges on table public.${table}`
      );
    }
    expect(queryabilityGraphMigration).toContain(
      "app_private.persist_queryability_graph_import"
    );
    expect(queryabilityGraphMigration).toContain(
      "public.persist_queryability_graph_import"
    );
    expect(queryabilityGraphMigration).toContain(
      "pg_advisory_xact_lock"
    );
    expect(queryabilityGraphMigration).toContain(
      "queryability graph artifacts are immutable"
    );
    expect(queryabilityGraphMigration).toContain(
      "queryability_graph->>'derivation_key'"
    );
    expect(queryabilityGraphMigration).toContain(
      "foreign key (tenant_id, connection_id)"
    );
    expect(queryabilityGraphMigration).toContain(
      "reuse_existing_snapshot boolean default false"
    );
    expect(queryabilityGraphMigration).toContain(
      "not in ('ok', 'partial', 'warning')"
    );
    expect(queryabilityGraphMigration).toContain(
      "alter column snapshot_hash set not null"
    );
    expect(queryabilityGraphMigration).toContain(
      "'queryability_graph.rebuilt'"
    );
    expect(queryabilityGraphMigration).toContain(
      "'not_initialized'::text"
    );
    expect(queryabilityGraphMigration).toContain(
      "drop function if exists public.persist_technical_schema_import("
    );
    expect(queryabilityGraphMigration).toContain(
      "drop function if exists app_private.persist_technical_schema_import("
    );
    expect(queryabilityGraphMigration).not.toContain(
      "insert into public.semantic_versions"
    );
    expect(queryabilityGraphMigration).not.toContain(
      "insert into public.semantic_relationships"
    );
    expect(concurrentSchemaImportsFixture).toContain(
      "public.persist_queryability_graph_import("
    );
    expect(concurrentSchemaImportsFixture).not.toContain(
      "public.persist_technical_schema_import("
    );
  });

  it("fixes the immutable metadata guard search path", () => {
    expect(migration).toMatch(
      /create or replace function app_private\.jsonb_has_forbidden_metadata_key[\s\S]*?set search_path = public, pg_temp/
    );
  });
});
