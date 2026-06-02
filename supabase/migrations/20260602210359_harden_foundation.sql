grant usage on schema public to authenticated;

alter table public.db_connections
  add constraint db_connections_tenant_id_id_unique unique (tenant_id, id);

alter table public.schema_snapshots
  add constraint schema_snapshots_tenant_id_id_unique unique (tenant_id, id),
  add constraint schema_snapshots_connection_tenant_fk
    foreign key (tenant_id, connection_id)
    references public.db_connections(tenant_id, id)
    on delete cascade;

alter table public.semantic_versions
  add constraint semantic_versions_tenant_id_id_unique unique (tenant_id, id),
  add constraint semantic_versions_connection_tenant_fk
    foreign key (tenant_id, connection_id)
    references public.db_connections(tenant_id, id)
    on delete cascade,
  add constraint semantic_versions_schema_snapshot_tenant_fk
    foreign key (tenant_id, schema_snapshot_id)
    references public.schema_snapshots(tenant_id, id)
    on delete set null;

alter table public.semantic_tables
  add constraint semantic_tables_tenant_id_id_unique unique (tenant_id, id),
  add constraint semantic_tables_version_tenant_fk
    foreign key (tenant_id, semantic_version_id)
    references public.semantic_versions(tenant_id, id)
    on delete cascade;

alter table public.semantic_columns
  add constraint semantic_columns_table_tenant_fk
    foreign key (tenant_id, semantic_table_id)
    references public.semantic_tables(tenant_id, id)
    on delete cascade;

alter table public.semantic_relationships
  add constraint semantic_relationships_version_tenant_fk
    foreign key (tenant_id, semantic_version_id)
    references public.semantic_versions(tenant_id, id)
    on delete cascade,
  add constraint semantic_relationships_from_table_tenant_fk
    foreign key (tenant_id, from_table_id)
    references public.semantic_tables(tenant_id, id)
    on delete cascade,
  add constraint semantic_relationships_to_table_tenant_fk
    foreign key (tenant_id, to_table_id)
    references public.semantic_tables(tenant_id, id)
    on delete cascade;

alter table public.semantic_metrics
  add constraint semantic_metrics_tenant_id_id_unique unique (tenant_id, id),
  add constraint semantic_metrics_version_tenant_fk
    foreign key (tenant_id, semantic_version_id)
    references public.semantic_versions(tenant_id, id)
    on delete cascade;

alter table public.business_anchors
  add constraint business_anchors_version_tenant_fk
    foreign key (tenant_id, semantic_version_id)
    references public.semantic_versions(tenant_id, id)
    on delete cascade,
  add constraint business_anchors_metric_tenant_fk
    foreign key (tenant_id, metric_id)
    references public.semantic_metrics(tenant_id, id)
    on delete cascade;

alter table public.dashboards
  add constraint dashboards_tenant_id_id_unique unique (tenant_id, id);

alter table public.widgets
  add constraint widgets_tenant_id_id_unique unique (tenant_id, id),
  add constraint widgets_connection_tenant_fk
    foreign key (tenant_id, connection_id)
    references public.db_connections(tenant_id, id)
    on delete restrict,
  add constraint widgets_semantic_version_tenant_fk
    foreign key (tenant_id, semantic_version_id)
    references public.semantic_versions(tenant_id, id)
    on delete set null;

alter table public.dashboard_widgets
  add constraint dashboard_widgets_dashboard_tenant_fk
    foreign key (tenant_id, dashboard_id)
    references public.dashboards(tenant_id, id)
    on delete cascade,
  add constraint dashboard_widgets_widget_tenant_fk
    foreign key (tenant_id, widget_id)
    references public.widgets(tenant_id, id)
    on delete cascade;

alter table public.query_history
  add constraint query_history_connection_tenant_fk
    foreign key (tenant_id, connection_id)
    references public.db_connections(tenant_id, id)
    on delete restrict,
  add constraint query_history_semantic_version_tenant_fk
    foreign key (tenant_id, semantic_version_id)
    references public.semantic_versions(tenant_id, id)
    on delete set null;

grant select, insert, update on table public.tenants to authenticated;
grant select, insert, update, delete on table public.tenant_memberships to authenticated;
grant select, insert on table public.schema_snapshots to authenticated;
grant select, insert, update, delete on table public.semantic_versions to authenticated;
grant select, insert, update, delete on table public.semantic_tables to authenticated;
grant select, insert, update, delete on table public.semantic_columns to authenticated;
grant select, insert, update, delete on table public.semantic_relationships to authenticated;
grant select, insert, update, delete on table public.semantic_metrics to authenticated;
grant select, insert, update, delete on table public.business_anchors to authenticated;
grant select, insert, update, delete on table public.dashboards to authenticated;
grant select, insert, update, delete on table public.widgets to authenticated;
grant select, insert, update, delete on table public.dashboard_widgets to authenticated;
grant select, insert on table public.query_history to authenticated;
grant select, insert on table public.audit_logs to authenticated;

