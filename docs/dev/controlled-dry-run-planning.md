# Controlled Dry-Run Planning

## 1. Summary

This document defines the planned Controlled Dry-Run Envelope V1 for Atlante BI.
It is a planning artifact only. It does not implement dry-run, execution, DB
connections, drivers, public APIs, Zod contracts, UI, migrations, or runtime
changes to Resolver, Semantic Layer, Queryability Graph, Technical Snapshot,
Preflight, Compiler, or Result Validator.

Dry-Run V1 means a metadata-first SQL Server validation envelope for a query
that has already passed:

1. Query Intent Resolver.
2. Query Compiler Preflight Gate.
3. Query Compiler V1 Narrow.
4. Result Validator V1 / Compiled Query Contract Validator.
5. Query Compiler Trace Join Predicate Hardening.

Dry-Run V1 may call SQL Server metadata procedures or metadata statements needed
for validation. It must not execute the compiled business query in a way that
returns or scans business result rows.

The core invariant remains:

```text
AI does not generate SQL.
The deterministic compiler produces SQL only after preflight.
The Result Validator validates the compiled query contract.
Dry-run validates SQL Server metadata compatibility under controlled conditions.
Execution remains forbidden until a separate execution envelope exists.
```

## 2. Current Pipeline Status

Current implementation state as of this planning document:

| Pipeline component | Status |
| --- | --- |
| Technical Snapshot SQL Server V1 | completed |
| Queryability Graph V1 | completed |
| Semantic Layer V1 plus invariant hardening | completed |
| Query Intent Resolver V1 | completed |
| Query Compiler Preflight Gate plus debug pass | completed |
| Query Compiler V1 Narrow plus debug pass | completed |
| Result Validator V1 plus debug pass | completed |
| Query Compiler Trace Join Predicate Hardening | completed |
| PRD v1.2 pipeline rebase | completed |

The dry-run input is expected to include:

* compiled SQL;
* compiled parameters;
* compiler trace;
* materialized `join_predicates`;
* Result Validator report;
* semantic hash;
* graph hash;
* snapshot hash;
* compiled SQL hash, if already present;
* Result Validator report hash, if already present.

If `compiled_sql_hash`, `result_validator_report_hash`, or `dry_run_report_hash`
are not yet present in the internal artifacts, they are prerequisites for the
implementation task and must not be silently skipped.

## 3. Definition Of Dry-Run In Atlante

Dry-run is a controlled SQL Server metadata validation boundary. It checks that
the already compiled and validated SQL can be described by SQL Server for the
same tenant connection and security principal, without returning business data
rows.

Dry-run may:

* open a controlled SQL Server connection in the future implementation;
* call metadata procedures such as `sp_describe_first_result_set`;
* run metadata-only statements required to validate shape and permissions;
* validate result column names, ordinals, SQL types, and nullability;
* validate parameter declarations and metadata compatibility;
* emit diagnostics, audit events, and hashes.

Dry-run must not:

* execute the compiled business query to return rows;
* scan business rows as a validation strategy;
* rewrite SQL to make it pass;
* repair missing metadata or relationships;
* regenerate Semantic Layer, Graph, Snapshot, Preflight, Compiler, or Validator
  artifacts;
* accept raw/native/manual SQL;
* broaden Query Compiler V1 scope;
* store customer result rows.

This distinction matters: SQL Server metadata procedures execute server-side
metadata logic, but Dry-Run V1 does not execute the compiled business query as a
row-returning workload.

## 4. SQL Server Options Evaluated

Primary Microsoft references:

* `sp_describe_first_result_set`: <https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-describe-first-result-set-transact-sql>
* `SET SHOWPLAN_XML`: <https://learn.microsoft.com/en-us/sql/t-sql/statements/set-showplan-xml-transact-sql>
* `SET NOEXEC`: <https://learn.microsoft.com/en-us/sql/t-sql/statements/set-noexec-transact-sql>
* `SET PARSEONLY`: <https://learn.microsoft.com/en-us/sql/t-sql/statements/set-parseonly-transact-sql>
* `SET FMTONLY`: <https://learn.microsoft.com/en-us/sql/t-sql/statements/set-fmtonly-transact-sql>
* ODBC Driver connection keywords: <https://learn.microsoft.com/en-us/sql/connect/odbc/dsn-connection-string-attribute>

