do $$
begin
  if exists (select 1 from public.schema_snapshots) then
    raise exception using
      errcode = '55000',
      message = 'legacy schema snapshots must be purged before this migration';
  end if;
end;
$$;

drop view if exists public.schema_snapshot_summaries;

drop function if exists public.persist_technical_schema_import(
  uuid,
  uuid,
  uuid,
  public.connection_engine,
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
  integer,
  integer,
  timestamptz
);

create type public.schema_coverage_status as enum (
  'ok',
  'partial',
  'warning',
  'blocked'
);

alter table public.schema_snapshots
  drop column coverage_state,
  add column coverage_status public.schema_coverage_status not null,
  add column summary jsonb not null;

create or replace function app_private.sanitize_schema_import_summary(
  target_summary jsonb
)
returns jsonb
language plpgsql
immutable
set search_path = public, app_private, pg_temp
as $$
declare
  allowed_keys constant text[] := array[
    'database_name',
    'engine',
    'engine_version',
    'schema_hash',
    'coverage_status',
    'captured_at',
    'duration_ms',
    'total_objects',
    'total_tables',
    'total_views',
    'total_columns',
    'queryable_objects',
    'non_queryable_objects',
    'queryable_columns',
    'non_queryable_columns',
    'primary_keys_count',
    'foreign_keys_count',
    'unique_constraints_count',
    'check_constraints_count',
    'default_constraints_count',
    'indexes_total_count',
    'table_indexes_count',
    'view_indexes_count',
    'unique_indexes_count',
    'filtered_indexes_count',
    'included_columns_indexes_count',
    'views_total',
    'views_with_definition_count',
    'views_without_definition_count',
    'views_with_lineage_count',
    'views_with_partial_lineage_count',
    'views_without_lineage_count',
    'view_lineage_dependencies_count',
    'columns_with_declared_type_count',
    'columns_without_declared_type_count',
    'columns_with_default_count',
    'computed_columns_count',
    'identity_columns_count',
    'pii_columns_count',
    'excluded_columns_count',
    'sensitive_columns_count',
    'coverage_warnings_count',
    'coverage_warnings_by_code'
  ];
  nonnegative_integer_keys constant text[] := array[
    'duration_ms',
    'total_objects',
    'total_tables',
    'total_views',
    'total_columns',
    'queryable_objects',
    'non_queryable_objects',
    'queryable_columns',
    'non_queryable_columns',
    'primary_keys_count',
    'foreign_keys_count',
    'unique_constraints_count',
    'check_constraints_count',
    'default_constraints_count',
    'indexes_total_count',
    'table_indexes_count',
    'view_indexes_count',
    'unique_indexes_count',
    'filtered_indexes_count',
    'included_columns_indexes_count',
    'views_total',
    'views_with_definition_count',
    'views_without_definition_count',
    'views_with_lineage_count',
    'views_with_partial_lineage_count',
    'views_without_lineage_count',
    'view_lineage_dependencies_count',
    'columns_with_declared_type_count',
    'columns_without_declared_type_count',
    'columns_with_default_count',
    'computed_columns_count',
    'identity_columns_count',
    'pii_columns_count',
    'excluded_columns_count',
    'sensitive_columns_count',
    'coverage_warnings_count'
  ];
  target_key text;
  warning_entry record;
begin
  if jsonb_typeof(target_summary) <> 'object'
    or not target_summary ?& allowed_keys
    or target_summary - allowed_keys <> '{}'::jsonb
  then
    raise exception 'schema import summary fields are invalid'
      using errcode = '22023';
  end if;

  if jsonb_typeof(target_summary->'database_name') <> 'string'
    or length(target_summary->>'database_name') not between 1 and 255
    or jsonb_typeof(target_summary->'engine') <> 'string'
    or target_summary->>'engine' not in ('sqlserver', 'mysql')
    or jsonb_typeof(target_summary->'engine_version') <> 'string'
    or length(target_summary->>'engine_version') not between 1 and 500
    or jsonb_typeof(target_summary->'schema_hash') <> 'string'
    or target_summary->>'schema_hash' !~ '^[0-9a-f]{64}$'
    or jsonb_typeof(target_summary->'coverage_status') <> 'string'
    or target_summary->>'coverage_status' not in (
      'ok',
      'partial',
      'warning',
      'blocked'
    )
    or jsonb_typeof(target_summary->'captured_at') <> 'string'
    or target_summary->>'captured_at' !~
      '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$'
  then
    raise exception 'schema import summary scalar fields are invalid'
      using errcode = '22023';
  end if;

  perform (target_summary->>'captured_at')::timestamptz;

  foreach target_key in array nonnegative_integer_keys
  loop
    if jsonb_typeof(target_summary->target_key) <> 'number'
      or target_summary->>target_key !~ '^[0-9]+$'
    then
      raise exception 'schema import summary count % is invalid', target_key
        using errcode = '22023';
    end if;
  end loop;

  if jsonb_typeof(target_summary->'coverage_warnings_by_code') <> 'object' then
    raise exception 'coverage_warnings_by_code must be an object'
      using errcode = '22023';
  end if;

  for warning_entry in
    select key, value
    from jsonb_each(target_summary->'coverage_warnings_by_code')
  loop
    if length(warning_entry.key) not between 1 and 100
      or jsonb_typeof(warning_entry.value) <> 'number'
      or warning_entry.value #>> '{}' !~ '^[1-9][0-9]*$'
    then
      raise exception 'coverage warning count is invalid'
        using errcode = '22023';
    end if;
  end loop;

  if app_private.jsonb_has_forbidden_metadata_key(target_summary) then
    raise exception 'schema import summary contains forbidden metadata'
      using errcode = '22023';
  end if;

  return target_summary;
