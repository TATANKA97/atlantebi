alter table public.tenants
  add column default_currency text
    check (default_currency is null or default_currency ~ '^[A-Z]{3}$');

alter table public.db_connections
  add column default_currency text
    check (default_currency is null or default_currency ~ '^[A-Z]{3}$'),
  add column semantic_policy_config jsonb
    check (
      semantic_policy_config is null
      or jsonb_typeof(semantic_policy_config) = 'object'
    ),
  add column resolved_semantic_policy jsonb
    check (
      resolved_semantic_policy is null
      or jsonb_typeof(resolved_semantic_policy) = 'object'
    ),
  add column semantic_policy_hash text
    check (
      semantic_policy_hash is null
      or semantic_policy_hash ~ '^[0-9a-f]{64}$'
    );

alter table public.semantic_layer_versions
  add column base_policy_hash text,
  add column semantic_policy_snapshot jsonb,
  add column quality_report jsonb;

alter table public.semantic_layer_metrics
  add column provenance text,
  add column provenance_detail text,
  add column source_spec_key text;

alter table public.semantic_layer_ambiguities
  add column severity text;

-- Existing test-era artifacts are deliberately made stale. The product does
-- not support them; they remain readable only until the tenant-scoped purge.
update public.semantic_layer_versions
set
  base_policy_hash = repeat('0', 64),
  semantic_policy_snapshot = jsonb_build_object(
    'policy_version', policy_version,
    'policy_hash', repeat('0', 64),
    'default_currency', null,
    'missing_currency_behavior', 'clarification_required',
    'activation_policy', 'manual_review',
    'minimum_eligible_metrics', 1,
    'required_concepts', jsonb_build_array(),
    'required_metric_specs', jsonb_build_array()
  ),
  quality_report = jsonb_build_object(
    'status', 'not_evaluated',
    'issues', jsonb_build_array(),
    'required_specs_count', 0,
    'satisfied_specs_count', 0,
    'compiler_eligible_required_count', 0,
    'rejected_candidates', jsonb_build_array()
  ),
  freshness = 'stale',
  artifact = artifact || jsonb_build_object(
    'base_policy_hash', repeat('0', 64),
    'semantic_policy_snapshot', jsonb_build_object(
      'policy_version', policy_version,
      'policy_hash', repeat('0', 64),
      'default_currency', null,
      'missing_currency_behavior', 'clarification_required',
      'activation_policy', 'manual_review',
      'minimum_eligible_metrics', 1,
      'required_concepts', jsonb_build_array(),
      'required_metric_specs', jsonb_build_array()
    ),
    'quality_report', jsonb_build_object(
      'status', 'not_evaluated',
      'issues', jsonb_build_array(),
      'required_specs_count', 0,
      'satisfied_specs_count', 0,
      'compiler_eligible_required_count', 0,
      'rejected_candidates', jsonb_build_array()
    ),
    'freshness', 'stale'
  );

update public.semantic_layer_metrics
set
  provenance = coalesce(
    payload->>'provenance',
    case status
      when 'ai_proposed' then 'ai'
      when 'human_verified' then 'human'
      else 'system'
    end
  ),
  provenance_detail = coalesce(
    payload->>'provenance_detail',
    case coalesce(
      payload->>'provenance',
      case status
        when 'ai_proposed' then 'ai'
        when 'human_verified' then 'human'
        else 'system'
      end
    )
      when 'ai' then 'ai_generation'
      when 'human' then 'human_override'
      else 'system_seed'
    end
  ),
  source_spec_key = payload->>'source_spec_key';

update public.semantic_layer_ambiguities
set severity = coalesce(payload->>'severity', 'material_ambiguity');

