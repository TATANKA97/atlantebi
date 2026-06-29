# Queryability Graph Hardening Test Report

## Summary

- Branch: `codex/fix-query-intent-suite-failures`
- Base hardening commit: `6ebcaf0 Harden queryability graph validation`
- Test/debug pass date: 2026-06-30
- Backend result: pass
- Web result: pass
- CI-ready: yes, based on local gates below

Important scope note: the branch is stacked on previous Query Intent Resolver runner commits, so the full diff against `origin/main` includes Query Intent UI/contracts/tests. The Queryability Graph hardening commit itself touched only:

- `docs/dev/queryability-graph-state-of-art.md`
- `services/query-engine/app/queryability.py`
- `services/query-engine/app/queryability_validation.py`
- `services/query-engine/tests/test_queryability.py`

This debug pass added only targeted coverage in `services/query-engine/tests/test_queryability.py` plus this report.

## Scope Check

Current debug-pass file changes:

- `services/query-engine/tests/test_queryability.py`
- `docs/dev/queryability-graph-hardening-test-report.md`

Explicitly not changed by this pass:

- Query Intent Resolver runtime logic
- Semantic Layer generation
- AI prompt/provider/transport
- SQL compiler
- SQL execution
- Dashboard/result validator

The hardening validator remains diagnostic and pure. It does not mutate or repair the graph, infer trusted relationships from names, choose business dates, or validate Semantic Layer freshness inside pure graph validation.

## Validator Coverage

| Area | Covered | Notes |
| --- | --- | --- |
| Structural invariants | yes | Duplicate node/column/edge keys, dangling edge refs, and FK column-pair mismatches are covered. The graph artifact does not currently expose declared count fields, so count-coherence is not applicable today. |
| Relationship invariants | yes | Trusted FK baseline, disabled/untrusted/unverified FK promotion, excluded FK columns, lineage join promotion, and self-reference diagnostics are covered. |
| Path ambiguity | yes | `find_queryability_paths` ambiguous result is validated separately through `validate_queryability_path_result`. |
| Bridge/m2m | yes | Bridge candidate and fanout path diagnostics are covered. |
| View lineage | yes | Lineage remains provenance-only, and forced lineage joins are invalid. |
| PII/sensitive | yes | Email, phone, codice fiscale, partita IVA, IBAN, password, and token behavior are covered. PII can remain technically queryable but requires downstream policy. |
| Multiple dates | yes | Multiple date columns produce `MULTIPLE_DATE_COLUMNS_REQUIRES_SEMANTIC_SELECTION`; graph does not choose a business date. |
| Composite keys | yes | Composite FK pair order is preserved and validated. |
| Table without PK | yes | Queryable table without candidate key produces `TABLE_WITHOUT_PK_UNSAFE_FOR_GRAIN`. |
| Freshness helper | yes | Graph hash and policy hash mismatch are tested through separate freshness helper, not graph invariants. |

## Anti-Demo Fixtures

| Fixture | Covered | Behavior verified |
| --- | --- | --- |
| AdventureWorks baseline | yes | Valid/valid-with-warnings, trusted FK available, lineage not joinable. |
| Missing FK header/detail | yes | No automatic join invented; `MISSING_FK_NO_TRUSTED_JOIN` only when expected relation is explicitly supplied by test helper. |
| Ugly PMI schema | yes | `DOTES`, `DORIG`, `ANACLI`, `ARTICO`, `CATART` get stable keys and no name-derived trusted joins. |
| Ambiguous paths | yes | Multiple trusted paths produce ambiguity; no silent shortest-path choice. |
| Bridge/many-to-many | yes | Bridge candidate requires compiler policy and fanout path is flagged. |
| View lineage | yes | View lineage edges are provenance only and cannot become join paths. |
| Multiple dates | yes | Requires semantic date selection; no graph-level business default. |
| Sensitive/PII | yes | Sensitive secrets excluded; PII tagged and policy-gated downstream. |
| Composite PK/FK | yes | Pair order preserved. |
| Table without PK | yes | Grain safety warning emitted. |

## Fail-Closed Checks

Verified:

- No explicit FK means no trusted join.
- Similar naming does not create trusted edges.
- Lineage does not create joins.
- Ambiguous paths are not silently selected.
- Bridge/m2m path is not compiler-safe without policy.
- PII is not dimension/filter-safe without downstream policy.
- Table without PK is not grain-safe without explicit semantic grain/policy.
- Disabled, untrusted, or unverified FK cannot be promoted to automatic join.

## Test Results

Commands run after the debug-pass test additions:

```text
services/query-engine/.venv/Scripts/python.exe -m pytest tests/test_queryability.py -q
20 passed in 4.65s

services/query-engine/.venv/Scripts/python.exe -m pytest tests/test_query_intent.py -q
22 passed in 5.82s

services/query-engine/.venv/Scripts/python.exe -m pytest -q
221 passed, 1 skipped in 19.68s

CI=true pnpm --filter @atlantebi/web test
67 passed across 19 test files

CI=true pnpm --filter @atlantebi/web typecheck
passed

CI=true pnpm lint
passed

CI=true pnpm --filter @atlantebi/web build
passed
```

## Bugs Found And Fixed

No runtime validator bug was found in this pass.

Coverage gaps were found and fixed:

- Missing explicit tests for duplicate node and edge keys.
- Missing explicit tests for FK column pairs that are missing or belong to the wrong node.
- Missing explicit tests for disabled and unverified FK promotion.
- Missing explicit test for automatic joins over excluded FK columns.
- Missing explicit test for self-reference compiler-safety diagnostics.
- Missing explicit test for lineage edges corrupted into automatic joins.
- Missing explicit test for unsupported technical type forced queryable.
- Missing policy-hash stale assertion in the freshness helper test.

The fix was to add targeted tests. No product runtime logic was changed during this debug pass.

## UI Manual Verification Required

The graph hardening pass did not change the Query Intent Runner UI, but downstream manual smoke remains useful after deploy:

- Deterministic suite expected: 35/35
- AI advisory suite expected: 35/35, 0 regressions
- Concept invariant suite expected: 6/6

## Remaining Risks

- Relationship inference from naming remains intentionally out of scope. This is correct for fail-closed V1, but real PMI databases without FK will need explicit approved inference/policy later.
- Compiler-facing path gate still needs to be implemented before SQL generation.
- Semantic Layer anti-demo fixtures still need their own hardening; graph hardening alone does not prove semantic discovery works on ugly ERP schemas.
- The current graph validator is diagnostic. It does not yet enforce runtime compiler blocking because the compiler does not exist.

## Final Recommendation

Proceed with merge of Queryability Graph Hardening if GitHub CI matches local.

Do not proceed to Query Compiler yet until compiler-facing path gate and Semantic/Schema hardening are planned. The graph is now better verified, but using it to generate SQL safely still needs a dedicated compiler gate.