exception
  when invalid_datetime_format or datetime_field_overflow then
    raise exception 'schema import summary captured_at is invalid'
      using errcode = '22023';
end;
$$;

create or replace function app_private.is_valid_schema_import_summary(
  target_summary jsonb
)
returns boolean
language plpgsql
immutable
set search_path = public, app_private, pg_temp
as $$
begin
  perform app_private.sanitize_schema_import_summary(target_summary);
  return true;
exception
  when others then
    return false;
end;
$$;

revoke all on function app_private.sanitize_schema_import_summary(jsonb)
  from public, anon, authenticated;
revoke all on function app_private.is_valid_schema_import_summary(jsonb)
  from public, anon, authenticated;

alter table public.schema_snapshots
  add constraint schema_snapshots_summary_strict
    check (app_private.is_valid_schema_import_summary(summary));

create or replace function app_private.persist_technical_schema_import(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_engine public.connection_engine,
  technical_snapshot jsonb,
  target_summary jsonb,
  semantic_table_projection jsonb,
  relationship_projection jsonb,
  target_table_count integer,
  target_column_count integer,
  target_introspected_at timestamptz
)
returns table (
  schema_snapshot_id uuid,
  semantic_version_id uuid,
  semantic_version_number integer
)
language plpgsql
set search_path = public, app_private, pg_temp
as $$
declare
  connection_database_name text;
  sanitized_summary jsonb;
  new_snapshot_id uuid;
  new_semantic_version_id uuid;
  new_version integer;
  table_item jsonb;
  column_item jsonb;
  relationship_item jsonb;
  new_table_id uuid;
  from_table_id uuid;
  to_table_id uuid;