alter table public.semantic_layer_versions
  alter column base_policy_hash set not null,
  alter column semantic_policy_snapshot set not null,
  alter column quality_report set not null,
  add constraint semantic_layer_versions_policy_hash_check
    check (base_policy_hash ~ '^[0-9a-f]{64}$'),
  add constraint semantic_layer_versions_policy_snapshot_check
    check (
      jsonb_typeof(semantic_policy_snapshot) = 'object'
      and semantic_policy_snapshot->>'policy_hash' = base_policy_hash
      and semantic_policy_snapshot->>'policy_version' = policy_version
      and semantic_policy_snapshot->>'missing_currency_behavior'
        in ('clarification_required', 'blocked')
      and semantic_policy_snapshot->>'activation_policy'
        in ('auto_validated', 'manual_review')
      and jsonb_typeof(semantic_policy_snapshot->'required_concepts') = 'array'
      and jsonb_typeof(semantic_policy_snapshot->'required_metric_specs') = 'array'
    ),
  add constraint semantic_layer_versions_quality_report_check
    check (
      jsonb_typeof(quality_report) = 'object'
      and quality_report->>'status' in ('not_evaluated', 'passed', 'blocked')
      and jsonb_typeof(quality_report->'issues') = 'array'
      and jsonb_typeof(quality_report->'rejected_candidates') = 'array'
      and (quality_report->>'required_specs_count')::integer >= 0
      and (quality_report->>'satisfied_specs_count')::integer >= 0
      and (quality_report->>'compiler_eligible_required_count')::integer >= 0
    );

alter table public.semantic_layer_metrics
  alter column provenance set not null,
  alter column provenance_detail set not null,
  add constraint semantic_layer_metrics_provenance_check
    check (provenance in ('system', 'ai', 'human')),
  add constraint semantic_layer_metrics_provenance_detail_check
    check (
      provenance_detail in (
        'system_seed',
        'ai_generation',
        'quality_profile',
        'human_override'
      )
    ),
  add constraint semantic_layer_metrics_source_spec_key_check
    check (
      source_spec_key is null
      or source_spec_key ~ '^[a-z][a-z0-9_.-]{1,99}$'
    ),
  add constraint semantic_layer_metrics_provenance_audit_check
    check (
      (
        provenance = 'system'
        and provenance_detail = 'system_seed'
        and source_spec_key is null
      )
      or (
        provenance = 'system'
        and provenance_detail = 'quality_profile'
        and source_spec_key is not null
      )
      or (
        provenance = 'ai'
        and provenance_detail = 'ai_generation'
        and source_spec_key is null
      )
      or (
        provenance = 'human'
        and provenance_detail = 'human_override'
        and source_spec_key is null
      )
    );

alter table public.semantic_layer_ambiguities
  alter column severity set not null,
  drop constraint if exists semantic_layer_ambiguities_provenance_check,
  add constraint semantic_layer_ambiguities_provenance_check
    check (provenance in ('system', 'ai', 'human')),
  add constraint semantic_layer_ambiguities_severity_check
    check (severity in ('material_ambiguity', 'minor_ambiguity', 'info'));

alter table public.semantic_layer_versions
  drop constraint semantic_layer_versions_artifact_shape_check,
  add constraint semantic_layer_versions_artifact_shape_check
    check (
      jsonb_typeof(artifact) = 'object'
      and artifact->>'contract_version' = 'semantic_layer.v1'
      and artifact->>'base_policy_hash' = base_policy_hash
      and artifact->'semantic_policy_snapshot' = semantic_policy_snapshot
      and artifact->'quality_report' = quality_report
      and jsonb_typeof(artifact->'tables') = 'array'
      and jsonb_typeof(artifact->'columns') = 'array'
      and jsonb_typeof(artifact->'relationships') = 'array'
      and jsonb_typeof(artifact->'business_concepts') = 'array'
      and jsonb_typeof(artifact->'ambiguities') = 'array'
      and jsonb_typeof(artifact->'metrics') = 'array'
      and jsonb_typeof(artifact->'validation_report') = 'object'
    );

