begin;

create extension if not exists pgtap with schema extensions;

select plan(28);

select ok(
  to_regclass('public.semantic_versions') is null,
  'legacy semantic version relation is removed'
);

select ok(
  to_regclass('public.semantic_metrics') is null
    and to_regclass('public.business_anchors') is null,
  'legacy metric and business-anchor domain is removed'
);

select ok(
  not has_table_privilege(
    'authenticated',
    'public.semantic_layer_versions',
    'SELECT,INSERT,UPDATE,DELETE'
  ),
  'authenticated has no direct semantic layer access'
);

select ok(
  not has_table_privilege(
    'service_role',
    'public.semantic_layer_versions',
    'INSERT,UPDATE,DELETE'
  ),
  'service role cannot bypass semantic lifecycle RPCs with direct DML'
);

select ok(
  has_table_privilege(
    'service_role',
    'public.semantic_layer_versions',
    'SELECT'
  ),
  'service role can read persisted semantic artifacts'
);

select ok(
  not has_function_privilege(
    'authenticated',
    'public.persist_semantic_layer_version(uuid,uuid,uuid,uuid,jsonb,jsonb,uuid,integer,uuid,text)',
    'EXECUTE'
  ),
  'authenticated cannot invoke semantic persistence'
);

select ok(
  has_function_privilege(
    'service_role',
    'public.persist_semantic_layer_version(uuid,uuid,uuid,uuid,jsonb,jsonb,uuid,integer,uuid,text)',
    'EXECUTE'
  ),
  'service role can invoke the controlled semantic persistence wrapper'
);

select ok(
  not has_function_privilege(
    'service_role',
    'app_private.persist_semantic_layer_version_core(uuid,uuid,uuid,uuid,jsonb,jsonb,uuid,integer,uuid,text)',
    'EXECUTE'
  ),
  'service role cannot call semantic persistence core directly'
);

insert into auth.users (
  instance_id,
  id,
  aud,
  role,
  email,
  encrypted_password,
  email_confirmed_at,
  raw_app_meta_data,
  raw_user_meta_data,
  created_at,
  updated_at,
  confirmation_token,
  email_change,
  email_change_token_new,
  recovery_token
)
values
(
  '00000000-0000-0000-0000-000000000000',
  '10000000-0000-4000-8000-000000000031',
  'authenticated',
  'authenticated',
  'semantic-owner@example.com',
  '',
  now(),
  '{"provider":"email","providers":["email"]}',
  '{}',
  now(),
  now(),
  '',
  '',
  '',
  ''
),
(
  '00000000-0000-0000-0000-000000000000',
  '10000000-0000-4000-8000-000000000032',
  'authenticated',
  'authenticated',
  'semantic-editor@example.com',
  '',
  now(),
  '{"provider":"email","providers":["email"]}',
  '{}',
  now(),
  now(),
  '',
  '',
  '',
  ''
);

insert into public.tenants (id, slug, name, created_by)
values (
  '20000000-0000-4000-8000-000000000031',
  'semantic-lifecycle-test',
  'Semantic Lifecycle Test',
  '10000000-0000-4000-8000-000000000031'
);

insert into public.tenant_memberships (tenant_id, user_id, role, status)
values
(
  '20000000-0000-4000-8000-000000000031',
  '10000000-0000-4000-8000-000000000031',
  'owner',
  'active'
),
(
  '20000000-0000-4000-8000-000000000031',
  '10000000-0000-4000-8000-000000000032',
  'editor',
  'active'
);

insert into public.db_connections (
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
  trust_server_certificate,
  secret_ref,
  status,
  created_by
)
values (
  '30000000-0000-4000-8000-000000000031',
  '20000000-0000-4000-8000-000000000031',
  'Semantic SQL Server',
  'sqlserver',
  'public_allowlist',
  'sql.example.com',
  1433,
  'demo',
  'readonly_user',
  true,
  false,
  'gcp-secret-manager://projects/demo/secrets/semantic',
  'ready',
  '10000000-0000-4000-8000-000000000031'
);

