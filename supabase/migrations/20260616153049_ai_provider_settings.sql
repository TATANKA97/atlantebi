create type public.ai_provider as enum (
  'openai',
  'anthropic'
);

create type public.ai_provider_setting_status as enum (
  'ready',
  'disabled',
  'failed'
);

create table public.ai_provider_settings (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  provider public.ai_provider not null,
  model_id text not null check (length(model_id) between 1 and 255),
  display_name text not null check (length(display_name) between 1 and 160),
  thinking jsonb not null,
  secret_ref text not null check (length(secret_ref) between 1 and 2000),
  status public.ai_provider_setting_status not null default 'ready',
  is_default boolean not null default false,
  last_test_status text check (
    last_test_status is null or last_test_status in ('ok', 'failed')
  ),
  last_tested_at timestamptz,
  created_by uuid references auth.users(id) on delete set null,
  updated_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ai_provider_settings_model_registry check (
    (
      provider = 'openai'
      and model_id = 'gpt-5.5'
      and thinking->>'type' = 'openai_reasoning'
      and thinking->>'effort' in ('none', 'low', 'medium', 'high', 'xhigh')
    )
    or (
      provider = 'anthropic'
      and model_id in ('claude-sonnet-4-6', 'claude-opus-4-8')
      and thinking->>'type' = 'anthropic_adaptive'
      and jsonb_typeof(thinking->'enabled') = 'boolean'
      and thinking->>'effort' in ('low', 'medium', 'high', 'xhigh', 'max')
      and not (
        model_id = 'claude-sonnet-4-6'
        and thinking->>'effort' in ('xhigh', 'max')
      )
      and not (
        (thinking->>'enabled')::boolean = false
        and thinking->>'effort' <> 'medium'
      )
    )
  ),
  constraint ai_provider_settings_secret_ref_binding check (
    secret_ref ~ (
      '^gcp-secret-manager://projects/[^/]+/secrets/atlantebi-' ||
      tenant_id::text || '-' || id::text || '-' || provider::text ||
      '-ai-key(?:/versions/[^/]+)?$'
    )
  )
);

create index ai_provider_settings_tenant_idx
  on public.ai_provider_settings (tenant_id, status, is_default);

create unique index ai_provider_settings_one_default_ready_idx
  on public.ai_provider_settings (tenant_id)
  where is_default and status = 'ready';

alter table public.ai_provider_settings enable row level security;
alter table public.ai_provider_settings force row level security;

revoke all privileges on table public.ai_provider_settings
  from public, anon, authenticated, service_role;
grant select on table public.ai_provider_settings
  to service_role;

create or replace function public.touch_ai_provider_settings_updated_at()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  new.updated_at := statement_timestamp();
  return new;
end;
$$;

revoke all on function public.touch_ai_provider_settings_updated_at()
  from public, anon, authenticated, service_role;

create trigger touch_ai_provider_settings_updated_at
before update on public.ai_provider_settings
for each row execute function public.touch_ai_provider_settings_updated_at();

create or replace view public.ai_provider_setting_summaries
as
select
  id,
  tenant_id,
  provider,
  model_id,
  display_name,
  thinking,
  status,
  is_default,
  last_test_status,
  last_tested_at,
  created_at,
  updated_at
from public.ai_provider_settings;

revoke all privileges on table public.ai_provider_setting_summaries
  from public, anon, authenticated, service_role;
grant select on table public.ai_provider_setting_summaries
  to service_role;

