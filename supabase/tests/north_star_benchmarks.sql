begin;

create extension if not exists pgtap with schema extensions;

select plan(15);

select ok(
  to_regclass('public.north_star_benchmarks') is not null,
  'north star benchmark table exists'
);

select ok(
  not has_table_privilege(
    'authenticated',
    'public.north_star_benchmarks',
    'SELECT,INSERT,UPDATE,DELETE'
  ),
  'authenticated has no direct north star table access'
);

select ok(
  not has_table_privilege(
    'service_role',
    'public.north_star_benchmarks',
    'INSERT,UPDATE,DELETE'
  ),
  'service role cannot bypass north star RPCs with direct DML'
);

select ok(
  has_table_privilege('service_role', 'public.north_star_benchmarks', 'SELECT'),
  'service role can read north star benchmarks'
);

select ok(
  has_function_privilege(
    'service_role',
    'public.create_north_star_benchmark(uuid,uuid,uuid,jsonb)',
    'EXECUTE'
  ),
  'service role can invoke controlled north star create RPC'
);

select ok(
  not has_function_privilege(
    'service_role',
    'app_private.create_north_star_benchmark(uuid,uuid,uuid,jsonb)',
    'EXECUTE'
  ),
  'service role cannot call north star core directly'
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
  '10000000-0000-4000-8000-000000000061',
  'authenticated',
  'authenticated',
  'north-star-owner@example.com',
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
  '10000000-0000-4000-8000-000000000062',
  'authenticated',
  'authenticated',
  'north-star-editor@example.com',
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
  '20000000-0000-4000-8000-000000000061',
  'north-star-test',
  'North Star Test',
  '10000000-0000-4000-8000-000000000061'
);

insert into public.tenant_memberships (tenant_id, user_id, role, status)
values
(
  '20000000-0000-4000-8000-000000000061',
  '10000000-0000-4000-8000-000000000061',
  'owner',
  'active'
),
(
  '20000000-0000-4000-8000-000000000061',
  '10000000-0000-4000-8000-000000000062',
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
  '30000000-0000-4000-8000-000000000061',
  '20000000-0000-4000-8000-000000000061',
  'North Star SQL Server',
  'sqlserver',
  'public_allowlist',
  'sql.example.com',
  1433,
  'demo',
  'readonly_user',
  true,
  false,
  'gcp-secret-manager://projects/demo/secrets/north-star',
  'ready',
  '10000000-0000-4000-8000-000000000061'
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
  '40000000-0000-4000-8000-000000000061',
  '20000000-0000-4000-8000-000000000061',
  '30000000-0000-4000-8000-000000000061',
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
    'captured_at', '2026-06-16T09:00:00Z',
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
  '10000000-0000-4000-8000-000000000061'
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
  '50000000-0000-4000-8000-000000000061',
  '20000000-0000-4000-8000-000000000061',
  '30000000-0000-4000-8000-000000000061',
  '40000000-0000-4000-8000-000000000061',
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
  1,
  1,
  0,
  '10000000-0000-4000-8000-000000000061'
);

insert into public.queryability_graph_derivations (
  tenant_id,
  connection_id,
  schema_snapshot_id,
  graph_version_id,
  created_by
)
values (
  '20000000-0000-4000-8000-000000000061',
  '30000000-0000-4000-8000-000000000061',
  '40000000-0000-4000-8000-000000000061',
  '50000000-0000-4000-8000-000000000061',
  '10000000-0000-4000-8000-000000000061'
);

