begin;

create extension if not exists pgtap with schema extensions;

select plan(12);

select ok(
  not has_table_privilege('authenticated', 'public.schema_snapshots', 'INSERT'),
  'authenticated cannot insert full schema snapshots'
);

select ok(
  not has_column_privilege(
    'authenticated',
    'public.schema_snapshots',
    'snapshot',
    'SELECT'
  ),
  'authenticated cannot select the sensitive snapshot JSON'
);

select ok(
  not has_table_privilege('authenticated', 'public.db_connections', 'UPDATE'),
  'authenticated cannot update connection metadata directly'
);

select ok(
  has_function_privilege(
    'service_role',
    'public.save_connection_test_result(uuid,jsonb)',
    'EXECUTE'
  ),
  'service role can persist connection test results'
);

select ok(
  not has_function_privilege(
    'authenticated',
    'public.save_connection_test_result(uuid,jsonb)',
    'EXECUTE'
  ),
  'authenticated cannot call the privileged connection RPC'
);

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
  '10000000-0000-4000-8000-000000000001',
  'authenticated',
  'authenticated',
  'hardening-test@example.com',
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
  '20000000-0000-4000-8000-000000000001',
  'hardening-test',
  'Hardening Test',
  '10000000-0000-4000-8000-000000000001'
);

insert into public.tenant_memberships (tenant_id, user_id, role, status)
values (
  '20000000-0000-4000-8000-000000000001',
  '10000000-0000-4000-8000-000000000001',
  'owner',
  'active'
);

select is(
  public.save_connection_test_result(
    '10000000-0000-4000-8000-000000000001',
    '{
      "id":"30000000-0000-4000-8000-000000000001",
      "tenant_id":"20000000-0000-4000-8000-000000000001",
      "name":"Hardening SQL Server",
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
      "secret_ref":"gcp-secret-manager://projects/demo/secrets/hardening",
      "status":"ready",
      "last_test_status":"ok",
      "last_test_error":null,
      "last_tested_at":"2026-06-05T09:00:00Z"
    }'::jsonb
  ),
  '30000000-0000-4000-8000-000000000001'::uuid,
  'service RPC persists a tested connection'
);

select throws_ok(
  $$
    select public.save_connection_test_result(
      '10000000-0000-4000-8000-000000000001',
      '{
        "id":"30000000-0000-4000-8000-000000000001",
        "tenant_id":"20000000-0000-4000-8000-000000000001",
        "name":"Hardening SQL Server",
        "engine":"sqlserver",
        "network_mode":"public_allowlist",
        "host":"different.example.com",
        "port":1433,
        "database_name":"demo",
        "username":"readonly_user",
        "tls_required":true,
        "tls_server_name":null,
        "trust_server_certificate":false,
        "expected_secret_ref":"gcp-secret-manager://projects/demo/secrets/hardening",
        "secret_ref":"gcp-secret-manager://projects/demo/secrets/hardening",
        "status":"ready",
        "last_test_status":"ok",
        "last_test_error":null,
        "last_tested_at":"2026-06-05T09:00:01Z"
      }'::jsonb
    )
  $$,
  '42501',
  'connection state changed while the test was running',
  'an existing secret cannot be rebound to a different endpoint'
);

select is(
  (
    select host
    from public.db_connections
    where id = '30000000-0000-4000-8000-000000000001'
  ),
  'sql.example.com',
  'rejected secret rebinding leaves connection metadata unchanged'
);

select is(
  (
    select semantic_version_number
    from public.persist_technical_schema_import(
      '10000000-0000-4000-8000-000000000001',
      '20000000-0000-4000-8000-000000000001',
      '30000000-0000-4000-8000-000000000001',
      'sqlserver',
      '{
        "status":"ok",
        "engine":"sqlserver",
        "tables":[],
        "foreign_keys":[],
        "coverage_state":"complete"
      }'::jsonb,
      '[]'::jsonb,
      '[]'::jsonb,
      0,
      0,
      '2026-06-05T09:00:00Z'
    )
  ),
  1,
  'first atomic import allocates version 1'
);

select is(
  (
    select semantic_version_number
    from public.persist_technical_schema_import(
      '10000000-0000-4000-8000-000000000001',
      '20000000-0000-4000-8000-000000000001',
      '30000000-0000-4000-8000-000000000001',
      'sqlserver',
      '{
        "status":"ok",
        "engine":"sqlserver",
        "tables":[],
        "foreign_keys":[],
        "coverage_state":"complete"
      }'::jsonb,
      '[]'::jsonb,
      '[]'::jsonb,
      0,
      0,
      '2026-06-05T09:01:00Z'
    )
  ),
  2,
  'second atomic import allocates version 2'
);

select throws_ok(
  $$
    select *
    from public.persist_technical_schema_import(
      '10000000-0000-4000-8000-000000000001',
      '20000000-0000-4000-8000-000000000001',
      '30000000-0000-4000-8000-000000000001',
      'sqlserver',
      '{
        "status":"ok",
        "engine":"sqlserver",
        "tables":[],
        "foreign_keys":[],
        "coverage_state":"complete"
      }'::jsonb,
      '[]'::jsonb,
      '[{
        "from_schema":"dbo",
        "from_table":"Missing",
        "from_columns":["Id"],
        "to_schema":"dbo",
        "to_table":"MissingToo",
        "to_columns":["Id"],
        "cardinality":"many_to_one",
        "constraint_name":"FK_Missing",
        "update_rule":"NO_ACTION",
        "delete_rule":"NO_ACTION",
        "is_disabled":false,
        "is_not_trusted":false,
        "verified_by_db":true
      }]'::jsonb,
      0,
      0,
      '2026-06-05T09:02:00Z'
    )
  $$,
  '23503',
  'relationship references unknown table',
  'invalid projection aborts the whole import'
);

select is(
  (
    select count(*)::integer
    from public.schema_snapshots
    where connection_id = '30000000-0000-4000-8000-000000000001'
  ),
  2,
  'failed import leaves no orphan snapshot'
);

select * from finish();
rollback;