create or replace function app_private.project_semantic_policy_artifact()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
declare
  current_policy_hash text;
begin
  if jsonb_typeof(new.artifact) <> 'object'
    or new.artifact->>'base_policy_hash' !~ '^[0-9a-f]{64}$'
    or jsonb_typeof(new.artifact->'semantic_policy_snapshot') <> 'object'
    or jsonb_typeof(new.artifact->'quality_report') <> 'object'
    or new.artifact->'semantic_policy_snapshot'->>'policy_hash'
      <> new.artifact->>'base_policy_hash'
  then
    raise exception 'semantic policy or quality artifact is invalid'
      using errcode = '22023';
  end if;

  new.base_policy_hash := new.artifact->>'base_policy_hash';
  new.semantic_policy_snapshot := new.artifact->'semantic_policy_snapshot';
  new.quality_report := new.artifact->'quality_report';

  if new.status <> 'archived'
    and not (
      current_setting('app.semantic_layer_rpc', true) = 'on'
      and new.freshness = 'stale'
    )
  then
    select connection.semantic_policy_hash
    into current_policy_hash
    from public.db_connections connection
    where connection.tenant_id = new.tenant_id
      and connection.id = new.connection_id;

    if current_policy_hash is null
      or current_policy_hash <> new.base_policy_hash
    then
      raise exception 'semantic policy is stale or not synchronized'
        using errcode = '55000';
    end if;
  end if;

  return new;
end;
$$;

revoke all on function app_private.project_semantic_policy_artifact()
  from public, anon, authenticated, service_role;

create trigger semantic_layer_versions_00_policy_projection
before insert or update on public.semantic_layer_versions
for each row execute function app_private.project_semantic_policy_artifact();

create or replace function app_private.project_semantic_metric_audit()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  new.provenance := new.payload->>'provenance';
  new.provenance_detail := new.payload->>'provenance_detail';
  new.source_spec_key := new.payload->>'source_spec_key';

  if new.provenance is null or new.provenance_detail is null then
    raise exception 'semantic metric provenance detail is required'
      using errcode = '22023';
  end if;

  return new;
end;
$$;

revoke all on function app_private.project_semantic_metric_audit()
  from public, anon, authenticated, service_role;

create trigger semantic_layer_metrics_00_audit_projection
before insert or update on public.semantic_layer_metrics
for each row execute function app_private.project_semantic_metric_audit();

create or replace function app_private.project_semantic_ambiguity_severity()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  new.severity := new.payload->>'severity';
  if new.severity is null then
    raise exception 'semantic ambiguity severity is required'
      using errcode = '22023';
  end if;
  return new;
end;
$$;

revoke all on function app_private.project_semantic_ambiguity_severity()
  from public, anon, authenticated, service_role;

create trigger semantic_layer_ambiguities_00_severity_projection
before insert or update on public.semantic_layer_ambiguities
for each row execute function app_private.project_semantic_ambiguity_severity();

create or replace function app_private.semantic_layer_effective_freshness(
  target_semantic_version_id uuid
)
returns public.semantic_layer_freshness
language sql
stable
set search_path = public, pg_temp
as $$
  select case
    when version.base_graph_hash = (
      select graph.graph_hash
      from public.queryability_graph_derivations derivation
      join public.queryability_graph_versions graph
        on graph.tenant_id = derivation.tenant_id
       and graph.connection_id = derivation.connection_id
       and graph.id = derivation.graph_version_id
      where derivation.tenant_id = version.tenant_id
        and derivation.connection_id = version.connection_id
      order by derivation.created_at desc, derivation.graph_version_id desc
      limit 1
    )
    and version.base_policy_hash = (
      select connection.semantic_policy_hash
      from public.db_connections connection
      where connection.tenant_id = version.tenant_id
        and connection.id = version.connection_id
    )
    then 'fresh'::public.semantic_layer_freshness
    else 'stale'::public.semantic_layer_freshness
  end
  from public.semantic_layer_versions version
  where version.id = target_semantic_version_id;