insert into public.semantic_layer_versions (
  id,
  tenant_id,
  connection_id,
  version,
  created_by,
  queryability_graph_version_id,
  base_graph_hash,
  contract_version,
  status,
  freshness,
  builder_version,
  ai_model_version,
  ai_prompt_version,
  validator_version,
  policy_version,
  revision,
  validated_revision,
  semantic_hash,
  artifact,
  validation_report,
  activated_at
)
values (
  '60000000-0000-4000-8000-000000000061',
  '20000000-0000-4000-8000-000000000061',
  '30000000-0000-4000-8000-000000000061',
  1,
  '10000000-0000-4000-8000-000000000061',
  '50000000-0000-4000-8000-000000000061',
  repeat('e', 64),
  'semantic_layer.v1',
  'active',
  'fresh',
  '1.0.0',
  'test',
  '1.0.0',
  '1.0.0',
  '1.0.0',
  1,
  1,
  repeat('f', 64),
  jsonb_build_object(
    'contract_version', 'semantic_layer.v1',
    'tenant_id', '20000000-0000-4000-8000-000000000061',
    'connection_id', '30000000-0000-4000-8000-000000000061',
    'semantic_version_id', '60000000-0000-4000-8000-000000000061',
    'queryability_graph_version_id', '50000000-0000-4000-8000-000000000061',
    'base_graph_hash', repeat('e', 64),
    'version', 1,
    'status', 'active',
    'freshness', 'fresh',
    'builder_version', '1.0.0',
    'ai_model_version', 'test',
    'ai_prompt_version', '1.0.0',
    'validator_version', '1.0.0',
    'policy_version', '1.0.0',
    'revision', 1,
    'semantic_hash', repeat('f', 64),
    'tables', jsonb_build_array(),
    'columns', jsonb_build_array(),
    'relationships', jsonb_build_array(),
    'business_concepts', jsonb_build_array(),
    'ambiguities', jsonb_build_array(),
    'metrics', jsonb_build_array(),
    'validation_report', jsonb_build_object(
      'status', 'valid',
      'blocking_errors', jsonb_build_array(),
      'warnings', jsonb_build_array(),
      'info', jsonb_build_array(),
      'validated_revision', 1,
      'validated_at', '2026-06-16T09:00:00Z',
      'validator_version', '1.0.0'
    )
  ),
  jsonb_build_object(
    'status', 'valid',
    'blocking_errors', jsonb_build_array(),
    'warnings', jsonb_build_array(),
    'info', jsonb_build_array(),
    'validated_revision', 1,
    'validated_at', '2026-06-16T09:00:00Z',
    'validator_version', '1.0.0'
  ),
  now()
);

insert into public.semantic_layer_tables (
  tenant_id,
  semantic_version_id,
  node_key,
  schema_name,
  object_name,
  object_type,
  display_name,
  status,
  included,
  queryability_status,
  payload
)
values (
  '20000000-0000-4000-8000-000000000061',
  '60000000-0000-4000-8000-000000000061',
  repeat('1', 64),
  'dbo',
  'SalesOrderHeader',
  'table',
  'Ordini',
  'ai_proposed',
  true,
  'queryable',
  '{}'::jsonb
);

insert into public.semantic_layer_business_concepts (
  tenant_id,
  semantic_version_id,
  business_concept_key,
  canonical_name,
  display_name,
  status,
  provenance,
  payload
)
values (
  '20000000-0000-4000-8000-000000000061',
  '60000000-0000-4000-8000-000000000061',
  '80000000-0000-4000-8000-000000000061',
  'revenue',
  'Fatturato',
  'ai_proposed',
  'ai',
  '{}'::jsonb
);

insert into public.semantic_layer_metrics (
  tenant_id,
  semantic_version_id,
  metric_key,
  canonical_name,
  metric_definition_hash,
  business_concept_key,
  metric_variant,
  name,
  status,
  source_table_key,
  aggregation,
  measure_column_key,
  grain_table_key,
  grain_column_keys,
  compiler_eligibility,
  confidence_score,
  confidence_label,
  enabled,
  payload
)
values (
  '20000000-0000-4000-8000-000000000061',
  '60000000-0000-4000-8000-000000000061',
  '70000000-0000-4000-8000-000000000061',
  'fatturato_netto',
  repeat('9', 64),
  '80000000-0000-4000-8000-000000000061',
  'net_header',
  'Fatturato netto',
  'ai_proposed',
  repeat('1', 64),
  'sum',
  repeat('2', 64),
  repeat('1', 64),
  array[repeat('2', 64)],
  'eligible_with_disclosure',
  0.95000,
  'high',
  true,
  '{}'::jsonb
);

select lives_ok(
  $test$
    select public.create_north_star_benchmark(
      '10000000-0000-4000-8000-000000000061',
      '20000000-0000-4000-8000-000000000061',
      '30000000-0000-4000-8000-000000000061',
      jsonb_build_object(
        'connection_id', '30000000-0000-4000-8000-000000000061',
        'semantic_version_id', '60000000-0000-4000-8000-000000000061',
        'metric_key', '70000000-0000-4000-8000-000000000061',
        'name', 'Fatturato annuo atteso',
        'expected_value', 10000000,
        'value_type', 'currency',
        'currency', 'EUR',
        'period_type', 'year',
        'tolerance_mode', 'percentage',
        'tolerance_percentage', 10,
        'severity', 'high',
        'enabled', true
      )
    )
  $test$,
  'owner can create a benchmark for an eligible active metric'
);

select is(
  (select count(*)::integer from public.north_star_benchmarks),
  1,
  'north star benchmark is persisted'
);

