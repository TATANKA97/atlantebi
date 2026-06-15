-- Semantic Layer V1 is a breaking dev-stage cutover. Legacy semantic data is
-- deliberately purged; the version registry is renamed so existing widget and
-- query-history foreign keys keep pointing at the same relation OID.

revoke all privileges on table public.semantic_versions
  from public, anon, authenticated, service_role;
revoke all privileges on table public.semantic_tables
  from public, anon, authenticated, service_role;
revoke all privileges on table public.semantic_columns
  from public, anon, authenticated, service_role;
revoke all privileges on table public.semantic_relationships
  from public, anon, authenticated, service_role;
revoke all privileges on table public.semantic_metrics
  from public, anon, authenticated, service_role;
revoke all privileges on table public.business_anchors
  from public, anon, authenticated, service_role;

drop policy if exists "members can read semantic versions"
  on public.semantic_versions;
drop policy if exists "tenant editors can manage semantic versions"
  on public.semantic_versions;
drop policy if exists "members can read semantic tables"
  on public.semantic_tables;
drop policy if exists "tenant editors can manage semantic tables"
  on public.semantic_tables;
drop policy if exists "members can read semantic columns"
  on public.semantic_columns;
drop policy if exists "tenant editors can manage semantic columns"
  on public.semantic_columns;
drop policy if exists "members can read semantic relationships"
  on public.semantic_relationships;
drop policy if exists "tenant editors can manage semantic relationships"
  on public.semantic_relationships;
drop policy if exists "members can read semantic metrics"
  on public.semantic_metrics;
drop policy if exists "tenant editors can manage semantic metrics"
  on public.semantic_metrics;
drop policy if exists "members can read business anchors"
  on public.business_anchors;
drop policy if exists "tenant editors can manage business anchors"
  on public.business_anchors;

-- ON DELETE CASCADE clears legacy projections; widget/query-history references
-- use ON DELETE SET NULL and remain structurally valid after the registry rename.
delete from public.semantic_versions;

drop table public.business_anchors;
drop table public.semantic_metrics;
drop table public.semantic_relationships;
drop table public.semantic_columns;
drop table public.semantic_tables;

alter table public.semantic_versions
  rename to semantic_layer_versions;

alter table public.semantic_layer_versions
  rename constraint semantic_versions_pkey
  to semantic_layer_versions_pkey;
alter table public.semantic_layer_versions
  rename constraint semantic_versions_tenant_id_id_unique
  to semantic_layer_versions_tenant_id_id_unique;
alter table public.semantic_layer_versions
  rename constraint semantic_versions_connection_tenant_fk
  to semantic_layer_versions_connection_tenant_fk;
alter table public.semantic_layer_versions
  rename constraint semantic_versions_tenant_id_connection_id_version_key
  to semantic_layer_versions_tenant_connection_version_key;

alter index if exists public.semantic_versions_tenant_status_idx
  rename to semantic_layer_versions_tenant_status_idx;
alter index if exists public.semantic_versions_tenant_connection_idx
  rename to semantic_layer_versions_tenant_connection_idx;
alter index if exists public.semantic_versions_created_by_idx
  rename to semantic_layer_versions_created_by_idx;
alter index if exists public.semantic_versions_connection_id_idx
  rename to semantic_layer_versions_connection_id_idx;

alter table public.semantic_layer_versions
  drop constraint if exists semantic_versions_schema_snapshot_connection_fk,
  drop column if exists schema_snapshot_id,
  drop column if exists activated_at,
  drop column status;

create type public.semantic_layer_version_status as enum (
  'draft',
  'proposed',
  'active',
  'archived'
);

create type public.semantic_layer_freshness as enum (
  'fresh',
  'stale'
);

alter table public.semantic_layer_versions
  add constraint semantic_layer_versions_tenant_connection_id_unique
    unique (tenant_id, connection_id, id),
  add column queryability_graph_version_id uuid not null,
  add column base_graph_hash text not null
    check (base_graph_hash ~ '^[0-9a-f]{64}$'),
  add column contract_version text not null
    check (contract_version = 'semantic_layer.v1'),
  add column status public.semantic_layer_version_status not null
    default 'draft',
  add column freshness public.semantic_layer_freshness not null
    default 'fresh',
  add column builder_version text not null
    check (length(builder_version) between 1 and 100),
  add column ai_model_version text
    check (
      ai_model_version is null
      or length(ai_model_version) between 1 and 255
    ),
  add column ai_prompt_version text
    check (
      ai_prompt_version is null
      or length(ai_prompt_version) between 1 and 100
    ),
  add column validator_version text not null
    check (length(validator_version) between 1 and 100),
  add column policy_version text not null
    check (length(policy_version) between 1 and 100),
  add column revision integer not null default 1 check (revision > 0),
  add column validated_revision integer
    check (validated_revision is null or validated_revision > 0),
  add column semantic_hash text not null
    check (semantic_hash ~ '^[0-9a-f]{64}$'),
  add column artifact jsonb not null,
  add column validation_report jsonb not null,
  add column activated_at timestamptz,
  add column archived_at timestamptz,
  add column rebased_from_version_id uuid,
  add column activation_policy text not null default 'auto_validated'
    check (activation_policy in ('auto_validated', 'manual_review')),
  add constraint semantic_layer_versions_graph_fk
    foreign key (
      tenant_id,
      connection_id,
      queryability_graph_version_id
    )
    references public.queryability_graph_versions(
      tenant_id,
      connection_id,
      id
    )
    on delete restrict,
  add constraint semantic_layer_versions_rebased_from_fk
    foreign key (tenant_id, connection_id, rebased_from_version_id)
    references public.semantic_layer_versions(tenant_id, connection_id, id)
    on delete restrict,
  add constraint semantic_layer_versions_artifact_shape_check
    check (
      jsonb_typeof(artifact) = 'object'
      and artifact->>'contract_version' = 'semantic_layer.v1'
      and jsonb_typeof(artifact->'tables') = 'array'
      and jsonb_typeof(artifact->'columns') = 'array'
      and jsonb_typeof(artifact->'relationships') = 'array'
      and jsonb_typeof(artifact->'business_concepts') = 'array'
      and jsonb_typeof(artifact->'ambiguities') = 'array'
      and jsonb_typeof(artifact->'metrics') = 'array'
      and jsonb_typeof(artifact->'validation_report') = 'object'
    ),
  add constraint semantic_layer_versions_validation_shape_check
    check (
      jsonb_typeof(validation_report) = 'object'
      and validation_report->>'status' in (
        'not_validated',
        'valid',
        'valid_with_warnings',
        'blocked'
      )
      and jsonb_typeof(validation_report->'blocking_errors') = 'array'
      and jsonb_typeof(validation_report->'warnings') = 'array'
      and jsonb_typeof(validation_report->'info') = 'array'
    ),
  add constraint semantic_layer_versions_validation_revision_check
    check (
      validated_revision is null
      or validated_revision <= revision
    ),
  add constraint semantic_layer_versions_lifecycle_timestamp_check
    check (
      (status <> 'active' or activated_at is not null)
      and (status <> 'archived' or archived_at is not null)
    );

