create type public.connection_test_status as enum ('ok', 'failed', 'engine_error');

alter table public.db_connections
  add column username text not null default 'pending' check (length(username) between 1 and 255),
  add column trust_server_certificate boolean not null default false,
  add column last_test_status public.connection_test_status,
  add column last_test_error text check (last_test_error is null or length(last_test_error) between 1 and 500);

alter table public.db_connections
  alter column username drop default;

grant insert, update, delete on table public.db_connections to authenticated;

drop view public.db_connection_summaries;

create view public.db_connection_summaries
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
  last_tested_at,
  created_by,
  created_at,
  updated_at
from public.db_connections;

grant select on table public.db_connection_summaries to authenticated;