select throws_ok(
  $test$
    select public.create_north_star_benchmark(
      '10000000-0000-4000-8000-000000000062',
      '20000000-0000-4000-8000-000000000061',
      '30000000-0000-4000-8000-000000000061',
      jsonb_build_object(
        'connection_id', '30000000-0000-4000-8000-000000000061',
        'semantic_version_id', '60000000-0000-4000-8000-000000000061',
        'metric_key', '70000000-0000-4000-8000-000000000061',
        'name', 'Benchmark editor',
        'expected_value', 10000000,
        'value_type', 'currency',
        'currency', 'EUR',
        'period_type', 'year',
        'tolerance_mode', 'percentage',
        'tolerance_percentage', 10,
        'severity', 'high',
        'enabled', true
      )
    )
  $test$,
  '42501',
  'north star owner or admin role required',
  'editor cannot create north star benchmarks'
);

select throws_ok(
  $test$
    select public.create_north_star_benchmark(
      '10000000-0000-4000-8000-000000000061',
      '20000000-0000-4000-8000-000000000061',
      '30000000-0000-4000-8000-000000000061',
      jsonb_build_object(
        'connection_id', '30000000-0000-4000-8000-000000000061',
        'semantic_version_id', '60000000-0000-4000-8000-000000000061',
        'metric_key', '70000000-0000-4000-8000-000000000099',
        'name', 'Metrica inesistente',
        'expected_value', 10000000,
        'value_type', 'currency',
        'currency', 'EUR',
        'period_type', 'year',
        'tolerance_mode', 'percentage',
        'tolerance_percentage', 10,
        'severity', 'high',
        'enabled', true
      )
    )
  $test$,
  '22023',
  'eligible active metric not found for north star benchmark',
  'missing metric is rejected'
);

select throws_ok(
  $test$
    select public.create_north_star_benchmark(
      '10000000-0000-4000-8000-000000000061',
      '20000000-0000-4000-8000-000000000061',
      '30000000-0000-4000-8000-000000000061',
      jsonb_build_object(
        'connection_id', '30000000-0000-4000-8000-000000000061',
        'semantic_version_id', '60000000-0000-4000-8000-000000000061',
        'metric_key', '70000000-0000-4000-8000-000000000061',
        'name', 'Campo extra',
        'expected_value', 10000000,
        'value_type', 'currency',
        'currency', 'EUR',
        'period_type', 'year',
        'tolerance_mode', 'percentage',
        'tolerance_percentage', 10,
        'severity', 'high',
        'enabled', true,
        'unexpected', true
      )
    )
  $test$,
  '22023',
  'north star payload contains unsupported fields',
  'north star RPC rejects unsupported payload fields'
);

select throws_ok(
  $test$
    select public.create_north_star_benchmark(
      '10000000-0000-4000-8000-000000000061',
      '20000000-0000-4000-8000-000000000061',
      '30000000-0000-4000-8000-000000000061',
      jsonb_build_object(
        'connection_id', '30000000-0000-4000-8000-000000000061',
        'semantic_version_id', '60000000-0000-4000-8000-000000000061',
        'metric_key', '70000000-0000-4000-8000-000000000061',
        'name', 'Numero stringificato',
        'expected_value', '10000000',
        'value_type', 'currency',
        'currency', 'EUR',
        'period_type', 'year',
        'tolerance_mode', 'percentage',
        'tolerance_percentage', 10,
        'severity', 'high',
        'enabled', true
      )
    )
  $test$,
  '22023',
  'north star expected_value is invalid',
  'north star RPC rejects stringified numeric fields'
);

select throws_ok(
  $test$
    select public.create_north_star_benchmark(
      '10000000-0000-4000-8000-000000000061',
      '20000000-0000-4000-8000-000000000061',
      '30000000-0000-4000-8000-000000000061',
      jsonb_build_object(
        'connection_id', '30000000-0000-4000-8000-000000000061',
        'semantic_version_id', '60000000-0000-4000-8000-000000000061',
        'metric_key', '70000000-0000-4000-8000-000000000061',
        'name', 'Conteggio con currency non valido',
        'expected_value', 100,
        'value_type', 'count',
        'currency', 'EUR',
        'period_type', 'month',
        'tolerance_mode', 'percentage',
        'tolerance_percentage', 10,
        'severity', 'medium',
        'enabled', true
      )
    )
  $test$,
  '23514',
  'non-currency benchmark cannot carry currency'
);

select lives_ok(
  $test$
    select public.delete_north_star_benchmark(
      '10000000-0000-4000-8000-000000000061',
      '20000000-0000-4000-8000-000000000061',
      (select benchmark_key from public.north_star_benchmarks limit 1)
    )
  $test$,
  'owner can delete north star benchmarks'
);

select is(
  (select count(*)::integer from public.north_star_benchmarks),
  0,
  'north star benchmark delete removes the benchmark'
);

rollback;
