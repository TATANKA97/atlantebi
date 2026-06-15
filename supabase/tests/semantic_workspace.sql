begin;

create extension if not exists pgtap with schema extensions;

select plan(4);

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
values
  (
    '00000000-0000-0000-0000-000000000000',
    '10000000-0000-4000-8000-000000000041',
    'authenticated',
    'authenticated',
    'semantic-owner@example.com',
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
  ),
  (
    '00000000-0000-0000-0000-000000000000',
    '10000000-0000-4000-8000-000000000042',
    'authenticated',
    'authenticated',
    'semantic-editor@example.com',
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
  '20000000-0000-4000-8000-000000000041',
  'semantic-workspace',
  'Semantic Workspace',
  '10000000-0000-4000-8000-000000000041'
);

insert into public.tenant_memberships (tenant_id, user_id, role, status)
values
  (
    '20000000-0000-4000-8000-000000000041',
    '10000000-0000-4000-8000-000000000041',
    'owner',
    'active'
  ),
  (
    '20000000-0000-4000-8000-000000000041',
    '10000000-0000-4000-8000-000000000042',
    'editor',
    'active'
  );

create temporary table semantic_workspace_leases (
  lease_id uuid primary key
);

insert into semantic_workspace_leases
select public.acquire_security_operation_lease(
  '10000000-0000-4000-8000-000000000041',
  '20000000-0000-4000-8000-000000000041',
  'semantic_generation',
  '30000000-0000-4000-8000-000000000041'
);

select is(
  (select count(*)::integer from semantic_workspace_leases),
  1,
  'owner can acquire a semantic generation lease'
);

select throws_ok(
  $$
    select public.acquire_security_operation_lease(
      '10000000-0000-4000-8000-000000000041',
      '20000000-0000-4000-8000-000000000041',
      'semantic_generation',
      '30000000-0000-4000-8000-000000000041'
    )
  $$,
  'P0001',
  'security operation resource is already busy',
  'semantic generation is serialized per connection'
);

select throws_ok(
  $$
    select public.acquire_security_operation_lease(
      '10000000-0000-4000-8000-000000000042',
      '20000000-0000-4000-8000-000000000041',
      'semantic_generation',
      '30000000-0000-4000-8000-000000000042'
    )
  $$,
  '42501',
  'actor cannot run this security operation',
  'editor cannot start semantic generation'
);

select public.release_security_operation_lease(
  (select lease_id from semantic_workspace_leases)
);

select is(
  (
    select count(*)::integer
    from app_private.security_operation_leases
    where tenant_id = '20000000-0000-4000-8000-000000000041'
      and operation = 'semantic_generation'
  ),
  0,
  'semantic generation lease is released'
);

select * from finish();
rollback;
