alter table public.schema_snapshots
  add column if not exists snapshot_hash text
    check (snapshot_hash ~ '^[0-9a-f]{64}$');

do $$
begin
  if exists (
    select 1
    from public.schema_snapshots snapshot
    join public.tenants tenant on tenant.id = snapshot.tenant_id
    where snapshot.snapshot_hash is null
      and not (
        lower(coalesce(tenant.settings->>'environment', '')) in ('demo', 'test')
        or tenant.slug ~* '(^|[-_])(demo|test)([-_]|$)'
        or tenant.name ~* '(^|[[:space:]_-])(demo|test)([[:space:]_-]|$)'
      )
  ) then
    raise exception
      'legacy schema snapshots exist outside demo/test tenants; purge them explicitly before Queryability Graph V1'
      using errcode = '55000';
  end if;

  delete from public.semantic_versions semantic_version
  using public.schema_snapshots snapshot, public.tenants tenant
  where semantic_version.tenant_id = snapshot.tenant_id
    and semantic_version.connection_id = snapshot.connection_id
    and tenant.id = snapshot.tenant_id
    and snapshot.snapshot_hash is null
    and (
      lower(coalesce(tenant.settings->>'environment', '')) in ('demo', 'test')
      or tenant.slug ~* '(^|[-_])(demo|test)([-_]|$)'
      or tenant.name ~* '(^|[[:space:]_-])(demo|test)([[:space:]_-]|$)'
    );

  delete from public.schema_snapshots snapshot
  using public.tenants tenant
  where tenant.id = snapshot.tenant_id
    and snapshot.snapshot_hash is null
    and (
      lower(coalesce(tenant.settings->>'environment', '')) in ('demo', 'test')
      or tenant.slug ~* '(^|[-_])(demo|test)([-_]|$)'
      or tenant.name ~* '(^|[[:space:]_-])(demo|test)([[:space:]_-]|$)'
    );
end;
$$;

alter table public.schema_snapshots
  alter column snapshot_hash set not null;

create unique index schema_snapshots_connection_snapshot_hash_idx
  on public.schema_snapshots (tenant_id, connection_id, snapshot_hash);

create type public.queryability_graph_status as enum (
  'complete',
  'partial'
);

create table public.queryability_graph_versions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  connection_id uuid not null,
  schema_snapshot_id uuid not null,
  version integer not null check (version > 0),
  contract_version text not null check (contract_version = 'queryability_graph.v1'),
  builder_version text not null check (length(builder_version) between 1 and 100),
  policy_version text not null check (length(policy_version) between 1 and 100),
  status public.queryability_graph_status not null,
  schema_hash text not null check (schema_hash ~ '^[0-9a-f]{64}$'),
  snapshot_hash text not null check (snapshot_hash ~ '^[0-9a-f]{64}$'),
  graph_input_hash text not null check (graph_input_hash ~ '^[0-9a-f]{64}$'),
  derivation_key text not null check (derivation_key ~ '^[0-9a-f]{64}$'),
  graph_hash text not null check (graph_hash ~ '^[0-9a-f]{64}$'),
  graph jsonb not null check (
    jsonb_typeof(graph) = 'object'
    and jsonb_typeof(graph->'nodes') = 'array'
    and jsonb_typeof(graph->'edges') = 'array'
  ),
  node_count integer not null check (node_count >= 0),
  column_count integer not null check (column_count >= 0),
  edge_count integer not null check (edge_count >= 0),
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  unique (tenant_id, connection_id, version),
  unique (tenant_id, connection_id, derivation_key),
  unique (tenant_id, id),
  unique (tenant_id, connection_id, id),
  foreign key (tenant_id, connection_id)
    references public.db_connections(tenant_id, id)
    on delete cascade,
  foreign key (tenant_id, connection_id, schema_snapshot_id)
    references public.schema_snapshots(tenant_id, connection_id, id)
    on delete cascade
);

