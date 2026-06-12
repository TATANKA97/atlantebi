create table public.queryability_graph_derivations (
  tenant_id uuid not null,
  connection_id uuid not null,
  schema_snapshot_id uuid not null,
  graph_version_id uuid not null,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  primary key (
    tenant_id,
    connection_id,
    schema_snapshot_id,
    graph_version_id
  ),
  foreign key (tenant_id, connection_id, schema_snapshot_id)
    references public.schema_snapshots(tenant_id, connection_id, id)
    on delete cascade,
  foreign key (tenant_id, connection_id, graph_version_id)
    references public.queryability_graph_versions(tenant_id, connection_id, id)
    on delete cascade
);

create index queryability_graph_derivations_graph_idx
  on public.queryability_graph_derivations (
    tenant_id,
    connection_id,
    graph_version_id
  );

alter table public.queryability_graph_derivations enable row level security;
revoke all on public.queryability_graph_derivations
  from public, anon, authenticated;
grant select, insert on public.queryability_graph_derivations
  to service_role;

revoke update, delete on
  public.schema_snapshots,
  public.queryability_graph_versions,
  public.queryability_graph_nodes,
  public.queryability_graph_columns,
  public.queryability_graph_edges
from service_role;

insert into public.queryability_graph_derivations (
  tenant_id,
  connection_id,
  schema_snapshot_id,
  graph_version_id,
  created_by,
  created_at
)
select
  tenant_id,
  connection_id,
  schema_snapshot_id,
  id,
  created_by,
  created_at
from public.queryability_graph_versions
on conflict do nothing;

alter function app_private.persist_queryability_graph_import(
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
) rename to persist_queryability_graph_import_core;

create function app_private.persist_queryability_graph_import(
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
security definer
set search_path = public, app_private, pg_temp
as $$
declare
  persisted record;
begin
  if exists (
    select 1
    from jsonb_array_elements(queryability_graph->'edges') edge
    where edge->>'edge_type' = 'fk_join'
      and (edge->>'automatic_join_allowed')::boolean
      and (
        edge->>'enforcement_status' <> 'enabled'
        or edge->>'validation_status' <> 'trusted'
        or edge->>'verified_by_db' <> 'true'
      )
  ) then
    raise exception 'automatic joins require enabled trusted database-verified foreign keys'
      using errcode = '22023';
  end if;

  select *
  into persisted
  from app_private.persist_queryability_graph_import_core(
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

  insert into public.queryability_graph_derivations (
    tenant_id,
    connection_id,
    schema_snapshot_id,
    graph_version_id,
    created_by
  )
  values (
    target_tenant_id,
    target_connection_id,
    persisted.schema_snapshot_id,
    persisted.queryability_graph_id,
    actor_user_id
  )
  on conflict do nothing;

  if persisted.deduplicated then
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
      'queryability_graph.deduplicated',
      'db_connection',
      target_connection_id,
      jsonb_build_object(
        'schema_snapshot_id', persisted.schema_snapshot_id,
        'queryability_graph_id', persisted.queryability_graph_id,
        'queryability_graph_version', persisted.queryability_graph_version,
        'schema_hash', technical_snapshot->>'schema_hash',
        'graph_hash', queryability_graph->>'graph_hash',
        'semantic_status', persisted.semantic_status
      )
    );
  end if;

  return query
  select
    persisted.schema_snapshot_id,
    persisted.queryability_graph_id,
    persisted.queryability_graph_version,
    persisted.deduplicated,
    persisted.semantic_status;
end;
$$;

revoke all on function app_private.persist_queryability_graph_import_core(
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
) from public, anon, authenticated, service_role;

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

drop function public.persist_queryability_graph_import(
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
);

create function public.persist_queryability_graph_import(
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