drop type public.semantic_version_status;

create unique index semantic_layer_versions_one_active_per_connection_idx
  on public.semantic_layer_versions (tenant_id, connection_id)
  where status = 'active';

create index semantic_layer_versions_graph_idx
  on public.semantic_layer_versions (
    tenant_id,
    connection_id,
    queryability_graph_version_id
  );

create index semantic_layer_versions_connection_created_idx
  on public.semantic_layer_versions (
    tenant_id,
    connection_id,
    created_at desc
  );

create table public.semantic_layer_tables (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  semantic_version_id uuid not null,
  node_key text not null check (node_key ~ '^[0-9a-f]{64}$'),
  schema_name text not null check (length(schema_name) between 1 and 255),
  object_name text not null check (length(object_name) between 1 and 255),
  object_type text not null check (object_type in ('table', 'view')),
  display_name text,
  status text not null check (
    status in (
      'system_seeded',
      'ai_proposed',
      'human_verified',
      'rejected',
      'disabled',
      'stale'
    )
  ),
  included boolean not null,
  queryability_status text not null
    check (queryability_status in ('queryable', 'excluded')),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  unique (semantic_version_id, node_key),
  unique (tenant_id, semantic_version_id, id),
  foreign key (tenant_id, semantic_version_id)
    references public.semantic_layer_versions(tenant_id, id)
    on delete cascade
);

create table public.semantic_layer_columns (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  semantic_version_id uuid not null,
  column_key text not null check (column_key ~ '^[0-9a-f]{64}$'),
  node_key text not null check (node_key ~ '^[0-9a-f]{64}$'),
  physical_name text not null check (length(physical_name) between 1 and 255),
  semantic_role text,
  status text not null check (
    status in (
      'system_seeded',
      'ai_proposed',
      'human_verified',
      'rejected',
      'disabled',
      'stale'
    )
  ),
  included boolean not null,
  queryability_status text not null
    check (queryability_status in ('queryable', 'excluded')),
  inherited_sensitivity text not null
    check (inherited_sensitivity in ('none', 'pii', 'sensitive')),
  sensitivity text not null
    check (sensitivity in ('none', 'pii', 'sensitive')),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  unique (semantic_version_id, column_key),
  foreign key (tenant_id, semantic_version_id)
    references public.semantic_layer_versions(tenant_id, id)
    on delete cascade,
  foreign key (semantic_version_id, node_key)
    references public.semantic_layer_tables(semantic_version_id, node_key)
    on delete cascade
);

create table public.semantic_layer_relationships (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  semantic_version_id uuid not null,
  edge_key text not null check (edge_key ~ '^[0-9a-f]{64}$'),
  from_node_key text not null check (from_node_key ~ '^[0-9a-f]{64}$'),
  to_node_key text not null check (to_node_key ~ '^[0-9a-f]{64}$'),
  status text not null check (
    status in (
      'system_seeded',
      'ai_proposed',
      'human_verified',
      'rejected',
      'disabled',
      'stale'
    )
  ),
  enabled boolean not null,
  relationship_shape text not null
    check (relationship_shape in ('one_to_one', 'many_to_one')),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  unique (semantic_version_id, edge_key),
  foreign key (tenant_id, semantic_version_id)
    references public.semantic_layer_versions(tenant_id, id)
    on delete cascade,
  foreign key (semantic_version_id, from_node_key)
    references public.semantic_layer_tables(semantic_version_id, node_key)
    on delete cascade,
  foreign key (semantic_version_id, to_node_key)
    references public.semantic_layer_tables(semantic_version_id, node_key)
    on delete cascade
);

create table public.semantic_layer_business_concepts (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  semantic_version_id uuid not null,
  business_concept_key uuid not null,
  canonical_name text not null
    check (canonical_name ~ '^[a-z][a-z0-9_]{1,99}$'),
  display_name text not null check (length(display_name) between 1 and 255),
  status text not null check (
    status in (
      'system_seeded',
      'ai_proposed',
      'human_verified',
      'rejected',
      'disabled',
      'stale'
    )
  ),
  provenance text not null check (provenance in ('system', 'ai', 'human')),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  unique (semantic_version_id, business_concept_key),
  unique (semantic_version_id, canonical_name),
  foreign key (tenant_id, semantic_version_id)
    references public.semantic_layer_versions(tenant_id, id)
    on delete cascade
);

create table public.semantic_layer_ambiguities (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  semantic_version_id uuid not null,
  ambiguity_key uuid not null,
  code text not null check (code ~ '^[A-Z][A-Z0-9_]{1,99}$'),
  target_type text not null check (
    target_type in ('table', 'column', 'business_concept', 'metric')
  ),
  target_key text not null check (length(target_key) between 1 and 255),
  status text not null check (status in ('open', 'resolved')),
  provenance text not null check (provenance in ('ai', 'human')),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  unique (semantic_version_id, ambiguity_key),
  foreign key (tenant_id, semantic_version_id)
    references public.semantic_layer_versions(tenant_id, id)
    on delete cascade
);