insert into public.schema_snapshots (
  id,
  tenant_id,
  connection_id,
  engine,
  snapshot,
  snapshot_version,
  table_count,
  column_count,
  introspected_at,
  engine_version,
  schema_hash,
  snapshot_hash,
  coverage_status,
  coverage_warnings,
  summary,
  created_by
)
values (
  '40000000-0000-4000-8000-000000000031',
  '20000000-0000-4000-8000-000000000031',
  '30000000-0000-4000-8000-000000000031',
  'sqlserver',
  jsonb_build_object(
    'status', 'ok',
    'engine', 'sqlserver',
    'engine_version', '16.0',
    'schema_hash', repeat('a', 64),
    'snapshot_hash', repeat('b', 64),
    'coverage_status', 'ok',
    'tables', jsonb_build_array(),
    'foreign_keys', jsonb_build_array(),
    'unique_constraints', jsonb_build_array(),
    'check_constraints', jsonb_build_array(),
    'default_constraints', jsonb_build_array(),
    'indexes', jsonb_build_array(),
    'coverage_warnings', jsonb_build_array()
  ),
  1,
  1,
  1,
  now(),
  '16.0',
  repeat('a', 64),
  repeat('b', 64),
  'ok',
  '[]'::jsonb,
  jsonb_build_object(
    'database_name', 'demo',
    'engine', 'sqlserver',
    'engine_version', '16.0',
    'schema_hash', repeat('a', 64),
    'coverage_status', 'ok',
    'captured_at', to_char(now() at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') || 'Z',
    'duration_ms', 1,
    'total_objects', 1,
    'total_tables', 1,
    'total_views', 0,
    'total_columns', 1,
    'queryable_objects', 1,
    'non_queryable_objects', 0,
    'queryable_columns', 1,
    'non_queryable_columns', 0,
    'primary_keys_count', 1,
    'foreign_keys_count', 0,
    'unique_constraints_count', 1,
    'check_constraints_count', 0,
    'default_constraints_count', 0,
    'indexes_total_count', 1,
    'table_indexes_count', 1,
    'view_indexes_count', 0,
    'unique_indexes_count', 1,
    'filtered_indexes_count', 0,
    'included_columns_indexes_count', 0,
    'views_total', 0,
    'views_with_definition_count', 0,
    'views_without_definition_count', 0,
    'views_with_lineage_count', 0,
    'views_with_partial_lineage_count', 0,
    'views_without_lineage_count', 0,
    'view_lineage_dependencies_count', 0,
    'columns_with_declared_type_count', 1,
    'columns_without_declared_type_count', 0,
    'columns_with_default_count', 0,
    'computed_columns_count', 0,
    'identity_columns_count', 1,
    'pii_columns_count', 0,
    'excluded_columns_count', 0,
    'sensitive_columns_count', 0,
    'coverage_warnings_count', 0,
    'coverage_warnings_by_code', '{}'::jsonb
  ),
  '10000000-0000-4000-8000-000000000031'
);

insert into public.queryability_graph_versions (
  id,
  tenant_id,
  connection_id,
  schema_snapshot_id,
  version,
  contract_version,
  builder_version,
  policy_version,
  status,
  schema_hash,
  snapshot_hash,
  graph_input_hash,
  derivation_key,
  graph_hash,
  graph,
  node_count,
  column_count,
  edge_count,
  created_by
)
values (
  '50000000-0000-4000-8000-000000000031',
  '20000000-0000-4000-8000-000000000031',
  '30000000-0000-4000-8000-000000000031',
  '40000000-0000-4000-8000-000000000031',
  1,
  'queryability_graph.v1',
  '1.0.0',
  '1.0.0',
  'complete',
  repeat('a', 64),
  repeat('b', 64),
  repeat('c', 64),
  repeat('d', 64),
  repeat('e', 64),
  '{"nodes":[],"edges":[]}'::jsonb,
  0,
  0,
  0,
  '10000000-0000-4000-8000-000000000031'
);

insert into public.queryability_graph_nodes (
  id,
  tenant_id,
  graph_version_id,
  node_key,
  database_name,
  schema_name,
  object_name,
  object_type,
  queryability_status,
  bridge_candidate,
  payload
)
values (
  '51000000-0000-4000-8000-000000000031',
  '20000000-0000-4000-8000-000000000031',
  '50000000-0000-4000-8000-000000000031',
  repeat('1', 64),
  'demo',
  'dbo',
  'Parent',
  'table',
  'queryable',
  false,
  '{}'::jsonb
);

insert into public.queryability_graph_columns (
  tenant_id,
  graph_version_id,
  node_id,
  column_key,
  column_name,
  ordinal_position,
  technical_role,
  queryability_status,
  sensitivity,
  payload
)
values (
  '20000000-0000-4000-8000-000000000031',
  '50000000-0000-4000-8000-000000000031',
  '51000000-0000-4000-8000-000000000031',
  repeat('2', 64),
  'ParentID',
  1,
  'identifier',
  'queryable',
  'none',
  '{}'::jsonb
);

insert into public.queryability_graph_derivations (
  tenant_id,
  connection_id,
  schema_snapshot_id,
  graph_version_id,
  created_by
)
values (
  '20000000-0000-4000-8000-000000000031',
  '30000000-0000-4000-8000-000000000031',
  '40000000-0000-4000-8000-000000000031',
  '50000000-0000-4000-8000-000000000031',
  '10000000-0000-4000-8000-000000000031'
);

create function pg_temp.semantic_artifact(
  target_id uuid,
  target_version integer,
  target_revision integer,
  target_status text,
  target_graph_id uuid,
  target_graph_hash text,
  target_semantic_hash text
)
returns jsonb
language sql
as $$
  select jsonb_build_object(
    'contract_version', 'semantic_layer.v1',
    'tenant_id', '20000000-0000-4000-8000-000000000031',
    'connection_id', '30000000-0000-4000-8000-000000000031',
    'semantic_version_id', target_id,
    'queryability_graph_version_id', target_graph_id,
    'base_graph_hash', target_graph_hash,
    'version', target_version,
    'status', target_status,
    'freshness', 'fresh',
    'builder_version', '1.0.0',
    'ai_model_version', null,
    'ai_prompt_version', null,
    'validator_version', '1.0.0',
    'policy_version', '1.0.0',
    'revision', target_revision,
    'semantic_hash', target_semantic_hash,
    'tables', jsonb_build_array(
      jsonb_build_object(
        'node_key', repeat('1', 64),
        'schema_name', 'dbo',
        'object_name', 'Parent',
        'object_type', 'table',
        'display_name', 'Parent',
        'synonyms', jsonb_build_array(),
        'status', 'system_seeded',
        'included', true,
        'queryability_status', 'queryable'
      )
    ),
    'columns', jsonb_build_array(
      jsonb_build_object(
        'column_key', repeat('2', 64),
        'node_key', repeat('1', 64),
        'physical_name', 'ParentID',
        'synonyms', jsonb_build_array(),
        'native_type', 'int',
        'normalized_type', 'int',
        'technical_role', 'identifier',
        'nullable', false,
        'status', 'system_seeded',
        'included', true,
        'queryability_status', 'queryable',
        'inherited_sensitivity', 'none',
        'sensitivity', 'none'
      )
    ),
    'relationships', jsonb_build_array(),
    'business_concepts', jsonb_build_array(),
    'ambiguities', jsonb_build_array(),
    'metrics', jsonb_build_array(),
    'validation_report', jsonb_build_object(
      'status', case
        when target_status = 'proposed' then 'valid'
        else 'not_validated'
      end,
      'blocking_errors', jsonb_build_array(),
      'warnings', jsonb_build_array(),
      'info', jsonb_build_array(),
      'validated_revision', case
        when target_status = 'proposed' then target_revision
        else null
      end,
      'validated_at', case
        when target_status = 'proposed' then '2026-06-14T12:00:00Z'
        else null
      end,
      'validator_version', '1.0.0'
    )
  );
$$;

select throws_ok(
  $$
    select *
    from public.persist_semantic_layer_version(
      '10000000-0000-4000-8000-000000000032',
      '20000000-0000-4000-8000-000000000031',
      '30000000-0000-4000-8000-000000000031',
      '50000000-0000-4000-8000-000000000031',
      pg_temp.semantic_artifact(
        '60000000-0000-4000-8000-000000000031',
        1,
        1,
        'draft',
        '50000000-0000-4000-8000-000000000031',
        repeat('e', 64),
        repeat('f', 64)
      )
    )
  $$,
  '42501',
  'semantic layer owner or admin role required',
  'editor cannot persist semantic layers through the service wrapper'
);

create temporary table semantic_first as
select *
from public.persist_semantic_layer_version(
  '10000000-0000-4000-8000-000000000031',
  '20000000-0000-4000-8000-000000000031',
  '30000000-0000-4000-8000-000000000031',
  '50000000-0000-4000-8000-000000000031',
  pg_temp.semantic_artifact(
    '60000000-0000-4000-8000-000000000031',
    1,
    1,
    'draft',
    '50000000-0000-4000-8000-000000000031',
    repeat('e', 64),
    repeat('f', 64)
  )
);

select is(
  (select semantic_version_number from semantic_first),
  1,
  'first semantic version is allocated under the connection lock'
);

select is(
  (
    select count(*)::integer
    from public.semantic_layer_tables
    where semantic_version_id =
      '60000000-0000-4000-8000-000000000031'
  ),
  1,
  'canonical artifact is projected transactionally'
);

select throws_ok(
  $$
    select *
    from public.persist_semantic_layer_version(
      '10000000-0000-4000-8000-000000000031',
      '20000000-0000-4000-8000-000000000031',
      '30000000-0000-4000-8000-000000000031',
      '50000000-0000-4000-8000-000000000031',
      pg_temp.semantic_artifact(
        '60000000-0000-4000-8000-000000000031',
        1,
        2,
        'proposed',
        '50000000-0000-4000-8000-000000000031',
        repeat('e', 64),
        repeat('1', 64)
      ),
      null,
      '60000000-0000-4000-8000-000000000031',
      9
    )
  $$,
  '40001',
  'semantic layer revision conflict',
  'optimistic concurrency rejects stale writers'
);

select lives_ok(
  $$
    select *
    from public.persist_semantic_layer_version(
      '10000000-0000-4000-8000-000000000031',
      '20000000-0000-4000-8000-000000000031',
      '30000000-0000-4000-8000-000000000031',
      '50000000-0000-4000-8000-000000000031',
      pg_temp.semantic_artifact(
        '60000000-0000-4000-8000-000000000031',
        1,
        2,
        'proposed',
        '50000000-0000-4000-8000-000000000031',
        repeat('e', 64),
        repeat('1', 64)
      ),
      null,
      '60000000-0000-4000-8000-000000000031',
      1
    )
  $$,
  'owner can persist a validated proposed revision'
);

select lives_ok(
  $$
    select public.activate_semantic_layer_version(
      '10000000-0000-4000-8000-000000000031',
      '20000000-0000-4000-8000-000000000031',
      '30000000-0000-4000-8000-000000000031',
      '60000000-0000-4000-8000-000000000031',
      2
    )
  $$,
  'validated fresh proposal activates atomically'
);

select is(
  (
    select count(*)::integer
    from public.semantic_layer_versions
    where tenant_id = '20000000-0000-4000-8000-000000000031'
      and connection_id = '30000000-0000-4000-8000-000000000031'
      and status = 'active'
  ),
  1,
  'database constraint permits only one active version'
);

select throws_ok(
  $$
    update public.semantic_layer_versions
    set semantic_hash = repeat('9', 64)
    where id = '60000000-0000-4000-8000-000000000031'
  $$,
  '55000',
  'active and archived semantic layer artifacts are immutable',
  'active semantic artifact rejects direct mutation'
);

select lives_ok(
  $$
    select *
    from public.persist_semantic_layer_version(
      '10000000-0000-4000-8000-000000000031',
      '20000000-0000-4000-8000-000000000031',
      '30000000-0000-4000-8000-000000000031',
      '50000000-0000-4000-8000-000000000031',
      pg_temp.semantic_artifact(
        '60000000-0000-4000-8000-000000000032',
        2,
        1,
        'draft',
        '50000000-0000-4000-8000-000000000031',
        repeat('e', 64),
        repeat('7', 64)
      ),
      null,
      null,
      null,
      '60000000-0000-4000-8000-000000000031'
    )
  $$,
  'rebase persists as a new draft from an active source'
);

select is(
  (
    select rebased_from_version_id
    from public.semantic_layer_versions
    where id = '60000000-0000-4000-8000-000000000032'
  ),
  '60000000-0000-4000-8000-000000000031'::uuid,
  'rebase provenance is persisted'
);

select throws_ok(
  $$
    select *
    from public.persist_semantic_layer_version(
      '10000000-0000-4000-8000-000000000031',
      '20000000-0000-4000-8000-000000000031',
      '30000000-0000-4000-8000-000000000031',
      '50000000-0000-4000-8000-000000000031',
      pg_temp.semantic_artifact(
        '60000000-0000-4000-8000-000000000032',
        2,
        2,
        'draft',
        '50000000-0000-4000-8000-000000000031',
        repeat('e', 64),
        repeat('8', 64)
      ),
      null,
      '60000000-0000-4000-8000-000000000032',
      1,
      null
    )
  $$,
  '55000',
  'semantic version graph and rebase provenance are immutable',
  'draft updates cannot erase or replace rebase provenance'
);

select throws_ok(
  $$
    select *
    from public.persist_semantic_layer_version(
      '10000000-0000-4000-8000-000000000031',
      '20000000-0000-4000-8000-000000000031',
      '30000000-0000-4000-8000-000000000031',
      '50000000-0000-4000-8000-000000000031',
      pg_temp.semantic_artifact(
        '60000000-0000-4000-8000-000000000034',
        3,
        1,
        'draft',
        '50000000-0000-4000-8000-000000000031',
        repeat('e', 64),
        repeat('9', 64)
      ),
      jsonb_build_object(
        'provider', 'openai',
        'model_version', 'test-model',
        'prompt_version', 'test-prompt',
        'input_hash', repeat('a', 64),
        'proposal_hash', repeat('b', 64),
        'response_id', 'response-atomicity-test',
        'generated_at', 'not-a-timestamp'
      )
    )
  $$,
  '22007',
  'invalid input syntax for type timestamp with time zone: "not-a-timestamp"',
  'late provenance failure aborts semantic persistence'
);

select ok(
  not exists (
    select 1
    from public.semantic_layer_versions
    where id = '60000000-0000-4000-8000-000000000034'
  )
  and not exists (
    select 1
    from public.audit_logs
    where subject_id = '60000000-0000-4000-8000-000000000034'
  ),
  'failed semantic persistence leaves no partial version or audit record'
);

insert into public.queryability_graph_versions (
  id,
  tenant_id,
  connection_id,
  schema_snapshot_id,
  version,
  contract_version,
  builder_version,
  policy_version,
  status,
  schema_hash,
  snapshot_hash,
  graph_input_hash,
  derivation_key,
  graph_hash,
  graph,
  node_count,
  column_count,
  edge_count,
  created_by
)
values (
  '50000000-0000-4000-8000-000000000032',
  '20000000-0000-4000-8000-000000000031',
  '30000000-0000-4000-8000-000000000031',
  '40000000-0000-4000-8000-000000000031',
  2,
  'queryability_graph.v1',
  '1.0.1',
  '1.0.0',
  'complete',
  repeat('a', 64),
  repeat('b', 64),
  repeat('3', 64),
  repeat('4', 64),
  repeat('5', 64),
  '{"nodes":[],"edges":[]}'::jsonb,
  0,
  0,
  0,
  '10000000-0000-4000-8000-000000000031'
);

insert into public.queryability_graph_derivations (
  tenant_id,
  connection_id,
  schema_snapshot_id,
  graph_version_id,
  created_by,
  created_at
)
values (
  '20000000-0000-4000-8000-000000000031',
  '30000000-0000-4000-8000-000000000031',
  '40000000-0000-4000-8000-000000000031',
  '50000000-0000-4000-8000-000000000032',
  '10000000-0000-4000-8000-000000000031',
  statement_timestamp() + interval '1 second'
);

select throws_ok(
  $$
    select *
    from public.persist_semantic_layer_version(
      '10000000-0000-4000-8000-000000000031',
      '20000000-0000-4000-8000-000000000031',
      '30000000-0000-4000-8000-000000000031',
      '50000000-0000-4000-8000-000000000031',
      pg_temp.semantic_artifact(
        '60000000-0000-4000-8000-000000000033',
        3,
        1,
        'draft',
        '50000000-0000-4000-8000-000000000031',
        repeat('e', 64),
        repeat('7', 64)
      )
    )
  $$,
  '55000',
  'semantic layer must target the current queryability graph',
  'new semantic drafts cannot claim freshness against an obsolete graph'
);

select is(
  app_private.semantic_layer_effective_freshness(
    '60000000-0000-4000-8000-000000000031'
  )::text,
  'stale',
  'freshness is derived from the current graph hash'
);

select is(
  (
    select freshness::text
    from public.semantic_layer_versions
    where id = '60000000-0000-4000-8000-000000000031'
  ),
  'fresh',
  'active artifact is not mutated merely to record staleness'
);

select throws_ok(
  $$
    select public.activate_semantic_layer_version(
      '10000000-0000-4000-8000-000000000032',
      '20000000-0000-4000-8000-000000000031',
      '30000000-0000-4000-8000-000000000031',
      '60000000-0000-4000-8000-000000000031',
      2
    )
  $$,
  '42501',
  'semantic layer owner or admin role required',
  'editor cannot activate semantic versions'
);

select lives_ok(
  $$
    select public.archive_semantic_layer_version(
      '10000000-0000-4000-8000-000000000031',
      '20000000-0000-4000-8000-000000000031',
      '30000000-0000-4000-8000-000000000031',
      '60000000-0000-4000-8000-000000000031'
    )
  $$,
  'owner can archive a semantic version'
);

select is(
  (
    select status::text
    from public.semantic_layer_versions
    where id = '60000000-0000-4000-8000-000000000031'
  ),
  'archived',
  'archive transition is persisted'
);

select ok(
  exists (
    select 1
    from public.audit_logs
    where subject_id = '60000000-0000-4000-8000-000000000031'
      and action = 'semantic_layer.activated'
  )
  and exists (
    select 1
    from public.audit_logs
    where subject_id = '60000000-0000-4000-8000-000000000031'
      and action = 'semantic_layer.archived'
  ),
  'semantic lifecycle transitions are audited'
);

select * from finish();

rollback;
