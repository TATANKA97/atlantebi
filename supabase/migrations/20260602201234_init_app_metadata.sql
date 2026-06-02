create extension if not exists pgcrypto;

create schema if not exists app_private;

create type public.tenant_role as enum ('owner', 'admin', 'editor', 'viewer');
create type public.membership_status as enum ('active', 'invited', 'disabled');
create type public.connection_engine as enum ('sqlserver', 'mysql');
create type public.network_mode as enum ('public_allowlist', 'vpn');
create type public.connection_status as enum ('draft', 'ready', 'failed', 'disabled');
create type public.semantic_version_status as enum ('draft', 'active', 'archived');
create type public.widget_refresh_interval as enum ('manual', '15m', '30m', '1h', '4h', '24h');
create type public.query_status as enum ('planned', 'running', 'completed', 'failed', 'needs_clarification');

create table public.tenants (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'),
  name text not null check (length(name) between 2 and 160),
  plan text not null default 'pilot',
  status text not null default 'active' check (status in ('active', 'suspended', 'deleted')),
  settings jsonb not null default '{}'::jsonb,
  created_by uuid not null default auth.uid() references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.tenant_memberships (
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role public.tenant_role not null,
  status public.membership_status not null default 'active',
  invited_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (tenant_id, user_id)
);

create table public.db_connections (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  name text not null check (length(name) between 2 and 160),
  engine public.connection_engine not null,
  network_mode public.network_mode not null,
  host text not null check (length(host) between 1 and 255),
  port integer not null check (port between 1 and 65535),
  database_name text not null check (length(database_name) between 1 and 255),
  tls_required boolean not null default true,
  tls_server_name text check (tls_server_name is null or length(tls_server_name) between 1 and 255),
  secret_ref text not null check (secret_ref ~ '^gcp-secret-manager://projects/[^/]+/secrets/[^/]+(/versions/[^/]+)?$'),
  status public.connection_status not null default 'draft',
  last_tested_at timestamptz,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, name)
);

create table public.schema_snapshots (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  connection_id uuid not null references public.db_connections(id) on delete cascade,
  engine public.connection_engine not null,
  snapshot jsonb not null,
  table_count integer not null check (table_count >= 0),
  column_count integer not null check (column_count >= 0),
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);

create table public.semantic_versions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  connection_id uuid not null references public.db_connections(id) on delete cascade,
  schema_snapshot_id uuid references public.schema_snapshots(id) on delete set null,
  version integer not null check (version > 0),
  status public.semantic_version_status not null default 'draft',
  created_by uuid not null references auth.users(id),
  activated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, connection_id, version)
);

create table public.semantic_tables (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  semantic_version_id uuid not null references public.semantic_versions(id) on delete cascade,
  physical_schema text not null,
  physical_name text not null,
  business_name text,
  active boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  unique (semantic_version_id, physical_schema, physical_name)
);

create table public.semantic_columns (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  semantic_table_id uuid not null references public.semantic_tables(id) on delete cascade,
  physical_name text not null,
  data_type text not null,
  business_name text,
  role text not null check (role in ('dimension', 'measure', 'date', 'identifier', 'unknown')),
  format jsonb,
  pii boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  unique (semantic_table_id, physical_name)
);

create table public.semantic_relationships (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  semantic_version_id uuid not null references public.semantic_versions(id) on delete cascade,
  from_table_id uuid not null references public.semantic_tables(id) on delete cascade,
  from_columns text[] not null check (array_length(from_columns, 1) > 0),
  to_table_id uuid not null references public.semantic_tables(id) on delete cascade,
  to_columns text[] not null check (array_length(to_columns, 1) > 0),
  cardinality text not null check (cardinality in ('one_to_one', 'one_to_many', 'many_to_one', 'many_to_many')),
  semantic_status text not null check (semantic_status in ('confirmed', 'suggested', 'rejected')),
  source text not null check (source in ('database_fk', 'user_validated', 'ai_suggested'))
);

