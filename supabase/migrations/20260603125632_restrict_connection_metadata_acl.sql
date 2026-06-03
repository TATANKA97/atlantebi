revoke all privileges on table public.db_connections from anon;
revoke all privileges on table public.db_connections from authenticated;

grant select (
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
  status,
  last_test_status,
  last_tested_at,
  created_by,
  created_at,
  updated_at
) on table public.db_connections to authenticated;

grant insert, update, delete on table public.db_connections to authenticated;

revoke all privileges on table public.db_connection_summaries from anon;
grant select on table public.db_connection_summaries to authenticated;
