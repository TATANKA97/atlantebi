alter table public.ai_provider_settings
  drop constraint if exists ai_provider_settings_model_registry;

alter table public.ai_provider_settings
  add constraint ai_provider_settings_model_registry check (
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
  );

do $$
begin
  if not exists (
    select 1
    from pg_constraint c
    join pg_class r on r.oid = c.conrelid
    join pg_namespace n on n.oid = r.relnamespace
    where n.nspname = 'public'
      and r.relname = 'ai_provider_settings'
      and c.conname = 'ai_provider_settings_secret_ref_binding'
  ) then
    alter table public.ai_provider_settings
      add constraint ai_provider_settings_secret_ref_binding check (
        secret_ref ~ (
          '^gcp-secret-manager://projects/[^/]+/secrets/atlantebi-' ||
          tenant_id::text || '-' || id::text || '-' || provider::text ||
          '-ai-key(?:/versions/[^/]+)?$'
        )
      );
  end if;
end;
$$;

revoke all privileges on table public.ai_provider_settings
  from public, anon, authenticated, service_role;
grant select on table public.ai_provider_settings
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