create table public.semantic_metrics (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  semantic_version_id uuid not null references public.semantic_versions(id) on delete cascade,
  name text not null,
  expression text not null,
  grain text[] not null default '{}',
  format jsonb not null,
  metadata jsonb not null default '{}'::jsonb,
  unique (semantic_version_id, name)
);

create table public.business_anchors (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  semantic_version_id uuid not null references public.semantic_versions(id) on delete cascade,
  metric_id uuid not null references public.semantic_metrics(id) on delete cascade,
  name text not null,
  expected_range jsonb not null,
  period text not null check (period in ('daily', 'monthly', 'quarterly', 'yearly')),
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);

create table public.dashboards (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  name text not null check (length(name) between 1 and 160),
  description text,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, name)
);

create table public.widgets (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  connection_id uuid not null references public.db_connections(id) on delete restrict,
  semantic_version_id uuid references public.semantic_versions(id) on delete set null,
  title text not null check (length(title) between 1 and 160),
  original_question text not null,
  generated_sql text not null,
  chart_spec jsonb not null,
  display_settings jsonb not null default '{}'::jsonb,
  refresh_interval public.widget_refresh_interval not null default 'manual',
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.dashboard_widgets (
  dashboard_id uuid not null references public.dashboards(id) on delete cascade,
  widget_id uuid not null references public.widgets(id) on delete cascade,
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  position jsonb not null,
  created_at timestamptz not null default now(),
  primary key (dashboard_id, widget_id)
);

create table public.query_history (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  connection_id uuid not null references public.db_connections(id) on delete restrict,
  semantic_version_id uuid references public.semantic_versions(id) on delete set null,
  asked_by uuid not null references auth.users(id),
  question text not null,
  status public.query_status not null,
  generated_sql text,
  row_count integer check (row_count is null or row_count >= 0),
  chart_spec jsonb,
  verification_summary jsonb,
  error_summary text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now()
);

create table public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  actor_user_id uuid references auth.users(id),
  action text not null,
  subject_type text not null,
  subject_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index tenant_memberships_user_id_idx on public.tenant_memberships(user_id);
create index db_connections_tenant_id_idx on public.db_connections(tenant_id);
create index schema_snapshots_connection_id_idx on public.schema_snapshots(connection_id);
create index semantic_versions_tenant_status_idx on public.semantic_versions(tenant_id, status);
create index semantic_tables_version_idx on public.semantic_tables(semantic_version_id);
create index semantic_columns_table_idx on public.semantic_columns(semantic_table_id);
create index dashboards_tenant_id_idx on public.dashboards(tenant_id);
create index widgets_tenant_id_idx on public.widgets(tenant_id);
create index dashboard_widgets_tenant_id_idx on public.dashboard_widgets(tenant_id);
create index query_history_tenant_created_idx on public.query_history(tenant_id, created_at desc);
create index audit_logs_tenant_created_idx on public.audit_logs(tenant_id, created_at desc);

create or replace function app_private.is_tenant_member(target_tenant_id uuid)
returns boolean
language sql
security definer
set search_path = public, pg_temp
stable
as $$
  select exists (
    select 1
    from public.tenant_memberships tm
    where tm.tenant_id = target_tenant_id
      and tm.user_id = (select auth.uid())
      and tm.status = 'active'
  );
$$;

create or replace function app_private.has_tenant_role(
  target_tenant_id uuid,
  allowed_roles public.tenant_role[]
)
returns boolean
language sql
security definer
set search_path = public, pg_temp
stable
as $$
  select exists (
    select 1
    from public.tenant_memberships tm
    where tm.tenant_id = target_tenant_id
      and tm.user_id = (select auth.uid())
      and tm.status = 'active'
      and tm.role = any(allowed_roles)
  );
$$;

grant usage on schema app_private to authenticated;
grant execute on function app_private.is_tenant_member(uuid) to authenticated;
grant execute on function app_private.has_tenant_role(uuid, public.tenant_role[]) to authenticated;

alter table public.tenants enable row level security;
alter table public.tenant_memberships enable row level security;
alter table public.db_connections enable row level security;
alter table public.schema_snapshots enable row level security;
alter table public.semantic_versions enable row level security;
alter table public.semantic_tables enable row level security;
alter table public.semantic_columns enable row level security;
alter table public.semantic_relationships enable row level security;
alter table public.semantic_metrics enable row level security;
alter table public.business_anchors enable row level security;
alter table public.dashboards enable row level security;
alter table public.widgets enable row level security;
alter table public.dashboard_widgets enable row level security;
alter table public.query_history enable row level security;
alter table public.audit_logs enable row level security;

create policy "members can read tenants"
on public.tenants for select
to authenticated
using (app_private.is_tenant_member(id));

create policy "authenticated users can create tenants"
on public.tenants for insert
to authenticated
with check (created_by = (select auth.uid()));

create policy "tenant admins can update tenants"
on public.tenants for update
to authenticated
using (app_private.has_tenant_role(id, array['owner', 'admin']::public.tenant_role[]))
with check (app_private.has_tenant_role(id, array['owner', 'admin']::public.tenant_role[]));

create policy "members can read memberships"
on public.tenant_memberships for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "creator can add initial owner membership"
on public.tenant_memberships for insert
to authenticated
with check (
  user_id = (select auth.uid())
  and role = 'owner'
  and exists (
    select 1
    from public.tenants t
    where t.id = tenant_id
      and t.created_by = (select auth.uid())
  )
);

create policy "tenant admins can manage memberships"
on public.tenant_memberships for update
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.tenant_role[]));

