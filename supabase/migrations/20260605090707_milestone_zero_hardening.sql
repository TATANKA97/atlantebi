grant usage on schema app_private to service_role;

alter table public.schema_snapshots
  add column engine_version text,
  add column schema_hash text
    check (schema_hash is null or schema_hash ~ '^[0-9a-f]{64}$'),
  add column coverage_state text
    check (coverage_state is null or coverage_state in ('complete', 'partial', 'unknown')),
  add column coverage_warnings jsonb not null default '[]'::jsonb
    check (jsonb_typeof(coverage_warnings) = 'array');

update public.schema_snapshots
set
  engine_version = snapshot->>'engine_version',
  schema_hash = snapshot->>'schema_hash',
  coverage_state = coalesce(snapshot->>'coverage_state', 'unknown'),
  coverage_warnings = coalesce(snapshot->'coverage_warnings', '[]'::jsonb);

revoke all privileges on table public.schema_snapshots from anon;
revoke all privileges on table public.schema_snapshots from authenticated;
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
  coverage_state,
  coverage_warnings,
  created_by,
  created_at
) on table public.schema_snapshots to authenticated;

revoke insert, update, delete on table public.db_connections from authenticated;
revoke insert, update, delete on table public.schema_snapshots from authenticated;
revoke insert, update, delete on table public.semantic_versions from authenticated;
revoke insert, update, delete on table public.semantic_tables from authenticated;
revoke insert, update, delete on table public.semantic_columns from authenticated;
revoke insert, update, delete on table public.semantic_relationships from authenticated;

drop policy if exists "tenant editors can create connections" on public.db_connections;
drop policy if exists "tenant editors can update connections" on public.db_connections;
drop policy if exists "tenant admins can delete connections" on public.db_connections;
drop policy if exists "tenant editors can create schema snapshots" on public.schema_snapshots;
drop policy if exists "tenant editors can manage semantic versions" on public.semantic_versions;
drop policy if exists "tenant editors can manage semantic tables" on public.semantic_tables;
drop policy if exists "tenant editors can manage semantic columns" on public.semantic_columns;
drop policy if exists "tenant editors can manage semantic relationships" on public.semantic_relationships;

create or replace function app_private.is_connection_editor(
  target_tenant_id uuid,
  target_user_id uuid
)
returns boolean
language sql
stable
set search_path = public, pg_temp
as $$
  select exists (
    select 1
    from public.tenant_memberships membership
    where membership.tenant_id = target_tenant_id
      and membership.user_id = target_user_id
      and membership.status = 'active'
      and membership.role in ('owner', 'admin', 'editor')
  );
$$;

create or replace function app_private.save_connection_test_result(
  actor_user_id uuid,
  connection_payload jsonb
)
returns uuid
language plpgsql
set search_path = public, pg_temp
as $$
declare
  connection_id uuid := (connection_payload->>'id')::uuid;
  target_tenant_id uuid := (connection_payload->>'tenant_id')::uuid;
  target_status public.connection_status := (connection_payload->>'status')::public.connection_status;
  target_secret_ref text := connection_payload->>'secret_ref';
  expected_secret_ref text := connection_payload->>'expected_secret_ref';
  allowed_keys constant text[] := array[
    'id',
    'tenant_id',
    'name',
    'engine',
    'network_mode',
    'host',
    'port',
    'database_name',
    'username',
    'tls_required',
    'tls_server_name',
    'trust_server_certificate',
    'expected_secret_ref',
    'secret_ref',
    'status',
    'last_test_status',
    'last_test_error',
    'last_tested_at'
  ];
