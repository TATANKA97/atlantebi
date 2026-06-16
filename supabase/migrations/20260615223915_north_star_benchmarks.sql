create table public.north_star_benchmarks (
  benchmark_key uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  connection_id uuid not null,
  dashboard_id uuid,
  semantic_version_id uuid,
  metric_key uuid,
  name text not null check (length(name) between 1 and 255),
  description text check (description is null or length(description) <= 2000),
  expected_value numeric not null,
  value_type text not null check (
    value_type in ('currency', 'number', 'percentage', 'count')
  ),
  currency text check (currency is null or currency ~ '^[A-Z]{3}$'),
  period_type text not null check (
    period_type in (
      'day',
      'week',
      'month',
      'quarter',
      'year',
      'rolling_12_months',
      'custom'
    )
  ),
  period_start date,
  period_end date,
  tolerance_mode text not null check (
    tolerance_mode in ('percentage', 'absolute', 'range')
  ),
  tolerance_percentage numeric,
  min_value numeric,
  max_value numeric,
  severity text not null check (
    severity in ('low', 'medium', 'high', 'critical')
  ),
  enabled boolean not null default true,
  created_by uuid not null references auth.users(id),
  updated_by uuid not null references auth.users(id),
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  foreign key (tenant_id, connection_id)
    references public.db_connections(tenant_id, id)
    on delete cascade,
  foreign key (tenant_id, dashboard_id)
    references public.dashboards(tenant_id, id)
    on delete set null (dashboard_id),
  foreign key (tenant_id, semantic_version_id)
    references public.semantic_layer_versions(tenant_id, id)
    on delete restrict,
  foreign key (semantic_version_id, metric_key)
    references public.semantic_layer_metrics(semantic_version_id, metric_key)
    on delete restrict,
  check (
    (value_type = 'currency' and currency is not null)
    or (value_type <> 'currency' and currency is null)
  ),
  check (
    (period_type = 'custom' and period_start is not null and period_end is not null)
    or period_type <> 'custom'
  ),
  check (period_start is null or period_end is null or period_start <= period_end),
  check (
    (
      tolerance_mode = 'percentage'
      and tolerance_percentage is not null
      and tolerance_percentage > 0
      and min_value is null
      and max_value is null
    )
    or (
      tolerance_mode in ('absolute', 'range')
      and tolerance_percentage is null
      and min_value is not null
      and max_value is not null
      and min_value <= max_value
    )
  ),
  check (
    (metric_key is null and semantic_version_id is null)
    or (metric_key is not null and semantic_version_id is not null)
  )
);

create index north_star_benchmarks_connection_idx
  on public.north_star_benchmarks (
    tenant_id,
    connection_id,
    enabled,
    created_at desc
  );

create index north_star_benchmarks_metric_idx
  on public.north_star_benchmarks (
    tenant_id,
    semantic_version_id,
    metric_key
  )
  where metric_key is not null;

create index north_star_benchmarks_dashboard_idx
  on public.north_star_benchmarks (tenant_id, dashboard_id)
  where dashboard_id is not null;

create unique index north_star_benchmarks_active_metric_period_unique_idx
  on public.north_star_benchmarks (
    tenant_id,
    connection_id,
    metric_key,
    period_type,
    coalesce(period_start, date '0001-01-01'),
    coalesce(period_end, date '9999-12-31')
  )
  where enabled and metric_key is not null;

alter table public.north_star_benchmarks enable row level security;

revoke all privileges on table public.north_star_benchmarks
  from public, anon, authenticated, service_role;

grant select on table public.north_star_benchmarks to service_role;

create or replace function app_private.resolve_north_star_metric_version(
  target_tenant_id uuid,
  target_connection_id uuid,
  requested_semantic_version_id uuid,
  requested_metric_key uuid
)
returns uuid
language plpgsql
stable
set search_path = public, app_private, pg_temp
as $$
declare
  resolved_semantic_version_id uuid;
