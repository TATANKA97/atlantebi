create index if not exists business_anchors_metric_id_idx
  on public.business_anchors (metric_id);

create index if not exists business_anchors_semantic_version_id_idx
  on public.business_anchors (semantic_version_id);

create index if not exists dashboard_widgets_widget_id_idx
  on public.dashboard_widgets (widget_id);

create index if not exists query_history_connection_id_idx
  on public.query_history (connection_id);

create index if not exists query_history_semantic_version_id_idx
  on public.query_history (semantic_version_id);

create index if not exists semantic_relationships_from_table_id_idx
  on public.semantic_relationships (from_table_id);

create index if not exists semantic_relationships_semantic_version_id_idx
  on public.semantic_relationships (semantic_version_id);

create index if not exists semantic_relationships_to_table_id_idx
  on public.semantic_relationships (to_table_id);

create index if not exists semantic_versions_connection_id_idx
  on public.semantic_versions (connection_id);

create index if not exists semantic_versions_schema_snapshot_id_idx
  on public.semantic_versions (schema_snapshot_id);

create index if not exists widgets_connection_id_idx
  on public.widgets (connection_id);

create index if not exists widgets_semantic_version_id_idx
  on public.widgets (semantic_version_id);
