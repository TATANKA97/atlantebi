alter table public.semantic_relationships
  add column if not exists constraint_name text,
  add column if not exists update_rule text,
  add column if not exists delete_rule text,
  add column if not exists is_disabled boolean not null default false,
  add column if not exists is_not_trusted boolean not null default false,
  add column if not exists verified_by_db boolean not null default false,
  add column if not exists metadata jsonb not null default '{}'::jsonb;

update public.semantic_relationships
set
  constraint_name = coalesce(constraint_name, 'legacy_database_fk_' || id::text),
  metadata = metadata || jsonb_build_object(
    'snapshot_source',
    'legacy_database_fk',
    'source_mapping',
    'db_fk->database_fk'
  )
where source = 'database_fk'
  and constraint_name is null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'semantic_relationships_db_fk_requires_constraint_name'
  ) then
    alter table public.semantic_relationships
      add constraint semantic_relationships_db_fk_requires_constraint_name
        check (source <> 'database_fk' or constraint_name is not null);
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'semantic_relationships_technical_metadata_object'
  ) then
    alter table public.semantic_relationships
      add constraint semantic_relationships_technical_metadata_object
        check (jsonb_typeof(metadata) = 'object');
  end if;
end;
$$;

comment on column public.semantic_relationships.constraint_name is
  'Technical FK constraint name mapped from schema_snapshots.snapshot foreign_keys[].name.';
comment on column public.semantic_relationships.source is
  'Semantic relationship source. Technical snapshot db_fk maps to database_fk here.';

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
  snapshot->>'engine_version' as engine_version,
  snapshot->>'schema_hash' as schema_hash,
  coalesce(snapshot->'coverage_warnings', '[]'::jsonb) as coverage_warnings,
  created_by,
  created_at
from public.schema_snapshots;

revoke all privileges on table public.schema_snapshot_summaries from anon;
revoke all privileges on table public.schema_snapshot_summaries from authenticated;
grant select on table public.schema_snapshot_summaries to authenticated;
