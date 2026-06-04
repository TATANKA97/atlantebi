create or replace function app_private.jsonb_has_forbidden_metadata_key(target jsonb)
returns boolean
language sql
immutable
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

alter table public.schema_snapshots
  add column snapshot_version integer not null default 1
    check (snapshot_version = 1),
  add column introspected_at timestamptz not null default now(),
  add constraint schema_snapshots_snapshot_metadata_only
    check (
      jsonb_typeof(snapshot) = 'object'
      and snapshot ? 'engine'
      and snapshot ? 'tables'
      and snapshot ? 'foreign_keys'
      and not app_private.jsonb_has_forbidden_metadata_key(snapshot)
    );

create index schema_snapshots_tenant_connection_created_idx
  on public.schema_snapshots(tenant_id, connection_id, created_at desc);

create or replace view public.schema_snapshot_summaries
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
  created_by,
  created_at
from public.schema_snapshots;

revoke all privileges on table public.schema_snapshot_summaries from anon;
revoke all privileges on table public.schema_snapshot_summaries from authenticated;
grant select on table public.schema_snapshot_summaries to authenticated;