create or replace function app_private.create_ai_provider_setting(
  target_actor_user_id uuid,
  target_tenant_id uuid,
  target_setting_id uuid,
  target_provider public.ai_provider,
  target_model_id text,
  target_display_name text,
  target_thinking jsonb,
  target_secret_ref text,
  target_is_default boolean
)
returns uuid
language plpgsql
security definer
set search_path = public, app_private, pg_temp
as $$
begin
  if target_actor_user_id is null
    or target_tenant_id is null
    or target_setting_id is null
    or target_provider is null
    or nullif(btrim(target_model_id), '') is null
    or nullif(btrim(target_display_name), '') is null
    or target_thinking is null
    or nullif(btrim(target_secret_ref), '') is null
  then
    raise exception using
      errcode = '22023',
      message = 'invalid AI provider setting request';
  end if;

  if not exists (
    select 1
    from public.tenant_memberships tm
    where tm.tenant_id = target_tenant_id
      and tm.user_id = target_actor_user_id
      and tm.status = 'active'
      and tm.role = any (array['owner', 'admin']::public.tenant_role[])
  ) then
    raise exception using
      errcode = '42501',
      message = 'AI provider settings require owner or admin role';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended(target_tenant_id::text || ':ai_provider_settings', 0)
  );

  if btrim(target_secret_ref) !~ (
    '^gcp-secret-manager://projects/[^/]+/secrets/atlantebi-' ||
    target_tenant_id::text || '-' || target_setting_id::text || '-' ||
    target_provider::text || '-ai-key(?:/versions/[^/]+)?$'
  ) then
    raise exception using
      errcode = '22023',
      message = 'AI provider secret_ref is not bound to this setting';
  end if;

  if target_is_default then
    update public.ai_provider_settings
    set
      is_default = false,
      updated_by = target_actor_user_id,
      updated_at = now()
    where tenant_id = target_tenant_id
      and is_default;
  end if;

  insert into public.ai_provider_settings (
    id,
    tenant_id,
    provider,
    model_id,
    display_name,
    thinking,
    secret_ref,
    status,
    is_default,
    last_test_status,
    last_tested_at,
    created_by,
    updated_by
  )
  values (
    target_setting_id,
    target_tenant_id,
    target_provider,
    btrim(target_model_id),
    btrim(target_display_name),
    target_thinking,
    btrim(target_secret_ref),
    'ready',
    target_is_default,
    null,
    null,
    target_actor_user_id,
    target_actor_user_id
  );

  return target_setting_id;
end;
$$;

revoke all on function app_private.create_ai_provider_setting(
  uuid,
  uuid,
  uuid,
  public.ai_provider,
  text,
  text,
  jsonb,
  text,
  boolean
) from public, anon, authenticated, service_role;

grant execute on function app_private.create_ai_provider_setting(
  uuid,
  uuid,
  uuid,
  public.ai_provider,
  text,
  text,
  jsonb,
  text,
  boolean
) to service_role;

create or replace function public.create_ai_provider_setting(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_setting_id uuid,
  target_provider public.ai_provider,
  target_model_id text,
  target_display_name text,
  target_thinking jsonb,
  target_secret_ref text,
  target_is_default boolean
)
returns uuid
language sql
security invoker
set search_path = public, pg_temp
as $$
  select app_private.create_ai_provider_setting(
    actor_user_id,
    target_tenant_id,
    target_setting_id,
    target_provider,
    target_model_id,
    target_display_name,
    target_thinking,
    target_secret_ref,
    target_is_default
  );
$$;

revoke all on function public.create_ai_provider_setting(
  uuid,
  uuid,
  uuid,
  public.ai_provider,
  text,
  text,
  jsonb,
  text,
  boolean
) from public, anon, authenticated, service_role;

grant execute on function public.create_ai_provider_setting(
  uuid,
  uuid,
  uuid,
  public.ai_provider,
  text,
  text,
  jsonb,
  text,
  boolean
) to service_role;

alter table app_private.security_operation_leases
  drop constraint if exists security_operation_leases_operation_check;

alter table app_private.security_operation_leases
  add constraint security_operation_leases_operation_check
  check (
    operation in (
      'connection_test',
      'schema_introspection',
      'semantic_generation',
      'ai_provider_setting'
    )
  );

alter table app_private.security_operation_windows
  drop constraint if exists security_operation_windows_operation_check;

