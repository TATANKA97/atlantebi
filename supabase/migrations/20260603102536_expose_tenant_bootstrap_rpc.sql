create or replace function public.create_tenant_with_owner(
  tenant_slug text,
  tenant_name text,
  tenant_plan text default 'pilot'
)
returns uuid
language sql
security invoker
set search_path = public, app_private, pg_temp
as $$
  select app_private.create_tenant_with_owner(tenant_slug, tenant_name, tenant_plan);
$$;

grant execute on function public.create_tenant_with_owner(text, text, text) to authenticated;