create table public.queryability_graph_nodes (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  graph_version_id uuid not null,
  node_key text not null check (node_key ~ '^[0-9a-f]{64}$'),
  database_name text not null check (length(database_name) between 1 and 255),
  schema_name text not null check (length(schema_name) between 1 and 255),
  object_name text not null check (length(object_name) between 1 and 255),
  object_type text not null check (object_type in ('table', 'view')),
  queryability_status text not null
    check (queryability_status in ('queryable', 'excluded')),
  bridge_candidate boolean not null,
  view_lineage_status text
    check (
      view_lineage_status is null
      or view_lineage_status in ('complete', 'partial', 'unavailable')
    ),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  unique (graph_version_id, node_key),
  unique (tenant_id, graph_version_id, id),
  foreign key (tenant_id, graph_version_id)
    references public.queryability_graph_versions(tenant_id, id)
    on delete cascade
);

create table public.queryability_graph_columns (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  graph_version_id uuid not null,
  node_id uuid not null,
  column_key text not null check (column_key ~ '^[0-9a-f]{64}$'),
  column_name text not null check (length(column_name) between 1 and 255),
  ordinal_position integer not null check (ordinal_position > 0),
  technical_role text not null,
  queryability_status text not null
    check (queryability_status in ('queryable', 'excluded')),
  sensitivity text not null check (sensitivity in ('none', 'pii', 'sensitive')),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  unique (graph_version_id, column_key),
  unique (graph_version_id, node_id, ordinal_position),
  unique (tenant_id, graph_version_id, id),
  foreign key (tenant_id, graph_version_id, node_id)
    references public.queryability_graph_nodes(tenant_id, graph_version_id, id)
    on delete cascade
);

create table public.queryability_graph_edges (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  graph_version_id uuid not null,
  edge_key text not null check (edge_key ~ '^[0-9a-f]{64}$'),
  edge_type text not null check (
    edge_type in (
      'fk_join',
      'view_depends_on',
      'view_column_derives_from'
    )
  ),
  from_node_id uuid not null,
  to_node_id uuid,
  automatic_join_allowed boolean not null,
  relationship_shape text
    check (
      relationship_shape is null
      or relationship_shape in ('one_to_one', 'many_to_one')
    ),
  enforcement_status text
    check (
      enforcement_status is null
      or enforcement_status in ('enabled', 'disabled')
    ),
  validation_status text
    check (
      validation_status is null
      or validation_status in ('trusted', 'untrusted')
    ),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  unique (graph_version_id, edge_key),
  foreign key (tenant_id, graph_version_id, from_node_id)
    references public.queryability_graph_nodes(tenant_id, graph_version_id, id)
    on delete cascade,
  foreign key (tenant_id, graph_version_id, to_node_id)
    references public.queryability_graph_nodes(tenant_id, graph_version_id, id)
    on delete cascade,
  check (
    (
      edge_type = 'fk_join'
      and to_node_id is not null
      and relationship_shape is not null
      and enforcement_status is not null
      and validation_status is not null
    )
    or (
      edge_type <> 'fk_join'
      and automatic_join_allowed = false
      and relationship_shape is null
      and enforcement_status is null
      and validation_status is null
    )
  )
);

create index queryability_graph_versions_connection_created_idx
  on public.queryability_graph_versions (
    tenant_id,
    connection_id,
    created_at desc
  );

create index queryability_graph_nodes_lookup_idx
  on public.queryability_graph_nodes (
    tenant_id,
    graph_version_id,
    schema_name,
    object_name
  );

create index queryability_graph_edges_from_idx
  on public.queryability_graph_edges (
    tenant_id,
    graph_version_id,
    from_node_id
  );

create index queryability_graph_edges_to_idx
  on public.queryability_graph_edges (
    tenant_id,
    graph_version_id,
    to_node_id
  )
  where to_node_id is not null;

alter table public.queryability_graph_versions enable row level security;
alter table public.queryability_graph_nodes enable row level security;
alter table public.queryability_graph_columns enable row level security;
alter table public.queryability_graph_edges enable row level security;

revoke all privileges on table public.queryability_graph_versions
  from public, anon, authenticated;