$$;

revoke all on function app_private.semantic_layer_effective_freshness(uuid)
  from public, anon, authenticated;
grant execute on function app_private.semantic_layer_effective_freshness(uuid)
  to service_role;

create or replace function app_private.enforce_semantic_activation_quality()
returns trigger
language plpgsql
set search_path = public, app_private, pg_temp
as $$
declare
  eligible_metric_count integer;
  required_activation_spec_count integer;
begin
  if new.status = 'active' and old.status is distinct from 'active' then
    select count(*)::integer
    into eligible_metric_count
    from public.semantic_layer_metrics metric
    where metric.tenant_id = new.tenant_id
      and metric.semantic_version_id = new.id
      and metric.enabled
      and metric.compiler_eligibility in (
        'eligible',
        'eligible_with_disclosure'
      );

    select count(*)::integer
    into required_activation_spec_count
    from jsonb_array_elements(
      new.semantic_policy_snapshot->'required_metric_specs'
    ) spec
    where (spec->>'required_for_activation')::boolean;

    if new.quality_report->>'status' <> 'passed'
      or new.validation_report->>'status' not in ('valid', 'valid_with_warnings')
      or jsonb_array_length(new.validation_report->'blocking_errors') <> 0
      or app_private.semantic_layer_effective_freshness(new.id) <> 'fresh'
      or (new.quality_report->>'satisfied_specs_count')::integer
        <> (new.quality_report->>'required_specs_count')::integer
      or (new.quality_report->>'compiler_eligible_required_count')::integer
        < required_activation_spec_count
      or eligible_metric_count < greatest(
        1,
        (new.semantic_policy_snapshot->>'minimum_eligible_metrics')::integer
      )
    then
      raise exception 'semantic version failed the activation quality gate'
        using errcode = '55000';
    end if;
  end if;

  return new;
end;
$$;

revoke all on function app_private.enforce_semantic_activation_quality()
  from public, anon, authenticated, service_role;

create trigger semantic_layer_versions_10_activation_quality
before update on public.semantic_layer_versions
for each row execute function app_private.enforce_semantic_activation_quality();

create or replace function app_private.mark_semantic_versions_policy_stale(
  target_tenant_id uuid,
  target_connection_id uuid
)
returns void
language plpgsql
set search_path = public, pg_temp
as $$
begin
  perform set_config('app.semantic_layer_rpc', 'on', true);
  update public.semantic_layer_versions
  set
    freshness = 'stale',
    artifact = jsonb_set(artifact, '{freshness}', '"stale"', false),
    updated_at = statement_timestamp()
  where tenant_id = target_tenant_id
    and connection_id = target_connection_id
    and status <> 'archived';
  perform set_config('app.semantic_layer_rpc', 'off', true);
end;
$$;

revoke all on function app_private.mark_semantic_versions_policy_stale(uuid, uuid)
  from public, anon, authenticated, service_role;

create or replace function app_private.update_semantic_policy_settings(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_default_currency text,
  target_policy_config jsonb,
  update_policy_config boolean
)
returns void
language plpgsql
security definer
set search_path = public, app_private, pg_temp
as $$
declare
  tenant_row public.tenants%rowtype;
  affected_connections integer;