grant select (
  id,
  tenant_id,
  name,
  engine,
  network_mode,
  host,
  port,
  database_name,
  tls_required,
  tls_server_name,
  status,
  last_tested_at,
  created_by,
  created_at,
  updated_at
) on table public.db_connections to authenticated;

grant all privileges on table public.tenants to service_role;
grant all privileges on table public.tenant_memberships to service_role;
grant all privileges on table public.db_connections to service_role;
grant all privileges on table public.schema_snapshots to service_role;
grant all privileges on table public.semantic_versions to service_role;
grant all privileges on table public.semantic_tables to service_role;
grant all privileges on table public.semantic_columns to service_role;
grant all privileges on table public.semantic_relationships to service_role;
grant all privileges on table public.semantic_metrics to service_role;
grant all privileges on table public.business_anchors to service_role;
grant all privileges on table public.dashboards to service_role;
grant all privileges on table public.widgets to service_role;
grant all privileges on table public.dashboard_widgets to service_role;
grant all privileges on table public.query_history to service_role;
grant all privileges on table public.audit_logs to service_role;

create or replace view public.db_connection_summaries
with (security_invoker = true)
as
select
  id,
  tenant_id,
  name,
  engine,
  network_mode,
  host,
  port,
  database_name,
  tls_required,
  tls_server_name,
  status,
  last_tested_at,
  created_by,
  created_at,
  updated_at
from public.db_connections;

grant select on table public.db_connection_summaries to authenticated;

drop policy if exists "authenticated users can create tenants" on public.tenants;
drop policy if exists "creator can add initial owner membership" on public.tenant_memberships;
drop policy if exists "tenant admins can manage memberships" on public.tenant_memberships;
drop policy if exists "tenant admins can delete memberships" on public.tenant_memberships;

create or replace function app_private.has_other_active_owner(
  target_tenant_id uuid,
  target_user_id uuid
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
      and tm.user_id <> target_user_id
      and tm.role = 'owner'
      and tm.status = 'active'
  );
$$;

create or replace function app_private.create_tenant_with_owner(
  tenant_slug text,
  tenant_name text,
  tenant_plan text default 'pilot'
)
returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  current_user_id uuid := (select auth.uid());
  new_tenant_id uuid;
begin
  if current_user_id is null then
    raise exception 'authenticated user required'
      using errcode = '28000';
  end if;

  insert into public.tenants (slug, name, plan, created_by)
  values (tenant_slug, tenant_name, tenant_plan, current_user_id)
  returning id into new_tenant_id;

  insert into public.tenant_memberships (tenant_id, user_id, role, status, invited_by)
  values (new_tenant_id, current_user_id, 'owner', 'active', current_user_id);

  return new_tenant_id;
end;
$$;

grant execute on function app_private.has_other_active_owner(uuid, uuid) to authenticated;
grant execute on function app_private.create_tenant_with_owner(text, text, text) to authenticated;

create policy "owners can add memberships"
on public.tenant_memberships for insert
to authenticated
with check (
  app_private.has_tenant_role(tenant_id, array['owner']::public.tenant_role[])
);

create policy "admins can add non-owner memberships"
on public.tenant_memberships for insert
to authenticated
with check (
  role <> 'owner'
  and app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.tenant_role[])
);

create policy "owners can update memberships"
on public.tenant_memberships for update
to authenticated
using (
  app_private.has_tenant_role(tenant_id, array['owner']::public.tenant_role[])
  and (
    role <> 'owner'
    or status <> 'active'
    or app_private.has_other_active_owner(tenant_id, user_id)
  )
)
with check (
  app_private.has_tenant_role(tenant_id, array['owner']::public.tenant_role[])
);

create policy "admins can update non-owner memberships"
on public.tenant_memberships for update
to authenticated
using (
  role <> 'owner'
  and app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.tenant_role[])
)
with check (
  role <> 'owner'
  and app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.tenant_role[])
);

create policy "owners can delete memberships"
on public.tenant_memberships for delete
to authenticated
using (
  app_private.has_tenant_role(tenant_id, array['owner']::public.tenant_role[])
  and (
    role <> 'owner'
    or status <> 'active'
    or app_private.has_other_active_owner(tenant_id, user_id)
  )
);

create policy "admins can delete non-owner memberships"
on public.tenant_memberships for delete
to authenticated
using (
  role <> 'owner'
  and app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.tenant_role[])
);
