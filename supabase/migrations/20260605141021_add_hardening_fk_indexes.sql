create index semantic_relationships_tenant_version_from_table_idx
  on public.semantic_relationships (tenant_id, semantic_version_id, from_table_id);

create index semantic_relationships_tenant_version_to_table_idx
  on public.semantic_relationships (tenant_id, semantic_version_id, to_table_id);

create index semantic_versions_tenant_connection_snapshot_idx
  on public.semantic_versions (tenant_id, connection_id, schema_snapshot_id);