begin
  if not app_private.is_semantic_layer_admin(target_tenant_id, actor_user_id) then
    raise exception 'semantic layer owner or admin role required'
      using errcode = '42501';
  end if;
  if target_default_currency is not null
    and target_default_currency !~ '^[A-Z]{3}$'
  then
    raise exception 'default currency must be a three-letter ISO code'
      using errcode = '22023';
  end if;
  if update_policy_config and (
    target_policy_config is null
    or jsonb_typeof(target_policy_config) <> 'object'
    or jsonb_typeof(target_policy_config->'required_concepts') <> 'array'
    or jsonb_typeof(target_policy_config->'required_metric_specs') <> 'array'
  ) then
    raise exception 'semantic policy config is invalid'
      using errcode = '22023';
  end if;

  select * into tenant_row
  from public.tenants tenant
  where tenant.id = target_tenant_id;

  if update_policy_config
    and jsonb_array_length(target_policy_config->'required_metric_specs') > 0
    and not (
      tenant_row.plan = 'enterprise'
      or tenant_row.settings->>'environment' in ('demo', 'test')
      or tenant_row.slug ~* '(^|[-_])(demo|test)([-_]|$)'
      or tenant_row.name ~* '(^|[-_[:space:]])(demo|test)([-_[:space:]]|$)'
      or tenant_row.settings->>'allow_stable_key_semantic_profiles' = 'true'
    )
  then
    raise exception 'stable-key semantic profiles require demo, test, or enterprise policy'
      using errcode = '42501';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(target_connection_id::text, 0));
  update public.db_connections
  set
    default_currency = target_default_currency,
    semantic_policy_config = case
      when update_policy_config then target_policy_config
      else semantic_policy_config
    end,
    resolved_semantic_policy = null,
    semantic_policy_hash = null,
    updated_at = statement_timestamp()
  where tenant_id = target_tenant_id
    and id = target_connection_id;
  get diagnostics affected_connections = row_count;
  if affected_connections = 0 then
    raise exception 'database connection not found'
      using errcode = 'P0002';
  end if;

  perform app_private.mark_semantic_versions_policy_stale(
    target_tenant_id,
    target_connection_id
  );

  insert into public.audit_logs (
    tenant_id,
    actor_user_id,
    action,
    subject_type,
    subject_id,
    metadata
  ) values (
    target_tenant_id,
    actor_user_id,
    'semantic_policy.settings_updated',
    'db_connection',
    target_connection_id,
    jsonb_build_object(
      'default_currency', target_default_currency,
      'policy_config_updated', update_policy_config
    )
  );
end;
$$;

revoke all on function app_private.update_semantic_policy_settings(
  uuid, uuid, uuid, text, jsonb, boolean
) from public, anon, authenticated;
grant execute on function app_private.update_semantic_policy_settings(
  uuid, uuid, uuid, text, jsonb, boolean
) to service_role;

create or replace function public.update_semantic_policy_settings(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_default_currency text,
  target_policy_config jsonb,
  update_policy_config boolean
)
returns void
language sql
set search_path = public, app_private, pg_temp
as $$
  select app_private.update_semantic_policy_settings(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    target_default_currency,
    target_policy_config,
    update_policy_config
  );
$$;

revoke all on function public.update_semantic_policy_settings(
  uuid, uuid, uuid, text, jsonb, boolean
) from public, anon, authenticated;
grant execute on function public.update_semantic_policy_settings(
  uuid, uuid, uuid, text, jsonb, boolean
) to service_role;

create or replace function app_private.save_resolved_semantic_policy(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_policy jsonb
)
returns text
language plpgsql
security definer
set search_path = public, app_private, pg_temp
as $$
declare
  expected_currency text;
  previous_hash text;
  target_hash text;