revoke all privileges on table public.queryability_graph_nodes
  from public, anon, authenticated;
revoke all privileges on table public.queryability_graph_columns
  from public, anon, authenticated;
revoke all privileges on table public.queryability_graph_edges
  from public, anon, authenticated;

grant select, insert on table public.queryability_graph_versions
  to service_role;
grant select, insert on table public.queryability_graph_nodes
  to service_role;
grant select, insert on table public.queryability_graph_columns
  to service_role;
grant select, insert on table public.queryability_graph_edges
  to service_role;

create or replace function app_private.reject_queryability_graph_update()
returns trigger
language plpgsql
set search_path = public, app_private, pg_temp
as $$
begin
  raise exception 'queryability graph artifacts are immutable'
    using errcode = '55000';
end;
$$;

create trigger queryability_graph_versions_immutable
before update on public.queryability_graph_versions
for each row execute function app_private.reject_queryability_graph_update();

create trigger queryability_graph_nodes_immutable
before update on public.queryability_graph_nodes
for each row execute function app_private.reject_queryability_graph_update();

create trigger queryability_graph_columns_immutable
before update on public.queryability_graph_columns
for each row execute function app_private.reject_queryability_graph_update();

create trigger queryability_graph_edges_immutable
before update on public.queryability_graph_edges
for each row execute function app_private.reject_queryability_graph_update();

create or replace function app_private.reject_schema_snapshot_update()
returns trigger
language plpgsql
set search_path = public, app_private, pg_temp
as $$
begin
  raise exception 'schema snapshots are immutable'
    using errcode = '55000';
end;
$$;

create trigger schema_snapshots_immutable
before update on public.schema_snapshots
for each row execute function app_private.reject_schema_snapshot_update();

create or replace function app_private.persist_queryability_graph_import(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_snapshot_id uuid,
  target_engine public.connection_engine,
  technical_snapshot jsonb,
  target_summary jsonb,
  queryability_graph jsonb,
  target_table_count integer,
  target_column_count integer,
  target_introspected_at timestamptz,
  reuse_existing_snapshot boolean default false
)
returns table (
  schema_snapshot_id uuid,
  queryability_graph_id uuid,
  queryability_graph_version integer,
  deduplicated boolean,
  semantic_status text
)
language plpgsql
set search_path = public, app_private, pg_temp
as $$
declare
  connection_database_name text;
  sanitized_summary jsonb;
  existing_graph public.queryability_graph_versions%rowtype;
  effective_snapshot_id uuid;
  normalized_graph jsonb;
  new_graph_id uuid;
  new_graph_version integer;
  inserted_node_count integer;
  inserted_column_count integer;
  inserted_edge_count integer;
  expected_node_count integer;
  expected_column_count integer;
  expected_edge_count integer;
