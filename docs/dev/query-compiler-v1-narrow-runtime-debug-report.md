# Query Compiler V1 Narrow Runtime Debug Report

## 1. Summary

| Item | Result |
| --- | --- |
| Branch | `main` |
| Commit | `7b4959958ee8a2b04cd6c3453aa39e3503bf121c` |
| Source | `origin/main`, after merge PR #57 |
| Date | 2026-07-01 |
| Backend gates | pass |
| Web/package gates | pass |
| Runtime code changes in this pass | none |
| CI-ready | yes |

The post-merge debug pass verified the Query Compiler V1 narrow implementation as a deterministic, preflight-gated, snapshot-bound SQL Server `SELECT` compiler. It does not execute SQL, does not import SQL drivers, does not search paths, and does not contain demo/fixture hardcoding.

This pass created only this report. No Resolver, Semantic Layer, Queryability Graph, Technical Snapshot runtime, API, Zod, UI, migration, compiler feature, dry-run, or execution change was introduced.

## 2. Scope Check

| Check | Verdict | Evidence |
| --- | --- | --- |
| Started from latest `origin/main` | pass | `git log -1`: `7b49599 Merge pull request #57 from TATANKA97/codex/query-compiler-v1-narrow` |
| Compiler PR present | pass | `services/query-engine/app/query_compiler.py`, `services/query-engine/tests/test_query_compiler.py`, `docs/dev/query-compiler-v1-narrow-report.md` |
| No local code ahead before report | pass | `git status --short --branch`: `## main...origin/main` |
| Runtime changes in this pass | none | Report-only diff |

## 3. Code Shape Verdict

| Requirement | Verdict | Notes |
| --- | --- | --- |
| No SQL driver imports | pass | Guard found no `pyodbc`, `sqlalchemy`, or SQL Server driver import. |
| No cursor/execute calls | pass | Guard found no `cursor` or `.execute`. |
| No raw SQL input accepted | pass | Compiler blocks raw SQL payloads with `RAW_SQL_NOT_ALLOWED`. |
| No path search | pass | Compiler validates selected paths; it does not call path search. |
| No relationship inference from naming | pass | Joins are compiled only from selected graph edge metadata. |
| Preflight-gated | pass | Only `ready/safe` and `ready_with_warnings/safe_with_disclosure` are accepted. |
| Snapshot-bound | pass | Missing `schema_snapshot` blocks with `SCHEMA_SNAPSHOT_MISSING`. |
| Replay protection | pass | Selected refs and hashes are checked with `PREFLIGHT_CONTEXT_MISMATCH`. |
| Deterministic debug output | pass | `to_debug_dict()` exists on result and trace dataclasses. |

## 4. Guards

| Guard | Command | Result |
| --- | --- | --- |
| No execution | `Select-String -Path services/query-engine/app/query_compiler.py -Pattern "cursor|\.execute|app\.drivers\.sqlserver|pyodbc|sqlalchemy"` | no matches |
| No demo/fixture literals | `Select-String -Path services/query-engine/app/query_compiler.py -Pattern "SalesOrder|ProductCategory|DOTES|DORIG|ANACLI|ARTICO|CATART"` | no matches |

## 5. Test Density Verdict

`tests/test_query_compiler.py` has targeted coverage for the critical compiler boundary. It is not just a happy-path suite.

| Area | Covered | Evidence |
| --- | --- | --- |
| Header metric with date range | yes | `test_header_metric_with_date_range_compiles_half_open_parameterized_sql` |
| Line metric grouped by category | yes | `test_line_metric_by_category_uses_trusted_path_group_shape_and_not_header_amount` |
| Ugly PMI explicit evidence | yes | `test_ugly_schema_with_explicit_evidence_compiles_without_demo_hardcoding` |
| Structured filters | yes | `test_structured_filters_expand_parameters_and_reject_invalid_shapes` |
| Composite multi-schema FK | yes | `test_composite_multischema_fk_preserves_pair_order_and_schema_qualification` |
| COUNT semantics | yes | `test_count_semantics_are_explicit_and_never_choose_grain_column_silently` |
| Preflight replay protection | yes | `test_binding_replay_hash_and_reference_mismatches_block` |
| Filter value replay mismatch | yes | `test_filter_value_replay_mismatch_blocks` |
| Rejected preflight states | yes | `test_non_accepted_preflight_snapshot_missing_and_unknown_dialect_block` |
| Untrusted/lineage/bridge/unsafe boundary | yes | `test_preflight_blocked_safety_cases_remain_blocked_at_compiler_boundary` |
| Cross-table filter path requirement | yes | `test_cross_table_filter_without_selected_path_blocks` |
| Identifier escaping | yes | `test_identifier_escaping_handles_reserved_spaces_and_closing_brackets` |
| Physical DB view source vs lineage join | yes | `test_view_source_can_compile_but_lineage_path_cannot` |
| No hardcoding/no execution calls | yes | `test_query_compiler_module_has_no_demo_literals_or_execution_calls` |

