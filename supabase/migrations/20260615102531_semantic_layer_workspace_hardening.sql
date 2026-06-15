alter table app_private.security_operation_leases
  drop constraint if exists security_operation_leases_operation_check;

alter table app_private.security_operation_leases
  add constraint security_operation_leases_operation_check
  check (
    operation in (
      'connection_test',
      'schema_introspection',
      'semantic_generation'
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
      'semantic_generation'
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
          target_operation = 'semantic_generation'
          and tm.role = any (
            array['owner', 'admin']::public.tenant_role[]
          )
        )
        or (
          target_operation <> 'semantic_generation'
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

create or replace function app_private.enforce_semantic_layer_graph_topology()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if exists (
    select 1
    from jsonb_array_elements(new.artifact->'columns') item
    left join public.queryability_graph_columns graph_column
      on graph_column.tenant_id = new.tenant_id
     and graph_column.graph_version_id = new.queryability_graph_version_id
     and graph_column.column_key = item->>'column_key'
    left join public.queryability_graph_nodes graph_node
      on graph_node.tenant_id = graph_column.tenant_id
     and graph_node.graph_version_id = graph_column.graph_version_id
     and graph_node.id = graph_column.node_id
    where graph_column.id is null
      or graph_node.node_key is distinct from item->>'node_key'
  ) or exists (
    select 1
    from jsonb_array_elements(new.artifact->'relationships') item
    left join public.queryability_graph_edges graph_edge
      on graph_edge.tenant_id = new.tenant_id
     and graph_edge.graph_version_id = new.queryability_graph_version_id
     and graph_edge.edge_key = item->>'edge_key'
    left join public.queryability_graph_nodes from_node
      on from_node.tenant_id = graph_edge.tenant_id
     and from_node.graph_version_id = graph_edge.graph_version_id
     and from_node.id = graph_edge.from_node_id
    left join public.queryability_graph_nodes to_node
      on to_node.tenant_id = graph_edge.tenant_id
     and to_node.graph_version_id = graph_edge.graph_version_id
     and to_node.id = graph_edge.to_node_id
    where graph_edge.id is null
      or from_node.node_key is distinct from item->>'from_node_key'
      or to_node.node_key is distinct from item->>'to_node_key'
  ) or exists (
    select 1
    from jsonb_array_elements(new.artifact->'metrics') metric
    left join public.queryability_graph_nodes source_node
      on source_node.tenant_id = new.tenant_id
     and source_node.graph_version_id = new.queryability_graph_version_id
     and source_node.node_key = metric->>'source_table_key'
    left join public.queryability_graph_nodes grain_node
      on grain_node.tenant_id = new.tenant_id
     and grain_node.graph_version_id = new.queryability_graph_version_id
     and grain_node.node_key = metric->>'grain_table_key'
    left join public.queryability_graph_columns measure_column
      on measure_column.tenant_id = new.tenant_id
     and measure_column.graph_version_id = new.queryability_graph_version_id
     and measure_column.column_key = metric->>'measure_column_key'
    left join public.queryability_graph_nodes measure_node
      on measure_node.tenant_id = measure_column.tenant_id
     and measure_node.graph_version_id = measure_column.graph_version_id
     and measure_node.id = measure_column.node_id
    where source_node.id is null
      or grain_node.id is null
      or (
        metric->>'measure_column_key' is not null
        and (
          measure_column.id is null
          or measure_node.node_key is distinct from metric->>'source_table_key'
        )
      )
      or exists (
        select 1
        from jsonb_array_elements_text(metric->'grain_column_keys') grain_key
        left join public.queryability_graph_columns grain_column
          on grain_column.tenant_id = new.tenant_id
         and grain_column.graph_version_id = new.queryability_graph_version_id
         and grain_column.column_key = grain_key
        left join public.queryability_graph_nodes grain_column_node
          on grain_column_node.tenant_id = grain_column.tenant_id
         and grain_column_node.graph_version_id = grain_column.graph_version_id
         and grain_column_node.id = grain_column.node_id
        where grain_column.id is null
          or grain_column_node.node_key
            is distinct from metric->>'grain_table_key'
      )
  ) then
    raise exception using
      errcode = '22023',
      message = 'semantic layer graph topology is invalid';
  end if;

  return new;
end;
$$;

revoke all on function app_private.enforce_semantic_layer_graph_topology()
  from public, anon, authenticated, service_role;

drop trigger if exists semantic_layer_versions_graph_topology
  on public.semantic_layer_versions;

create trigger semantic_layer_versions_graph_topology
before insert or update of artifact, queryability_graph_version_id
on public.semantic_layer_versions
for each row
execute function app_private.enforce_semantic_layer_graph_topology();

create or replace function app_private.enforce_semantic_layer_graph_references()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if exists (
    select 1
    from jsonb_array_elements(new.artifact->'metrics') metric
    where not exists (
      select 1
      from jsonb_array_elements(new.artifact->'tables') semantic_table
      where semantic_table->>'node_key' = metric->>'source_table_key'
    )
      or not exists (
        select 1
        from jsonb_array_elements(new.artifact->'tables') semantic_table
        where semantic_table->>'node_key' = metric->>'grain_table_key'
      )
      or (
        metric->>'measure_column_key' is not null
        and not exists (
          select 1
          from jsonb_array_elements(new.artifact->'columns') semantic_column
          where semantic_column->>'column_key' =
            metric->>'measure_column_key'
        )
      )
      or (
        metric->>'default_date_column_key' is not null
        and not exists (
          select 1
          from jsonb_array_elements(new.artifact->'columns') semantic_column
          where semantic_column->>'column_key' =
            metric->>'default_date_column_key'
        )
      )
      or exists (
        select 1
        from jsonb_array_elements_text(metric->'grain_column_keys') key
        where not exists (
          select 1
          from jsonb_array_elements(new.artifact->'columns') semantic_column
          where semantic_column->>'column_key' = key
        )
      )
      or exists (
        select 1
        from jsonb_array_elements_text(metric->'required_join_edge_keys') key
        left join public.queryability_graph_edges graph_edge
          on graph_edge.tenant_id = new.tenant_id
         and graph_edge.graph_version_id = new.queryability_graph_version_id
         and graph_edge.edge_key = key
        where graph_edge.id is null
          or graph_edge.edge_type <> 'fk_join'
          or not graph_edge.automatic_join_allowed
          or graph_edge.enforcement_status <> 'enabled'
          or graph_edge.validation_status <> 'trusted'
          or not exists (
            select 1
            from jsonb_array_elements(new.artifact->'relationships')
              relationship
            where relationship->>'edge_key' = key
              and (relationship->>'enabled')::boolean
          )
      )
      or exists (
        select 1
        from jsonb_array_elements(metric->'common_dimension_compatibility')
          compatibility
        where not exists (
          select 1
          from jsonb_array_elements(new.artifact->'columns') semantic_column
          where semantic_column->>'column_key' =
            compatibility->>'dimension_column_key'
        )
          or exists (
            select 1
            from jsonb_array_elements_text(compatibility->'edge_path') key
            left join public.queryability_graph_edges graph_edge
              on graph_edge.tenant_id = new.tenant_id
             and graph_edge.graph_version_id =
               new.queryability_graph_version_id
             and graph_edge.edge_key = key
            where graph_edge.id is null
              or graph_edge.edge_type <> 'fk_join'
              or not graph_edge.automatic_join_allowed
              or graph_edge.enforcement_status <> 'enabled'
              or graph_edge.validation_status <> 'trusted'
              or not exists (
                select 1
                from jsonb_array_elements(new.artifact->'relationships')
                  relationship
                where relationship->>'edge_key' = key
                  and (relationship->>'enabled')::boolean
              )
          )
      )
      or exists (
        select 1
        from jsonb_array_elements_text(metric->'preferred_for_dimensions') key
        where not exists (
          select 1
          from jsonb_array_elements(new.artifact->'columns') semantic_column
          where semantic_column->>'column_key' = key
        )
      )
      or exists (
        select 1
        from jsonb_array_elements(metric->'filters') filter_item
        where not exists (
          select 1
          from jsonb_array_elements(new.artifact->'columns') semantic_column
          where semantic_column->>'column_key' =
            filter_item->>'column_key'
        )
      )
  ) then
    raise exception using
      errcode = '22023',
      message = 'semantic layer graph references are invalid';
  end if;

  return new;
end;
$$;

revoke all on function app_private.enforce_semantic_layer_graph_references()
  from public, anon, authenticated, service_role;

drop trigger if exists semantic_layer_versions_graph_references
  on public.semantic_layer_versions;

create trigger semantic_layer_versions_graph_references
before insert or update of artifact, queryability_graph_version_id
on public.semantic_layer_versions
for each row
execute function app_private.enforce_semantic_layer_graph_references();

do $$
begin
  perform set_config('app.semantic_layer_rpc', 'on', true);
  update public.semantic_layer_versions
  set artifact = artifact;
end;
$$;
