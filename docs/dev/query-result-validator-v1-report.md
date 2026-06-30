# Query Result Validator V1 Report

## 1. Summary

Result Validator V1 adds an internal Python-only compiled query contract validator. It validates the output of Query Compiler V1 Narrow before any future dry-run or execution path exists.

The validator is deliberately narrow:

- no SQL execution;
- no DB connections;
- no SQL driver imports;
- no public API, Zod, UI, DB migration, Resolver, Semantic Layer, Queryability Graph, Technical Snapshot, Preflight, or Compiler runtime changes;
- no compiler re-entry.

Final recommendation:

| Question | Answer |
| --- | --- |
| Can controlled dry-run planning start after this PR? | Yes, if this validator remains green and dry-run stays read-only/planned separately. |
| Can execution start after this PR? | No. Execution still needs a separate controlled dry-run/execution design and safeguards. |

## 2. Implemented Validation Stages

| Stage | Purpose |
| --- | --- |
| `compiler_result_integrity` | Validates compiled status, SQL presence, trace presence, dialect, compiler errors, and core objects. |
| `context_binding` | Binds compiler output to the same intent, preflight trace, semantic hash, graph hash, snapshot hash, metric/date/dimension/filter/path refs. |
| `canonical_sql_validation` | Reconstructs expected SQL clauses independently and compares clause-by-clause. |
| `sql_shape_guardrails` | Blocks DDL/DML/EXEC, comments, semicolons, raw SQL-shaped payloads, CTE/subquery/window shapes outside V1. |
| `parameter_validation` | Validates `@p0..@pN` order, usage, uniqueness, complete parameter object equality, date/filter/limit parameters. |
| `trace_consistency` | Validates compiler trace against canonical refs, aliases, tables, columns, joins, filters, group/order metadata. |
| `identifier_reference_validation` | Validates table/column/alias refs against graph + snapshot and bracket escaping. |
| `join_contract_validation` | Validates FK joins, snapshot FK metadata, pair order, no lineage, no bridge/m2m. |
| `filter_contract_validation` | Validates structured filter operators, parameter arity, null semantics, cross-table path metadata. |
| `aggregation_contract_validation` | Validates aggregation semantics against the selected semantic metric. |
| `result_contract_validation` | Builds expected result contract and checks aliases, type expectations, date/limit/disclosure propagation. |
| `final_decision` | Computes final status/category and blocking codes. |

The validator collects all relevant issues across stages when possible. It skips downstream stages only when a missing core object makes later validation impossible.

## 3. Canonical Recompilation Strategy

The validator does not call `compile_query_plan()` and does not reuse the compiler orchestration path.

It independently reconstructs expected SQL from:

- `QueryIntentResult.plan`;
- `QueryCompilerPreflightReport.plan_trace`;
- `QueryCompilerResult.trace`;
- `SemanticMetric`;
- `QueryabilityGraphArtifact`;
- Technical Snapshot;
- `CompiledSqlParameter` metadata.

It compares canonical clauses instead of only checking string containment:

- `SELECT`;
- `FROM`;
- `JOIN`;
- `WHERE`;
- `GROUP BY`;
- `ORDER BY`;
- parameters.

Clause-level diagnostics include:

- `CANONICAL_SELECT_MISMATCH`;
- `CANONICAL_FROM_MISMATCH`;
- `CANONICAL_JOIN_MISMATCH`;
- `CANONICAL_WHERE_MISMATCH`;
- `CANONICAL_GROUP_BY_MISMATCH`;
- `CANONICAL_ORDER_BY_MISMATCH`;
- `CANONICAL_PARAMETER_MISMATCH`.

## 4. Supported Contract

Supported:

- SQL Server `SELECT`;
- one compiled metric;
- optional date range;
- optional one group-by dimension;
- structured filters compiled by Query Compiler V1;
- trusted FK joins selected by preflight/compiler trace;
- scalar result: `metric_value`;
- grouped result: `dimension_0`, `metric_value`;
- deterministic parameter names `@p0..@pN`;
- physical DB views as safe source objects when already selected by preflight/compiler trace.

Unsupported:

- SQL execution;
- dry-run;
- native/raw SQL semantic objects;
- multi-statement SQL;
- DDL/DML/EXEC;
- CTE/subquery/window shapes outside V1;
- name-inferred joins;
- lineage as join evidence;
- bridge/m2m joins;
- untrusted/disabled FK;
- unsupported calculated/multi-metric result shapes.

## 5. PMI/ERP Anti-Demo Coverage

The test suite includes non-demo and corruption scenarios:

| Scenario | Coverage |
| --- | --- |
| Ugly ERP header/detail/item/category | Passes only when selected columns and FK paths match graph/snapshot/trace. |
| Composite company/document keys | Validates composite pair order and blocks dropped key parts. |
| Multi-schema same names | Uses schema-qualified references and blocks wrong schema/table refs through canonical/context checks. |
| Weird identifiers | Covers spaces and closing bracket escaping. |
| Physical DB views | Allows source view, blocks lineage-as-join through join contract. |
| Corrupted SQL and corrupted trace together | Blocks via context binding, canonical SQL, trace consistency, and parameter checks. |
| Multi-issue corrupted output | Reports multiple issue codes instead of failing on the first mismatch. |

Production validator logic has no AdventureWorks or PMI fixture literals.

## 6. No Execution Proof

Hard guard results:

| Guard | Result |
| --- | --- |
| `cursor|\.execute|app\.drivers\.sqlserver|pyodbc|sqlalchemy` | no matches |
| `SalesOrder|ProductCategory|DOTES|DORIG|ANACLI|ARTICO|CATART` | no matches |
| `compile_query_plan\(` | no matches |

The validator imports compiler result dataclasses only. It does not call compiler orchestration.

## 7. Test Results

| Command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_result_validator.py -q` | `10 passed in 3.95s` |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_compiler.py -q` | `14 passed in 2.25s` |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_compiler_preflight.py -q` | `15 passed in 6.19s` |
| `.\.venv\Scripts\python.exe -m pytest tests/test_introspection.py -q` | `31 passed in 5.41s` |
| `.\.venv\Scripts\python.exe -m pytest tests/test_queryability.py -q` | `20 passed in 5.50s` |
| `.\.venv\Scripts\python.exe -m pytest tests/test_semantic_invariants.py -q` | `10 passed in 2.27s` |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_intent.py -q` | `22 passed in 5.00s` |
| `.\.venv\Scripts\python.exe -m pytest -q` | `270 passed, 1 skipped in 19.41s` |
| `$env:CI='true'; pnpm --filter @atlantebi/contracts test` | `44 passed` |
| `$env:CI='true'; pnpm --filter @atlantebi/db test` | `35 passed` |
| `$env:CI='true'; pnpm --filter @atlantebi/web test` | `67 passed` |
| `$env:CI='true'; pnpm --filter @atlantebi/web typecheck` | pass |
| `$env:CI='true'; pnpm lint` | pass |
| `$env:CI='true'; pnpm --filter @atlantebi/web build` | pass |

## 8. No False Confidence

This validator validates the compiled query contract.

It does not validate actual database rows.

It does not prove business correctness.

It does not replace FieldProfile, SemanticSegments, durable policy, row-level security design, runtime permissions, result-quality checks, or execution safeguards.

Execution must remain blocked after this PR.
