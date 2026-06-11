insert into auth.users (
  instance_id,
  id,
  aud,
  role,
  email,
  encrypted_password,
  email_confirmed_at,
  raw_app_meta_data,
  raw_user_meta_data,
  created_at,
  updated_at,
  confirmation_token,
  email_change,
  email_change_token_new,
  recovery_token
)
values (
  '00000000-0000-0000-0000-000000000000',
  '10000000-0000-4000-8000-000000000002',
  'authenticated',
  'authenticated',
  'concurrent-import@example.com',
  '',
  now(),
  '{"provider":"email","providers":["email"]}',
  '{}',
  now(),
  now(),
  '',
  '',
  '',
  ''
);

insert into public.tenants (id, slug, name, created_by)
values (
  '20000000-0000-4000-8000-000000000002',
  'concurrent-import',
  'Concurrent Import',
  '10000000-0000-4000-8000-000000000002'
);

insert into public.tenant_memberships (tenant_id, user_id, role, status)
values (
  '20000000-0000-4000-8000-000000000002',
  '10000000-0000-4000-8000-000000000002',
  'owner',
  'active'
);

select public.save_connection_test_result(
  '10000000-0000-4000-8000-000000000002',
  '{
    "id":"30000000-0000-4000-8000-000000000002",
    "tenant_id":"20000000-0000-4000-8000-000000000002",
    "name":"Concurrent SQL Server",
    "engine":"sqlserver",
    "network_mode":"public_allowlist",
    "host":"sql.example.com",
    "port":1433,
    "database_name":"demo",
    "username":"readonly_user",
    "tls_required":true,
    "tls_server_name":null,
    "trust_server_certificate":false,
    "expected_secret_ref":null,
    "secret_ref":"gcp-secret-manager://projects/demo/secrets/concurrent",
    "status":"ready",
    "last_test_status":"ok",
    "last_test_error":null,
    "last_tested_at":"2026-06-05T09:00:00Z"
  }'::jsonb
);

create or replace function public.hardening_test_concurrent_import()
returns integer
language plpgsql
as $$
declare
  captured_at timestamptz := clock_timestamp();
  imported_version integer;
begin
  select semantic_version_number
  into imported_version
  from public.persist_technical_schema_import(
    '10000000-0000-4000-8000-000000000002',
    '20000000-0000-4000-8000-000000000002',
    '30000000-0000-4000-8000-000000000002',
    'sqlserver',
    jsonb_build_object(
      'status', 'ok',
      'engine', 'sqlserver',
      'engine_version', 'test',
      'schema_hash', repeat('a', 64),
      'coverage_status', 'ok',
      'tables', jsonb_build_array(),
      'foreign_keys', jsonb_build_array(),
      'coverage_warnings', jsonb_build_array()
    ),
    jsonb_build_object(
      'database_name', 'demo',
      'engine', 'sqlserver',
      'engine_version', 'test',
      'schema_hash', repeat('a', 64),
      'coverage_status', 'ok',
      'captured_at', to_char(captured_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') || 'Z',
      'duration_ms', 0,
      'total_objects', 0,
      'total_tables', 0,
      'total_views', 0,
      'total_columns', 0,
      'queryable_objects', 0,
      'non_queryable_objects', 0,
      'queryable_columns', 0,
      'non_queryable_columns', 0,
      'primary_keys_count', 0,
      'foreign_keys_count', 0,
      'unique_constraints_count', 0,
      'check_constraints_count', 0,
      'default_constraints_count', 0,
      'indexes_total_count', 0,
      'table_indexes_count', 0,
      'view_indexes_count', 0,
      'unique_indexes_count', 0,
      'filtered_indexes_count', 0,
      'included_columns_indexes_count', 0,
      'views_total', 0,
      'views_with_definition_count', 0,
      'views_without_definition_count', 0,
      'views_with_lineage_count', 0,
      'views_with_partial_lineage_count', 0,
      'views_without_lineage_count', 0,
      'view_lineage_dependencies_count', 0,
      'columns_with_declared_type_count', 0,
      'columns_without_declared_type_count', 0,
      'columns_with_default_count', 0,
      'computed_columns_count', 0,
      'identity_columns_count', 0,
      'pii_columns_count', 0,
      'excluded_columns_count', 0,
      'sensitive_columns_count', 0,
      'coverage_warnings_count', 0,
      'coverage_warnings_by_code', jsonb_build_object()
    ),
    '[]'::jsonb,
    '[]'::jsonb,
    0,
    0,
    captured_at
  );
  return imported_version;
end;
$$;