begin
  if not app_private.is_connection_editor(target_tenant_id, actor_user_id) then
    raise exception 'connection editor role required'
      using errcode = '42501';
  end if;

  if target_engine <> 'sqlserver' then
    raise exception 'queryability graph V1 supports SQL Server only'
      using errcode = '0A000';
  end if;

  select connection.database_name
  into connection_database_name
  from public.db_connections connection
  where connection.id = target_connection_id
    and connection.tenant_id = target_tenant_id
    and connection.engine = target_engine
    and connection.status = 'ready';

  if connection_database_name is null then
    raise exception 'ready connection not found'
      using errcode = 'P0002';
  end if;

  sanitized_summary :=
    app_private.sanitize_schema_import_summary(target_summary);

  if jsonb_typeof(technical_snapshot) <> 'object'
    or technical_snapshot->>'status' <> 'ok'
    or coalesce(technical_snapshot->>'coverage_status', '')
      not in ('ok', 'partial', 'warning')
    or technical_snapshot->>'schema_hash' !~ '^[0-9a-f]{64}$'
    or technical_snapshot->>'snapshot_hash' !~ '^[0-9a-f]{64}$'
  then
    raise exception 'technical snapshot is invalid or blocked'
      using errcode = '22023';
  end if;

  if jsonb_typeof(queryability_graph) <> 'object'
    or queryability_graph->>'contract_version' <> 'queryability_graph.v1'
    or queryability_graph->>'engine' <> 'sqlserver'
    or queryability_graph->>'status' not in ('complete', 'partial')
    or queryability_graph->>'semantic_status' <> 'not_initialized'
    or queryability_graph->>'tenant_id' <> target_tenant_id::text
    or queryability_graph->>'connection_id' <> target_connection_id::text
    or queryability_graph->>'schema_snapshot_id' <> target_snapshot_id::text
    or queryability_graph->>'schema_hash'
      is distinct from technical_snapshot->>'schema_hash'
    or queryability_graph->>'snapshot_hash'
      is distinct from technical_snapshot->>'snapshot_hash'
    or queryability_graph->>'graph_input_hash' !~ '^[0-9a-f]{64}$'
    or queryability_graph->>'derivation_key' !~ '^[0-9a-f]{64}$'
    or queryability_graph->>'graph_hash' !~ '^[0-9a-f]{64}$'
    or jsonb_typeof(queryability_graph->'nodes') <> 'array'
    or jsonb_typeof(queryability_graph->'edges') <> 'array'
  then
    raise exception 'queryability graph is invalid'
      using errcode = '22023';
  end if;

  if jsonb_array_length(queryability_graph->'nodes') > 5000
    or jsonb_array_length(queryability_graph->'edges') > 250000
    or exists (
      select 1
      from jsonb_array_elements(queryability_graph->'nodes') node
      where jsonb_typeof(node) <> 'object'
        or node->>'node_key' !~ '^[0-9a-f]{64}$'
        or node->>'object_type' not in ('table', 'view')
        or node->>'queryability_status' not in ('queryable', 'excluded')
        or jsonb_typeof(node->'columns') <> 'array'
        or jsonb_array_length(node->'columns') > 50000
    )
    or exists (
      select 1
      from jsonb_array_elements(queryability_graph->'nodes') node
      cross join lateral jsonb_array_elements(node->'columns') graph_column
      where jsonb_typeof(graph_column) <> 'object'
        or graph_column->>'column_key' !~ '^[0-9a-f]{64}$'
        or graph_column->>'ordinal_position' !~ '^[1-9][0-9]*$'
        or graph_column->>'queryability_status'
          not in ('queryable', 'excluded')
        or graph_column->>'sensitivity'
          not in ('none', 'pii', 'sensitive')
    )
    or exists (
      select node->>'node_key'
      from jsonb_array_elements(queryability_graph->'nodes') node
      group by node->>'node_key'
      having count(*) > 1
    )
    or exists (
      select graph_column->>'column_key'
      from jsonb_array_elements(queryability_graph->'nodes') node
      cross join lateral jsonb_array_elements(node->'columns') graph_column
      group by graph_column->>'column_key'
      having count(*) > 1
    )
    or exists (
      select 1
      from jsonb_array_elements(queryability_graph->'edges') edge
      where jsonb_typeof(edge) <> 'object'
        or edge->>'edge_key' !~ '^[0-9a-f]{64}$'
        or edge->>'edge_type' not in (
          'fk_join',
          'view_depends_on',
          'view_column_derives_from'
        )
        or jsonb_typeof(edge->'reason_codes') <> 'array'
        or (
          edge->>'edge_type' = 'fk_join'
          and (
            jsonb_typeof(edge->'column_pairs') <> 'array'
            or jsonb_array_length(edge->'column_pairs') = 0
            or edge->>'relationship_shape'
              not in ('one_to_one', 'many_to_one')
            or edge->>'enforcement_status' not in ('enabled', 'disabled')
            or edge->>'validation_status' not in ('trusted', 'untrusted')
          )
        )
        or (
          edge->>'edge_type' <> 'fk_join'
          and edge->>'automatic_join_allowed' <> 'false'
        )
    )
    or exists (
      select edge->>'edge_key'
      from jsonb_array_elements(queryability_graph->'edges') edge
      group by edge->>'edge_key'
      having count(*) > 1
    )
  then
    raise exception 'queryability graph contract invariants are invalid'
      using errcode = '22023';
  end if;

  if sanitized_summary->>'database_name' <> connection_database_name
    or sanitized_summary->>'engine' <> target_engine::text
    or sanitized_summary->>'engine_version'
      is distinct from technical_snapshot->>'engine_version'
    or sanitized_summary->>'schema_hash'
      is distinct from technical_snapshot->>'schema_hash'
    or sanitized_summary->>'coverage_status'
      is distinct from technical_snapshot->>'coverage_status'
    or (sanitized_summary->>'captured_at')::timestamptz
      is distinct from target_introspected_at
    or (sanitized_summary->>'total_tables')::integer <> target_table_count
    or (sanitized_summary->>'total_columns')::integer <> target_column_count
  then
    raise exception 'schema import summary does not match the import'
      using errcode = '22023';
  end if;

  expected_node_count := jsonb_array_length(queryability_graph->'nodes');
  expected_edge_count := jsonb_array_length(queryability_graph->'edges');
  select coalesce(sum(jsonb_array_length(node->'columns')), 0)::integer
  into expected_column_count
  from jsonb_array_elements(queryability_graph->'nodes') as node;

  perform pg_advisory_xact_lock(
    hashtextextended(target_connection_id::text, 0)
  );

  effective_snapshot_id := target_snapshot_id;
  if reuse_existing_snapshot then
    if not exists (
      select 1
      from public.schema_snapshots snapshot
      where snapshot.id = target_snapshot_id
        and snapshot.tenant_id = target_tenant_id
        and snapshot.connection_id = target_connection_id
        and snapshot.engine = target_engine
        and snapshot.schema_hash = technical_snapshot->>'schema_hash'
        and snapshot.snapshot_hash = technical_snapshot->>'snapshot_hash'
        and snapshot.snapshot = technical_snapshot
        and snapshot.id = (
          select latest.id
          from public.schema_snapshots latest
          where latest.tenant_id = target_tenant_id
            and latest.connection_id = target_connection_id
          order by latest.created_at desc, latest.introspected_at desc, latest.id desc
          limit 1
        )
    ) then
      raise exception 'only the latest matching schema snapshot can be rebuilt'
        using errcode = '22023';
    end if;
  else
    select snapshot.id
    into effective_snapshot_id
    from public.schema_snapshots snapshot
    where snapshot.tenant_id = target_tenant_id
      and snapshot.connection_id = target_connection_id
      and snapshot.snapshot_hash = technical_snapshot->>'snapshot_hash'
      and snapshot.snapshot = technical_snapshot
    limit 1;

    if effective_snapshot_id is null then
      effective_snapshot_id := target_snapshot_id;
      insert into public.schema_snapshots (
        id,
        tenant_id,
        connection_id,
        engine,
        snapshot,
        snapshot_version,
        table_count,
        column_count,
        introspected_at,
        engine_version,
        schema_hash,
        snapshot_hash,
        coverage_status,
        coverage_warnings,
        summary,
        created_by,
        created_at
      )
      values (
        effective_snapshot_id,
        target_tenant_id,
        target_connection_id,
        target_engine,
        technical_snapshot,
        1,
        target_table_count,
        target_column_count,
        target_introspected_at,
        technical_snapshot->>'engine_version',
        technical_snapshot->>'schema_hash',
        technical_snapshot->>'snapshot_hash',
        (technical_snapshot->>'coverage_status')::public.schema_coverage_status,
        coalesce(technical_snapshot->'coverage_warnings', '[]'::jsonb),
        sanitized_summary,
        actor_user_id,
        clock_timestamp()
      );
    end if;
  end if;

  normalized_graph := jsonb_set(
    queryability_graph,
    '{schema_snapshot_id}',
    to_jsonb(effective_snapshot_id::text)
  );

  select *
  into existing_graph
  from public.queryability_graph_versions graph_version
  where graph_version.tenant_id = target_tenant_id
    and graph_version.connection_id = target_connection_id
    and graph_version.derivation_key =
      queryability_graph->>'derivation_key';

  if found then
    if existing_graph.graph_hash <> queryability_graph->>'graph_hash'
      or existing_graph.graph_input_hash
        <> queryability_graph->>'graph_input_hash'
      or existing_graph.builder_version
        <> queryability_graph->>'builder_version'
      or existing_graph.policy_version
        <> queryability_graph->>'policy_version'
      or existing_graph.contract_version
        <> queryability_graph->>'contract_version'
      or existing_graph.status::text <> queryability_graph->>'status'
      or existing_graph.graph->'status_reasons'
        is distinct from queryability_graph->'status_reasons'
      or existing_graph.graph->'nodes'
        is distinct from queryability_graph->'nodes'
      or existing_graph.graph->'edges'
        is distinct from queryability_graph->'edges'
    then
      raise exception 'queryability graph derivation collision'
        using errcode = '23505';
    end if;

    return query
    select
      effective_snapshot_id,
      existing_graph.id,
      existing_graph.version,
      true,
      'not_initialized'::text;
    return;
  end if;

  if exists (
    select 1
    from jsonb_array_elements(queryability_graph->'edges') edge
    where not exists (
      select 1
      from jsonb_array_elements(queryability_graph->'nodes') node
      where node->>'node_key' = edge->>'from_node_key'
    )
    or (
      edge->>'to_node_key' is not null
      and not exists (
        select 1
        from jsonb_array_elements(queryability_graph->'nodes') node
        where node->>'node_key' = edge->>'to_node_key'
      )
    )
  ) then
    raise exception 'queryability graph edge references unknown node'
      using errcode = '23503';
  end if;

  select coalesce(max(version), 0) + 1
  into new_graph_version
  from public.queryability_graph_versions
  where tenant_id = target_tenant_id
    and connection_id = target_connection_id;

  insert into public.queryability_graph_versions (
    tenant_id,
    connection_id,
    schema_snapshot_id,
    version,
    contract_version,
    builder_version,
    policy_version,
    status,
    schema_hash,
    snapshot_hash,
    graph_input_hash,
    derivation_key,
    graph_hash,
    graph,
    node_count,
    column_count,
    edge_count,
    created_by
  )
  values (
    target_tenant_id,
    target_connection_id,
    effective_snapshot_id,
    new_graph_version,
    queryability_graph->>'contract_version',
    queryability_graph->>'builder_version',
    queryability_graph->>'policy_version',
    (queryability_graph->>'status')::public.queryability_graph_status,
    queryability_graph->>'schema_hash',
    queryability_graph->>'snapshot_hash',
    queryability_graph->>'graph_input_hash',
    queryability_graph->>'derivation_key',
    queryability_graph->>'graph_hash',
    normalized_graph,
    expected_node_count,
    expected_column_count,
    expected_edge_count,
    actor_user_id
  )
  returning id into new_graph_id;

  insert into public.queryability_graph_nodes (
    tenant_id,
    graph_version_id,
    node_key,
    database_name,
    schema_name,
    object_name,
    object_type,
    queryability_status,
    bridge_candidate,
    view_lineage_status,
    payload
  )
  select
    target_tenant_id,
    new_graph_id,
    node->>'node_key',
    node->>'database_name',
    node->>'schema_name',
    node->>'object_name',
    node->>'object_type',
    node->>'queryability_status',
    (node->>'bridge_candidate')::boolean,
    node->>'view_lineage_status',
    node
  from jsonb_array_elements(queryability_graph->'nodes') node;

  get diagnostics inserted_node_count = row_count;
  if inserted_node_count <> expected_node_count then
    raise exception 'queryability graph node count mismatch'
      using errcode = '22023';
  end if;

  insert into public.queryability_graph_columns (
    tenant_id,
    graph_version_id,
    node_id,
    column_key,
    column_name,
    ordinal_position,
    technical_role,
    queryability_status,
    sensitivity,
    payload
  )
  select
    target_tenant_id,
    new_graph_id,
    stored_node.id,
    graph_column->>'column_key',
    graph_column->>'name',
    (graph_column->>'ordinal_position')::integer,
    graph_column->>'technical_role',
    graph_column->>'queryability_status',
    graph_column->>'sensitivity',
    graph_column
  from jsonb_array_elements(queryability_graph->'nodes') node
  cross join lateral jsonb_array_elements(node->'columns') graph_column
  join public.queryability_graph_nodes stored_node
    on stored_node.tenant_id = target_tenant_id
    and stored_node.graph_version_id = new_graph_id
    and stored_node.node_key = node->>'node_key';

  get diagnostics inserted_column_count = row_count;
  if inserted_column_count <> expected_column_count then
    raise exception 'queryability graph column count mismatch'
      using errcode = '22023';
  end if;

  if exists (
    select 1
    from jsonb_array_elements(queryability_graph->'edges') edge
    cross join lateral jsonb_array_elements(
      case
        when edge->>'edge_type' = 'fk_join'
        then edge->'column_pairs'
        else '[]'::jsonb
      end
    ) pair
    where not exists (
      select 1
      from public.queryability_graph_columns graph_column
      join public.queryability_graph_nodes graph_node
        on graph_node.tenant_id = graph_column.tenant_id
        and graph_node.graph_version_id = graph_column.graph_version_id
        and graph_node.id = graph_column.node_id
      where graph_column.tenant_id = target_tenant_id
        and graph_column.graph_version_id = new_graph_id
        and graph_node.node_key = edge->>'from_node_key'
        and graph_column.column_key = pair->>'from_column_key'
    )
    or not exists (
      select 1
      from public.queryability_graph_columns graph_column
      join public.queryability_graph_nodes graph_node
        on graph_node.tenant_id = graph_column.tenant_id
        and graph_node.graph_version_id = graph_column.graph_version_id
        and graph_node.id = graph_column.node_id
      where graph_column.tenant_id = target_tenant_id
        and graph_column.graph_version_id = new_graph_id
        and graph_node.node_key = edge->>'to_node_key'
        and graph_column.column_key = pair->>'to_column_key'
    )
  ) then
    raise exception 'queryability graph FK references unknown column'
      using errcode = '23503';
  end if;

  if exists (
    select 1
    from jsonb_array_elements(queryability_graph->'edges') edge
    where edge->>'edge_type' = 'view_column_derives_from'
      and (
        not exists (
          select 1
          from public.queryability_graph_columns graph_column
          join public.queryability_graph_nodes graph_node
            on graph_node.tenant_id = graph_column.tenant_id
            and graph_node.graph_version_id = graph_column.graph_version_id
            and graph_node.id = graph_column.node_id
          where graph_column.tenant_id = target_tenant_id
            and graph_column.graph_version_id = new_graph_id
            and graph_node.node_key = edge->>'from_node_key'
            and graph_column.column_key = edge->>'from_column_key'
        )
        or (
          edge->>'to_column_key' is not null
          and not exists (
            select 1
            from public.queryability_graph_columns graph_column
            join public.queryability_graph_nodes graph_node
              on graph_node.tenant_id = graph_column.tenant_id
              and graph_node.graph_version_id = graph_column.graph_version_id
              and graph_node.id = graph_column.node_id
            where graph_column.tenant_id = target_tenant_id
              and graph_column.graph_version_id = new_graph_id
              and graph_node.node_key = edge->>'to_node_key'
              and graph_column.column_key = edge->>'to_column_key'
          )
        )
      )
  ) then
    raise exception 'queryability graph lineage references unknown column'
      using errcode = '23503';
  end if;

  insert into public.queryability_graph_edges (
    tenant_id,
    graph_version_id,
    edge_key,
    edge_type,
    from_node_id,
    to_node_id,
    automatic_join_allowed,
    relationship_shape,
    enforcement_status,
    validation_status,
    payload
  )
  select
    target_tenant_id,
    new_graph_id,
    edge->>'edge_key',
    edge->>'edge_type',
    from_node.id,
    to_node.id,
    (edge->>'automatic_join_allowed')::boolean,
    edge->>'relationship_shape',
    edge->>'enforcement_status',
    edge->>'validation_status',
    edge
  from jsonb_array_elements(queryability_graph->'edges') edge
  join public.queryability_graph_nodes from_node
    on from_node.tenant_id = target_tenant_id
    and from_node.graph_version_id = new_graph_id
    and from_node.node_key = edge->>'from_node_key'
  left join public.queryability_graph_nodes to_node
    on to_node.tenant_id = target_tenant_id
    and to_node.graph_version_id = new_graph_id
    and to_node.node_key = edge->>'to_node_key';

  get diagnostics inserted_edge_count = row_count;
  if inserted_edge_count <> expected_edge_count then
    raise exception 'queryability graph edge count mismatch'
      using errcode = '22023';
  end if;

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
    case
      when reuse_existing_snapshot then 'queryability_graph.rebuilt'
      else 'queryability_graph.imported'
    end,
    'db_connection',
    target_connection_id,
    jsonb_build_object(
      'schema_snapshot_id', effective_snapshot_id,
      'queryability_graph_id', new_graph_id,
      'queryability_graph_version', new_graph_version,
      'schema_hash', technical_snapshot->>'schema_hash',
      'graph_hash', queryability_graph->>'graph_hash',
      'status', queryability_graph->>'status',
      'reused_schema_snapshot', reuse_existing_snapshot,
      'semantic_status', 'not_initialized'
    )
  );

  return query
  select
    effective_snapshot_id,
    new_graph_id,
    new_graph_version,
    false,
    'not_initialized'::text;
