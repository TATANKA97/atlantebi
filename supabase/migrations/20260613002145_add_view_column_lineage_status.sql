alter table public.queryability_graph_nodes
  add column view_column_lineage_status text
  generated always as (payload->>'view_column_lineage_status') stored;

alter table public.queryability_graph_nodes
  add constraint queryability_graph_nodes_view_column_lineage_status_check
  check (
    view_column_lineage_status is null
    or view_column_lineage_status in ('complete', 'partial', 'unavailable')
  );