### Option Matrix

| Option | Syntax | Objects and columns | Permissions | Parameters | Result metadata | Execution risk | Version / driver risk | V1 suitability |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sp_describe_first_result_set` | Yes, through static analysis | Often, but can fail when metadata cannot be determined | Uses SQL Server metadata visibility and permissions; restricted users may fail | Supports parameter declarations through `@params` | Yes, first result set metadata | Does not return business rows, but runs metadata procedure | Available in modern SQL Server family; ODBC can use it when `UseFMTONLY=No` and SQL Server 2012+ | Preferred V1 metadata gate |
| `SET PARSEONLY ON` | Yes | No reliable object/column validation | Low permission signal | Weak | No | No execution | Syntax-only; not enough for SQL Server metadata compatibility | Rejected as insufficient |
| `SET NOEXEC ON` | Parses and compiles | Partial; deferred name resolution can hide missing objects | Weak/partial | Partial | No stable first-result contract | Does not execute compiled batch | Public role; still not enough because missing objects may not throw | Not sufficient alone |
| `SET SHOWPLAN_XML ON` | Yes | Produces estimated plan if compilation succeeds | Requires `SHOWPLAN` permission on referenced databases/objects | Possible, but operationally heavier | Plan, not result contract | Does not execute statements while enabled | Permission-heavy for PMI read-only users; not allowed inside stored procedures; batch constraints | Optional/future diagnostic, not default V1 onboarding |
| `TOP 0` rewrite | Yes, if rewritten correctly | Often | Requires query permissions | Uses normal query binding | Returns zero rows but query shape is rewritten | Too close to query execution semantics; optimizer may still do work | Rewriting changes query contract and can introduce false confidence | Rejected for V1 |
| Transaction rollback pattern | Yes | Yes, by actually running | Requires execution permissions | Yes | Yes, if query runs | Executes business query work before rollback | Can scan rows, take locks, and has side effects through functions/procs | Out of scope for dry-run V1 |
| Estimated execution plan retrieval | Yes | Similar to SHOWPLAN | Requires plan permissions | Possible | Plan, not result contract | No business rows | Same SHOWPLAN/permission concerns | Future diagnostic only |
| Actual limited execution | Yes | Yes | Requires execution permissions | Yes | Yes | Executes business query and may scan rows | Operational and privacy risk | Out of scope for dry-run V1 |
| `SET FMTONLY ON` | Historical | Historically metadata-only | Inconsistent | Weak | Partial metadata | No rows, but deprecated behavior | Microsoft says not to use it and points to replacement metadata APIs | Explicitly rejected |

### `sp_describe_first_result_set` Position

`sp_describe_first_result_set` is the preferred V1 candidate because it accepts
the query text through `@tsql`, accepts parameter declarations through `@params`,
and returns first-result metadata such as column order, name, nullability, and
system type. It is still only a metadata gate, not universal proof.

It can fail when:

* SQL Server cannot statically determine first-result metadata;
* the SQL shape is unsupported by the metadata procedure;
* object, column, or view definitions drifted after snapshot;
* the caller lacks metadata or SELECT permission;
* parameter declarations do not match the compiled SQL;
* the driver or engine returns a metadata error.

These failures must be categorized as metadata, engine, permission, or policy
failures. They are not proof that business data is wrong.

### `@browse_information_mode`

`sp_describe_first_result_set` exposes `@browse_information_mode`.

Recommended V1 default:

```text
@browse_information_mode = 0
```

Reason: mode 0 validates the exposed result contract. It avoids depending on
base-table lineage, which is especially important for approved physical DB view
sources, restricted metadata users, and ERP databases where base tables may be
hidden.

Mode 1 may expose base table/source column details. It is useful for diagnostics
but less suitable as a default because it can require metadata visibility that a
read-only PMI user may not have, and it may pull validation toward lineage that
Atlante deliberately does not trust as join evidence.

Mode 2 may be considered later for cursor-like or richer source metadata
diagnostics. It is not a V1 default.

For physical DB views approved by Preflight, Compiler, and Result Validator,
dry-run validates the view output contract. It must not infer join evidence from
captured view definitions or lineage.

### Version And Compatibility

Dry-Run V1 planning targets:

* SQL Server 2012+;
* SQL Server 2016;
* SQL Server 2019;
* SQL Server 2022;
* Azure SQL Database.

The preferred strategy depends on `sp_describe_first_result_set`, which is the
right baseline for SQL Server 2012+ environments. If a target server does not
support the required metadata procedure or the driver cannot use it safely,
dry-run must block with `unsupported_sql_shape`, `sqlserver_metadata_error`, or
`driver_error` instead of falling back to row execution.

`SHOWPLAN_XML` remains optional because many read-only PMI users will not have
SHOWPLAN permissions on every referenced database or object.

## 5. Recommended V1 Strategy

Dry-Run V1 should be staged.

### Stage 1 - Pre-Runtime Artifact Gates

Block before opening a SQL Server metadata validation attempt unless:

* Preflight status is `ready` or `ready_with_warnings`;
* compiler status is `compiled`;
* Result Validator status is `valid` or `valid_with_warnings`;
* Preflight, Compiler, and Validator context hashes match;
* semantic hash, graph hash, and snapshot hash match the current artifacts;
* compiled SQL hash matches the query validated by the Result Validator;
* Result Validator report hash matches the supplied report;
* `join_predicates` exist for every compiled SQL `JOIN`;
* no raw/manual/native SQL source is present;
* no stale artifact is present.

### Stage 2 - SQL Server Metadata Validation

Default V1 method:

```sql
EXEC sys.sp_describe_first_result_set
  @tsql = @compiled_sql,
  @params = @parameter_declarations,
  @browse_information_mode = 0;