end;
$$;

revoke all on function app_private.persist_queryability_graph_import(
  uuid,
  uuid,
  uuid,
  uuid,
  public.connection_engine,
  jsonb,
  jsonb,
  jsonb,
  integer,
  integer,
  timestamptz,
  boolean
) from public, anon, authenticated;

grant execute on function app_private.persist_queryability_graph_import(
  uuid,
  uuid,
  uuid,
  uuid,
  public.connection_engine,
  jsonb,
  jsonb,
  jsonb,
  integer,
  integer,
  timestamptz,
  boolean
) to service_role;

create or replace function public.persist_queryability_graph_import(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_snapshot_id uuid,
  target_engine public.connection_engine,
  technical_snapshot jsonb,
  target_summary jsonb,
  queryability_graph jsonb,
  target_table_count integer,
  target_column_count integer,
  target_introspected_at timestamptz,
  reuse_existing_snapshot boolean default false
)
returns table (
  schema_snapshot_id uuid,
  queryability_graph_id uuid,
  queryability_graph_version integer,
  deduplicated boolean,
  semantic_status text
)
language sql
set search_path = public, app_private, pg_temp
as $$
  select *
  from app_private.persist_queryability_graph_import(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    target_snapshot_id,
    target_engine,
    technical_snapshot,
    target_summary,
    queryability_graph,
    target_table_count,
    target_column_count,
    target_introspected_at,
    reuse_existing_snapshot
  );
$$;

revoke all on function public.persist_queryability_graph_import(
  uuid,
  uuid,
  uuid,
  uuid,
  public.connection_engine,
  jsonb,
  jsonb,
  jsonb,
  integer,
  integer,
  timestamptz,
  boolean
) from public, anon, authenticated;

grant execute on function public.persist_queryability_graph_import(
  uuid,
  uuid,
  uuid,
  uuid,
  public.connection_engine,
  jsonb,
  jsonb,
  jsonb,
  integer,
  integer,
  timestamptz,
  boolean
) to service_role;

drop function if exists public.persist_technical_schema_import(
  uuid,
  uuid,
  uuid,
  public.connection_engine,
  jsonb,
  jsonb,
  jsonb,
  jsonb,
  integer,
  integer,
  timestamptz
);

drop function if exists app_private.persist_technical_schema_import(
  uuid,
  uuid,
  uuid,
  public.connection_engine,
  jsonb,
  jsonb,
  jsonb,
  jsonb,
  integer,
  integer,
  timestamptz
);
