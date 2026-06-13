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
security definer
set search_path = public, app_private, pg_temp
as $$
declare
  persisted record;
  existing_snapshot public.schema_snapshots%rowtype;
  effective_technical_snapshot jsonb := technical_snapshot;
  effective_summary jsonb := target_summary;
  effective_table_count integer := target_table_count;
  effective_column_count integer := target_column_count;
  effective_introspected_at timestamptz := target_introspected_at;
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

  perform pg_advisory_xact_lock(
    hashtextextended(target_connection_id::text, 0)
  );

  if not reuse_existing_snapshot then
    select snapshot.*
    into existing_snapshot
    from public.schema_snapshots snapshot
    where snapshot.tenant_id = target_tenant_id
      and snapshot.connection_id = target_connection_id
      and snapshot.snapshot_hash = technical_snapshot->>'snapshot_hash'
    limit 1;

    if found then
      if existing_snapshot.engine <> target_engine
        or existing_snapshot.schema_hash
          is distinct from technical_snapshot->>'schema_hash'
        or existing_snapshot.table_count <> target_table_count
        or existing_snapshot.column_count <> target_column_count
        or existing_snapshot.snapshot->>'snapshot_hash'
          is distinct from technical_snapshot->>'snapshot_hash'
      then
        raise exception 'technical snapshot hash collision'
          using errcode = '23505';
      end if;

      effective_technical_snapshot := existing_snapshot.snapshot;
      effective_summary := existing_snapshot.summary;
      effective_table_count := existing_snapshot.table_count;
      effective_column_count := existing_snapshot.column_count;
      effective_introspected_at := existing_snapshot.introspected_at;
    end if;
  end if;

  select *
  into persisted
  from app_private.persist_queryability_graph_import_core(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    target_snapshot_id,
    target_engine,
    effective_technical_snapshot,
    effective_summary,
    queryability_graph,
    effective_table_count,
    effective_column_count,
    effective_introspected_at,
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
