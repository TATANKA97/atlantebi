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
language sql
as $$
  select semantic_version_number
  from public.persist_technical_schema_import(
    '10000000-0000-4000-8000-000000000002',
    '20000000-0000-4000-8000-000000000002',
    '30000000-0000-4000-8000-000000000002',
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
    now()
  );
$$;
