# Controlled Dry-Run Envelope V1 Runtime Debug Report

## Summary

Post-merge debug pass completed for the Controlled Dry-Run Envelope V1 core.

This pass confirms the current module is still an offline core envelope, not the
live SQL Server metadata adapter. It prepares metadata request descriptors and
validates supplied SQL Server metadata responses. It does not open DB
connections, import SQL Server drivers, call SQL Server, or execute business
SQL.

## Branch And Commit

* Branch: `codex/controlled-dry-run-debug-pass`
* Starting commit: `79e204f Merge pull request #61 from TATANKA97/codex/query-compiler-join-predicate-trace`
* Merge confirmation: PR #61 is present in `origin/main`; local `main` was
  fast-forwarded before this pass.

## Files Changed In This Debug Pass

* `services/query-engine/app/controlled_dry_run.py`
* `services/query-engine/tests/test_controlled_dry_run.py`
* `docs/dev/controlled-dry-run-envelope-v1-runtime-debug-report.md`

## Runtime Code Changes

Minimal fix added:

* `prepare_controlled_dry_run(...)` now accepts optional
  `expected_compiled_sql_hash` and `expected_validator_report_hash`.
* The new `hash_replay_gate` blocks when supplied expected hashes do not match
  the compiled SQL or Result Validator report.

No live adapter, DB driver import, DB connection, SQL Server call, API contract,
Zod schema, UI, migration, Resolver, Semantic Layer, Queryability Graph,
Technical Snapshot, Preflight, Compiler, or Result Validator runtime change was
introduced.

## Test Changes

`tests/test_controlled_dry_run.py` expanded from 6 tests to 11 tests.

Added explicit coverage for:

* preflight not accepted;
* compiler not compiled;
* Result Validator blocked;
* stale Semantic Layer;
* graph hash mismatch;
* snapshot hash mismatch;
* compiled SQL hash mismatch;
* validator report hash mismatch;
* SQL comments;
* semicolon/multiple statement payload;
* forbidden SQL keyword;
* cross-database reference;
* `IN` expanded parameters;
* `BETWEEN` decimal parameters;
* date range parameter declarations;
* deterministic unicode/string parameter declarations;
* parameter order duplicate/gap behavior;
* metadata extra/missing column;
* metadata ordinal mismatch;
* metadata type mismatch for numeric metric;
* binary dimension metadata rejection;
* physical DB view source with no join;
* weird bracket-escaped identifiers;
* side-effect free validation of inputs and preparation report.

## Code Shape Verdict

Pass.

`controlled_dry_run.py`:

* builds metadata request descriptors only;
* validates supplied metadata only;
* does not mutate input artifacts;
* does not rewrite compiled SQL;
* does not execute or simulate business SQL;
* does not silently re-introspect stale schemas;
* does not weaken Result Validator decisions.

The module remains a core envelope. The live SQL Server metadata adapter is not
implemented here.

## No-Execution Guard Result

Hard guard run:

```powershell
Select-String -Path services/query-engine/app/controlled_dry_run.py -Pattern "cursor|\.execute|app\.drivers\.sqlserver|pyodbc|sqlalchemy|pymssql|create_engine|connect\("
```

Result: no matches.

## Hardcoding Guard Result

Hard guard run:

```powershell
Select-String -Path services/query-engine/app/controlled_dry_run.py -Pattern "SalesOrder|ProductCategory|DOTES|DORIG|ANACLI|ARTICO|CATART"
```

Result: no matches.

Fixture/demo names remain limited to tests.

## Parameter Declaration Verdict

Pass.

The debug suite now verifies:

* deterministic `@p0..@pN` ordering;
* date declaration as `date`;
* grouped limit declaration as `int`;
* unicode/string declaration as `nvarchar(4000)`;
* decimal declaration as `decimal(38,10)`;
* values are fingerprinted and not echoed into compiled SQL or declarations;
* unsupported types block instead of guessing;
* duplicate/gap parameter names block via `PARAMETER_ORDER_INVALID`.

## Metadata Contract Verdict