create table public.semantic_layer_metrics (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  semantic_version_id uuid not null,
  metric_key uuid not null,
  canonical_name text not null
    check (canonical_name ~ '^[a-z][a-z0-9_]{1,99}$'),
  metric_definition_hash text not null
    check (metric_definition_hash ~ '^[0-9a-f]{64}$'),
  business_concept_key uuid not null,
  metric_variant text not null
    check (metric_variant ~ '^[a-z][a-z0-9_]{1,99}$'),
  name text not null check (length(name) between 1 and 255),
  status text not null check (
    status in (
      'system_seeded',
      'ai_proposed',
      'human_verified',
      'rejected',
      'disabled',
      'stale'
    )
  ),
  source_table_key text not null check (source_table_key ~ '^[0-9a-f]{64}$'),
  aggregation text not null
    check (aggregation in ('count', 'count_distinct', 'sum', 'avg', 'min', 'max')),
  measure_column_key text
    check (measure_column_key is null or measure_column_key ~ '^[0-9a-f]{64}$'),
  grain_table_key text not null check (grain_table_key ~ '^[0-9a-f]{64}$'),
  grain_column_keys text[] not null check (cardinality(grain_column_keys) > 0),
  compiler_eligibility text not null check (
    compiler_eligibility in (
      'eligible',
      'eligible_with_disclosure',
      'clarification_required',
      'not_eligible'
    )
  ),
  confidence_score numeric(6, 5) not null
    check (confidence_score between 0 and 1),
  confidence_label text not null check (
    confidence_label in ('high', 'medium', 'low', 'blocked')
  ),
  enabled boolean not null,
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  unique (semantic_version_id, metric_key),
  unique (semantic_version_id, canonical_name),
  foreign key (tenant_id, semantic_version_id)
    references public.semantic_layer_versions(tenant_id, id)
    on delete cascade,
  foreign key (semantic_version_id, business_concept_key)
    references public.semantic_layer_business_concepts(
      semantic_version_id,
      business_concept_key
    )
    on delete cascade,
  foreign key (semantic_version_id, source_table_key)
    references public.semantic_layer_tables(semantic_version_id, node_key)
    on delete restrict,
  foreign key (semantic_version_id, grain_table_key)
    references public.semantic_layer_tables(semantic_version_id, node_key)
    on delete restrict
);

create table public.semantic_layer_metric_common_dimensions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  semantic_version_id uuid not null,
  metric_key uuid not null,
  dimension_column_key text not null
    check (dimension_column_key ~ '^[0-9a-f]{64}$'),
  edge_path text[] not null default '{}',
  safety text not null check (safety in ('safe', 'forbidden')),
  reason_code text not null check (length(reason_code) between 1 and 100),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  unique (semantic_version_id, metric_key, dimension_column_key),
  foreign key (tenant_id, semantic_version_id)
    references public.semantic_layer_versions(tenant_id, id)
    on delete cascade,
  foreign key (semantic_version_id, metric_key)
    references public.semantic_layer_metrics(semantic_version_id, metric_key)
    on delete cascade,
  foreign key (semantic_version_id, dimension_column_key)
    references public.semantic_layer_columns(semantic_version_id, column_key)
    on delete cascade
);

create table public.semantic_generation_runs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  connection_id uuid not null,
  semantic_version_id uuid not null,
  provider text not null check (length(provider) between 1 and 100),
  model_version text not null check (length(model_version) between 1 and 255),
  prompt_version text not null check (length(prompt_version) between 1 and 100),
  input_hash text not null check (input_hash ~ '^[0-9a-f]{64}$'),
  proposal_hash text not null check (proposal_hash ~ '^[0-9a-f]{64}$'),
  response_id text not null check (length(response_id) between 1 and 255),
  generated_at timestamptz not null,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  unique (tenant_id, connection_id, response_id),
  foreign key (tenant_id, connection_id)
    references public.db_connections(tenant_id, id)
    on delete cascade,
  foreign key (tenant_id, semantic_version_id)
    references public.semantic_layer_versions(tenant_id, id)
    on delete cascade
);

create index semantic_layer_tables_version_idx
  on public.semantic_layer_tables(tenant_id, semantic_version_id);
create index semantic_layer_columns_version_node_idx
  on public.semantic_layer_columns(tenant_id, semantic_version_id, node_key);
create index semantic_layer_relationships_version_idx
  on public.semantic_layer_relationships(tenant_id, semantic_version_id);
create index semantic_layer_metrics_version_eligibility_idx
  on public.semantic_layer_metrics(
    tenant_id,
    semantic_version_id,
    compiler_eligibility
  );
create index semantic_generation_runs_version_idx
  on public.semantic_generation_runs(
    tenant_id,
    semantic_version_id,
    created_at desc
  );

alter table public.semantic_layer_versions enable row level security;
alter table public.semantic_layer_tables enable row level security;
alter table public.semantic_layer_columns enable row level security;
alter table public.semantic_layer_relationships enable row level security;
alter table public.semantic_layer_business_concepts enable row level security;
alter table public.semantic_layer_ambiguities enable row level security;
alter table public.semantic_layer_metrics enable row level security;
alter table public.semantic_layer_metric_common_dimensions enable row level security;
alter table public.semantic_generation_runs enable row level security;

revoke all privileges on table public.semantic_layer_versions
  from public, anon, authenticated, service_role;
revoke all privileges on table public.semantic_layer_tables
  from public, anon, authenticated, service_role;
revoke all privileges on table public.semantic_layer_columns
  from public, anon, authenticated, service_role;
revoke all privileges on table public.semantic_layer_relationships
  from public, anon, authenticated, service_role;
revoke all privileges on table public.semantic_layer_business_concepts
  from public, anon, authenticated, service_role;
revoke all privileges on table public.semantic_layer_ambiguities
  from public, anon, authenticated, service_role;
revoke all privileges on table public.semantic_layer_metrics
  from public, anon, authenticated, service_role;
revoke all privileges on table public.semantic_layer_metric_common_dimensions
  from public, anon, authenticated, service_role;
revoke all privileges on table public.semantic_generation_runs
  from public, anon, authenticated, service_role;

grant select on table public.semantic_layer_versions to service_role;
grant select on table public.semantic_layer_tables to service_role;
grant select on table public.semantic_layer_columns to service_role;
grant select on table public.semantic_layer_relationships to service_role;
grant select on table public.semantic_layer_business_concepts to service_role;
grant select on table public.semantic_layer_ambiguities to service_role;
grant select on table public.semantic_layer_metrics to service_role;
grant select on table public.semantic_layer_metric_common_dimensions
  to service_role;
grant select on table public.semantic_generation_runs to service_role;

create or replace function app_private.is_semantic_layer_admin(
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
      and membership.role in ('owner', 'admin')
  );
$$;

revoke all on function app_private.is_semantic_layer_admin(uuid, uuid)
  from public, anon, authenticated, service_role;

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

create or replace function app_private.reject_immutable_semantic_layer()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
declare
  parent_status public.semantic_layer_version_status;
begin
  if current_setting('app.semantic_layer_rpc', true) = 'on' then
    return coalesce(new, old);
  end if;

  if tg_table_name = 'semantic_layer_versions' then
    parent_status := old.status;
  else
    select version.status
    into parent_status
    from public.semantic_layer_versions version
    where version.id = old.semantic_version_id;
  end if;

  if parent_status in ('active', 'archived') then
    raise exception 'active and archived semantic layer artifacts are immutable'
      using errcode = '55000';
  end if;

  return coalesce(new, old);
