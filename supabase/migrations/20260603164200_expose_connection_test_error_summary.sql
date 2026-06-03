alter table public.db_connections
  alter column secret_ref drop not null;

alter table public.db_connections
  add constraint db_connections_ready_requires_secret_ref
  check (status <> 'ready' or secret_ref is not null);

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
  last_test_error,
  last_tested_at,
  created_by,
  created_at,
  updated_at
) on table public.db_connections to authenticated;

drop view public.db_connection_summaries;

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
  username,
  tls_required,
  tls_server_name,
  trust_server_certificate,
  status,
  last_test_status,
  last_test_error,
  last_tested_at,
  created_by,
  created_at,
  updated_at
from public.db_connections;

grant select on table public.db_connection_summaries to authenticated;