begin
  if not app_private.is_semantic_layer_admin(target_tenant_id, actor_user_id) then
    raise exception 'semantic layer owner or admin role required'
      using errcode = '42501';
  end if;
  if jsonb_typeof(target_policy) <> 'object'
    or target_policy->>'policy_hash' !~ '^[0-9a-f]{64}$'
    or target_policy->>'missing_currency_behavior'
      not in ('clarification_required', 'blocked')
    or target_policy->>'activation_policy'
      not in ('auto_validated', 'manual_review')
    or jsonb_typeof(target_policy->'required_concepts') <> 'array'
    or jsonb_typeof(target_policy->'required_metric_specs') <> 'array'
  then
    raise exception 'resolved semantic policy is invalid'
      using errcode = '22023';
  end if;

  select
    coalesce(connection.default_currency, tenant.default_currency),
    connection.semantic_policy_hash
  into expected_currency, previous_hash
  from public.db_connections connection
  join public.tenants tenant on tenant.id = connection.tenant_id
  where connection.tenant_id = target_tenant_id
    and connection.id = target_connection_id
  for update of connection;

  if not found then
    raise exception 'database connection not found'
      using errcode = 'P0002';
  end if;
  if target_policy->>'default_currency' is distinct from expected_currency then
    raise exception 'resolved semantic policy currency does not match tenant policy'
      using errcode = '22023';
  end if;

  target_hash := target_policy->>'policy_hash';
  update public.db_connections
  set
    resolved_semantic_policy = target_policy,
    semantic_policy_hash = target_hash,
    updated_at = statement_timestamp()
  where tenant_id = target_tenant_id
    and id = target_connection_id;

  if previous_hash is distinct from target_hash then
    perform app_private.mark_semantic_versions_policy_stale(
      target_tenant_id,
      target_connection_id
    );
    insert into public.audit_logs (
      tenant_id,
      actor_user_id,
      action,
      subject_type,
      subject_id,
      metadata
    ) values (
      target_tenant_id,
      actor_user_id,
      'semantic_policy.resolved',
      'db_connection',
      target_connection_id,
      jsonb_build_object(
        'previous_policy_hash', previous_hash,
        'policy_hash', target_hash
      )
    );
  end if;

  return target_hash;
end;
$$;

revoke all on function app_private.save_resolved_semantic_policy(
  uuid, uuid, uuid, jsonb
) from public, anon, authenticated;
grant execute on function app_private.save_resolved_semantic_policy(
  uuid, uuid, uuid, jsonb
) to service_role;

create or replace function public.save_resolved_semantic_policy(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_policy jsonb
)
returns text
language sql
set search_path = public, app_private, pg_temp
as $$
  select app_private.save_resolved_semantic_policy(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    target_policy
  );
$$;

revoke all on function public.save_resolved_semantic_policy(
  uuid, uuid, uuid, jsonb
) from public, anon, authenticated;
grant execute on function public.save_resolved_semantic_policy(
  uuid, uuid, uuid, jsonb
) to service_role;

create or replace function app_private.update_tenant_default_currency(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_default_currency text
)
returns void
language plpgsql
security definer
set search_path = public, app_private, pg_temp
as $$
declare
  connection record;
begin
  if not app_private.is_semantic_layer_admin(target_tenant_id, actor_user_id) then
    raise exception 'semantic layer owner or admin role required'
      using errcode = '42501';
  end if;
  if target_default_currency is not null
    and target_default_currency !~ '^[A-Z]{3}$'
  then
    raise exception 'default currency must be a three-letter ISO code'
      using errcode = '22023';
  end if;

  update public.tenants
  set
    default_currency = target_default_currency,
    updated_at = statement_timestamp()
  where id = target_tenant_id;
  if not found then
    raise exception 'tenant not found' using errcode = 'P0002';
  end if;

  for connection in
    update public.db_connections
    set
      resolved_semantic_policy = null,
      semantic_policy_hash = null,
      updated_at = statement_timestamp()
    where tenant_id = target_tenant_id
      and default_currency is null
    returning id
  loop
    perform app_private.mark_semantic_versions_policy_stale(
      target_tenant_id,
      connection.id
    );
  end loop;

  insert into public.audit_logs (
    tenant_id,
    actor_user_id,
    action,
    subject_type,
    subject_id,
    metadata
  ) values (
    target_tenant_id,
    actor_user_id,
    'semantic_policy.tenant_currency_updated',
    'tenant',
    target_tenant_id,
    jsonb_build_object('default_currency', target_default_currency)
  );
end;
$$;