```

Implementation detail to resolve in the dry-run PR: whether this is called
through `EXEC sys.sp_describe_first_result_set` with positional driver bindings
or named procedure parameter bindings. Either way, compiled SQL and parameter
declarations must be passed as parameter values, not string-concatenated from
user input.

The returned metadata must be compared against the Result Validator contract:

* scalar aggregate: exactly `metric_value`;
* grouped aggregate: exactly `dimension_0`, `metric_value`;
* expected SQL types and nullability compatible with contract;
* no extra columns;
* no missing columns.

### Stage 3 - Optional/Future Plan Diagnostics

`SET SHOWPLAN_XML ON` can be considered later as a diagnostic, not as a default
V1 requirement. It may help identify obvious plan-level failures, but it adds
permission burden and does not validate business correctness.

### Stage 4 - No Row-Returning Execution

Dry-Run V1 must not run the compiled business query with `TOP`, `TOP 0`, a
transaction rollback, or a limited result. Those are execution envelope topics,
not dry-run V1.

## 6. Input Contract

Dry-run can accept only:

* `QueryIntentResult`;
* `QueryCompilerPreflightReport`;
* `QueryCompilerResult`;
* `QueryResultValidationReport`;
* Technical Snapshot;
* Queryability Graph;
* Semantic Layer;
* tenant/user context;
* connection reference.

Dry-run blocks unless:

```text
preflight_report.status in ["ready", "ready_with_warnings"]
compiler_result.status == "compiled"
query_result_validation_report.status in ["valid", "valid_with_warnings"]
semantic_layer is active/fresh
graph/snapshot/semantic hashes match
compiled SQL hash matches validator input
join_predicates exist for every JOIN
```

Dry-run must also reject:

* raw SQL payloads;
* native/manual SQL artifacts;
* missing compiled parameters;
* missing result contract;
* missing or stale snapshot;
* missing tenant/user/connection context;
* cross-database references;
* multiple statements;
* any compiler trace mismatch.

## 7. Safety Envelope

Mandatory controls:

* read-only SQL Server user;
* SQL Server user must not have DDL/DML permissions for V1;
* no stored procedure execution except approved metadata procedures;
* no `EXEC` in compiled business SQL;
* no temp table creation in V1;
* no cross-database references;
* no multiple statements;
* no native/raw SQL;
* parameterized metadata procedure calls only;
* metadata timeout;
* connection timeout;
* cancellation support;
* max metadata payload size;
* no result rows returned in Dry-Run V1;
* no automatic retry on logical SQL errors;
* audit log for every attempt;
* all SQL must come from the deterministic compiler.

### Session Options

Allowed or recommended:

* `SET LOCK_TIMEOUT <bounded_ms>` for metadata calls, if validated against SQL
  Server behavior;
* connection-level query timeout;
* `SET NOCOUNT ON` for wrapper batches if needed and if it does not affect
  metadata behavior.

Deferred:

* `SET QUERY_GOVERNOR_COST_LIMIT`, because availability and semantics vary by
  environment;
* `SET SHOWPLAN_XML ON`, optional diagnostics only;
* `SET DATEFORMAT` and `SET LANGUAGE`, only if future parameter binding proves
  string date parsing is unavoidable. V1 should bind typed date values instead.

Rejected as default:

* `SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED`, because metadata dry-run
  should not execute row reads;
* `SET XACT_ABORT ON` as a safety substitute, because Dry-Run V1 should not run
  business statements needing rollback semantics;
* session options that silently alter business semantics.

### Operational Impact

Even metadata validation can stress legacy SQL Server systems. V1 must include:

* bounded connection timeout;
* bounded metadata query timeout;
* cancellation;
* no repeated automatic retries;
* audit of slow dry-runs;
* protection against long plan compilation;
* no strategy that intentionally scans business tables.

## 8. SQL Server Connection Policy

Dry-Run V1 implementation should use:

* Microsoft ODBC Driver 18 or newer;
* TLS required by default;
* `Encrypt=yes`;
* `TrustServerCertificate=no` by default;
* tenant connection isolation;
* credentials sourced only from GCP Secret Manager;
* no database password stored in Supabase;
* connection timeout;
* metadata query timeout;
* cancellation and cleanup on timeout;
* connection pool boundaries by tenant and connection reference;
* structured failure handling.

ODBC Driver 18 defaults encryption to yes/mandatory. This is a useful default,
but Atlante should still set the intended TLS posture explicitly so tenant
connection behavior is auditable.

`TrustServerCertificate=yes` may be a future tenant-specific exception only with
explicit policy, audit, and disclosure. It must not be the default.

## 9. Parameter Binding Policy

The compiler emits deterministic named parameters:

```text
@p0, @p1, @p2, ...
```

Dry-run implementation must preserve that order and never interpolate values
into SQL strings.

For `sp_describe_first_result_set`, the key binding is:

* pass compiled SQL as `@tsql`;
* pass a deterministic `@params` declaration string;
* use `@browse_information_mode = 0`;
* bind procedure arguments through the driver, not string interpolation.

If the future driver path requires positional placeholders, translate
`@p0..@pN` to positional `?` only at the driver binding boundary while keeping
the artifact contract and audit records in deterministic `@pN` order.

### Type Policy

V1 supported parameter families:

* `int`, `bigint`, `smallint`;
* `decimal(p,s)` and `numeric(p,s)`;
* `money` and `smallmoney`, mapped cautiously with exact decimal handling;
* `float` and `real`, only when the semantic metric/filter permits approximate
  numeric values;
* `date`, `datetime`, `datetime2`, `smalldatetime`;
* `bit`;
* `varchar` and `nvarchar`, with `nvarchar` preferred for user-visible text;
* `uniqueidentifier`;
* nullable parameters when the structured operator allows null;
* empty string distinct from `NULL`;
* Unicode strings with accents.

V1 blocked or deferred parameter families:

* `text`, `ntext`, `image`;
* `sql_variant`;
* `xml`;
* `geography`, `geometry`, `hierarchyid`;
* CLR/user-defined types;
* table-valued parameters;
* JSON-like strings unless the structured filter type explicitly allows them.

Filter-specific rules remain inherited from Compiler and Result Validator:

* `IN` and `NOT IN` are already expanded by compiler as one parameter per item;
* `BETWEEN` has exactly two parameters;
* `IS NULL` and `IS NOT NULL` have no value parameter;
* `eq null` and `neq null` are invalid before dry-run;
* no `LIKE`, regex, or contains operator in V1 unless a future compiler scope
  explicitly adds them.

## 10. Result Metadata Contract

Dry-run returns no business rows. It returns a metadata report.

```text
DryRunReport:
  status: passed | passed_with_warnings | blocked | engine_error
  decision_category
  sqlserver_validation_method
  result_columns[]
  parameter_bindings[]
  warnings[]
  errors[]
  duration_ms
  audit_ref
  compiled_sql_hash
  validator_report_hash