create policy "tenant admins can delete memberships"
on public.tenant_memberships for delete
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.tenant_role[]));

create policy "members can read connections"
on public.db_connections for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "tenant editors can create connections"
on public.db_connections for insert
to authenticated
with check (
  created_by = (select auth.uid())
  and app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[])
);

create policy "tenant editors can update connections"
on public.db_connections for update
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant admins can delete connections"
on public.db_connections for delete
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.tenant_role[]));

create policy "members can read schema snapshots"
on public.schema_snapshots for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "tenant editors can create schema snapshots"
on public.schema_snapshots for insert
to authenticated
with check (
  created_by = (select auth.uid())
  and app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[])
);

create policy "members can read semantic versions"
on public.semantic_versions for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "tenant editors can manage semantic versions"
on public.semantic_versions for all
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "members can read semantic tables"
on public.semantic_tables for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "tenant editors can manage semantic tables"
on public.semantic_tables for all
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "members can read semantic columns"
on public.semantic_columns for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "tenant editors can manage semantic columns"
on public.semantic_columns for all
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "members can read semantic relationships"
on public.semantic_relationships for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "tenant editors can manage semantic relationships"
on public.semantic_relationships for all
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "members can read semantic metrics"
on public.semantic_metrics for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "tenant editors can manage semantic metrics"
on public.semantic_metrics for all
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "members can read business anchors"
on public.business_anchors for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "tenant editors can manage business anchors"
on public.business_anchors for all
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "members can read dashboards"
on public.dashboards for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "tenant editors can manage dashboards"
on public.dashboards for all
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "members can read widgets"
on public.widgets for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "tenant editors can manage widgets"
on public.widgets for all
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "members can read dashboard widgets"
on public.dashboard_widgets for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "tenant editors can manage dashboard widgets"
on public.dashboard_widgets for all
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "members can read query history"
on public.query_history for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "members can create query history"
on public.query_history for insert
to authenticated
with check (
  asked_by = (select auth.uid())
  and app_private.is_tenant_member(tenant_id)
);

create policy "members can read audit logs"
on public.audit_logs for select
to authenticated
using (app_private.is_tenant_member(tenant_id));

create policy "members can create audit logs"
on public.audit_logs for insert
to authenticated
with check (
  actor_user_id = (select auth.uid())
  and app_private.is_tenant_member(tenant_id)
);