## 6. Scenario Matrix

| Scenario | Result | Notes |
| --- | --- | --- |
| Single metric, date range | pass | Compiles half-open date range with deterministic `@p0`, `@p1` parameters. |
| Grouped line metric | pass | Uses trusted FK path and deterministic grouped SQL shape. |
| Ugly PMI with explicit evidence | pass | Works through stable keys and explicit metadata, not table-name special cases. |
| Missing/blocked/non-accepted preflight | pass | Blocks before SQL generation. |
| Missing snapshot | pass | Blocks because V1 requires physical snapshot confirmation. |
| Hash/reference replay mismatch | pass | Blocks reused preflight reports with `PREFLIGHT_CONTEXT_MISMATCH`. |
| Filter value replay mismatch | pass | Blocks valid-looking preflight reused with changed filter values. |
| Untrusted FK path | pass | Blocks at compiler boundary. |
| Lineage edge as join | pass | Blocks; physical DB view source is separate from lineage-as-join. |
| Bridge/many-to-many | pass | Blocks unless future policy/preflight support exists. |
| PII/unsafe filter via non-accepted preflight | pass | Compiler rejects non-accepted preflight state. |
| Identifier escaping | pass | Bracket escaping covers reserved words, spaces, and `]`. |
| No execution | pass | Static guard and tests confirm no driver/cursor/execute path. |

## 7. Verification Results

| Command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_compiler.py -q` | `14 passed in 5.05s` |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_compiler_preflight.py -q` | `15 passed in 4.81s` |
| `.\.venv\Scripts\python.exe -m pytest tests/test_introspection.py -q` | `31 passed in 12.69s` |
| `.\.venv\Scripts\python.exe -m pytest tests/test_queryability.py -q` | `20 passed in 12.75s` |
| `.\.venv\Scripts\python.exe -m pytest tests/test_semantic_invariants.py -q` | `10 passed in 10.93s` |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_intent.py -q` | `22 passed in 29.28s` |
| `.\.venv\Scripts\python.exe -m pytest -q` | `260 passed, 1 skipped in 41.14s` |
| `$env:CI='true'; pnpm --filter @atlantebi/contracts test` | `44 passed` |
| `$env:CI='true'; pnpm --filter @atlantebi/db test` | `35 passed` |
| `$env:CI='true'; pnpm --filter @atlantebi/web test` | `67 passed` |
| `$env:CI='true'; pnpm --filter @atlantebi/web typecheck` | pass |
| `$env:CI='true'; pnpm lint` | pass |
| `$env:CI='true'; pnpm --filter @atlantebi/web build` | pass |

## 8. Bugs Found And Fixed

No new post-merge runtime bug was found in this pass.

The merged compiler PR already includes the earlier local debug fix for preflight replay protection over filter values. Without that fix, a valid preflight report for one filter value could be reused with a different filter value. The current merged test coverage includes `test_filter_value_replay_mismatch_blocks`.

## 9. Remaining Limitations

| Limitation | Status |
| --- | --- |
| No SQL execution | intentional |
| No dry-run/explain | intentional |
| No Result Validator | not implemented yet |
| No multi-metric/calculated/comparison support | intentionally blocked |
| No bridge/many-to-many policy support | intentionally blocked |
| No native/raw SQL semantic objects | intentionally blocked |
| No broad execution permission model | out of scope until execution planning |

## 10. Final Recommendation

Can Query Compiler V1 narrow stand as the base for Result Validator V1?

Yes.

Can execution or dry-run start after this PR?

No.

Next recommended step:

1. Implement Result Validator V1.
2. Run a post-merge/debug pass for the validator.
3. Only after that, plan controlled dry-run/execution. Execution should remain blocked until compiled SQL output is validated structurally and operationally against explicit read-only policy.