Pass.

The debug suite now verifies:

* scalar metadata contract requires `metric_value`;
* grouped metadata contract requires `dimension_0`, `metric_value`;
* aliases must match;
* ordinals must match;
* numeric metric SQL type must be in the allowed numeric/count family;
* binary/variant-like dimension metadata is rejected;
* extra and missing metadata columns block;
* nullable metadata is recorded and does not automatically block.

## Hash And Context Binding Verdict

Pass.

The debug pass added and verified explicit replay hash checks:

* `COMPILED_SQL_HASH_MISMATCH`;
* `VALIDATOR_REPORT_HASH_MISMATCH`.

The suite also verifies stale semantic, graph hash mismatch and snapshot hash
mismatch gates.

Hash calculation uses canonical JSON with sorted keys for report payloads and
does not include secret values because the envelope does not accept secrets or
credentials.

## PMI / Legacy Readiness Verdict

Pass for the offline core envelope.

Coverage now includes:

* grouped queries with joins and mandatory materialized `join_predicates`;
* composite company/document key fixture through the existing compiler trace;
* non-dbo schema via composite fixture;
* physical DB view source with no join;
* weird bracket-escaped identifiers;
* permission denied surfaced as SQL Server metadata error category;
* metadata type mismatch;
* case-sensitive alias mismatch through exact alias matching.

This still does not prove live SQL Server behavior. Restricted metadata
visibility, SQL Server version differences, TLS, ODBC Driver 18 behavior,
timeouts and cancellation remain adapter-level responsibilities.

## PRD / Planning Consistency Verdict

Pass for safety meaning, with one expected state lag.

The PRD and planning docs still communicate the important constraints:

* Dry-Run V1 is metadata/safety validation only;
* metadata procedures may be called only by a future live adapter;
* business query rows must not be returned or scanned by dry-run;
* execution cannot start yet;
* AdventureWorksLT is regression baseline only;
* PMI/ERP readiness is required.

Known limitation: `docs/PRD.md` still describes Dry-Run Envelope V1 as a future
milestone because it was last rebased before this core envelope merge. That is a
documentation state lag, not a safety contradiction. A later PRD update should
mark the offline core as completed after the live adapter plan is settled.

## Bugs Found And Fixed

Fixed:

* Missing explicit replay hash inputs/gates for compiled SQL hash and Result
  Validator report hash.
* Test density was too low for a safety boundary; targeted negative and
  PMI/legacy tests were added.

No DB IO bug was found.

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
tests/test_controlled_dry_run.py: 11 passed
tests/test_query_result_validator.py: 15 passed
tests/test_query_compiler.py: 15 passed
tests/test_query_compiler_preflight.py: 15 passed
tests/test_queryability.py: 20 passed
tests/test_semantic_invariants.py: 10 passed
tests/test_query_intent.py: 22 passed
full query-engine suite: 287 passed, 1 skipped
```

Run from repo root:

```powershell
$env:CI='true'; pnpm --filter @atlantebi/contracts test
$env:CI='true'; pnpm --filter @atlantebi/db test
$env:CI='true'; pnpm --filter @atlantebi/web test
$env:CI='true'; pnpm --filter @atlantebi/web typecheck
$env:CI='true'; pnpm lint
$env:CI='true'; pnpm --filter @atlantebi/web build
```

Results:

```text
@atlantebi/contracts test: 5 files passed, 44 tests passed
@atlantebi/db test: 1 file passed, 35 tests passed
@atlantebi/web test: 19 files passed, 67 tests passed
@atlantebi/web typecheck: passed
pnpm lint: passed
@atlantebi/web build: passed
```

## Final Recommendation

Can live SQL Server metadata adapter implementation start after this pass?

```text
Yes, if this debug-pass branch is merged.
```

Can business SQL execution start?

```text
No.
```

The live SQL Server metadata adapter can start after this post-merge debug pass
if all gates remain green in PR/CI.

Business query execution remains blocked until the live dry-run adapter, audit
envelope, runtime result validation and execution envelope are implemented and
verified.