end;
$$;

create trigger semantic_layer_versions_immutable
before update or delete on public.semantic_layer_versions
for each row execute function app_private.reject_immutable_semantic_layer();

create trigger semantic_layer_tables_immutable
before update or delete on public.semantic_layer_tables
for each row execute function app_private.reject_immutable_semantic_layer();
create trigger semantic_layer_columns_immutable
before update or delete on public.semantic_layer_columns
for each row execute function app_private.reject_immutable_semantic_layer();
create trigger semantic_layer_relationships_immutable
before update or delete on public.semantic_layer_relationships
for each row execute function app_private.reject_immutable_semantic_layer();
create trigger semantic_layer_business_concepts_immutable
before update or delete on public.semantic_layer_business_concepts
for each row execute function app_private.reject_immutable_semantic_layer();
create trigger semantic_layer_ambiguities_immutable
before update or delete on public.semantic_layer_ambiguities
for each row execute function app_private.reject_immutable_semantic_layer();
create trigger semantic_layer_metrics_immutable
before update or delete on public.semantic_layer_metrics
for each row execute function app_private.reject_immutable_semantic_layer();
create trigger semantic_layer_metric_dimensions_immutable
before update or delete on public.semantic_layer_metric_common_dimensions
for each row execute function app_private.reject_immutable_semantic_layer();

create or replace function app_private.refresh_semantic_layer_freshness()
returns trigger
language plpgsql
security definer
set search_path = public, app_private, pg_temp
as $$
declare
  current_graph_hash text;
begin
  select graph.graph_hash
  into current_graph_hash
  from public.queryability_graph_versions graph
  where graph.tenant_id = new.tenant_id
    and graph.connection_id = new.connection_id
    and graph.id = new.graph_version_id;

  update public.semantic_layer_versions version
  set
    freshness = case
      when version.base_graph_hash = current_graph_hash
        then 'fresh'::public.semantic_layer_freshness
      else 'stale'::public.semantic_layer_freshness
    end,
    artifact = jsonb_set(
      version.artifact,
      '{freshness}',
      to_jsonb(
        case
          when version.base_graph_hash = current_graph_hash then 'fresh'::text
          else 'stale'::text
        end
      ),
      false
    ),
    updated_at = statement_timestamp()
  where version.tenant_id = new.tenant_id
    and version.connection_id = new.connection_id
    and version.status in ('draft', 'proposed');

  return new;
end;
$$;

create trigger queryability_derivation_refreshes_semantic_freshness
after insert on public.queryability_graph_derivations
for each row execute function app_private.refresh_semantic_layer_freshness();

create or replace function app_private.validate_semantic_layer_artifact(
  target_actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_graph_version_id uuid,
  target_artifact jsonb
)
returns void
language plpgsql
set search_path = public, app_private, pg_temp
as $$
declare
  graph_hash text;
  current_graph_hash text;
begin
  if not app_private.is_semantic_layer_admin(
    target_tenant_id,
    target_actor_user_id
  ) then
    raise exception 'semantic layer owner or admin role required'
      using errcode = '42501';
  end if;

  select graph.graph_hash
  into graph_hash
  from public.queryability_graph_versions graph
  where graph.id = target_graph_version_id
    and graph.tenant_id = target_tenant_id
    and graph.connection_id = target_connection_id;

  if graph_hash is null then
    raise exception 'queryability graph not found'
      using errcode = 'P0002';
  end if;

  select graph.graph_hash
  into current_graph_hash
  from public.queryability_graph_derivations derivation
  join public.queryability_graph_versions graph
    on graph.tenant_id = derivation.tenant_id
   and graph.connection_id = derivation.connection_id
   and graph.id = derivation.graph_version_id
  where derivation.tenant_id = target_tenant_id
    and derivation.connection_id = target_connection_id
  order by derivation.created_at desc, derivation.graph_version_id desc
  limit 1;

  if current_graph_hash is null or graph_hash <> current_graph_hash then
    raise exception 'semantic layer must target the current queryability graph'
      using errcode = '55000';
  end if;

  if jsonb_typeof(target_artifact) <> 'object'
    or target_artifact->>'contract_version' <> 'semantic_layer.v1'
    or target_artifact->>'tenant_id' <> target_tenant_id::text
    or target_artifact->>'connection_id' <> target_connection_id::text
    or target_artifact->>'queryability_graph_version_id'
      <> target_graph_version_id::text
    or target_artifact->>'base_graph_hash' <> graph_hash
    or target_artifact->>'freshness' <> 'fresh'
    or target_artifact->>'status' not in ('draft', 'proposed')
    or target_artifact->>'semantic_version_id'
      !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    or target_artifact->>'version' !~ '^[1-9][0-9]*$'
    or target_artifact->>'revision' !~ '^[1-9][0-9]*$'
    or target_artifact->>'semantic_hash' !~ '^[0-9a-f]{64}$'
    or jsonb_typeof(target_artifact->'tables') <> 'array'
    or jsonb_typeof(target_artifact->'columns') <> 'array'
    or jsonb_typeof(target_artifact->'relationships') <> 'array'
    or jsonb_typeof(target_artifact->'business_concepts') <> 'array'
    or jsonb_typeof(target_artifact->'ambiguities') <> 'array'
    or jsonb_typeof(target_artifact->'metrics') <> 'array'
    or jsonb_typeof(target_artifact->'validation_report') <> 'object'
    or jsonb_array_length(target_artifact->'tables') > 5000
    or jsonb_array_length(target_artifact->'columns') > 250000
    or jsonb_array_length(target_artifact->'relationships') > 250000
    or jsonb_array_length(target_artifact->'business_concepts') > 10000
    or jsonb_array_length(target_artifact->'ambiguities') > 10000
    or jsonb_array_length(target_artifact->'metrics') > 100000
  then
    raise exception 'semantic layer artifact is invalid'
      using errcode = '22023';
  end if;

  if exists (
    select 1
    from jsonb_array_elements(target_artifact->'tables') item
    where item->>'node_key' !~ '^[0-9a-f]{64}$'
      or item->>'status' not in (
        'system_seeded',
        'ai_proposed',
        'human_verified',
        'rejected',
        'disabled',
        'stale'
      )
      or item->>'queryability_status' not in ('queryable', 'excluded')
  ) or exists (
    select 1
    from jsonb_array_elements(target_artifact->'columns') item
    where item->>'column_key' !~ '^[0-9a-f]{64}$'
      or item->>'node_key' !~ '^[0-9a-f]{64}$'
      or item->>'sensitivity' not in ('none', 'pii', 'sensitive')
      or item->>'inherited_sensitivity' not in ('none', 'pii', 'sensitive')
  ) or exists (
    select 1
    from jsonb_array_elements(target_artifact->'relationships') item
    where item->>'edge_key' !~ '^[0-9a-f]{64}$'
  ) or exists (
    select 1
    from jsonb_array_elements(target_artifact->'metrics') item
    where item->>'metric_definition_hash' !~ '^[0-9a-f]{64}$'
      or item->>'compiler_eligibility' not in (
        'eligible',
        'eligible_with_disclosure',
        'clarification_required',
        'not_eligible'
      )
  ) then
    raise exception 'semantic layer artifact projections are invalid'
      using errcode = '22023';
  end if;

  if exists (
    select 1
    from jsonb_array_elements(target_artifact->'tables') item
    left join public.queryability_graph_nodes node
      on node.tenant_id = target_tenant_id
     and node.graph_version_id = target_graph_version_id
     and node.node_key = item->>'node_key'
    where node.id is null
      or (
        (item->>'included')::boolean
        and node.queryability_status <> 'queryable'
      )
  ) or exists (
    select 1
    from jsonb_array_elements(target_artifact->'columns') item
    left join public.queryability_graph_columns graph_column
      on graph_column.tenant_id = target_tenant_id
     and graph_column.graph_version_id = target_graph_version_id
     and graph_column.column_key = item->>'column_key'
    where graph_column.id is null
      or (
        (item->>'included')::boolean
        and graph_column.queryability_status <> 'queryable'
      )
      or case graph_column.sensitivity
        when 'sensitive' then 2
        when 'pii' then 1
        else 0
      end > case item->>'sensitivity'
        when 'sensitive' then 2
        when 'pii' then 1
        else 0
      end
  ) or exists (
    select 1
    from jsonb_array_elements(target_artifact->'relationships') item
    left join public.queryability_graph_edges edge
      on edge.tenant_id = target_tenant_id
     and edge.graph_version_id = target_graph_version_id
     and edge.edge_key = item->>'edge_key'
    where edge.id is null
      or edge.edge_type <> 'fk_join'
      or not edge.automatic_join_allowed
      or edge.enforcement_status <> 'enabled'
      or edge.validation_status <> 'trusted'
  ) then
    raise exception 'semantic layer references unavailable graph elements'
      using errcode = '22023';
  end if;