begin
  if requested_metric_key is null then
    if requested_semantic_version_id is not null then
      select version.id
      into resolved_semantic_version_id
      from public.semantic_layer_versions version
      where version.tenant_id = target_tenant_id
        and version.connection_id = target_connection_id
        and version.id = requested_semantic_version_id
        and version.status = 'active'
        and app_private.semantic_layer_effective_freshness(version.id) = 'fresh';

      if resolved_semantic_version_id is null then
        raise exception 'active fresh semantic version not found'
          using errcode = '22023';
      end if;
    end if;

    return resolved_semantic_version_id;
  end if;

  if requested_semantic_version_id is not null then
    select version.id
    into resolved_semantic_version_id
    from public.semantic_layer_versions version
    join public.semantic_layer_metrics metric
      on metric.tenant_id = version.tenant_id
     and metric.semantic_version_id = version.id
     and metric.metric_key = requested_metric_key
    where version.tenant_id = target_tenant_id
      and version.connection_id = target_connection_id
      and version.id = requested_semantic_version_id
      and version.status = 'active'
      and app_private.semantic_layer_effective_freshness(version.id) = 'fresh'
      and metric.enabled
      and metric.status in ('ai_proposed', 'human_verified')
      and metric.compiler_eligibility in (
        'eligible',
        'eligible_with_disclosure'
      );
  else
    select version.id
    into resolved_semantic_version_id
    from public.semantic_layer_versions version
    join public.semantic_layer_metrics metric
      on metric.tenant_id = version.tenant_id
     and metric.semantic_version_id = version.id
     and metric.metric_key = requested_metric_key
    where version.tenant_id = target_tenant_id
      and version.connection_id = target_connection_id
      and version.status = 'active'
      and app_private.semantic_layer_effective_freshness(version.id) = 'fresh'
      and metric.enabled
      and metric.status in ('ai_proposed', 'human_verified')
      and metric.compiler_eligibility in (
        'eligible',
        'eligible_with_disclosure'
      )
    order by version.version desc, version.created_at desc
    limit 1;
  end if;

  if resolved_semantic_version_id is null then
    raise exception 'eligible active metric not found for north star benchmark'
      using errcode = '22023';
  end if;

  return resolved_semantic_version_id;
end;
$$;

revoke all on function app_private.resolve_north_star_metric_version(
  uuid,
  uuid,
  uuid,
  uuid
) from public, anon, authenticated, service_role;

