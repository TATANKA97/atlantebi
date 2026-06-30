# Query Compiler V1 Narrow Report

## Summary

Implemented an internal Python-only SQL Server read-only compiler for preflight-approved query intent plans. The compiler does not run SQL, does not import execution drivers, does not accept raw SQL semantic objects, and does not change public API/Zod/UI/DB contracts.

The implementation is intentionally narrow: it compiles one metric, optional half-open date range, optional one safe dimension, simple structured filters, and trusted FK joins only.

## Implemented Scope

| Area | Status | Notes |
| --- | --- | --- |
| SQL Server `SELECT` compilation | implemented | Internal module only: `services/query-engine/app/query_compiler.py`. |
| Preflight gate enforcement | implemented | Accepts only `ready/safe` and `ready_with_warnings/safe_with_disclosure`. |
| Replay/context binding | implemented | Compares selected metric/date/dimensions/filters/paths plus semantic, graph, and snapshot hashes. |
| Snapshot requirement | implemented | Compilation blocks without a matching Technical Snapshot. |
| Trusted FK joins | implemented | Join predicates come from graph FK column pairs and are verified against snapshot FK metadata. |
| Physical DB views | implemented | Views can be source objects; lineage is never join evidence. |
| Parameterization | implemented | Uses deterministic `@p0`, `@p1`, ... for date/filter/limit values. |
| Execution | not implemented | No cursor, driver execution, or query run path exists. |

## Supported SQL Shape

- Scalar aggregate:

```sql
SELECT
  <metric_expr> AS [metric_value]
FROM [schema].[table] AS [t0]
JOIN ...
WHERE ...
```

- Grouped aggregate:

```sql
SELECT TOP (@pN)
  <dimension_expr> AS [dimension_0],
  <metric_expr> AS [metric_value]
FROM [schema].[table] AS [t0]
JOIN ...
WHERE ...
GROUP BY <dimension_expr>
ORDER BY [metric_value] DESC, [dimension_0] ASC
```

Grouped queries use an internal default limit of `500`, parameterized as a normal compiled parameter. There is no public limit input in this PR.

## Unsupported SQL Shape

- execution;
- multi-metric queries;
- calculated metrics;
- YoY/MoM/comparisons;
- window functions;
- subqueries/CTEs;
- bridge/many-to-many paths;
- untrusted/disabled FK joins;
- lineage-as-join;
- native/raw SQL semantic objects;
- LIKE/contains/regex filters;
- PII filters without policy;
- unresolved status/currency/date ambiguity.

## Safety Guarantees

| Guarantee | Evidence |
| --- | --- |
| No AI SQL generation | Compiler accepts only structured intent, semantic metrics, graph paths, snapshot metadata, and preflight reports. |
| No raw SQL input | Raw SQL-like payload keys in the intent are blocked with `RAW_SQL_NOT_ALLOWED`. |
| No replayed preflight | Mismatched selected refs/hashes block with `PREFLIGHT_CONTEXT_MISMATCH`. |
| No name-based joins | Compiler does not call path search and only consumes selected preflight-approved edge keys. |
| No lineage joins | Non-FK edges block with `GRAPH_PATH_USES_LINEAGE`. |
| No value interpolation | All literal values become `CompiledSqlParameter` entries. |
| Safe identifier quoting | SQL Server bracket quoting escapes closing brackets as `]]`. |
| No silent COUNT target | COUNT uses only explicit row/entity count, explicit non-null count column, or count-distinct measure. |

## COUNT Semantics

Supported:

- `COUNT_BIG(*)` only for `aggregation="count"`, no measure column, `format.value_type="count"`, and row/entity aggregation level.
- `COUNT([alias].[column])` only when a measure column is explicit and confirmed non-null in graph and snapshot.
- `COUNT(DISTINCT [alias].[column])` only for `aggregation="count_distinct"` with explicit measure column.

Blocked:

- nullable count column;
- count metric without explicit row/entity semantics;
- count metric where the compiler would have to choose a grain column silently.

## Test Coverage

Positive fixtures:

- header metric with date range;
- line metric by category;
- ugly PMI schema with explicit semantic evidence;
- structured filter with parameterized values;
- composite/multi-schema FK path;
- physical DB view as safe technical source;
- COUNT_BIG, COUNT(column), and COUNT(DISTINCT column);
- unusual identifiers with spaces, reserved words, and closing brackets.

Negative fixtures:

- missing/blocked/non-accepted preflight;
- replayed preflight context;
- hash mismatch;
- missing snapshot;
- raw SQL payload;
- bridge/m2m;
- untrusted/disabled FK through preflight boundary;
- cross-table filter without selected path;
- invalid filter values;
- nullable count column;
- count without explicit evidence;
- unknown dialect.

## Hardcoding Guard

Command:

```powershell
Select-String -Path services/query-engine/app/query_compiler.py -Pattern "SalesOrder|ProductCategory|DOTES|DORIG|ANACLI|ARTICO|CATART"
```

Result: no matches.

Additional no-execution guard:

```powershell
Select-String -Path services/query-engine/app/query_compiler.py -Pattern "cursor|\.execute|app\.drivers\.sqlserver"
```

Result: no matches.

## Verification Results

| Command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_compiler.py -q` | 13 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_compiler_preflight.py -q` | 15 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_introspection.py -q` | 31 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_queryability.py -q` | 20 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_semantic_invariants.py -q` | 10 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_intent.py -q` | 22 passed |
| `.\.venv\Scripts\python.exe -m pytest -q` | 259 passed, 1 skipped |
| `$env:CI='true'; pnpm --filter @atlantebi/contracts test` | 44 passed |
| `$env:CI='true'; pnpm --filter @atlantebi/db test` | 35 passed |
| `$env:CI='true'; pnpm --filter @atlantebi/web test` | 67 passed |
| `$env:CI='true'; pnpm --filter @atlantebi/web typecheck` | passed |
| `$env:CI='true'; pnpm lint` | passed |
| `$env:CI='true'; pnpm --filter @atlantebi/web build` | passed |

## Final Recommendation

Can execution start after this PR?

No.

The compiler now produces deterministic SQL text and parameter metadata, but there is still no Result Validator V1, no execution policy envelope, no row/result safety validator, and no controlled dry-run lifecycle. The next steps should be:

1. Query Compiler post-merge debug pass.
2. Result Validator V1.
3. Controlled dry-run/execution planning only after validator coverage exists.
