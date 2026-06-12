begin;

create extension if not exists pgtap with schema extensions;

select plan(18);

select ok(
  not has_table_privilege(
    'authenticated',
    'public.queryability_graph_versions',
    'SELECT'
  ),
  'authenticated cannot read full queryability graph payloads directly'
);

select ok(
  not has_table_privilege(
    'authenticated',
    'public.queryability_graph_edges',
    'INSERT'
  ),
  'authenticated cannot forge graph edges'
);

select ok(
  has_function_privilege(
    'service_role',
    'public.persist_queryability_graph_import(uuid,uuid,uuid,uuid,public.connection_engine,jsonb,jsonb,jsonb,integer,integer,timestamptz,boolean)',
    'EXECUTE'
  ),
  'service role can persist snapshot and graph atomically'
);

select ok(
  to_regprocedure(
    'public.persist_technical_schema_import(uuid,uuid,uuid,public.connection_engine,jsonb,jsonb,jsonb,jsonb,integer,integer,timestamptz)'
  ) is null,
  'legacy semantic projection import is removed'
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
values (
  '00000000-0000-0000-0000-000000000000',
  '10000000-0000-4000-8000-000000000020',
  'authenticated',
  'authenticated',
  'queryability-graph@example.com',
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
  '20000000-0000-4000-8000-000000000020',
  'queryability-graph-test',
  'Queryability Graph Test',
  '10000000-0000-4000-8000-000000000020'
);

insert into public.tenant_memberships (tenant_id, user_id, role, status)
values (
  '20000000-0000-4000-8000-000000000020',
  '10000000-0000-4000-8000-000000000020',
  'owner',
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
  '30000000-0000-4000-8000-000000000020',
  '20000000-0000-4000-8000-000000000020',
  'Queryability SQL Server',
  'sqlserver',
  'public_allowlist',
  'sql.example.com',
  1433,
  'demo',
  'readonly_user',
  true,
  false,
  'gcp-secret-manager://projects/demo/secrets/queryability',
  'ready',
  '10000000-0000-4000-8000-000000000020'
);

create temporary table queryability_fixture (
  snapshot jsonb not null,
  summary jsonb not null,
  graph jsonb not null
) on commit drop;

insert into queryability_fixture (snapshot, summary, graph)
values (
  '{
    "status":"ok",
    "message":"Schema introspection completed.",
    "introspected_at":"2026-06-12T08:00:00Z",
    "duration_ms":10,
    "engine":"sqlserver",
    "database_name":"demo",
    "engine_version":"16.0.1000.6",
    "schema_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "snapshot_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "coverage_status":"ok",
    "tables":[{"schema":"dbo","name":"Parent","table_type":"base_table","columns":[],"view_lineage":[]}],
    "foreign_keys":[],
    "unique_constraints":[],
    "check_constraints":[],
    "default_constraints":[],
    "indexes":[],
    "coverage_warnings":[]
  }',
  '{
    "database_name":"demo",
    "engine":"sqlserver",
    "engine_version":"16.0.1000.6",
    "schema_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "coverage_status":"ok",
    "captured_at":"2026-06-12T08:00:00Z",
    "duration_ms":10,
    "total_objects":1,
    "total_tables":1,
    "total_views":0,
    "total_columns":0,
    "queryable_objects":0,
    "non_queryable_objects":1,
    "queryable_columns":0,
    "non_queryable_columns":0,
    "primary_keys_count":0,
    "foreign_keys_count":0,
    "unique_constraints_count":0,
    "check_constraints_count":0,
    "default_constraints_count":0,
    "indexes_total_count":0,
    "table_indexes_count":0,
    "view_indexes_count":0,
    "unique_indexes_count":0,
    "filtered_indexes_count":0,
    "included_columns_indexes_count":0,
    "views_total":0,
    "views_with_definition_count":0,
    "views_without_definition_count":0,
    "views_with_lineage_count":0,
    "views_with_partial_lineage_count":0,
    "views_without_lineage_count":0,
    "view_lineage_dependencies_count":0,
    "columns_with_declared_type_count":0,
    "columns_without_declared_type_count":0,
    "columns_with_default_count":0,
    "computed_columns_count":0,
    "identity_columns_count":0,
    "pii_columns_count":0,
    "excluded_columns_count":0,
    "sensitive_columns_count":0,
    "coverage_warnings_count":0,
    "coverage_warnings_by_code":{}
  }',
  '{
    "contract_version":"queryability_graph.v1",
    "tenant_id":"20000000-0000-4000-8000-000000000020",
    "connection_id":"30000000-0000-4000-8000-000000000020",
    "schema_snapshot_id":"40000000-0000-4000-8000-000000000020",
    "engine":"sqlserver",
    "schema_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "snapshot_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "graph_input_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "derivation_key":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "graph_hash":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "builder_version":"1.0.0",
    "policy_version":"1.0.0",
    "status":"complete",
    "status_reasons":[],
    "semantic_status":"not_initialized",
    "nodes":[{
      "node_key":"1111111111111111111111111111111111111111111111111111111111111111",
      "database_name":"demo",
      "schema_name":"dbo",
      "object_name":"Parent",
      "object_type":"table",
      "queryability_status":"excluded",
      "reason_codes":["NO_QUERYABLE_COLUMNS"],
      "bridge_candidate":false,
      "candidate_keys":[],
      "columns":[]
    }],
    "edges":[]
  }'
);

