create index if not exists tenants_created_by_idx
  on public.tenants (created_by);

create index if not exists tenant_memberships_invited_by_idx
  on public.tenant_memberships (invited_by);

create index if not exists db_connections_created_by_idx
  on public.db_connections (created_by);

create index if not exists schema_snapshots_tenant_connection_idx
  on public.schema_snapshots (tenant_id, connection_id);

create index if not exists schema_snapshots_created_by_idx
  on public.schema_snapshots (created_by);

create index if not exists semantic_versions_tenant_connection_idx
  on public.semantic_versions (tenant_id, connection_id);

create index if not exists semantic_versions_tenant_schema_snapshot_idx
  on public.semantic_versions (tenant_id, schema_snapshot_id);

create index if not exists semantic_versions_created_by_idx
  on public.semantic_versions (created_by);

create index if not exists semantic_tables_tenant_version_idx
  on public.semantic_tables (tenant_id, semantic_version_id);

create index if not exists semantic_columns_tenant_table_idx
  on public.semantic_columns (tenant_id, semantic_table_id);

create index if not exists semantic_relationships_tenant_version_idx
  on public.semantic_relationships (tenant_id, semantic_version_id);

create index if not exists semantic_relationships_tenant_from_table_idx
  on public.semantic_relationships (tenant_id, from_table_id);

create index if not exists semantic_relationships_tenant_to_table_idx
  on public.semantic_relationships (tenant_id, to_table_id);

create index if not exists semantic_metrics_tenant_version_idx
  on public.semantic_metrics (tenant_id, semantic_version_id);

create index if not exists business_anchors_tenant_version_idx
  on public.business_anchors (tenant_id, semantic_version_id);

create index if not exists business_anchors_tenant_metric_idx
  on public.business_anchors (tenant_id, metric_id);

create index if not exists business_anchors_created_by_idx
  on public.business_anchors (created_by);

create index if not exists dashboards_created_by_idx
  on public.dashboards (created_by);

create index if not exists dashboard_widgets_tenant_dashboard_idx
  on public.dashboard_widgets (tenant_id, dashboard_id);

create index if not exists dashboard_widgets_tenant_widget_idx
  on public.dashboard_widgets (tenant_id, widget_id);

create index if not exists query_history_tenant_connection_idx
  on public.query_history (tenant_id, connection_id);

create index if not exists query_history_tenant_semantic_version_idx
  on public.query_history (tenant_id, semantic_version_id);

create index if not exists query_history_asked_by_idx
  on public.query_history (asked_by);

create index if not exists audit_logs_actor_user_id_idx
  on public.audit_logs (actor_user_id);

create index if not exists widgets_tenant_connection_idx
  on public.widgets (tenant_id, connection_id);

create index if not exists widgets_tenant_semantic_version_idx
  on public.widgets (tenant_id, semantic_version_id);

create index if not exists widgets_created_by_idx
  on public.widgets (created_by);

drop policy if exists "tenant editors can manage semantic versions" on public.semantic_versions;
drop policy if exists "tenant editors can manage semantic tables" on public.semantic_tables;
drop policy if exists "tenant editors can manage semantic columns" on public.semantic_columns;
drop policy if exists "tenant editors can manage semantic relationships" on public.semantic_relationships;
drop policy if exists "tenant editors can manage semantic metrics" on public.semantic_metrics;
drop policy if exists "tenant editors can manage business anchors" on public.business_anchors;
drop policy if exists "tenant editors can manage dashboards" on public.dashboards;
drop policy if exists "tenant editors can manage widgets" on public.widgets;
drop policy if exists "tenant editors can manage dashboard widgets" on public.dashboard_widgets;

drop policy if exists "owners can add memberships" on public.tenant_memberships;
drop policy if exists "admins can add non-owner memberships" on public.tenant_memberships;
drop policy if exists "owners can update memberships" on public.tenant_memberships;
drop policy if exists "admins can update non-owner memberships" on public.tenant_memberships;
drop policy if exists "owners can delete memberships" on public.tenant_memberships;
drop policy if exists "admins can delete non-owner memberships" on public.tenant_memberships;

create policy "tenant owners and admins can add memberships"
on public.tenant_memberships for insert
to authenticated
with check (
  (
    role = 'owner'
    and app_private.has_tenant_role(tenant_id, array['owner']::public.tenant_role[])
  )
  or (
    role <> 'owner'
    and app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.tenant_role[])
  )
);

create policy "tenant owners and admins can update memberships"
on public.tenant_memberships for update
to authenticated
using (
  (
    app_private.has_tenant_role(tenant_id, array['owner']::public.tenant_role[])
    and (
      role <> 'owner'
      or status <> 'active'
      or app_private.has_other_active_owner(tenant_id, user_id)
    )
  )
  or (
    role <> 'owner'
    and app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.tenant_role[])
  )
)
with check (
  (
    role = 'owner'
    and app_private.has_tenant_role(tenant_id, array['owner']::public.tenant_role[])
  )
  or (
    role <> 'owner'
    and app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.tenant_role[])
  )
);

create policy "tenant owners and admins can delete memberships"
on public.tenant_memberships for delete
to authenticated
using (
  (
    app_private.has_tenant_role(tenant_id, array['owner']::public.tenant_role[])
    and (
      role <> 'owner'
      or status <> 'active'
      or app_private.has_other_active_owner(tenant_id, user_id)
    )
  )
  or (
    role <> 'owner'
    and app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.tenant_role[])
  )
);

create policy "tenant editors can create semantic versions"
on public.semantic_versions for insert
to authenticated
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can update semantic versions"
on public.semantic_versions for update
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can delete semantic versions"
on public.semantic_versions for delete
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can create semantic tables"
on public.semantic_tables for insert
to authenticated
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can update semantic tables"
on public.semantic_tables for update
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can delete semantic tables"
on public.semantic_tables for delete
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can create semantic columns"
on public.semantic_columns for insert
to authenticated
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can update semantic columns"
on public.semantic_columns for update
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can delete semantic columns"
on public.semantic_columns for delete
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can create semantic relationships"
on public.semantic_relationships for insert
to authenticated
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can update semantic relationships"
on public.semantic_relationships for update
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can delete semantic relationships"
on public.semantic_relationships for delete
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can create semantic metrics"
on public.semantic_metrics for insert
to authenticated
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can update semantic metrics"
on public.semantic_metrics for update
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can delete semantic metrics"
on public.semantic_metrics for delete
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can create business anchors"
on public.business_anchors for insert
to authenticated
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can update business anchors"
on public.business_anchors for update
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can delete business anchors"
on public.business_anchors for delete
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can create dashboards"
on public.dashboards for insert
to authenticated
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can update dashboards"
on public.dashboards for update
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can delete dashboards"
on public.dashboards for delete
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can create widgets"
on public.widgets for insert
to authenticated
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can update widgets"
on public.widgets for update
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can delete widgets"
on public.widgets for delete
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can create dashboard widgets"
on public.dashboard_widgets for insert
to authenticated
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can update dashboard widgets"
on public.dashboard_widgets for update
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]))
with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));

create policy "tenant editors can delete dashboard widgets"
on public.dashboard_widgets for delete
to authenticated
using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'editor']::public.tenant_role[]));
