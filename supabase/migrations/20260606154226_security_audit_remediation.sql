revoke insert on table public.audit_logs from anon, authenticated;
drop policy if exists "members can create audit logs" on public.audit_logs;

revoke update, delete on table public.tenant_memberships from authenticated;
drop policy if exists "tenant owners and admins can update memberships"
  on public.tenant_memberships;
drop policy if exists "tenant owners and admins can delete memberships"
  on public.tenant_memberships;

create table if not exists app_private.security_operation_leases (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  actor_user_id uuid not null references auth.users(id) on delete cascade,
  operation text not null check (
    operation in ('connection_test', 'schema_introspection')
  ),
  resource_key text not null,
  created_at timestamptz not null default statement_timestamp(),
  expires_at timestamptz not null
);

create index if not exists security_operation_leases_active_idx
  on app_private.security_operation_leases (
    tenant_id,
    operation,
    expires_at
  );

create index if not exists security_operation_leases_resource_idx
  on app_private.security_operation_leases (
    tenant_id,
    operation,
    resource_key,
    expires_at
  );

create table if not exists app_private.security_operation_windows (
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  actor_user_id uuid not null references auth.users(id) on delete cascade,
  operation text not null check (
    operation in ('connection_test', 'schema_introspection')
  ),
  window_started_at timestamptz not null,
  request_count integer not null check (request_count > 0),
  primary key (
    tenant_id,
    actor_user_id,
    operation,
    window_started_at
  )
);

revoke all privileges on table app_private.security_operation_leases from public;
revoke all privileges on table app_private.security_operation_windows from public;

create or replace function app_private.acquire_security_operation_lease(
  target_actor_user_id uuid,
  target_tenant_id uuid,
  target_operation text,
  target_resource_key text
)
returns uuid
language plpgsql
security definer
set search_path = public, app_private, pg_temp
as $$
declare
  lease_id uuid;
  max_concurrency integer;
  max_resource_concurrency integer;
  max_requests integer;
  window_seconds integer;
  lease_seconds integer;
  current_request_count integer;
  current_concurrency integer;
  current_resource_concurrency integer;
  current_window timestamptz;
  normalized_resource_key text;
begin
  if target_actor_user_id is null
    or target_tenant_id is null
    or nullif(btrim(target_resource_key), '') is null
  then
    raise exception using
      errcode = '22023',
      message = 'invalid security operation lease request';
  end if;

  if not exists (
    select 1
    from public.tenant_memberships tm
    where tm.tenant_id = target_tenant_id
      and tm.user_id = target_actor_user_id
      and tm.status = 'active'
      and tm.role = any (
        array['owner', 'admin', 'editor']::public.tenant_role[]
      )
  ) then
    raise exception using
      errcode = '42501',
      message = 'actor cannot run this security operation';
  end if;

  case target_operation
    when 'connection_test' then
      max_concurrency := 3;
      max_resource_concurrency := 2;
      max_requests := 20;
      window_seconds := 60;
      lease_seconds := 130;
    when 'schema_introspection' then
      max_concurrency := 2;
      max_resource_concurrency := 1;
      max_requests := 6;
      window_seconds := 3600;
      lease_seconds := 900;
    else
      raise exception using
        errcode = '22023',
        message = 'unsupported security operation';
  end case;

  normalized_resource_key := btrim(target_resource_key);

  perform pg_advisory_xact_lock(
    hashtextextended(
      target_tenant_id::text || ':' || target_operation,
      0
    )
  );

  delete from app_private.security_operation_leases
  where expires_at <= clock_timestamp();

  delete from app_private.security_operation_windows
  where window_started_at < clock_timestamp() - interval '2 days';

  current_window := date_bin(
    make_interval(secs => window_seconds),
    clock_timestamp(),
    timestamptz '2000-01-01 00:00:00+00'
  );

  insert into app_private.security_operation_windows (
    tenant_id,
    actor_user_id,
    operation,
    window_started_at,
    request_count
  )
  values (
    target_tenant_id,
    target_actor_user_id,
    target_operation,
    current_window,
    1
  )
  on conflict (
    tenant_id,
    actor_user_id,
    operation,
    window_started_at
  )
  do update
  set request_count =
    app_private.security_operation_windows.request_count + 1
  returning request_count into current_request_count;

  if current_request_count > max_requests then
    raise exception using
      errcode = 'P0001',
      message = 'security operation rate limit exceeded';
  end if;

  select count(*)::integer
  into current_concurrency
  from app_private.security_operation_leases
  where tenant_id = target_tenant_id
    and operation = target_operation
    and expires_at > clock_timestamp();

  if current_concurrency >= max_concurrency then
    raise exception using
      errcode = 'P0001',
      message = 'security operation concurrency limit exceeded';
  end if;

  select count(*)::integer
  into current_resource_concurrency
  from app_private.security_operation_leases
  where tenant_id = target_tenant_id
    and operation = target_operation
    and resource_key = normalized_resource_key
    and expires_at > clock_timestamp();

  if current_resource_concurrency >= max_resource_concurrency then
    raise exception using
      errcode = 'P0001',
      message = 'security operation resource is already busy';
  end if;

  insert into app_private.security_operation_leases (
    tenant_id,
    actor_user_id,
    operation,
    resource_key,
    expires_at
  )
  values (
    target_tenant_id,
    target_actor_user_id,
    target_operation,
    normalized_resource_key,
    clock_timestamp() + make_interval(secs => lease_seconds)
  )
  returning id into lease_id;

  return lease_id;
end;
$$;

create or replace function app_private.release_security_operation_lease(
  target_lease_id uuid
)
returns void
language sql
security definer
set search_path = public, app_private, pg_temp
as $$
  delete from app_private.security_operation_leases
  where id = target_lease_id;
$$;

create or replace function public.acquire_security_operation_lease(
  target_actor_user_id uuid,
  target_tenant_id uuid,
  target_operation text,
  target_resource_key text
)
returns uuid
language sql
security invoker
set search_path = public, app_private, pg_temp
as $$
  select app_private.acquire_security_operation_lease(
    target_actor_user_id,
    target_tenant_id,
    target_operation,
    target_resource_key
  );
$$;

create or replace function public.release_security_operation_lease(
  target_lease_id uuid
)
returns void
language sql
security invoker
set search_path = public, app_private, pg_temp
as $$
  select app_private.release_security_operation_lease(target_lease_id);
$$;

revoke all on function app_private.acquire_security_operation_lease(
  uuid,
  uuid,
  text,
  text
) from public, anon, authenticated;
revoke all on function app_private.release_security_operation_lease(uuid)
  from public, anon, authenticated;
revoke all on function public.acquire_security_operation_lease(
  uuid,
  uuid,
  text,
  text
) from public, anon, authenticated;
revoke all on function public.release_security_operation_lease(uuid)
  from public, anon, authenticated;

grant usage on schema app_private to service_role;
grant execute on function app_private.acquire_security_operation_lease(
  uuid,
  uuid,
  text,
  text
) to service_role;
grant execute on function app_private.release_security_operation_lease(uuid)
  to service_role;
grant execute on function public.acquire_security_operation_lease(
  uuid,
  uuid,
  text,
  text
) to service_role;
grant execute on function public.release_security_operation_lease(uuid)
  to service_role;