begin
  if not app_private.is_connection_editor(target_tenant_id, actor_user_id) then
    raise exception 'connection editor role required'
      using errcode = '42501';
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

  if jsonb_typeof(technical_snapshot) <> 'object'
    or technical_snapshot ? 'coverage_state'
    or not technical_snapshot ? 'coverage_status'
    or technical_snapshot->>'coverage_status' not in (
      'ok',
      'partial',
      'warning',
      'blocked'
    )
  then
    raise exception 'technical snapshot coverage_status is invalid'
      using errcode = '22023';
  end if;

  if jsonb_typeof(semantic_table_projection) <> 'array'
    or jsonb_typeof(relationship_projection) <> 'array'
  then
    raise exception 'semantic projection must be arrays'
      using errcode = '22023';
  end if;

  sanitized_summary :=
    app_private.sanitize_schema_import_summary(target_summary);

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
    or (sanitized_summary->>'coverage_warnings_count')::integer
      <> jsonb_array_length(
        coalesce(technical_snapshot->'coverage_warnings', '[]'::jsonb)
      )
  then
    raise exception 'schema import summary does not match the import'
      using errcode = '22023';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(target_connection_id::text, 0));

  insert into public.schema_snapshots (
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
    coverage_status,
    coverage_warnings,
    summary,
    created_by
  )
  values (
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
    (technical_snapshot->>'coverage_status')::public.schema_coverage_status,
    coalesce(technical_snapshot->'coverage_warnings', '[]'::jsonb),
    sanitized_summary,
    actor_user_id
  )
  returning id into new_snapshot_id;

  select coalesce(max(version), 0) + 1
  into new_version
  from public.semantic_versions
  where tenant_id = target_tenant_id
    and connection_id = target_connection_id;

  insert into public.semantic_versions (
    tenant_id,
    connection_id,
    schema_snapshot_id,
    version,
    status,
    created_by
  )
  values (
    target_tenant_id,
    target_connection_id,
    new_snapshot_id,
    new_version,
    'draft',
    actor_user_id
  )
  returning id into new_semantic_version_id;

  for table_item in
    select value from jsonb_array_elements(semantic_table_projection)
  loop
    insert into public.semantic_tables (
      tenant_id,
      semantic_version_id,
      physical_schema,
      physical_name,
      active,
      metadata
    )
    values (
      target_tenant_id,
      new_semantic_version_id,
      table_item->>'physical_schema',
      table_item->>'physical_name',
      false,
      coalesce(table_item->'metadata', '{}'::jsonb)
    )
    returning id into new_table_id;

    for column_item in
      select value
      from jsonb_array_elements(
        coalesce(table_item->'columns', '[]'::jsonb)
      )
    loop
      insert into public.semantic_columns (
        tenant_id,
        semantic_table_id,
        physical_name,
        data_type,
        role,
        pii,
        metadata
      )
      values (
        target_tenant_id,
        new_table_id,
        column_item->>'physical_name',
        column_item->>'data_type',
        column_item->>'role',
        coalesce((column_item->>'pii')::boolean, false),
        coalesce(column_item->'metadata', '{}'::jsonb)
      );
    end loop;
  end loop;

  for relationship_item in
    select value from jsonb_array_elements(relationship_projection)
  loop
    select id
    into from_table_id
    from public.semantic_tables projected_table
    where projected_table.tenant_id = target_tenant_id
      and projected_table.semantic_version_id = new_semantic_version_id
      and projected_table.physical_schema =
        relationship_item->>'from_schema'
      and projected_table.physical_name =
        relationship_item->>'from_table';

    select id
    into to_table_id
    from public.semantic_tables projected_table
    where projected_table.tenant_id = target_tenant_id
      and projected_table.semantic_version_id = new_semantic_version_id
      and projected_table.physical_schema =
        relationship_item->>'to_schema'
      and projected_table.physical_name =
        relationship_item->>'to_table';

    if from_table_id is null or to_table_id is null then
      raise exception 'relationship references unknown table'
        using errcode = '23503';
    end if;

    insert into public.semantic_relationships (
      tenant_id,
      semantic_version_id,
      from_table_id,
      from_columns,
      to_table_id,
      to_columns,
      cardinality,
      semantic_status,
      source,
      constraint_name,
      update_rule,
      delete_rule,
      is_disabled,
      is_not_trusted,
      verified_by_db,
      metadata
    )
    values (
      target_tenant_id,
      new_semantic_version_id,
      from_table_id,
      array(
        select jsonb_array_elements_text(
          relationship_item->'from_columns'
        )
      ),
      to_table_id,
      array(
        select jsonb_array_elements_text(
          relationship_item->'to_columns'
        )
      ),
      relationship_item->>'cardinality',
      'confirmed',
      'database_fk',
      relationship_item->>'constraint_name',
      relationship_item->>'update_rule',
      relationship_item->>'delete_rule',
      coalesce((relationship_item->>'is_disabled')::boolean, false),
      coalesce((relationship_item->>'is_not_trusted')::boolean, false),
      coalesce((relationship_item->>'verified_by_db')::boolean, true),
      jsonb_build_object(
        'snapshot_source', 'db_fk',
        'source_mapping', 'db_fk->database_fk'
      )
    );
  end loop;

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
    'schema.introspected',
    'db_connection',
    target_connection_id,
    jsonb_build_object(
      'schema_snapshot_id', new_snapshot_id,
      'semantic_version_id', new_semantic_version_id,
      'schema_hash', technical_snapshot->>'schema_hash',
      'engine_version', technical_snapshot->>'engine_version',
      'coverage_status', technical_snapshot->>'coverage_status',
      'table_count', target_table_count,
      'column_count', target_column_count
    )
  );

  return query
  select new_snapshot_id, new_semantic_version_id, new_version;
end;
$$;

revoke all on function app_private.persist_technical_schema_import(
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
) from public, anon, authenticated;

grant execute on function app_private.persist_technical_schema_import(
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
) to service_role;

create or replace function public.persist_technical_schema_import(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_engine public.connection_engine,
  technical_snapshot jsonb,
  target_summary jsonb,
  semantic_table_projection jsonb,
  relationship_projection jsonb,
  target_table_count integer,
  target_column_count integer,
  target_introspected_at timestamptz
)
returns table (
  schema_snapshot_id uuid,
  semantic_version_id uuid,
  semantic_version_number integer
)
language sql
set search_path = public, app_private, pg_temp
as $$
  select *
  from app_private.persist_technical_schema_import(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    target_engine,
    technical_snapshot,
    target_summary,
    semantic_table_projection,
    relationship_projection,
    target_table_count,
    target_column_count,
    target_introspected_at
  );
$$;

revoke all on function public.persist_technical_schema_import(
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
) from public, anon, authenticated;

grant execute on function public.persist_technical_schema_import(
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
) to service_role;

grant select (
  id,
  tenant_id,
  connection_id,
  engine,
  snapshot_version,
  table_count,
  column_count,
  introspected_at,
  engine_version,
  schema_hash,
  coverage_status,
  coverage_warnings,
  summary,
  created_by,
  created_at
) on table public.schema_snapshots to authenticated;

create view public.schema_snapshot_summaries
with (security_invoker = true)
as
select
  id,
  tenant_id,
  connection_id,
  engine,
  snapshot_version,
  table_count,
  column_count,
  introspected_at,
  engine_version,
  schema_hash,
  coverage_status,
  coverage_warnings,
  summary,
  created_by,
  created_at
from public.schema_snapshots;

revoke all privileges on table public.schema_snapshot_summaries
  from anon, authenticated;
grant select on table public.schema_snapshot_summaries to authenticated;