revoke all on function app_private.update_tenant_default_currency(
  uuid, uuid, text
) from public, anon, authenticated;
grant execute on function app_private.update_tenant_default_currency(
  uuid, uuid, text
) to service_role;

create or replace function public.update_tenant_default_currency(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_default_currency text
)
returns void
language sql
set search_path = public, app_private, pg_temp
as $$
  select app_private.update_tenant_default_currency(
    actor_user_id,
    target_tenant_id,
    target_default_currency
  );
$$;

revoke all on function public.update_tenant_default_currency(uuid, uuid, text)
  from public, anon, authenticated;
grant execute on function public.update_tenant_default_currency(uuid, uuid, text)
  to service_role;

create or replace function app_private.purge_demo_semantic_versions(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  confirmation text
)
returns integer
language plpgsql
security definer
set search_path = public, app_private, pg_temp
as $$
declare
  tenant_row public.tenants%rowtype;
  connection_database text;
  deleted_count integer;
begin
  if confirmation <> 'AdventureWorksLT' then
    raise exception 'semantic purge confirmation is invalid'
      using errcode = '22023';
  end if;
  if not app_private.is_semantic_layer_admin(target_tenant_id, actor_user_id) then
    raise exception 'semantic layer owner or admin role required'
      using errcode = '42501';
  end if;

  select * into tenant_row
  from public.tenants tenant
  where tenant.id = target_tenant_id;
  if not (
    tenant_row.settings->>'environment' in ('demo', 'test')
    or tenant_row.slug ~* '(^|[-_])(demo|test)([-_]|$)'
    or tenant_row.name ~* '(^|[-_[:space:]])(demo|test)([-_[:space:]]|$)'
  ) then
    raise exception 'semantic purge is restricted to demo or test tenants'
      using errcode = '42501';
  end if;

  select connection.database_name
  into connection_database
  from public.db_connections connection
  where connection.tenant_id = target_tenant_id
    and connection.id = target_connection_id
  for update;
  if connection_database is distinct from 'AdventureWorksLT' then
    raise exception 'AdventureWorksLT connection not found'
      using errcode = 'P0002';
  end if;

  update public.north_star_benchmarks
  set
    semantic_version_id = null,
    metric_key = null,
    updated_by = actor_user_id,
    updated_at = statement_timestamp()
  where tenant_id = target_tenant_id
    and connection_id = target_connection_id
    and semantic_version_id is not null;

  perform set_config('app.semantic_layer_rpc', 'on', true);
  delete from public.semantic_layer_versions
  where tenant_id = target_tenant_id
    and connection_id = target_connection_id;
  get diagnostics deleted_count = row_count;
  perform set_config('app.semantic_layer_rpc', 'off', true);

  insert into public.audit_logs (
    tenant_id,
    actor_user_id,
    action,
    subject_type,
    subject_id,
    metadata
  ) values (
    target_tenant_id,
    actor_user_id,
    'semantic_layer.demo_versions_purged',
    'db_connection',
    target_connection_id,
    jsonb_build_object('deleted_versions', deleted_count)
  );

  return deleted_count;
end;
$$;

revoke all on function app_private.purge_demo_semantic_versions(
  uuid, uuid, uuid, text
) from public, anon, authenticated;
grant execute on function app_private.purge_demo_semantic_versions(
  uuid, uuid, uuid, text
) to service_role;

create or replace function public.purge_demo_semantic_versions(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  confirmation text
)
returns integer
language sql
set search_path = public, app_private, pg_temp
as $$
  select app_private.purge_demo_semantic_versions(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    confirmation
  );
$$;

revoke all on function public.purge_demo_semantic_versions(
  uuid, uuid, uuid, text
) from public, anon, authenticated;
grant execute on function public.purge_demo_semantic_versions(
  uuid, uuid, uuid, text
) to service_role;

notify pgrst, 'reload schema';