end;
$$;

revoke all on function app_private.validate_semantic_layer_artifact(
  uuid,
  uuid,
  uuid,
  uuid,
  jsonb
) from public, anon, authenticated, service_role;

create or replace function app_private.replace_semantic_layer_projections(
  target_tenant_id uuid,
  target_semantic_version_id uuid,
  target_artifact jsonb
)
returns void
language plpgsql
set search_path = public, pg_temp
as $$
begin
  delete from public.semantic_layer_metric_common_dimensions
  where tenant_id = target_tenant_id
    and semantic_version_id = target_semantic_version_id;
  delete from public.semantic_layer_metrics
  where tenant_id = target_tenant_id
    and semantic_version_id = target_semantic_version_id;
  delete from public.semantic_layer_ambiguities
  where tenant_id = target_tenant_id
    and semantic_version_id = target_semantic_version_id;
  delete from public.semantic_layer_business_concepts
  where tenant_id = target_tenant_id
    and semantic_version_id = target_semantic_version_id;
  delete from public.semantic_layer_relationships
  where tenant_id = target_tenant_id
    and semantic_version_id = target_semantic_version_id;
  delete from public.semantic_layer_columns
  where tenant_id = target_tenant_id
    and semantic_version_id = target_semantic_version_id;
  delete from public.semantic_layer_tables
  where tenant_id = target_tenant_id
    and semantic_version_id = target_semantic_version_id;

  insert into public.semantic_layer_tables (
    tenant_id,
    semantic_version_id,
    node_key,
    schema_name,
    object_name,
    object_type,
    display_name,
    status,
    included,
    queryability_status,
    payload
  )
  select
    target_tenant_id,
    target_semantic_version_id,
    item->>'node_key',
    item->>'schema_name',
    item->>'object_name',
    item->>'object_type',
    item->>'display_name',
    item->>'status',
    (item->>'included')::boolean,
    item->>'queryability_status',
    item
  from jsonb_array_elements(target_artifact->'tables') item;

  insert into public.semantic_layer_columns (
    tenant_id,
    semantic_version_id,
    column_key,
    node_key,
    physical_name,
    semantic_role,
    status,
    included,
    queryability_status,
    inherited_sensitivity,
    sensitivity,
    payload
  )
  select
    target_tenant_id,
    target_semantic_version_id,
    item->>'column_key',
    item->>'node_key',
    item->>'physical_name',
    item->>'semantic_role',
    item->>'status',
    (item->>'included')::boolean,
    item->>'queryability_status',
    item->>'inherited_sensitivity',
    item->>'sensitivity',
    item
  from jsonb_array_elements(target_artifact->'columns') item;

  insert into public.semantic_layer_relationships (
    tenant_id,
    semantic_version_id,
    edge_key,
    from_node_key,
    to_node_key,
    status,
    enabled,
    relationship_shape,
    payload
  )
  select
    target_tenant_id,
    target_semantic_version_id,
    item->>'edge_key',
    item->>'from_node_key',
    item->>'to_node_key',
    item->>'status',
    (item->>'enabled')::boolean,
    item->>'relationship_shape',
    item
  from jsonb_array_elements(target_artifact->'relationships') item;

  insert into public.semantic_layer_business_concepts (
    tenant_id,
    semantic_version_id,
    business_concept_key,
    canonical_name,
    display_name,
    status,
    provenance,
    payload
  )
  select
    target_tenant_id,
    target_semantic_version_id,
    (item->>'business_concept_key')::uuid,
    item->>'canonical_name',
    item->>'display_name',
    item->>'status',
    item->>'provenance',
    item
  from jsonb_array_elements(target_artifact->'business_concepts') item;

  insert into public.semantic_layer_ambiguities (
    tenant_id,
    semantic_version_id,
    ambiguity_key,
    code,
    target_type,
    target_key,
    status,
    provenance,
    payload
  )
  select
    target_tenant_id,
    target_semantic_version_id,
    (item->>'ambiguity_key')::uuid,
    item->>'code',
    item->>'target_type',
    item->>'target_key',
    item->>'status',
    item->>'provenance',
    item
  from jsonb_array_elements(target_artifact->'ambiguities') item;

  insert into public.semantic_layer_metrics (
    tenant_id,
    semantic_version_id,
    metric_key,
    canonical_name,
    metric_definition_hash,
    business_concept_key,
    metric_variant,
    name,
    status,
    source_table_key,
    aggregation,
    measure_column_key,
    grain_table_key,
    grain_column_keys,
    compiler_eligibility,
    confidence_score,
    confidence_label,
    enabled,
    payload
  )
  select
    target_tenant_id,
    target_semantic_version_id,
    (item->>'metric_key')::uuid,
    item->>'canonical_name',
    item->>'metric_definition_hash',
    (item->>'business_concept_key')::uuid,
    item->>'metric_variant',
    item->>'name',
    item->>'status',
    item->>'source_table_key',
    item->>'aggregation',
    item->>'measure_column_key',
    item->>'grain_table_key',
    array(
      select jsonb_array_elements_text(item->'grain_column_keys')
    ),
    item->>'compiler_eligibility',
    (item->>'confidence_score')::numeric,
    item->>'confidence_label',
    (item->>'enabled')::boolean,
    item
  from jsonb_array_elements(target_artifact->'metrics') item;

  insert into public.semantic_layer_metric_common_dimensions (
    tenant_id,
    semantic_version_id,
    metric_key,
    dimension_column_key,
    edge_path,
    safety,
    reason_code,
    payload
  )
  select
    target_tenant_id,
    target_semantic_version_id,
    (metric->>'metric_key')::uuid,
    dimension->>'dimension_column_key',
    array(
      select jsonb_array_elements_text(dimension->'edge_path')
    ),
    dimension->>'safety',
    dimension->>'reason_code',
    dimension
  from jsonb_array_elements(target_artifact->'metrics') metric
  cross join lateral jsonb_array_elements(
    metric->'common_dimension_compatibility'
  ) dimension;
