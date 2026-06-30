# Query Compiler Preflight Gate Report

## Summary

This PR adds an internal Python-only Query Compiler preflight gate. The gate does not generate SQL, execute queries, expose API/Zod contracts, add UI, add migrations, or change Resolver/Semantic/Graph/Snapshot runtime behavior.

The preflight gate answers one question: can a resolved `QueryIntentResult` safely reach a future deterministic SQL Server read-only compiler?

## Implemented Stage Pipeline

The validator is stage-based, not monolithic:

| Stage | Purpose |
| --- | --- |
| `normalize_intent` | Validate ready intent shape and reject unsupported/raw-SQL intent payloads. |
| `artifact_freshness` | Check active/fresh Semantic Layer, graph validation, semantic invariant report, quality gate, snapshot availability/coverage. |
| `metadata_prefetch` | Collect selected metric, source/grain/date/dimension/filter/path metadata before deeper checks. |
| `metric_resolution` | Validate metric eligibility, source/grain safety, amount ambiguity, currency strategy, raw-SQL semantic payloads. |
| `date_resolution` | Validate selected date column/path and block silent audit-date or multi-date ambiguity. |
| `dimension_resolution` | Validate group-by dimension compatibility and fanout/allocation safety. |
| `filter_resolution` | Validate structured filters, PII policy, and SQL-like filter payloads. |
| `path_resolution` | Validate selected paths use trusted/enabled/verified FK joins and no lineage-as-join. |
| `policy_permission_check` | Diagnostic-only policy checks for metric access, status scope, currency, and native SQL prohibition. |
| `final_decision` | Merge diagnostics into final status and decision category. |

## Decision Contract

The report returns:

- `status`: `ready`, `ready_with_warnings`, `blocked`.
- `decision_category`: `safe`, `safe_with_disclosure`, `needs_policy`, `insufficient_metadata`, `unsafe`, `unsupported`, `stale`, `invalid_artifact`.
- `stage_results`: deterministic per-stage diagnostics.
- `plan_trace`: structured dry-plan trace with selected metric/date/dimension/filter/path references and no SQL.

Blocking category precedence is deterministic:

```text
invalid_artifact > stale > unsafe > unsupported > insufficient_metadata > needs_policy
```

If `schema_snapshot` is missing and snapshot checks are applicable, the report emits only `SCHEMA_SNAPSHOT_MISSING` for snapshot absence and caps readiness at `ready_with_warnings`.

## Positive Fixtures

| Fixture | Result |
| --- | --- |
| AdventureWorks customer master baseline | Ready with missing-snapshot warning when snapshot is omitted. |
| AdventureWorks revenue baseline | Status-scope disclosure is surfaced from Semantic Layer/Resolver output. |
| Ugly PMI schema with explicit semantic evidence | Quantity by category can pass through trusted FK paths. |
| Physical DB view as source object | Allowed when represented by snapshot/graph/semantic evidence; lineage is not treated as join evidence. |
| Composite/multi-hop explicit paths | Supported through stable edge keys, not physical names. |

## Negative Fixtures

Covered targeted failures include:

- blocked Query Intent;
- invalid graph validation report;
- stale Semantic Layer;
- missing selected metric;
- semantic invariant errors;
- missing FK path;
- disabled/untrusted FK path;
- lineage edge in join path;
- raw SQL semantic payload;
- silent amount/date/status/currency ambiguity;
- PII filter without policy;
- table without candidate key;
- snapshot coverage/object/FK gaps when a snapshot is provided.

## PMI/ERP Anti-Demo Coverage

The implementation avoids AdventureWorks/demo hardcoding in `query_compiler_preflight.py`. PMI/ERP cases live only in tests and include:

- ugly names such as `DOTES`, `DORIG`, `ANACLI`, `ARTICO`, `CATART`;
- missing FK header/detail;
- disabled FK header/detail;
- multiple amount columns;
- multiple business dates plus audit date;
- status/cancelled fields;
- PII fields;
- physical DB views and lineage.

Relationship inference from naming is not trusted. Manual relationship overrides are not implemented as durable policy and cannot silently promote a relationship to trusted FK evidence.