select throws_ok(
  $$
    select *
    from public.persist_queryability_graph_import(
      '10000000-0000-4000-8000-000000000020',
      '20000000-0000-4000-8000-000000000020',
      '30000000-0000-4000-8000-000000000020',
      '40000000-0000-4000-8000-000000000020',
      'sqlserver',
      (
        select
          (snapshot - 'coverage_status')
          || '{"coverage_state":"complete"}'::jsonb
        from queryability_fixture
      ),
      (select summary from queryability_fixture),
      (select graph from queryability_fixture),
      1,
      0,
      '2026-06-12T08:00:00Z'
    )
  $$,
  '22023',
  'technical snapshot is invalid or blocked',
  'legacy coverage_state imports are rejected'
);

create temporary table first_import as
select *
from public.persist_queryability_graph_import(
  '10000000-0000-4000-8000-000000000020',
  '20000000-0000-4000-8000-000000000020',
  '30000000-0000-4000-8000-000000000020',
  '40000000-0000-4000-8000-000000000020',
  'sqlserver',
  (select snapshot from queryability_fixture),
  (select summary from queryability_fixture),
  (select graph from queryability_fixture),
  1,
  0,
  '2026-06-12T08:00:00Z'
);

select is(
  (select deduplicated from first_import),
  false,
  'first graph import creates immutable artifacts'
);

select is(
  (select semantic_status from first_import),
  'not_initialized',
  'successful import leaves semantic layer absent'
);

select is(
  (
    select count(*)::integer
    from public.queryability_graph_versions
    where tenant_id = '20000000-0000-4000-8000-000000000020'
  ),
  1,
  'one graph version is persisted'
);

select is(
  (
    select coverage_status::text
    from public.schema_snapshot_summaries
    where id = (select schema_snapshot_id from first_import)
  ),
  'ok',
  'snapshot summary exposes strict coverage status'
);

select is(
  (
    select summary->>'database_name'
    from public.schema_snapshot_summaries
    where id = (select schema_snapshot_id from first_import)
  ),
  'demo',
  'snapshot summary exposes the persisted sanitized import summary'
);

select is(
  (
    select count(*)::integer
    from public.semantic_versions
    where tenant_id = '20000000-0000-4000-8000-000000000020'
  ),
  0,
  'graph import creates no semantic draft'
);

update queryability_fixture
set graph = jsonb_set(
  graph,
  '{schema_snapshot_id}',
  '"40000000-0000-4000-8000-000000000021"'
);