create or replace function app_private.assert_north_star_payload_shape(
  benchmark_payload jsonb,
  require_connection_id boolean
)
returns void
language plpgsql
immutable
set search_path = pg_temp
as $$
begin
  if jsonb_typeof(benchmark_payload) <> 'object' then
    raise exception 'north star payload must be an object'
      using errcode = '22023';
  end if;

  if exists (
    select 1
    from jsonb_object_keys(benchmark_payload) as payload_key(key)
    where payload_key.key not in (
      'connection_id',
      'dashboard_id',
      'semantic_version_id',
      'metric_key',
      'name',
      'description',
      'expected_value',
      'value_type',
      'currency',
      'period_type',
      'period_start',
      'period_end',
      'tolerance_mode',
      'tolerance_percentage',
      'min_value',
      'max_value',
      'severity',
      'enabled'
    )
  ) then
    raise exception 'north star payload contains unsupported fields'
      using errcode = '22023';
  end if;

  if require_connection_id
    and coalesce(benchmark_payload->>'connection_id', '') !~
      '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  then
    raise exception 'north star payload connection_id is invalid'
      using errcode = '22023';
  end if;

  if benchmark_payload ? 'dashboard_id'
    and benchmark_payload->>'dashboard_id' is not null
    and benchmark_payload->>'dashboard_id' !~
      '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  then
    raise exception 'north star payload dashboard_id is invalid'
      using errcode = '22023';
  end if;

  if benchmark_payload ? 'semantic_version_id'
    and benchmark_payload->>'semantic_version_id' is not null
    and benchmark_payload->>'semantic_version_id' !~
      '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  then
    raise exception 'north star payload semantic_version_id is invalid'
      using errcode = '22023';
  end if;

  if benchmark_payload ? 'metric_key'
    and benchmark_payload->>'metric_key' is not null
    and benchmark_payload->>'metric_key' !~
      '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  then
    raise exception 'north star payload metric_key is invalid'
      using errcode = '22023';
  end if;

  if jsonb_typeof(benchmark_payload->'name') is distinct from 'string'
    or length(trim(coalesce(benchmark_payload->>'name', ''))) = 0
    or length(trim(benchmark_payload->>'name')) > 255
  then
    raise exception 'north star name is invalid'
      using errcode = '22023';
  end if;

  if benchmark_payload ? 'description'
    and benchmark_payload->>'description' is not null
    and (
      jsonb_typeof(benchmark_payload->'description') <> 'string'
      or length(benchmark_payload->>'description') > 2000
    )
  then
    raise exception 'north star description is invalid'
      using errcode = '22023';
  end if;

  if jsonb_typeof(benchmark_payload->'expected_value') is distinct from 'number'
  then
    raise exception 'north star expected_value is invalid'
      using errcode = '22023';
  end if;

  if jsonb_typeof(benchmark_payload->'value_type') is distinct from 'string'
    or benchmark_payload->>'value_type' not in (
    'currency',
    'number',
    'percentage',
    'count'
  ) then
    raise exception 'north star value_type is invalid'
      using errcode = '22023';
  end if;

  if benchmark_payload ? 'currency'
    and benchmark_payload->>'currency' is not null
    and (
      jsonb_typeof(benchmark_payload->'currency') <> 'string'
      or benchmark_payload->>'currency' !~ '^[A-Z]{3}$'
    )
  then
    raise exception 'north star currency is invalid'
      using errcode = '22023';
  end if;

  if jsonb_typeof(benchmark_payload->'period_type') is distinct from 'string'
    or benchmark_payload->>'period_type' not in (
    'day',
    'week',
    'month',
    'quarter',
    'year',
    'rolling_12_months',
    'custom'
  ) then
    raise exception 'north star period_type is invalid'
      using errcode = '22023';
  end if;

  if benchmark_payload ? 'period_start'
    and benchmark_payload->>'period_start' is not null
    and (
      jsonb_typeof(benchmark_payload->'period_start') <> 'string'
      or benchmark_payload->>'period_start' !~ '^\d{4}-\d{2}-\d{2}$'
    )
  then
    raise exception 'north star period_start is invalid'
      using errcode = '22023';
  end if;

  if benchmark_payload ? 'period_end'
    and benchmark_payload->>'period_end' is not null
    and (
      jsonb_typeof(benchmark_payload->'period_end') <> 'string'
      or benchmark_payload->>'period_end' !~ '^\d{4}-\d{2}-\d{2}$'
    )
  then
    raise exception 'north star period_end is invalid'
      using errcode = '22023';
  end if;

  if jsonb_typeof(benchmark_payload->'tolerance_mode') is distinct from 'string'
    or benchmark_payload->>'tolerance_mode' not in (
    'percentage',
    'absolute',
    'range'
  ) then
    raise exception 'north star tolerance_mode is invalid'
      using errcode = '22023';
  end if;

  if benchmark_payload ? 'tolerance_percentage'
    and benchmark_payload->>'tolerance_percentage' is not null
    and jsonb_typeof(benchmark_payload->'tolerance_percentage') <> 'number'
  then
    raise exception 'north star tolerance_percentage is invalid'
      using errcode = '22023';
  end if;

  if benchmark_payload ? 'min_value'
    and benchmark_payload->>'min_value' is not null
    and jsonb_typeof(benchmark_payload->'min_value') <> 'number'
  then
    raise exception 'north star min_value is invalid'
      using errcode = '22023';
  end if;

  if benchmark_payload ? 'max_value'
    and benchmark_payload->>'max_value' is not null
    and jsonb_typeof(benchmark_payload->'max_value') <> 'number'
  then
    raise exception 'north star max_value is invalid'
      using errcode = '22023';
  end if;

  if jsonb_typeof(benchmark_payload->'severity') is distinct from 'string'
    or benchmark_payload->>'severity' not in (
    'low',
    'medium',
    'high',
    'critical'
  ) then
    raise exception 'north star severity is invalid'
      using errcode = '22023';
  end if;

  if benchmark_payload ? 'enabled'
    and jsonb_typeof(benchmark_payload->'enabled') <> 'boolean'
  then
    raise exception 'north star enabled is invalid'
      using errcode = '22023';
  end if;
end;
$$;

revoke all on function app_private.assert_north_star_payload_shape(
  jsonb,
  boolean
) from public, anon, authenticated, service_role;

