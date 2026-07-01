# Query Compiler Trace Join Predicate Hardening Report

## Summary

This hardening adds materialized FK join predicate details to the internal
`QueryCompilerTrace`.

It closes the previous Result Validator debug limitation where
`QueryCompilerTrace` stored selected `join_paths` but not the concrete FK
column-pair predicates emitted by the Query Compiler. The validator can now
audit the compiled SQL join contract directly from trace materialization, while
still confirming graph and Technical Snapshot metadata.

No dry-run, SQL execution, DB connection, public API, Zod contract, UI,
migration, Resolver, Semantic Layer, Queryability Graph, Technical Snapshot or
Preflight runtime changes were introduced.

## Field Added

Internal dataclasses added in `services/query-engine/app/query_compiler.py`:

```python
CompiledJoinPredicate
CompiledJoinColumnPair
```

`QueryCompilerTrace` now includes:

```python
join_predicates: list[CompiledJoinPredicate]
```

Trace serialization remains deterministic through dataclass `asdict()` via
`to_debug_dict()`.

## Trace Shape

Each `CompiledJoinPredicate` records:

* graph FK edge key;
* FK from/to table keys, physical schema and table names;
* SQL aliases used for each FK side;
* constraint name;
* V1 join metadata: `join_type="inner"` and `source="graph_fk"`;
* `traversal_direction`:
  * `forward` when SQL traversal follows the FK edge direction;
  * `reverse` when SQL traversal joins through the same FK in reverse;
* ordered `CompiledJoinColumnPair` entries.

Each `CompiledJoinColumnPair` records both:

* FK-order metadata from graph/snapshot: ordinal, from/to column keys and
  physical column names;
* SQL-side metadata: left/right aliases, column keys, physical names and SQL
  identifiers.

## Compiler Behavior

The compiler materializes `join_predicates` at the same point where it emits SQL
`JOIN` clauses. Every emitted SQL join has one trace predicate, and every column
equality in the SQL join predicate has one trace column-pair record.

Composite FK pair order is preserved from graph/snapshot ordinal order. Reverse
traversal preserves FK pair order while recording that SQL traversal moved in
the reverse graph direction.

The compiler still blocks before SQL compilation when:

* selected edge is not a trusted/enabled/verified FK edge;
* selected path uses lineage, bridge/many-to-many, or untrusted evidence;
* FK metadata is missing or mismatched in the Technical Snapshot;
* FK physical columns are absent from the snapshot.

## Validator Behavior

`services/query-engine/app/query_result_validator.py` now treats
`join_predicates` as mandatory when compiled SQL contains `JOIN`.

Result Validator V1 blocks when:

* SQL contains `JOIN` but trace has no materialized join predicates;
* SQL join count differs from trace predicate count;
* trace predicates differ from the independently reconstructed canonical
  contract;
* SQL join clause differs from the materialized predicate;
* predicate aliases differ from compiler trace aliases;
* FK pair order, physical columns, graph edge or snapshot FK metadata differ;
* lineage, bridge/m2m, missing FK or untrusted FK evidence appears.

`join_paths` remains useful as selected graph path evidence, but it is no longer
sufficient on its own for validator join approval.

## Composite FK Coverage

Tests cover composite FK joins with `(COMPANY_ID, DOC_ID)` and verify:

* all column pairs are present;
* pair ordinals remain `[1, 2]`;
* SQL predicate order matches trace order;
* dropping one FK pair blocks validation;
* reversing pair order in trace blocks validation.

## Multi-Schema Coverage

Tests cover schema-qualified joins and ensure trace predicates retain physical
schema/table metadata. Existing multi-schema same-name coverage remains in the
Result Validator suite, with canonical SQL and trace checks preventing schema
drift.

## Anti-Demo / PMI Coverage

Coverage includes both AdventureWorks regression and non-demo PMI/ERP-style
fixtures:

* ugly physical table names in tests only;
* explicit semantic evidence over stable graph/snapshot keys;
* trusted FK paths;
* composite FK;
* reverse FK traversal;
* physical DB view source with no join predicate;
* lineage/bridge/untrusted paths remaining blocked.

Production compiler/validator modules do not contain fixture/demo literals.

## Hard Guard Results

All hard guards passed with no matches:

```powershell
Select-String -Path services/query-engine/app/query_compiler.py -Pattern "SalesOrder|ProductCategory|DOTES|DORIG|ANACLI|ARTICO|CATART"
Select-String -Path services/query-engine/app/query_result_validator.py -Pattern "SalesOrder|ProductCategory|DOTES|DORIG|ANACLI|ARTICO|CATART"
Select-String -Path services/query-engine/app/query_compiler.py -Pattern "cursor|\.execute|app\.drivers\.sqlserver|pyodbc|sqlalchemy"
Select-String -Path services/query-engine/app/query_result_validator.py -Pattern "cursor|\.execute|app\.drivers\.sqlserver|pyodbc|sqlalchemy"
```

## Verification Results

Python:

```text
tests/test_query_compiler.py -q: 15 passed
tests/test_query_result_validator.py -q: 15 passed
tests/test_query_compiler_preflight.py -q: 15 passed
tests/test_queryability.py -q: 20 passed
tests/test_semantic_invariants.py -q: 10 passed
tests/test_query_intent.py -q: 22 passed
pytest -q: 276 passed, 1 skipped
```

Frontend/packages:

```text
pnpm --filter @atlantebi/contracts test: 5 files, 44 tests passed
pnpm --filter @atlantebi/db test: 1 file, 35 tests passed
pnpm --filter @atlantebi/web test: 19 files, 67 tests passed
pnpm --filter @atlantebi/web typecheck: passed
pnpm lint: passed
pnpm --filter @atlantebi/web build: passed
```

## Final Recommendation

Can controlled dry-run planning start after this hardening?

Yes, if this branch is reviewed and the same gates pass in CI.

Can dry-run implementation start immediately?

No. It should wait for the controlled dry-run planning/spec task.

Can execution start?

No. Execution remains out of scope until a dry-run envelope, execution envelope
and runtime result validation path exist.