create temporary table second_import as
select *
from public.persist_queryability_graph_import(
  '10000000-0000-4000-8000-000000000020',
  '20000000-0000-4000-8000-000000000020',
  '30000000-0000-4000-8000-000000000020',
  '40000000-0000-4000-8000-000000000021',
  'sqlserver',
  (select snapshot from queryability_fixture),
  (select summary from queryability_fixture),
  (select graph from queryability_fixture),
  1,
  0,
  '2026-06-12T08:00:00Z'
);

select is(
  (select deduplicated from second_import),
  true,
  'same derivation key and graph hash are deduplicated'
);

select is(
  (select schema_snapshot_id from second_import),
  (select schema_snapshot_id from first_import),
  'deduplication returns the original snapshot'
);

update queryability_fixture
set graph = jsonb_set(
  jsonb_set(
    jsonb_set(
      jsonb_set(
        graph,
        '{schema_snapshot_id}',
        '"40000000-0000-4000-8000-000000000020"'
      ),
      '{policy_version}',
      '"2.0.0"'
    ),
    '{derivation_key}',
    '"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"'
  ),
  '{graph_hash}',
  '"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"'
);

create temporary table rebuilt_graph as
select *
from public.persist_queryability_graph_import(
  '10000000-0000-4000-8000-000000000020',
  '20000000-0000-4000-8000-000000000020',
  '30000000-0000-4000-8000-000000000020',
  '40000000-0000-4000-8000-000000000020',
  'sqlserver',
  (select snapshot from queryability_fixture),
  (select summary from queryability_fixture),
  (select graph from queryability_fixture),
  1,
  0,
  '2026-06-12T08:00:00Z',
  true
);

select is(
  (select queryability_graph_version from rebuilt_graph),
  2,
  'changed policy creates a new immutable graph version'
);

select is(
  (
    select count(*)::integer
    from public.schema_snapshots
    where tenant_id = '20000000-0000-4000-8000-000000000020'
  ),
  1,
  'manual rebuild reuses the protected schema snapshot'
);

update queryability_fixture
set graph = jsonb_set(
  jsonb_set(
    jsonb_set(
      graph,
      '{schema_snapshot_id}',
      '"40000000-0000-4000-8000-000000000022"'
    ),
    '{derivation_key}',
    '"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"'
  ),
  '{edges}',
  '[{
    "edge_key":"9999999999999999999999999999999999999999999999999999999999999999",
    "edge_type":"fk_join",
    "constraint_name":"FK_Dangling",
    "from_node_key":"8888888888888888888888888888888888888888888888888888888888888888",
    "to_node_key":"1111111111111111111111111111111111111111111111111111111111111111",
    "column_pairs":[],
    "relationship_shape":"many_to_one",
    "child_to_parent":"exactly_one",
    "parent_to_child":"zero_or_many",
    "nullable_fk":false,
    "self_reference":false,
    "verified_by_db":true,
    "enforcement_status":"enabled",
    "validation_status":"trusted",
    "automatic_join_allowed":true,
    "reason_codes":[]
  }]'::jsonb
);

select throws_ok(
  $$
    select *
    from public.persist_queryability_graph_import(
      '10000000-0000-4000-8000-000000000020',
      '20000000-0000-4000-8000-000000000020',
      '30000000-0000-4000-8000-000000000020',
      '40000000-0000-4000-8000-000000000022',
      'sqlserver',
      (select snapshot from queryability_fixture),
      (select summary from queryability_fixture),
      (select graph from queryability_fixture),
      1,
      0,
      '2026-06-12T08:00:00Z'
    )
  $$,
  '23503',
  'queryability graph edge references unknown node',
  'dangling edges reject the complete transaction'
);

select is(
  (
    select count(*)::integer
    from public.schema_snapshots
    where id = '40000000-0000-4000-8000-000000000022'
  ),
  0,
  'failed graph import leaves no partial snapshot'
);

select throws_ok(
  $$
    update public.queryability_graph_versions
    set graph_hash = '0000000000000000000000000000000000000000000000000000000000000000'
    where id = (select queryability_graph_id from first_import)
  $$,
  '55000',
  'queryability graph artifacts are immutable',
  'persisted graph versions cannot be updated'
);

select * from finish();
rollback;