create or replace function app_private.create_north_star_benchmark(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  benchmark_payload jsonb
)
returns uuid
language plpgsql
set search_path = public, app_private, pg_temp
as $$
declare
  created_benchmark_key uuid;
  resolved_semantic_version_id uuid;
  payload_connection_id uuid;
  payload_dashboard_id uuid;
  payload_metric_key uuid;
  payload_semantic_version_id uuid;
begin
  if not app_private.is_semantic_layer_admin(
    target_tenant_id,
    actor_user_id
  ) then
    raise exception 'north star owner or admin role required'
      using errcode = '42501';
  end if;

  perform app_private.assert_north_star_payload_shape(
    benchmark_payload,
    true
  );

  payload_connection_id := (benchmark_payload->>'connection_id')::uuid;
  if payload_connection_id <> target_connection_id then
    raise exception 'north star connection mismatch'
      using errcode = '22023';
  end if;

  payload_dashboard_id := nullif(benchmark_payload->>'dashboard_id', '')::uuid;
  payload_metric_key := nullif(benchmark_payload->>'metric_key', '')::uuid;
  payload_semantic_version_id :=
    nullif(benchmark_payload->>'semantic_version_id', '')::uuid;

  resolved_semantic_version_id :=
    app_private.resolve_north_star_metric_version(
      target_tenant_id,
      target_connection_id,
      payload_semantic_version_id,
      payload_metric_key
    );

  insert into public.north_star_benchmarks (
    tenant_id,
    connection_id,
    dashboard_id,
    semantic_version_id,
    metric_key,
    name,
    description,
    expected_value,
    value_type,
    currency,
    period_type,
    period_start,
    period_end,
    tolerance_mode,
    tolerance_percentage,
    min_value,
    max_value,
    severity,
    enabled,
    created_by,
    updated_by
  )
  values (
    target_tenant_id,
    target_connection_id,
    payload_dashboard_id,
    resolved_semantic_version_id,
    payload_metric_key,
    trim(benchmark_payload->>'name'),
    nullif(benchmark_payload->>'description', ''),
    (benchmark_payload->>'expected_value')::numeric,
    benchmark_payload->>'value_type',
    nullif(benchmark_payload->>'currency', ''),
    benchmark_payload->>'period_type',
    nullif(benchmark_payload->>'period_start', '')::date,
    nullif(benchmark_payload->>'period_end', '')::date,
    benchmark_payload->>'tolerance_mode',
    nullif(benchmark_payload->>'tolerance_percentage', '')::numeric,
    nullif(benchmark_payload->>'min_value', '')::numeric,
    nullif(benchmark_payload->>'max_value', '')::numeric,
    benchmark_payload->>'severity',
    coalesce((benchmark_payload->>'enabled')::boolean, true),
    actor_user_id,
    actor_user_id
  )
  returning benchmark_key into created_benchmark_key;

  insert into public.audit_logs (
    tenant_id,
    actor_user_id,
    action,
    subject_type,
    subject_id,
    metadata
  )
  values (
    target_tenant_id,
    actor_user_id,
    'north_star_benchmark.created',
    'north_star_benchmark',
    created_benchmark_key,
    jsonb_build_object(
      'connection_id', target_connection_id,
      'semantic_version_id', resolved_semantic_version_id,
      'metric_key', payload_metric_key
    )
  );

  return created_benchmark_key;
end;
$$;

revoke all on function app_private.create_north_star_benchmark(
  uuid,
  uuid,
  uuid,
  jsonb
) from public, anon, authenticated, service_role;

create or replace function app_private.update_north_star_benchmark(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_benchmark_key uuid,
  benchmark_payload jsonb
)
returns uuid
language plpgsql
set search_path = public, app_private, pg_temp
as $$
declare
  existing_benchmark public.north_star_benchmarks%rowtype;
  resolved_semantic_version_id uuid;
  payload_connection_id uuid;
  payload_dashboard_id uuid;
  payload_metric_key uuid;
  payload_semantic_version_id uuid;