## Future Hooks

Reserved but not implemented:

```text
SemanticSegment:
  segment_key
  display_name
  base_table_key
  structured_filter_expression
  required_policy
  provenance
  status

FieldProfile:
  column_key
  distinct_count_estimate
  null_ratio
  min_value
  max_value
  top_values_redacted
  enum_like_confidence
  status_like_confidence
  pii_redacted
  profiled_at
  profile_hash

ConfirmedExampleRecord:
  natural_language_question
  query_intent_plan
  preflight_report
  selected_metric_key
  selected_dimension_keys
  selected_filter_keys
  compiled_sql_hash nullable
  human_outcome: accepted | corrected | rejected

FutureDependencyRecord:
  artifact_type: metric | dimension | segment | dashboard_widget | saved_intent
  artifact_key
  depends_on_metric_keys
  depends_on_column_keys
  depends_on_edge_keys
  depends_on_policy_keys
  semantic_hash
  graph_hash
```

The `plan_trace.cache_key_inputs_preview` exposes future-safe cache key inputs, but no cache keys or cache entries are computed.

## Explicit Non-Adoption

Atlante does not adopt an agent-written SQL model here.

```text
AI does not generate SQL.
Resolver outputs structured intent.
Preflight validates structured intent.
Compiler later generates SQL deterministically.
```

Native SQL, `ref_sql`, transform-like semantic objects, and free-form SQL authored inside Atlante artifacts are unsupported until a dedicated validator exists. Physical DB views are different: they can be technical source objects, while their captured definitions/lineage remain provenance, not trusted join evidence.

## Known Limitations

- Policy is internal/test-only. There is no durable tenant policy, RLS integration, user/group permission lookup, API contract, Zod schema, or UI.
- Field profiles are not implemented, so value semantics are never inferred from data distributions.
- Segments/named filters are not implemented; only report hooks exist.
- The gate validates selected plan references. It is not a full compiler and does not build SQL ASTs.
- Snapshot checks are strongest when the matching Technical Snapshot is supplied.

## Test Results

Implemented test file:

```text
services/query-engine/tests/test_query_compiler_preflight.py
```

Executed verification:

| Command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_compiler_preflight.py -q` | 10 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_introspection.py -q` | 31 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_queryability.py -q` | 20 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_semantic_invariants.py -q` | 10 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_intent.py -q` | 22 passed |
| `.\.venv\Scripts\python.exe -m pytest -q` | 241 passed, 1 skipped |
| `$env:CI='true'; pnpm --filter @atlantebi/contracts test` | 44 passed |
| `$env:CI='true'; pnpm --filter @atlantebi/db test` | 35 passed |
| `$env:CI='true'; pnpm --filter @atlantebi/web test` | 67 passed |
| `$env:CI='true'; pnpm --filter @atlantebi/web typecheck` | passed |
| `$env:CI='true'; pnpm lint` | passed |
| `$env:CI='true'; pnpm --filter @atlantebi/web build` | passed |

Hardcoded-name guard:

```powershell
Select-String -Path services/query-engine/app/query_compiler_preflight.py -Pattern "SalesOrder|ProductCategory|DOTES|DORIG|ANACLI|ARTICO|CATART"
```

Result: no matches.

## Final Recommendation

Query Compiler V1 can start only in a narrow scope after this PR:

- SQL Server read-only only;
- single resolved metric;
- no multi-metric, calculated metric, comparison, native SQL, or execution;
- no bridge/many-to-many unless explicit policy exists;
- trusted/enabled/verified FK paths only;
- active/fresh Semantic Layer and valid Graph/Semantic invariant reports;
- structured filters only;
- PII/status/currency/date ambiguity must be policied or disclosed;
- matching Technical Snapshot should be supplied for clean readiness.

Do not proceed to a broad Query Compiler V1 yet. The next PR should implement the narrow compiler behind this preflight gate, or first add durable policy/preflight integration if the desired compiler scope includes PII filters, bridge paths, view-backed metrics with policy, or status/currency rules beyond disclosures.
