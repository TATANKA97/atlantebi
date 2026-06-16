begin;

create extension if not exists pgtap with schema extensions;

select plan(11);

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

truncate table semantic_workspace_leases;

insert into semantic_workspace_leases
select public.acquire_security_operation_lease(
  '10000000-0000-4000-8000-000000000041',
  '20000000-0000-4000-8000-000000000041',
  'ai_provider_setting',
  'openai:gpt-5.5'
);

select is(
  (select count(*)::integer from semantic_workspace_leases),
  1,
  'owner can acquire an AI provider setting lease'
);

select throws_ok(
  $$
    select public.acquire_security_operation_lease(
      '10000000-0000-4000-8000-000000000042',
      '20000000-0000-4000-8000-000000000041',
      'ai_provider_setting',
      'anthropic:claude-opus-4-8'
    )
  $$,
  '42501',
  'actor cannot run this security operation',
  'editor cannot configure tenant AI provider settings'
);

select throws_ok(
  $$
    insert into public.ai_provider_settings (
      tenant_id,
      provider,
      model_id,
      display_name,
      thinking,
      secret_ref,
      created_by,
      updated_by
    )
    values (
      '20000000-0000-4000-8000-000000000041',
      'anthropic',
      'claude-sonnet-4-6',
      'Invalid Sonnet',
      '{"type":"anthropic_adaptive","enabled":true,"effort":"xhigh"}'::jsonb,
      'projects/demo/secrets/invalid',
      '10000000-0000-4000-8000-000000000041',
      '10000000-0000-4000-8000-000000000041'
    )
  $$,
  '23514',
  null,
  'Sonnet 4.6 cannot use Anthropic xhigh effort'
);

select is(
  public.create_ai_provider_setting(
    '10000000-0000-4000-8000-000000000041',
    '20000000-0000-4000-8000-000000000041',
    '30000000-0000-4000-8000-000000000051',
    'openai',
    'gpt-5.5',
    'OpenAI default',
    '{"type":"openai_reasoning","effort":"high"}'::jsonb,
    'gcp-secret-manager://projects/demo/secrets/atlantebi-20000000-0000-4000-8000-000000000041-30000000-0000-4000-8000-000000000051-openai-ai-key',
    true
  ),
  '30000000-0000-4000-8000-000000000051'::uuid,
  'service RPC creates a default AI provider setting'
);

select is(
  public.create_ai_provider_setting(
    '10000000-0000-4000-8000-000000000041',
    '20000000-0000-4000-8000-000000000041',
    '30000000-0000-4000-8000-000000000052',
    'anthropic',
    'claude-opus-4-8',
    'Anthropic default',
    '{"type":"anthropic_adaptive","enabled":true,"effort":"xhigh"}'::jsonb,
    'gcp-secret-manager://projects/demo/secrets/atlantebi-20000000-0000-4000-8000-000000000041-30000000-0000-4000-8000-000000000052-anthropic-ai-key',
    true
  ),
  '30000000-0000-4000-8000-000000000052'::uuid,
  'service RPC atomically replaces the default AI provider setting'
);

select throws_ok(
  $$
    select public.create_ai_provider_setting(
      '10000000-0000-4000-8000-000000000041',
      '20000000-0000-4000-8000-000000000041',
      '30000000-0000-4000-8000-000000000053',
      'openai',
      'gpt-5.5',
      'Unbound OpenAI',
      '{"type":"openai_reasoning","effort":"medium"}'::jsonb,
      'gcp-secret-manager://projects/demo/secrets/unbound-secret',
      true
    )
  $$,
  '22023',
  'AI provider secret_ref is not bound to this setting',
  'service RPC rejects unbound AI provider secret references'
);

select is(
  (
    select count(*)::integer
    from public.ai_provider_settings
    where tenant_id = '20000000-0000-4000-8000-000000000041'
      and is_default
      and id = '30000000-0000-4000-8000-000000000052'
  ),
  1,
  'only the newest default AI provider remains active'
);

select * from finish();
rollback;