begin
  if not app_private.is_semantic_layer_admin(
    target_tenant_id,
    actor_user_id
  ) then
    raise exception 'north star owner or admin role required'
      using errcode = '42501';
  end if;

  select *
  into existing_benchmark
  from public.north_star_benchmarks benchmark
  where benchmark.tenant_id = target_tenant_id
    and benchmark.benchmark_key = target_benchmark_key;

  if existing_benchmark.benchmark_key is null then
    raise exception 'north star benchmark not found'
      using errcode = 'P0002';
  end if;

  perform app_private.assert_north_star_payload_shape(
    benchmark_payload,
    false
  );

  payload_connection_id :=
    coalesce(
      nullif(benchmark_payload->>'connection_id', '')::uuid,
      existing_benchmark.connection_id
    );
  if payload_connection_id <> existing_benchmark.connection_id then
    raise exception 'north star benchmark cannot move connection'
      using errcode = '22023';
  end if;

  payload_dashboard_id := nullif(benchmark_payload->>'dashboard_id', '')::uuid;
  payload_metric_key := nullif(benchmark_payload->>'metric_key', '')::uuid;
  payload_semantic_version_id :=
    nullif(benchmark_payload->>'semantic_version_id', '')::uuid;

  resolved_semantic_version_id :=
    app_private.resolve_north_star_metric_version(
      target_tenant_id,
      existing_benchmark.connection_id,
      payload_semantic_version_id,
      payload_metric_key
    );

  update public.north_star_benchmarks benchmark
  set
    dashboard_id = payload_dashboard_id,
    semantic_version_id = resolved_semantic_version_id,
    metric_key = payload_metric_key,
    name = trim(benchmark_payload->>'name'),
    description = nullif(benchmark_payload->>'description', ''),
    expected_value = (benchmark_payload->>'expected_value')::numeric,
    value_type = benchmark_payload->>'value_type',
    currency = nullif(benchmark_payload->>'currency', ''),
    period_type = benchmark_payload->>'period_type',
    period_start = nullif(benchmark_payload->>'period_start', '')::date,
    period_end = nullif(benchmark_payload->>'period_end', '')::date,
    tolerance_mode = benchmark_payload->>'tolerance_mode',
    tolerance_percentage =
      nullif(benchmark_payload->>'tolerance_percentage', '')::numeric,
    min_value = nullif(benchmark_payload->>'min_value', '')::numeric,
    max_value = nullif(benchmark_payload->>'max_value', '')::numeric,
    severity = benchmark_payload->>'severity',
    enabled = coalesce((benchmark_payload->>'enabled')::boolean, true),
    updated_by = actor_user_id,
    updated_at = statement_timestamp()
  where benchmark.tenant_id = target_tenant_id
    and benchmark.benchmark_key = target_benchmark_key;

  insert into public.audit_logs (
    tenant_id,
    actor_user_id,
    action,
    subject_type,
    subject_id,
    metadata
  )
  values (
    target_tenant_id,
    actor_user_id,
    'north_star_benchmark.updated',
    'north_star_benchmark',
    target_benchmark_key,
    jsonb_build_object(
      'connection_id', existing_benchmark.connection_id,
      'semantic_version_id', resolved_semantic_version_id,
      'metric_key', payload_metric_key
    )
  );

  return target_benchmark_key;
end;
$$;

revoke all on function app_private.update_north_star_benchmark(
  uuid,
  uuid,
  uuid,
  jsonb
) from public, anon, authenticated, service_role;

create or replace function app_private.delete_north_star_benchmark(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_benchmark_key uuid
)
returns uuid
language plpgsql
set search_path = public, app_private, pg_temp
as $$
declare
  existing_benchmark public.north_star_benchmarks%rowtype;
begin
  if not app_private.is_semantic_layer_admin(
    target_tenant_id,
    actor_user_id
  ) then
    raise exception 'north star owner or admin role required'
      using errcode = '42501';
  end if;

  select *
  into existing_benchmark
  from public.north_star_benchmarks benchmark
  where benchmark.tenant_id = target_tenant_id
    and benchmark.benchmark_key = target_benchmark_key;

  if existing_benchmark.benchmark_key is null then
    raise exception 'north star benchmark not found'
      using errcode = 'P0002';
  end if;

  delete from public.north_star_benchmarks benchmark
  where benchmark.tenant_id = target_tenant_id
    and benchmark.benchmark_key = target_benchmark_key;

  insert into public.audit_logs (
    tenant_id,
    actor_user_id,
    action,
    subject_type,
    subject_id,
    metadata
  )
  values (
    target_tenant_id,
    actor_user_id,
    'north_star_benchmark.deleted',
    'north_star_benchmark',
    target_benchmark_key,
    jsonb_build_object(
      'connection_id', existing_benchmark.connection_id,
      'semantic_version_id', existing_benchmark.semantic_version_id,
      'metric_key', existing_benchmark.metric_key
    )
  );

  return target_benchmark_key;