alter table app_private.security_operation_windows
  add constraint security_operation_windows_operation_check
  check (
    operation in (
      'connection_test',
      'schema_introspection',
      'semantic_generation',
      'ai_provider_setting'
    )
  );

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
      and (
        (
          target_operation in (
            'semantic_generation',
            'ai_provider_setting'
          )
          and tm.role = any (
            array['owner', 'admin']::public.tenant_role[]
          )
        )
        or (
          target_operation not in (
            'semantic_generation',
            'ai_provider_setting'
          )
          and tm.role = any (
            array['owner', 'admin', 'editor']::public.tenant_role[]
          )
        )
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
    when 'semantic_generation' then
      max_concurrency := 2;
      max_resource_concurrency := 1;
      max_requests := 10;
      window_seconds := 3600;
      lease_seconds := 180;
    when 'ai_provider_setting' then
      max_concurrency := 2;
      max_resource_concurrency := 1;
      max_requests := 10;
      window_seconds := 3600;
      lease_seconds := 60;
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

alter table public.semantic_generation_runs
  add column if not exists thinking_config jsonb;

create or replace function app_private.persist_semantic_layer_version(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_graph_version_id uuid,
  target_artifact jsonb,
  target_generation_provenance jsonb default null,
  target_semantic_version_id uuid default null,
  expected_revision integer default null,
  target_rebased_from_version_id uuid default null,
  target_activation_policy text default 'auto_validated'
)
returns table (
  semantic_version_id uuid,
  semantic_version_number integer,
  revision integer,
  status public.semantic_layer_version_status
)
language plpgsql
security definer
set search_path = public, app_private, pg_temp
as $$
declare
  persisted record;
begin
  select *
  into persisted
  from app_private.persist_semantic_layer_version_core(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    target_graph_version_id,
    target_artifact,
    null,
    target_semantic_version_id,
    expected_revision,
    target_rebased_from_version_id,
    target_activation_policy
  );

  if target_generation_provenance is not null then
    if jsonb_typeof(target_generation_provenance) <> 'object'
      or target_generation_provenance->>'provider' not in ('openai', 'anthropic')
      or target_generation_provenance->>'input_hash'
        !~ '^[0-9a-f]{64}$'
      or target_generation_provenance->>'proposal_hash'
        !~ '^[0-9a-f]{64}$'
      or coalesce(target_generation_provenance->>'model_version', '') = ''
      or coalesce(target_generation_provenance->>'prompt_version', '') = ''
      or coalesce(target_generation_provenance->>'response_id', '') = ''
      or coalesce(target_generation_provenance->>'generated_at', '') = ''
    then
      raise exception 'semantic generation provenance is invalid'
        using errcode = '22023';
    end if;

    insert into public.semantic_generation_runs (
      tenant_id,
      connection_id,
      semantic_version_id,
      provider,
      model_version,
      prompt_version,
      input_hash,
      proposal_hash,
      response_id,
      generated_at,
      thinking_config,
      created_by
    )
    values (
      target_tenant_id,
      target_connection_id,
      persisted.semantic_version_id,
      target_generation_provenance->>'provider',
      target_generation_provenance->>'model_version',
      target_generation_provenance->>'prompt_version',
      target_generation_provenance->>'input_hash',
      target_generation_provenance->>'proposal_hash',
      target_generation_provenance->>'response_id',
      (target_generation_provenance->>'generated_at')::timestamptz,
      target_generation_provenance->'thinking_config',
      actor_user_id
    )
    on conflict (tenant_id, connection_id, response_id) do nothing;
  end if;

  return query
  select
    persisted.semantic_version_id::uuid,
    persisted.semantic_version_number::integer,
    persisted.revision::integer,
    persisted.status::public.semantic_layer_version_status;
end;
$$;

revoke all on function app_private.persist_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid,
  jsonb,
  jsonb,
  uuid,
  integer,
  uuid,
  text
) from public, anon, authenticated;
grant execute on function app_private.persist_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid,
  jsonb,
  jsonb,
  uuid,
  integer,
  uuid,
  text
) to service_role;