end;
$$;

revoke all on function app_private.replace_semantic_layer_projections(
  uuid,
  uuid,
  jsonb
) from public, anon, authenticated, service_role;

create or replace function app_private.persist_semantic_layer_version_core(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_graph_version_id uuid,
  target_artifact jsonb,
  target_generation_provenance jsonb default null,
  target_semantic_version_id uuid default null,
  expected_revision integer default null,
  target_rebased_from_version_id uuid default null,
  target_activation_policy text default 'auto_validated'
)
returns table (
  semantic_version_id uuid,
  semantic_version_number integer,
  revision integer,
  status public.semantic_layer_version_status
)
language plpgsql
set search_path = public, app_private, pg_temp
as $$
declare
  persisted_id uuid;
  persisted_version integer;
  persisted_revision integer;
  persisted_status public.semantic_layer_version_status;
  persisted_graph_version_id uuid;
  persisted_base_graph_hash text;
  persisted_rebased_from_version_id uuid;
  rebase_source_status public.semantic_layer_version_status;
  rebase_source_version integer;
  validation_status text;
  artifact_validated_revision integer;
begin
  perform app_private.validate_semantic_layer_artifact(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    target_graph_version_id,
    target_artifact
  );

  if target_activation_policy not in ('auto_validated', 'manual_review') then
    raise exception 'invalid semantic activation policy'
      using errcode = '22023';
  end if;

  validation_status := target_artifact
    ->'validation_report'
    ->>'status';
  artifact_validated_revision := nullif(
    target_artifact->'validation_report'->>'validated_revision',
    ''
  )::integer;

  if target_artifact->>'status' = 'proposed'
    and (
      validation_status not in ('valid', 'valid_with_warnings')
      or artifact_validated_revision
        is distinct from (target_artifact->>'revision')::integer
      or jsonb_array_length(
        target_artifact->'validation_report'->'blocking_errors'
      ) <> 0
    )
  then
    raise exception 'proposed semantic layer must be validated'
      using errcode = '22023';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended(target_connection_id::text, 0)
  );

  if target_semantic_version_id is null then
    persisted_id := (target_artifact->>'semantic_version_id')::uuid;

    select coalesce(max(version), 0) + 1
    into persisted_version
    from public.semantic_layer_versions
    where tenant_id = target_tenant_id
      and connection_id = target_connection_id;

    if (target_artifact->>'version')::integer <> persisted_version then
      raise exception 'semantic layer version allocation mismatch'
        using errcode = '40001';
    end if;

    if exists (
      select 1
      from public.semantic_layer_versions
      where id = persisted_id
    ) then
      raise exception 'semantic version id already exists'
        using errcode = '23505';
    end if;

    if target_rebased_from_version_id is not null then
      select version.status, version.version
      into rebase_source_status, rebase_source_version
      from public.semantic_layer_versions version
      where version.id = target_rebased_from_version_id
        and version.tenant_id = target_tenant_id
        and version.connection_id = target_connection_id;

      if rebase_source_status not in ('active', 'archived')
        or rebase_source_version >= persisted_version
      then
        raise exception 'semantic rebase source is invalid'
          using errcode = '22023';
      end if;
    end if;

    insert into public.semantic_layer_versions (
      id,
      tenant_id,
      connection_id,
      queryability_graph_version_id,
      base_graph_hash,
      version,
      contract_version,
      status,
      freshness,
      builder_version,
      ai_model_version,
      ai_prompt_version,
      validator_version,
      policy_version,
      revision,
      validated_revision,
      semantic_hash,
      artifact,
      validation_report,
      rebased_from_version_id,
      activation_policy,
      created_by
    )
    values (
      persisted_id,
      target_tenant_id,
      target_connection_id,
      target_graph_version_id,
      target_artifact->>'base_graph_hash',
      persisted_version,
      target_artifact->>'contract_version',
      (target_artifact->>'status')::public.semantic_layer_version_status,
      (target_artifact->>'freshness')::public.semantic_layer_freshness,
      target_artifact->>'builder_version',
      target_artifact->>'ai_model_version',
      target_artifact->>'ai_prompt_version',
      target_artifact->>'validator_version',
      target_artifact->>'policy_version',
      (target_artifact->>'revision')::integer,
      artifact_validated_revision,
      target_artifact->>'semantic_hash',
      target_artifact,
      target_artifact->'validation_report',
      target_rebased_from_version_id,
      target_activation_policy,
      actor_user_id
    );
  else
    select
      version.id,
      version.version,
      version.revision,
      version.queryability_graph_version_id,
      version.base_graph_hash,
      version.rebased_from_version_id
    into
      persisted_id,
      persisted_version,
      persisted_revision,
      persisted_graph_version_id,
      persisted_base_graph_hash,
      persisted_rebased_from_version_id
    from public.semantic_layer_versions version
    where version.id = target_semantic_version_id
      and version.tenant_id = target_tenant_id
      and version.connection_id = target_connection_id
      and version.status in ('draft', 'proposed')
    for update;

    if persisted_id is null then
      raise exception 'mutable semantic version not found'
        using errcode = 'P0002';
    end if;

    if expected_revision is null
      or expected_revision <> persisted_revision
    then
      raise exception 'semantic layer revision conflict'
        using errcode = '40001';
    end if;

    if (target_artifact->>'semantic_version_id')::uuid <> persisted_id
      or (target_artifact->>'version')::integer <> persisted_version
      or (target_artifact->>'revision')::integer <> persisted_revision + 1
    then
      raise exception 'semantic layer identity or revision mismatch'
        using errcode = '40001';
    end if;

    if target_graph_version_id <> persisted_graph_version_id
      or target_artifact->>'base_graph_hash' <> persisted_base_graph_hash
      or target_rebased_from_version_id
        is distinct from persisted_rebased_from_version_id
    then
      raise exception 'semantic version graph and rebase provenance are immutable'
        using errcode = '55000';
    end if;

    update public.semantic_layer_versions
    set
      queryability_graph_version_id = target_graph_version_id,
      base_graph_hash = target_artifact->>'base_graph_hash',
      status = (
        target_artifact->>'status'
      )::public.semantic_layer_version_status,
      freshness = (
        target_artifact->>'freshness'
      )::public.semantic_layer_freshness,
      builder_version = target_artifact->>'builder_version',
      ai_model_version = target_artifact->>'ai_model_version',
      ai_prompt_version = target_artifact->>'ai_prompt_version',
      validator_version = target_artifact->>'validator_version',
      policy_version = target_artifact->>'policy_version',
      revision = (target_artifact->>'revision')::integer,
      validated_revision = artifact_validated_revision,
      semantic_hash = target_artifact->>'semantic_hash',
      artifact = target_artifact,
      validation_report = target_artifact->'validation_report',
      rebased_from_version_id = target_rebased_from_version_id,
      activation_policy = target_activation_policy,
      updated_at = statement_timestamp()
    where id = persisted_id;
  end if;

  perform app_private.replace_semantic_layer_projections(
    target_tenant_id,
    persisted_id,
    target_artifact
  );

  if target_generation_provenance is not null then
    if jsonb_typeof(target_generation_provenance) <> 'object'
      or target_generation_provenance->>'provider' <> 'openai'
      or target_generation_provenance->>'input_hash'
        !~ '^[0-9a-f]{64}$'
      or target_generation_provenance->>'proposal_hash'
        !~ '^[0-9a-f]{64}$'
    then
      raise exception 'semantic generation provenance is invalid'
        using errcode = '22023';
    end if;

    insert into public.semantic_generation_runs (
      tenant_id,
      connection_id,
      semantic_version_id,
      provider,
      model_version,
      prompt_version,
      input_hash,
      proposal_hash,
      response_id,
      generated_at,
      created_by
    )
    values (
      target_tenant_id,
      target_connection_id,
      persisted_id,
      target_generation_provenance->>'provider',
      target_generation_provenance->>'model_version',
      target_generation_provenance->>'prompt_version',
      target_generation_provenance->>'input_hash',
      target_generation_provenance->>'proposal_hash',
      target_generation_provenance->>'response_id',
      (target_generation_provenance->>'generated_at')::timestamptz,
      actor_user_id
    )
    on conflict (tenant_id, connection_id, response_id) do nothing;
  end if;

  select version.revision, version.status
  into persisted_revision, persisted_status
  from public.semantic_layer_versions version
  where version.id = persisted_id;

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
      when target_semantic_version_id is null
        then 'semantic_layer.created'
      else 'semantic_layer.updated'
    end,
    'semantic_layer_version',
    persisted_id,
    jsonb_build_object(
      'connection_id', target_connection_id,
      'queryability_graph_version_id', target_graph_version_id,
      'version', persisted_version,
      'revision', persisted_revision,
      'status', persisted_status,
      'semantic_hash', target_artifact->>'semantic_hash'
    )
  );

  return query
  select
    persisted_id,
    persisted_version,
    persisted_revision,
    persisted_status;
