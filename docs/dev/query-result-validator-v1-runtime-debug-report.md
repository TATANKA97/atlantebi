# Query Result Validator V1 Runtime Debug Report

## Summary

| Field | Value |
| --- | --- |
| Branch | `main` |
| Commit | `48f9268 Merge pull request #59 from TATANKA97/codex/prd-v1.2-pipeline-rebase` |
| Result Validator merge | Present: `45bee6b Merge pull request #58 from TATANKA97/codex/query-result-validator-v1` |
| PRD v1.2 merge | Present: `48f9268 Merge pull request #59 from TATANKA97/codex/prd-v1.2-pipeline-rebase` |
| Runtime code changes in this pass | None |
| Test changes in this pass | Added targeted Result Validator debug tests |
| Report created | `docs/dev/query-result-validator-v1-runtime-debug-report.md` |

## Scope Check

This pass did not implement dry-run, execution, DB connections, DB drivers,
Resolver changes, Semantic Layer changes, Queryability Graph changes, Technical
Snapshot changes, public API/Zod changes, UI changes, or migrations.

Changed files:

```txt
services/query-engine/tests/test_query_result_validator.py
docs/dev/query-result-validator-v1-runtime-debug-report.md
```

## Code Shape Verdict

Verdict: pass.

`services/query-engine/app/query_result_validator.py` is stage-based and emits
deterministic `stage_results`. It reconstructs expected SQL in
`_build_expected_sql()` and validates clauses in `_validate_canonical_sql()`.
Regex/scanner logic is limited to SQL guardrails such as forbidden keywords,
comments, multiple statements, raw SQL-like payloads and parameter extraction.

The validator imports compiler dataclasses from `app.query_compiler`:

```txt
CompiledSqlParameter
CompiledSqlReference
QueryCompilerResult
QueryCompilerTrace
```

It does not import or call `compile_query_plan()` and does not reuse the compiler
orchestration function.

## Static Hard Guards

| Guard | Result |
| --- | --- |
| `cursor|\.execute|app\.drivers\.sqlserver|pyodbc|sqlalchemy` | pass, no matches |
| `compile_query_plan\(` | pass, no matches |
| `SalesOrder|ProductCategory|DOTES|DORIG|ANACLI|ARTICO|CATART` | pass, no matches |

Fixture/demo literals remain limited to tests.

## Anti-Demo / PMI-ERP Coverage Verdict

Verdict: pass after test density additions.

Coverage now explicitly includes:

* ugly ERP-style table/column names;
* composite keys;
* multi-schema same table names;
* missing FK in snapshot;
* untrusted FK in graph;
* lineage edge used as join;
* bridge/many-to-many path;
* physical DB view as safe source object;
* weird identifiers with spaces and closing bracket escaping;
* extra table/join/filter corruption;
* missing date/filter corruption;
* parameter value and metadata mismatch;
* disclosure propagation;
* raw SQL-like payload leak.

## Canonical Validation Verdict

Verdict: pass.

The validator compares normalized compiled SQL against independently rebuilt
canonical clauses and emits clause-level diagnostics:

```txt
CANONICAL_SELECT_MISMATCH
CANONICAL_FROM_MISMATCH
CANONICAL_JOIN_MISMATCH
CANONICAL_WHERE_MISMATCH
CANONICAL_GROUP_BY_MISMATCH
CANONICAL_ORDER_BY_MISMATCH
CANONICAL_PARAMETER_MISMATCH
```

Tests assert clause-level codes for changed measure/select, source/from,
join/composite predicate, where/date/filter, group/order shape and parameter
object mismatch.

## Tautology / Compiler-Trust Verdict

Verdict: pass with one trace model limitation.

The validator does not trust compiler trace alone. It validates against:

* QueryIntentResult plan;
* preflight plan trace;
* compiler trace;
* semantic metric definition;
* Queryability Graph;
* Technical Snapshot;
* compiled parameters.

Added/verified negative tests where SQL and compiler trace are corrupted
together:

* changed measure/source/filter/dimension references are blocked through context
  binding, trace mismatch and canonical SQL validation;
* count semantics changed under a valid compiled output are blocked against the
  semantic metric contract.

Limitation: the current `QueryCompilerTrace` stores `join_paths` but not the
individual FK column-pair list. Therefore "trace removes one pair from a
composite FK" cannot be represented literally. The equivalent safety condition
is covered by canonical SQL join validation plus graph/snapshot FK pair-order
checks: SQL missing one composite predicate and snapshot FK pair mismatch both
block.

## Regex / Scanner Boundary Verdict

Verdict: pass.

Regex/scanners are guardrails, not the core validation mechanism. Added/verified:

* `SELECT ...; DROP/DELETE ...` blocks;
* suspicious SQL comment payload blocks;
* raw SQL-like user/intent payload blocks;
* valid scalar/grouped SQL passes only when canonical shape, trace, graph,
  snapshot and parameters match.

## Parameter Validation Verdict