begin
  if connection_payload - allowed_keys <> '{}'::jsonb then
    raise exception 'unsupported connection metadata field'
      using errcode = '22023';
  end if;

  if not app_private.is_connection_editor(target_tenant_id, actor_user_id) then
    raise exception 'connection editor role required'
      using errcode = '42501';
  end if;

  if target_status = 'ready' and target_secret_ref is null then
    raise exception 'ready connection requires secret reference'
      using errcode = '23514';
  end if;

  insert into public.db_connections (
    id,
    tenant_id,
    name,
    engine,
    network_mode,
    host,
    port,
    database_name,
    username,
    tls_required,
    tls_server_name,
    trust_server_certificate,
    secret_ref,
    status,
    last_test_status,
    last_test_error,
    last_tested_at,
    created_by,
    updated_at
  )
  values (
    connection_id,
    target_tenant_id,
    connection_payload->>'name',
    (connection_payload->>'engine')::public.connection_engine,
    (connection_payload->>'network_mode')::public.network_mode,
    connection_payload->>'host',
    (connection_payload->>'port')::integer,
    connection_payload->>'database_name',
    connection_payload->>'username',
    (connection_payload->>'tls_required')::boolean,
    connection_payload->>'tls_server_name',
    coalesce((connection_payload->>'trust_server_certificate')::boolean, false),
    target_secret_ref,
    target_status,
    (connection_payload->>'last_test_status')::public.connection_test_status,
    connection_payload->>'last_test_error',
    (connection_payload->>'last_tested_at')::timestamptz,
    actor_user_id,
    now()
  )
  on conflict (id) do update
  set
    name = excluded.name,
    engine = excluded.engine,
    network_mode = excluded.network_mode,
    host = excluded.host,
    port = excluded.port,
    database_name = excluded.database_name,
    username = excluded.username,
    tls_required = excluded.tls_required,
    tls_server_name = excluded.tls_server_name,
    trust_server_certificate = excluded.trust_server_certificate,
    secret_ref = excluded.secret_ref,
    status = excluded.status,
    last_test_status = excluded.last_test_status,
    last_test_error = excluded.last_test_error,
    last_tested_at = excluded.last_tested_at,
    updated_at = now()
  where public.db_connections.tenant_id = excluded.tenant_id
    and public.db_connections.secret_ref is not distinct from expected_secret_ref
    and (
      (
        public.db_connections.host = excluded.host
        and public.db_connections.port = excluded.port
        and public.db_connections.database_name = excluded.database_name
        and public.db_connections.username = excluded.username
        and public.db_connections.tls_server_name is not distinct from excluded.tls_server_name
      )
      or excluded.secret_ref is null
      or excluded.secret_ref is distinct from public.db_connections.secret_ref
    );

  if not found then
    raise exception 'connection state changed while the test was running'
      using errcode = '42501';
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
    'connection.test_result_saved',
    'db_connection',
    connection_id,
    jsonb_build_object(
      'status', target_status,
      'test_status', connection_payload->>'last_test_status'
    )
  );

  return connection_id;
end;
$$;

revoke all on function app_private.save_connection_test_result(uuid, jsonb) from public;
revoke all on function app_private.save_connection_test_result(uuid, jsonb) from anon;
revoke all on function app_private.save_connection_test_result(uuid, jsonb) from authenticated;
grant execute on function app_private.save_connection_test_result(uuid, jsonb) to service_role;

create or replace function public.save_connection_test_result(
  actor_user_id uuid,
  connection_payload jsonb
)
returns uuid
language sql
set search_path = public, app_private, pg_temp
as $$
  select app_private.save_connection_test_result(actor_user_id, connection_payload);
$$;

revoke all on function public.save_connection_test_result(uuid, jsonb) from public;
revoke all on function public.save_connection_test_result(uuid, jsonb) from anon;
revoke all on function public.save_connection_test_result(uuid, jsonb) from authenticated;
grant execute on function public.save_connection_test_result(uuid, jsonb) to service_role;

alter table public.semantic_tables
  add constraint semantic_tables_tenant_version_id_unique
    unique (tenant_id, semantic_version_id, id);

alter table public.schema_snapshots
  add constraint schema_snapshots_tenant_connection_id_unique
    unique (tenant_id, connection_id, id);

alter table public.semantic_versions
  drop constraint semantic_versions_schema_snapshot_tenant_fk,
  add constraint semantic_versions_schema_snapshot_connection_fk
    foreign key (tenant_id, connection_id, schema_snapshot_id)
    references public.schema_snapshots(tenant_id, connection_id, id)
    on delete set null;

alter table public.semantic_relationships
  drop constraint semantic_relationships_from_table_tenant_fk,
  drop constraint semantic_relationships_to_table_tenant_fk,
  add constraint semantic_relationships_from_table_version_fk
    foreign key (tenant_id, semantic_version_id, from_table_id)
    references public.semantic_tables(tenant_id, semantic_version_id, id)
    on delete cascade,
  add constraint semantic_relationships_to_table_version_fk
    foreign key (tenant_id, semantic_version_id, to_table_id)
    references public.semantic_tables(tenant_id, semantic_version_id, id)
    on delete cascade;

