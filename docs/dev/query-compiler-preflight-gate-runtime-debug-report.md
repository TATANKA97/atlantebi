# Query Compiler Preflight Gate Runtime Debug Report

## Summary

| Item | Result |
| --- | --- |
| Branch | `main` |
| Base commit | `62bc94c8bddac0503c48a5d89410c0f169490889` |
| Merge confirmed | yes, PR #56 is present in `origin/main` |
| Debug date | 2026-06-30 |
| Backend gates | pass |
| Web/package gates | pass |
| CI-ready | yes |

This pass verified the preflight gate after merge and added targeted tests for coverage gaps found during audit. No Query Compiler, SQL generation, SQL execution, Resolver runtime change, Semantic generator change, Queryability builder change, Schema Retrieval runtime change, API contract, Zod schema, DB migration, or UI change was introduced.

## Scope Check

Changed files in this debug pass:

| File | Reason |
| --- | --- |
| `services/query-engine/app/query_compiler_preflight.py` | Minimal category fix: missing selected path evidence is now `GRAPH_PATH_INVALID` and maps to `insufficient_metadata`, matching the missing-FK fail-closed contract. |
| `services/query-engine/tests/test_query_compiler_preflight.py` | Added targeted density tests for not-eligible metrics, snapshot metadata gaps, mixed category precedence, bridge/m2m, composite multi-schema path, and missing-FK category. |
| `docs/dev/query-compiler-preflight-gate-runtime-debug-report.md` | This runtime/debug report. |

## Code Shape Verdict

| Check | Verdict | Evidence |
| --- | --- | --- |
| Stage-based implementation | pass | `validate_query_compiler_preflight` runs ordered stage helpers and appends `final_decision`. |
| Not monolithic | pass | Validation logic is split across `normalize_intent`, `artifact_freshness`, `metadata_prefetch`, `metric_resolution`, `date_resolution`, `dimension_resolution`, `filter_resolution`, `path_resolution`, `policy_permission_check`, and `final_decision`. |
| `stage_results` populated | pass | Every stage returns `QueryCompilerPreflightStageResult`. |
| `plan_trace` has no SQL | pass | Tests assert trace serialization does not contain SQL text; raw SQL payloads are separately blocked. |
| `to_debug_dict()` deterministic | pass | Report dataclasses serialize with `asdict`; tests assert stable stage order and trace shape. |
| Resolver output side effects | pass | Test compares Resolver result before/after preflight. |

## Hardcoding Guard

Command:

```powershell
Select-String -Path services/query-engine/app/query_compiler_preflight.py -Pattern "SalesOrder|ProductCategory|DOTES|DORIG|ANACLI|ARTICO|CATART"
```

Result: no matches.

Verdict: pass. Fixture/demo names remain in tests only.

## Test Density Verdict

The original 10-test suite was good but not dense enough for post-merge confidence. Added tests to cover:

- not-eligible metric;
- snapshot selected metadata gap;
- missing FK as `insufficient_metadata`;
- stale + untrusted FK + missing policy precedence;
- bridge/many-to-many policy requirement;
- composite multi-schema trusted FK path.

Current preflight suite result:

```text
15 passed
```

Coverage matrix:

