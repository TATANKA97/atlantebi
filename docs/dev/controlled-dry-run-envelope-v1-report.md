# Controlled Dry-Run Envelope V1 Report

## Summary

Implemented the internal Controlled Dry-Run Envelope V1 core as a Python-only
metadata boundary.

This implementation does not open SQL Server connections, does not import DB
drivers, and does not execute SQL. It prepares the deterministic SQL Server
metadata request and validates a supplied SQL Server metadata response against
the Result Validator contract.

The live SQL Server adapter that actually calls `sp_describe_first_result_set`
remains a separate implementation step.

## Files Changed

* `services/query-engine/app/controlled_dry_run.py`
* `services/query-engine/tests/test_controlled_dry_run.py`
* `docs/dev/controlled-dry-run-envelope-v1-report.md`
* `docs/dev/controlled-dry-run-planning.md`
* `docs/dev/controlled-dry-run-planning-report.md`

## Implemented Scope

The module exposes two internal functions:

```python
prepare_controlled_dry_run(...)
validate_controlled_dry_run_metadata(...)
```

`prepare_controlled_dry_run(...)` performs pre-runtime gates and builds a
metadata request descriptor for:

```sql
EXEC sys.sp_describe_first_result_set
  @tsql = ?,
  @params = ?,
  @browse_information_mode = ?
```

V1 fixes `@browse_information_mode = 0` and supports only
`sp_describe_first_result_set` as the default metadata gate.

`validate_controlled_dry_run_metadata(...)` validates supplied SQL Server
metadata columns against the Result Validator result contract. It does not call
SQL Server itself.

## Safety Guarantees

Implemented gates require:

* ready Query Intent;
* accepted Preflight status/category;
* compiled Compiler result;
* valid or valid_with_warnings Result Validator report;
* active/fresh Semantic Layer;
* matching semantic, graph and snapshot hashes;
* Technical Snapshot present;
* `join_predicates` present for every compiled SQL `JOIN`;
* `sp_describe_first_result_set` as validation method;
* `browse_information_mode = 0`;
* deterministic `@p0..@pN` parameter order;
* supported SQL Server parameter declaration types only;
* no semicolon-separated SQL;
* no SQL comments;
* no forbidden DDL/DML/EXEC keywords in compiled SQL;
* no cross-database references.

The module computes:

* `compiled_sql_hash`;
* `validator_report_hash`;
* `dry_run_report_hash`.

Parameter bindings include value fingerprints rather than raw value echoing.

## Result Metadata Validation

The dry-run metadata validation compares supplied metadata to the Result
Validator contract:

* scalar result: `metric_value`;
* grouped result: `dimension_0`, `metric_value`;
* ordinal order must match;
* metric SQL type must be numeric for numeric/count contracts;
* dimension SQL type must avoid unsupported binary/variant shapes.

SQL Server metadata errors can be surfaced as:

* `permission_error`;
* `sqlserver_metadata_error`;
* `driver_error`;
* other planned dry-run categories.

These errors do not imply business-data incorrectness.

## No-Execution Proof

`controlled_dry_run.py` does not import:

* `app.drivers.sqlserver`;
* `pyodbc`;
* `sqlalchemy`.

It does not call `cursor`, `.execute`, or any DB connection primitive.

The SQL Server metadata statement is represented as a descriptor only. No IO is
performed in this module.

## Tests

Added `tests/test_controlled_dry_run.py` with coverage for:

* scalar metric with date range metadata request;
* grouped metric with join predicate requirement;
* metadata shape mismatch;
* engine/permission metadata error;
* hash/context mismatch;
* unsupported validation method;
* unsupported browse mode;
* unsupported parameter type;
* composite key preparation with join predicates;
* no driver/no execution/no demo literal hard guard.

## Known Limitations

This is the core envelope, not the live SQL Server adapter. It does not yet:

* open tenant SQL Server connections;
* call `sp_describe_first_result_set`;
* enforce ODBC Driver 18 connection options at runtime;
* implement cancellation against a live metadata call;
* persist audit events;
* validate real SQL Server permissions.

Those belong in the next dry-run adapter task.

## Verification Results

Run from `services/query-engine`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_controlled_dry_run.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_query_result_validator.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_query_compiler.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_query_compiler_preflight.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_queryability.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_semantic_invariants.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_query_intent.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Results:

```text
tests/test_controlled_dry_run.py: 6 passed
tests/test_query_result_validator.py: 15 passed
tests/test_query_compiler.py: 15 passed
tests/test_query_compiler_preflight.py: 15 passed
tests/test_queryability.py: 20 passed
tests/test_semantic_invariants.py: 10 passed
tests/test_query_intent.py: 22 passed
full query-engine suite: 282 passed, 1 skipped
```

Static guards run from repo root:

```powershell
Select-String -Path services/query-engine/app/controlled_dry_run.py -Pattern "cursor|\.execute|app\.drivers\.sqlserver|pyodbc|sqlalchemy"
Select-String -Path services/query-engine/app/controlled_dry_run.py -Pattern "SalesOrder|ProductCategory|DOTES|DORIG|ANACLI|ARTICO|CATART"
```

Result: no matches.

pnpm/web gates were not run because this change is limited to Python internal
dry-run envelope code, tests, and documentation.

## Final Recommendation

Can controlled dry-run planning proceed to live adapter implementation?

```text
Yes, with a narrow next task: SQL Server metadata adapter that calls
sp_describe_first_result_set using this request descriptor and returns metadata
columns into validate_controlled_dry_run_metadata(...).
```

Can business SQL execution start?

```text
No.
```

Execution remains out of scope until the dry-run adapter, audit envelope,
runtime result validation, and execution envelope are implemented and verified.