end;
$$;

revoke all on function app_private.persist_semantic_layer_version_core(
  uuid,
  uuid,
  uuid,
  uuid,
  jsonb,
  jsonb,
  uuid,
  integer,
  uuid,
  text
) from public, anon, authenticated, service_role;

create or replace function app_private.persist_semantic_layer_version(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_graph_version_id uuid,
  target_artifact jsonb,
  target_generation_provenance jsonb default null,
  target_semantic_version_id uuid default null,
  expected_revision integer default null,
  target_rebased_from_version_id uuid default null,
  target_activation_policy text default 'auto_validated'
)
returns table (
  semantic_version_id uuid,
  semantic_version_number integer,
  revision integer,
  status public.semantic_layer_version_status
)
language sql
security definer
set search_path = public, app_private, pg_temp
as $$
  select *
  from app_private.persist_semantic_layer_version_core(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    target_graph_version_id,
    target_artifact,
    target_generation_provenance,
    target_semantic_version_id,
    expected_revision,
    target_rebased_from_version_id,
    target_activation_policy
  );
$$;

revoke all on function app_private.persist_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid,
  jsonb,
  jsonb,
  uuid,
  integer,
  uuid,
  text
) from public, anon, authenticated;
grant execute on function app_private.persist_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid,
  jsonb,
  jsonb,
  uuid,
  integer,
  uuid,
  text
) to service_role;

create or replace function public.persist_semantic_layer_version(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_graph_version_id uuid,
  target_artifact jsonb,
  target_generation_provenance jsonb default null,
  target_semantic_version_id uuid default null,
  expected_revision integer default null,
  target_rebased_from_version_id uuid default null,
  target_activation_policy text default 'auto_validated'
)
returns table (
  semantic_version_id uuid,
  semantic_version_number integer,
  revision integer,
  status public.semantic_layer_version_status
)
language sql
set search_path = public, app_private, pg_temp
as $$
  select *
  from app_private.persist_semantic_layer_version(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    target_graph_version_id,
    target_artifact,
    target_generation_provenance,
    target_semantic_version_id,
    expected_revision,
    target_rebased_from_version_id,
    target_activation_policy
  );