```

Each result column:

```text
name
ordinal
sql_type
nullable
expected_role: metric_value | dimension_0
matches_result_contract boolean
```

The metadata contract must compare SQL Server output against Result Validator
expectations:

* scalar aggregate: exactly `metric_value`;
* grouped aggregate: exactly `dimension_0`, then `metric_value`;
* grouped output includes the expected limit contract in the validated artifacts;
* date range presence is recorded if the query is date-bounded;
* disclosures from Preflight and Result Validator remain attached.

If SQL Server metadata differs from the validated result contract, the dry-run
status is `blocked` or `engine_error` depending on whether the failure is a
contract mismatch or SQL Server metadata failure.

## 11. Error Taxonomy

Dry-Run V1 should use these categories:

```text
policy_blocked
context_mismatch
connection_error
tls_error
authentication_error
permission_error
object_not_found
column_not_found
parameter_binding_error
syntax_error
unsupported_sql_shape
metadata_shape_mismatch
timeout
cancelled
driver_error
sqlserver_metadata_error
engine_error
```

Diagnostic rules:

* `engine_error` is not data incorrectness;
* metadata failure does not prove business data is wrong;
* permission errors are not semantic failures;
* object/column errors may indicate snapshot drift;
* dry-run failure must not rewrite SQL;
* dry-run failure must not mutate Semantic Layer, Graph, Snapshot, Preflight,
  Compiler, or Validator artifacts;
* diagnostics should point to the likely next action: permission review,
  re-introspection, unsupported SQL shape, parameter declaration fix, or tenant
  connection repair.

## 12. Audit And Observability

Audit events:

```text
dry_run_requested
dry_run_blocked_by_policy
dry_run_started
dry_run_passed
dry_run_failed
dry_run_engine_error
dry_run_timeout
dry_run_cancelled
```

Each event should include:

```text
tenant_id
user_id
connection_id
semantic_hash
graph_hash
snapshot_hash
compiled_sql_hash
result_validator_report_hash
status
duration_ms
error_category nullable
correlation_id
request_id
no raw password
no secret value
```

Cloud Logging fields should support:

* tenant-scoped correlation;
* artifact hash correlation;
* SQL Server validation method;
* timeout/cancellation diagnosis;
* permission failure diagnosis;
* slow metadata validation detection.

Logs must not include:

* database passwords;
* Secret Manager secret values;
* raw customer result rows;
* broad unredacted parameter values where policy marks them sensitive.

## 13. Security Boundaries

Dry-run does not prove:

* business correctness;
* semantic correctness;
* result plausibility;
* absence of join amplification at runtime;
* North Star consistency;
* dashboard suitability.

Dry-run does not replace:

* Result Validator;
* Runtime Result Validator;
* FieldProfile / Fingerprinting;
* SemanticSegments / Named Filters;
* durable policy and business context;
* tenant authorization checks.

Dry-run must not:

* allow raw/manual SQL;
* bypass tenant permissions;
* execute dashboard refreshes;
* store customer result rows;
* broaden compiler scope;
* trust physical DB view lineage as join evidence;
* infer missing relationships from naming.

## 14. Anti-Demo / PMI-ERP Acceptance

AdventureWorksLT remains a regression baseline only. Dry-Run V1 is not complete
if it only works on clean demo schemas.

Acceptance cases must include:

* ugly ERP-style schema;
* header/detail tables with no enforced FK;
* trusted composite company/document FK path;
* multi-company fields such as `company_id`, `cod_azienda`, `ditta`;
* document fields such as `tipo_doc`, `causale`, `serie`, `numero`;
* status/cancelled fields such as `stato`, `annullato`, `chiuso`, `evaso`;
* customer/supplier mixed master tables;
* item/category bridge tables;
* fiscal-year tables or year-suffixed archive tables;
* archive schemas;
* multi-schema same table names;
* physical DB views as approved source objects;
* views with computed columns and renamed output columns;
* views whose base-table lineage is partial or unavailable;
* restricted-permission user;
* metadata visibility gaps in `sys.*`;
* object exists but metadata is hidden;
* SELECT permission missing;
* metadata method permission denied;
* views visible while base tables are hidden;
* missing table after snapshot;
* column renamed after snapshot;
* FK disabled after snapshot;
* view changed after snapshot;
* permission removed after snapshot;
* parameter type mismatch;
* weird identifiers: spaces, reserved words, closing bracket `]`, mixed case,
  accented names, numeric-like names, non-dbo schemas;
* case-sensitive collation and database collation differences;
* read-only permission failure;
* metadata timeout;
* stale snapshot/hash mismatch;
* `join_predicates` mismatch;
* missing FK in the live database despite previous snapshot.

Dry-run must not infer relationships from names. If Compiler and Validator did
not approve a trusted path, dry-run must not repair the query.

### Real SQL Server Fixture Requirements

Before Dry-Run Envelope V1 implementation is considered complete, the
implementation task must include at least:

* AdventureWorksLT regression baseline;
* ugly PMI/ERP-style fixture with composite keys;
* view-based source fixture;
* restricted-permission user fixture;
* missing/stale object fixture;
* weird identifier fixture.

If live SQL Server fixtures are not available locally, the implementation PR
must include a CI or manual release checklist that exercises these categories.

## 15. Backlog Before Implementation

Required or recommended prerequisites:

* add `compiled_sql_hash` to `QueryCompilerResult` if absent;
* add `result_validator_report_hash`;
* add `dry_run_report_hash`;
* keep materialized `join_predicates` mandatory for joins;
* finalize the exact `sp_describe_first_result_set` invocation shape;
* implement parameter declaration builder for SQL Server metadata calls;
* implement parameter type mapping and unsupported-type blocks;
* create SQL Server metadata-only dry-run fixtures;
* define failure taxonomy constants;
* define audit event schema;
* define connection timeout and cancellation policy;
* define max metadata payload;
* enforce no result-row storage;
* define permission diagnostics for hidden metadata vs missing object;
* decide whether optional `SHOWPLAN_XML` diagnostics belong in a later milestone;
* define re-introspection/rebase workflow after snapshot drift.

## 16. Final Recommendation

Can Dry-Run Envelope V1 implementation start after this planning task?

```text
Yes, if the implementation task follows this strategy and satisfies the listed
prerequisites: metadata-first validation, `sp_describe_first_result_set` as the
default V1 candidate, mode 0 browse information, deterministic parameter
declarations, strict artifact hash binding, mandatory join_predicates, read-only
connection policy, audit model, and PMI/ERP fixtures.
```

Can SQL execution start after this planning task?

```text
No.
```

Dry-run planning enables the next implementation milestone. It does not
authorize business query execution. Execution still requires a separate
read-only execution envelope, runtime result validation, timeout/cancellation
controls, audit controls, and explicit non-demo acceptance.