Verdict: pass.

Validated:

* every `@pN` in SQL has one parameter object;
* no duplicate names;
* no gaps in sequence;
* unused parameters block;
* changed value blocks;
* changed logical type/source/operator/context blocks;
* `IN` expands one parameter per value;
* `BETWEEN` has two parameters;
* `IS NULL` / `IS NOT NULL` use no parameter;
* interpolated literal filter values block.

## Side-Effect Free Verdict

Verdict: pass.

Existing side-effect test deep-copies:

* compiler result;
* query intent result;
* preflight report;
* semantic layer;
* queryability graph;
* schema snapshot.

Validation leaves all inputs unchanged.

## Disclosure Propagation Verdict

Verdict: pass.

`ready_with_warnings / safe_with_disclosure` paths propagate active disclosures
from query intent and preflight plan trace into the generated result contract.
The validator emits `DISCLOSURE_PROPAGATED` warning when disclosures are active.

Note: Result Validator V1 builds the result contract internally; there is no
external caller-supplied result contract object to corrupt for a literal
"missing disclosure in input contract" test. The safety-critical behavior is
that the returned contract carries active disclosures.

## Result Contract Verdict

Verdict: pass.

Validated:

* scalar contract uses `metric_value`;
* grouped contract uses `dimension_0`, `metric_value`;
* grouped SQL requires `TOP (@pN)`;
* grouped SQL requires deterministic `ORDER BY [metric_value] DESC, [dimension_0] ASC`;
* date range and limit expectations are recorded;
* metric type and dimension shape are checked;
* invalid COUNT semantics block.

## Join Contract Verdict

Verdict: pass.

Validated:

* every join must come from selected trace join paths;
* every edge must exist in graph;
* every FK must exist in snapshot;
* FK must be trusted/enabled/verified;
* composite key pair order must match graph and snapshot;
* lineage edges are not join evidence;
* bridge/many-to-many paths are blocked;
* physical DB views are allowed as source objects only, not lineage joins;
* same table names in different schemas remain schema-qualified.

## PRD Consistency Check

Verdict: pass.

Checked with:

```powershell
Select-String -Path docs/PRD.md -Pattern "Result Validator|execution|dry-run|AI.*SQL|manual_sql|AdventureWorks|raw SQL|North Star|lineage"
```

Matches are expected and consistent with v1.2:

* Result Validator V1 validates compiled query contract only;
* it does not validate real rows;
* controlled dry-run planning starts after validator and post-merge debug;
* execution cannot start yet;
* AdventureWorksLT is regression baseline only;
* raw/manual SQL is not active V1 functionality;
* lineage is provenance, not join evidence;
* North Star does not change semantic metrics or query definitions.

## Test Density Verdict

Verdict: pass after additions.

Added targeted tests for:

* unknown dialect;
* not-compiled result;
* raw SQL-like payload leak;
* changed parameter metadata;
* literal filter interpolation;
* missing FK in snapshot;
* untrusted FK in graph;
* bridge/m2m join path;
* lineage edge as join;
* invalid COUNT contract;
* grouped alias/limit contract enforcement.

## Bugs Found And Fixed

No runtime validator bug was found.

The only gap found was test-density related: several required negative cases
were covered indirectly or not explicitly. Fixed by adding targeted tests in
`services/query-engine/tests/test_query_result_validator.py`.

## Verification Results

### Python

| Command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_result_validator.py -q` | pass, 15 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_compiler.py -q` | pass, 14 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_compiler_preflight.py -q` | pass, 15 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_introspection.py -q` | pass, 31 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_queryability.py -q` | pass, 20 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_semantic_invariants.py -q` | pass, 10 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/test_query_intent.py -q` | pass, 22 passed |
| `.\.venv\Scripts\python.exe -m pytest -q` | pass, 275 passed, 1 skipped |

### Web / Packages

| Command | Result |
| --- | --- |
| `$env:CI='true'; pnpm --filter @atlantebi/contracts test` | pass, 44 passed |
| `$env:CI='true'; pnpm --filter @atlantebi/db test` | pass, 35 passed |
| `$env:CI='true'; pnpm --filter @atlantebi/web test` | pass, 67 passed |
| `$env:CI='true'; pnpm --filter @atlantebi/web typecheck` | pass |
| `$env:CI='true'; pnpm lint` | pass |
| `$env:CI='true'; pnpm --filter @atlantebi/web build` | pass |

## Final Recommendation

Can controlled dry-run planning start after this pass?

Yes.

Can dry-run implementation start immediately?

No. It should wait for the dedicated controlled dry-run planning task/spec.

Can execution start?

No.

Controlled dry-run planning can start because the Result Validator V1 gate is
non-tautological, no-execution, no-compiler-reentry, anti-demo covered and green
across backend/web gates. Dry-run implementation should follow only after its
planning task. Execution remains blocked until dry-run envelope, execution
envelope and runtime result validation are designed and implemented.