create or replace function app_private.persist_technical_schema_import(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_engine public.connection_engine,
  technical_snapshot jsonb,
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
set search_path = public, pg_temp
as $$
declare
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

  if not exists (
    select 1
    from public.db_connections connection
    where connection.id = target_connection_id
      and connection.tenant_id = target_tenant_id
      and connection.engine = target_engine
      and connection.status = 'ready'
  ) then
    raise exception 'ready connection not found'
      using errcode = 'P0002';
  end if;

  if jsonb_typeof(semantic_table_projection) <> 'array'
    or jsonb_typeof(relationship_projection) <> 'array' then
    raise exception 'semantic projection must be arrays'
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
    coverage_state,
    coverage_warnings,
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
    coalesce(technical_snapshot->>'coverage_state', 'unknown'),
    coalesce(technical_snapshot->'coverage_warnings', '[]'::jsonb),
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
      select value from jsonb_array_elements(coalesce(table_item->'columns', '[]'::jsonb))
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
    from public.semantic_tables as projected_table
    where projected_table.tenant_id = target_tenant_id
      and projected_table.semantic_version_id = new_semantic_version_id
      and projected_table.physical_schema = relationship_item->>'from_schema'
      and projected_table.physical_name = relationship_item->>'from_table';

    select id
    into to_table_id
    from public.semantic_tables as projected_table
    where projected_table.tenant_id = target_tenant_id
      and projected_table.semantic_version_id = new_semantic_version_id
      and projected_table.physical_schema = relationship_item->>'to_schema'
      and projected_table.physical_name = relationship_item->>'to_table';

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
      array(select jsonb_array_elements_text(relationship_item->'from_columns')),
      to_table_id,
      array(select jsonb_array_elements_text(relationship_item->'to_columns')),
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
  integer,
  integer,
  timestamptz
) from public;
revoke all on function app_private.persist_technical_schema_import(
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
) from anon;
revoke all on function app_private.persist_technical_schema_import(
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
) from authenticated;
grant execute on function app_private.persist_technical_schema_import(
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
) to service_role;

create or replace function public.persist_technical_schema_import(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_engine public.connection_engine,
  technical_snapshot jsonb,
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
  integer,
  integer,
  timestamptz
) from public;
revoke all on function public.persist_technical_schema_import(
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
) from anon;
revoke all on function public.persist_technical_schema_import(
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
) from authenticated;
grant execute on function public.persist_technical_schema_import(
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
) to service_role;

drop view if exists public.schema_snapshot_summaries;

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
  coverage_state,
  coverage_warnings,
  created_by,
  created_at
from public.schema_snapshots;

revoke all privileges on table public.schema_snapshot_summaries from anon;
revoke all privileges on table public.schema_snapshot_summaries from authenticated;
grant select on table public.schema_snapshot_summaries to authenticated;

create or replace function app_private.jsonb_has_forbidden_metadata_key(target jsonb)
returns boolean
language sql
immutable
set search_path = public, pg_temp
as $$
with recursive walk(value) as (
  select target
  union all
  select child.value
  from walk
  cross join lateral (
    select object_entry.value
    from jsonb_each(
      case
        when jsonb_typeof(walk.value) = 'object' then walk.value
        else '{}'::jsonb
      end
    ) as object_entry
    union all
    select array_entry.value
    from jsonb_array_elements(
      case
        when jsonb_typeof(walk.value) = 'array' then walk.value
        else '[]'::jsonb
      end
    ) as array_entry
  ) as child
)
select exists (
  select 1
  from walk
  where jsonb_typeof(value) = 'object'
    and exists (
      select 1
      from jsonb_object_keys(value) as object_key(key)
      where lower(object_key.key) = any (array[
        'secret_ref',
        'password',
        'db_password',
        'connection_string',
        'dsn',
        'secret_value',
        'private_key',
        'sample_rows',
        'preview_rows',
        'result_rows',
        'raw_rows',
        'cached_result',
        'data_cache'
      ])
    )
);
$$;
