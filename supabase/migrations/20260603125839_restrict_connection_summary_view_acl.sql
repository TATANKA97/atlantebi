revoke all privileges on table public.db_connection_summaries from anon;
revoke all privileges on table public.db_connection_summaries from authenticated;

grant select on table public.db_connection_summaries to authenticated;
