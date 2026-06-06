begin;

create extension if not exists pgtap with schema extensions;

select plan(11);

select ok(
  not has_table_privilege('authenticated', 'public.audit_logs', 'INSERT'),
  'authenticated cannot forge audit records'
);

select ok(
  not has_table_privilege(
    'authenticated',
    'public.tenant_memberships',
    'UPDATE'
  ),
  'authenticated cannot update memberships directly'
);

select ok(
  not has_table_privilege(
    'authenticated',
    'public.tenant_memberships',
    'DELETE'
  ),
  'authenticated cannot delete memberships directly'
);

select ok(
  not has_function_privilege(
    'authenticated',
    'public.acquire_security_operation_lease(uuid,uuid,text,text)',
    'EXECUTE'
  ),
  'authenticated cannot acquire privileged operation leases'
);

select ok(
  has_function_privilege(
    'service_role',
    'public.acquire_security_operation_lease(uuid,uuid,text,text)',
    'EXECUTE'
  ),
  'service role can acquire operation leases'
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
  '10000000-0000-4000-8000-000000000010',
  'authenticated',
  'authenticated',
  'security-remediation@example.com',
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
  '20000000-0000-4000-8000-000000000010',
  'security-remediation',
  'Security Remediation',
  '10000000-0000-4000-8000-000000000010'
);

insert into public.tenant_memberships (tenant_id, user_id, role, status)
values (
  '20000000-0000-4000-8000-000000000010',
  '10000000-0000-4000-8000-000000000010',
  'owner',
  'active'
);

create temporary table remediation_test_leases (
  lease_id uuid primary key
);

insert into remediation_test_leases
select public.acquire_security_operation_lease(
  '10000000-0000-4000-8000-000000000010',
  '20000000-0000-4000-8000-000000000010',
  'schema_introspection',
  '30000000-0000-4000-8000-000000000010'
);

select is(
  (select count(*)::integer from remediation_test_leases),
  1,
  'first schema introspection lease is acquired'
);

select ok(
  (
    select expires_at > clock_timestamp() + interval '14 minutes'
    from app_private.security_operation_leases
    where id = (select lease_id from remediation_test_leases)
  ),
  'schema introspection lease covers the full operation budget'
);

select throws_ok(
  $$
    select public.acquire_security_operation_lease(
      '10000000-0000-4000-8000-000000000010',
      '20000000-0000-4000-8000-000000000010',
      'schema_introspection',
      ' 30000000-0000-4000-8000-000000000010 '
    )
  $$,
  'P0001',
  'security operation resource is already busy',
  'a second introspection for the same connection is rejected'
);

select public.release_security_operation_lease(
  (select lease_id from remediation_test_leases)
);

select is(
  (
    select count(*)::integer
    from app_private.security_operation_leases
    where tenant_id = '20000000-0000-4000-8000-000000000010'
  ),
  0,
  'released operation lease is removed'
);

select throws_ok(
  $$
    select public.acquire_security_operation_lease(
      '10000000-0000-4000-8000-000000000099',
      '20000000-0000-4000-8000-000000000010',
      'connection_test',
      'sql.example.com:1433'
    )
  $$,
  '42501',
  'actor cannot run this security operation',
  'a non-member cannot acquire a lease'
);

select ok(
  has_function_privilege(
    'service_role',
    'public.release_security_operation_lease(uuid)',
    'EXECUTE'
  ),
  'service role can release operation leases'
);

select * from finish();
rollback;