$$;

revoke all on function public.persist_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid,
  jsonb,
  jsonb,
  uuid,
  integer,
  uuid,
  text
) from public, anon, authenticated;
grant execute on function public.persist_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid,
  jsonb,
  jsonb,
  uuid,
  integer,
  uuid,
  text
) to service_role;

create or replace function app_private.activate_semantic_layer_version_core(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_semantic_version_id uuid,
  expected_revision integer
)
returns uuid
language plpgsql
set search_path = public, app_private, pg_temp
as $$
declare
  candidate public.semantic_layer_versions%rowtype;
begin
  if not app_private.is_semantic_layer_admin(
    target_tenant_id,
    actor_user_id
  ) then
    raise exception 'semantic layer owner or admin role required'
      using errcode = '42501';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended(target_connection_id::text, 0)
  );

  select *
  into candidate
  from public.semantic_layer_versions version
  where version.id = target_semantic_version_id
    and version.tenant_id = target_tenant_id
    and version.connection_id = target_connection_id
  for update;

  if candidate.id is null then
    raise exception 'semantic version not found'
      using errcode = 'P0002';
  end if;

  if candidate.status <> 'proposed'
    or candidate.revision <> expected_revision
    or candidate.validated_revision is distinct from candidate.revision
    or candidate.validation_report->>'status'
      not in ('valid', 'valid_with_warnings')
    or jsonb_array_length(
      candidate.validation_report->'blocking_errors'
    ) <> 0
    or app_private.semantic_layer_effective_freshness(candidate.id) <> 'fresh'
  then
    raise exception 'semantic version is not activation eligible'
      using errcode = '55000';
  end if;

  perform set_config('app.semantic_layer_rpc', 'on', true);

  update public.semantic_layer_versions
  set
    status = 'archived',
    artifact = jsonb_set(artifact, '{status}', '"archived"', false),
    archived_at = statement_timestamp(),
    updated_at = statement_timestamp()
  where tenant_id = target_tenant_id
    and connection_id = target_connection_id
    and status = 'active'
    and id <> target_semantic_version_id;

  update public.semantic_layer_versions
  set
    status = 'active',
    artifact = jsonb_set(artifact, '{status}', '"active"', false),
    activated_at = statement_timestamp(),
    archived_at = null,
    updated_at = statement_timestamp()
  where id = target_semantic_version_id;

  perform set_config('app.semantic_layer_rpc', 'off', true);

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
    'semantic_layer.activated',
    'semantic_layer_version',
    target_semantic_version_id,
    jsonb_build_object(
      'connection_id', target_connection_id,
      'version', candidate.version,
      'revision', candidate.revision,
      'base_graph_hash', candidate.base_graph_hash
    )
  );

  return target_semantic_version_id;
end;
$$;

revoke all on function app_private.activate_semantic_layer_version_core(
  uuid,
  uuid,
  uuid,
  uuid,
  integer
) from public, anon, authenticated, service_role;

create or replace function app_private.activate_semantic_layer_version(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_semantic_version_id uuid,
  expected_revision integer
)
returns uuid
language sql
security definer
set search_path = public, app_private, pg_temp
as $$
  select app_private.activate_semantic_layer_version_core(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    target_semantic_version_id,
    expected_revision
  );
$$;

revoke all on function app_private.activate_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid,
  integer
) from public, anon, authenticated;
grant execute on function app_private.activate_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid,
  integer
) to service_role;

create or replace function public.activate_semantic_layer_version(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_semantic_version_id uuid,
  expected_revision integer
)
returns uuid
language sql
set search_path = public, app_private, pg_temp
as $$
  select app_private.activate_semantic_layer_version(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    target_semantic_version_id,
    expected_revision
  );
$$;

revoke all on function public.activate_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid,
  integer
) from public, anon, authenticated;
grant execute on function public.activate_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid,
  integer
) to service_role;

create or replace function app_private.archive_semantic_layer_version_core(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_semantic_version_id uuid
)
returns uuid
language plpgsql
set search_path = public, app_private, pg_temp
as $$
declare
  current_status public.semantic_layer_version_status;
begin
  if not app_private.is_semantic_layer_admin(
    target_tenant_id,
    actor_user_id
  ) then
    raise exception 'semantic layer owner or admin role required'
      using errcode = '42501';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended(target_connection_id::text, 0)
  );

  select version.status
  into current_status
  from public.semantic_layer_versions version
  where version.id = target_semantic_version_id
    and version.tenant_id = target_tenant_id
    and version.connection_id = target_connection_id
  for update;

  if current_status is null then
    raise exception 'semantic version not found'
      using errcode = 'P0002';
  end if;

  if current_status = 'archived' then
    return target_semantic_version_id;
  end if;

  perform set_config('app.semantic_layer_rpc', 'on', true);

  update public.semantic_layer_versions
  set
    status = 'archived',
    artifact = jsonb_set(artifact, '{status}', '"archived"', false),
    archived_at = statement_timestamp(),
    updated_at = statement_timestamp()
  where id = target_semantic_version_id;

  perform set_config('app.semantic_layer_rpc', 'off', true);

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
    'semantic_layer.archived',
    'semantic_layer_version',
    target_semantic_version_id,
    jsonb_build_object('connection_id', target_connection_id)
  );

  return target_semantic_version_id;
end;
$$;

revoke all on function app_private.archive_semantic_layer_version_core(
  uuid,
  uuid,
  uuid,
  uuid
) from public, anon, authenticated, service_role;

create or replace function app_private.archive_semantic_layer_version(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_semantic_version_id uuid
)
returns uuid
language sql
security definer
set search_path = public, app_private, pg_temp
as $$
  select app_private.archive_semantic_layer_version_core(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    target_semantic_version_id
  );
$$;

revoke all on function app_private.archive_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid
) from public, anon, authenticated;
grant execute on function app_private.archive_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid
) to service_role;

create or replace function public.archive_semantic_layer_version(
  actor_user_id uuid,
  target_tenant_id uuid,
  target_connection_id uuid,
  target_semantic_version_id uuid
)
returns uuid
language sql
set search_path = public, app_private, pg_temp
as $$
  select app_private.archive_semantic_layer_version(
    actor_user_id,
    target_tenant_id,
    target_connection_id,
    target_semantic_version_id
  );
$$;

revoke all on function public.archive_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid
) from public, anon, authenticated;
grant execute on function public.archive_semantic_layer_version(
  uuid,
  uuid,
  uuid,
  uuid
) to service_role;