| Scenario | Covered | Notes |
| --- | --- | --- |
| blocked QueryIntent | yes | Unsupported intent blocks before compiler. |
| invalid graph | yes | Category precedence test. |
| stale semantic | yes | Direct stale layer test and mixed category test. |
| semantic invariant error | yes | Injected invariant error blocks. |
| missing selected metric | yes | Metadata prefetch blocks early. |
| not eligible metric | yes | Added in this pass. |
| missing snapshot | yes | Caps at `ready_with_warnings`. |
| snapshot selected metadata gap | yes | Added `SCHEMA_FK_NOT_FOUND` test. |
| missing FK | yes | Now `blocked + insufficient_metadata`. |
| disabled/untrusted FK | yes | `blocked + unsafe`. |
| lineage-as-join | yes | Physical view source allowed, lineage join blocked. |
| raw SQL semantic payload | yes | Raw SQL text blocks. |
| amount ambiguity | yes | Generic amount ambiguity blocks. |
| date ambiguity | yes | Multiple date + audit date diagnostics. |
| status/cancelled ambiguity | yes | Missing policy/disclosure blocks. |
| currency ambiguity | yes | Missing currency strategy blocks. |
| PII filter | yes | PII filter blocks without policy. |
| table without candidate key | yes | Grain unsafe diagnostic. |
| physical DB view as source | yes | Allowed as technical source object. |
| ugly PMI without evidence | yes | Blocks, no business meaning invented. |
| ugly PMI with evidence | yes | Passes through trusted FK evidence. |
| composite/multi-schema trusted path | yes | Added in this pass. |
| category precedence mixed errors | yes | Invalid/stale precedence plus stale/unsafe/policy mix. |
| policy source attribution | yes | Status disclosure source asserted. |
| no SQL in `plan_trace` | yes | Trace serialization assertion. |

## Runtime-Style Scenario Matrix

| Scenario | Expected | Verified Result |
| --- | --- | --- |
| AdventureWorks v12-style baseline | `ready_with_warnings + safe_with_disclosure`, status disclosure, no SQL | pass |
| Ugly PMI without evidence | `blocked`, no name-based relationship inference | pass |
| Ugly PMI with explicit evidence | `ready` or `ready_with_warnings`, trusted FK paths only | pass |
| Missing FK header/detail | `blocked + insufficient_metadata` | pass |
| Disabled/untrusted FK | `blocked + unsafe` | pass |
| Physical DB view | technical source allowed, lineage not join evidence | pass |
| Mixed blocking categories | all codes emitted; precedence respected | pass |

## Bugs Found And Fixed

| Symptom | Root Cause | Fix | Regression |
| --- | --- | --- | --- |
| Missing FK header/detail was categorized as `invalid_artifact`. | Missing selected edge used `GRAPH_REFERENCE_INVALID`, which is appropriate for broken artifact references but too strong for absent relationship evidence. | Changed missing selected path evidence to `GRAPH_PATH_INVALID` and mapped it to `insufficient_metadata`. | `test_missing_and_disabled_fk_fail_closed_without_name_inference` |
| Test suite did not explicitly cover not-eligible metric, snapshot FK gap, bridge/m2m, or composite multi-schema path. | Initial tests covered broad behavior but left several acceptance bullets indirect. | Added targeted tests. | New tests in `test_query_compiler_preflight.py` |

## Verification Results

| Command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_compiler_preflight.py -q` | 15 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_introspection.py -q` | 31 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_queryability.py -q` | 20 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_semantic_invariants.py -q` | 10 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_intent.py -q` | 22 passed |
| `.\.venv\Scripts\python.exe -m pytest -q` | 246 passed, 1 skipped |
| `$env:CI='true'; pnpm --filter @atlantebi/contracts test` | 44 passed |
| `$env:CI='true'; pnpm --filter @atlantebi/db test` | 35 passed |
| `$env:CI='true'; pnpm --filter @atlantebi/web test` | 67 passed |
| `$env:CI='true'; pnpm --filter @atlantebi/web typecheck` | passed |
| `$env:CI='true'; pnpm lint` | passed |
| `$env:CI='true'; pnpm --filter @atlantebi/web build` | passed |

## Final Recommendation

Can Query Compiler V1 narrow start?

Yes, but only in the narrow scope below.

Allowed compiler scope:

- SQL Server read-only;
- single metric;
- optional date range;
- optional one safe dimension;
- simple structured filters only;
- trusted FK paths only;
- no multi-metric;
- no calculated metrics;
- no comparisons;
- no bridge/m2m without policy;
- no native/raw SQL;
- no execution in compiler PR.

Do not start a broad compiler. The first compiler PR should consume this preflight gate, compile only the allowed narrow shape, and keep SQL execution out of scope.