end;
$$;

revoke all on function app_private.delete_north_star_benchmark(
  uuid,
  uuid,
  uuid
) from public, anon, authenticated, service_role;

create or replace function app_private.create_north_star_benchmark_rpc(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  benchmark_payload jsonb
)
returns uuid
language sql
security definer
set search_path = public, app_private, pg_temp
as $$
  select app_private.create_north_star_benchmark(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    benchmark_payload
  );
$$;

create or replace function app_private.update_north_star_benchmark_rpc(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_benchmark_key uuid,
  benchmark_payload jsonb
)
returns uuid
language sql
security definer
set search_path = public, app_private, pg_temp
as $$
  select app_private.update_north_star_benchmark(
    actor_user_id,
    target_tenant_id,
    target_benchmark_key,
    benchmark_payload
  );
$$;

create or replace function app_private.delete_north_star_benchmark_rpc(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_benchmark_key uuid
)
returns uuid
language sql
security definer
set search_path = public, app_private, pg_temp
as $$
  select app_private.delete_north_star_benchmark(
    actor_user_id,
    target_tenant_id,
    target_benchmark_key
  );
$$;

revoke all on function app_private.create_north_star_benchmark_rpc(
  uuid,
  uuid,
  uuid,
  jsonb
) from public, anon, authenticated;
revoke all on function app_private.update_north_star_benchmark_rpc(
  uuid,
  uuid,
  uuid,
  jsonb
) from public, anon, authenticated;
revoke all on function app_private.delete_north_star_benchmark_rpc(
  uuid,
  uuid,
  uuid
) from public, anon, authenticated;

grant execute on function app_private.create_north_star_benchmark_rpc(
  uuid,
  uuid,
  uuid,
  jsonb
) to service_role;
grant execute on function app_private.update_north_star_benchmark_rpc(
  uuid,
  uuid,
  uuid,
  jsonb
) to service_role;
grant execute on function app_private.delete_north_star_benchmark_rpc(
  uuid,
  uuid,
  uuid
) to service_role;

create or replace function public.create_north_star_benchmark(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  benchmark_payload jsonb
)
returns uuid
language sql
set search_path = public, app_private, pg_temp
as $$
  select app_private.create_north_star_benchmark_rpc(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    benchmark_payload
  );
$$;

create or replace function public.update_north_star_benchmark(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_benchmark_key uuid,
  benchmark_payload jsonb
)
returns uuid
language sql
set search_path = public, app_private, pg_temp
as $$
  select app_private.update_north_star_benchmark_rpc(
    actor_user_id,
    target_tenant_id,
    target_benchmark_key,
    benchmark_payload
  );
$$;

create or replace function public.delete_north_star_benchmark(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_benchmark_key uuid
)
returns uuid
language sql
set search_path = public, app_private, pg_temp
as $$
  select app_private.delete_north_star_benchmark_rpc(
    actor_user_id,
    target_tenant_id,
    target_benchmark_key
  );
$$;

revoke all on function public.create_north_star_benchmark(
  uuid,
  uuid,
  uuid,
  jsonb
) from public, anon, authenticated;
revoke all on function public.update_north_star_benchmark(
  uuid,
  uuid,
  uuid,
  jsonb
) from public, anon, authenticated;
revoke all on function public.delete_north_star_benchmark(
  uuid,
  uuid,
  uuid
) from public, anon, authenticated;

grant execute on function public.create_north_star_benchmark(
  uuid,
  uuid,
  uuid,
  jsonb
) to service_role;
grant execute on function public.update_north_star_benchmark(
  uuid,
  uuid,
  uuid,
  jsonb
) to service_role;
grant execute on function public.delete_north_star_benchmark(
  uuid,
  uuid,
  uuid
) to service_role;
