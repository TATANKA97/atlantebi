# Controlled Dry-Run Planning Report

## Summary

Created the Controlled Dry-Run Planning specification for SQL Server. This was a
documentation-only task. No runtime code, DB connection logic, drivers, public
APIs, Zod contracts, UI, migrations, Resolver, Semantic Layer, Queryability
Graph, Technical Snapshot, Preflight, Compiler, or Result Validator code was
changed.

## Files Created

* `docs/dev/controlled-dry-run-planning.md`
* `docs/dev/controlled-dry-run-planning-report.md`

## Selected Strategy

The planned Dry-Run Envelope V1 is metadata-first:

1. Run pre-runtime artifact gates before any SQL Server metadata call.
2. Require Preflight accepted status, compiled Compiler result, valid Result
   Validator report, matching semantic/graph/snapshot hashes, compiled SQL hash,
   validator report hash, and `join_predicates` for every SQL `JOIN`.
3. Use `sp_describe_first_result_set` as the preferred V1 SQL Server metadata
   gate, with deterministic parameter declarations.
4. Default `@browse_information_mode` to `0` so validation checks the exposed
   result contract, especially for approved physical DB view sources.
5. Compare SQL Server metadata against the Result Validator contract.
6. Return no business data rows and do not scan business result rows.

This strategy treats `sp_describe_first_result_set` as a metadata gate, not as
proof of business correctness.

## Rejected Or Downgraded Alternatives

* `SET PARSEONLY ON`: rejected because it validates syntax only.
* `SET NOEXEC ON`: downgraded because deferred name resolution can hide missing
  objects and it does not provide a result contract.
* `SET SHOWPLAN_XML ON`: deferred to optional/future diagnostics because it
  requires SHOWPLAN permissions that many PMI read-only users will not have.
* `TOP 0` rewrite: rejected for V1 because it rewrites query shape and is too
  close to execution semantics.
* Transaction rollback and limited execution: rejected for Dry-Run V1 because
  they execute business query work.
* `SET FMTONLY ON`: rejected because Microsoft documents it as deprecated in
  practice and points to replacement metadata APIs.

## Open Risks

* SQL Server metadata visibility differs by user and may hide objects even when
  a snapshot previously saw them.
* `sp_describe_first_result_set` can fail when metadata cannot be statically
  determined.
* Physical DB views may hide base table metadata; V1 must validate view output
  rather than lineage.
* Parameter declaration generation must be exact and deterministic.
* SQL Server version, driver behavior, collation, and restricted permissions
  need real fixture coverage.
* Metadata validation can still impose operational load through compilation or
  metadata lookup, so timeouts and cancellation are mandatory.

## Prerequisites Before Implementation

* `compiled_sql_hash` in compiler artifacts if absent.
* `result_validator_report_hash`.
* `dry_run_report_hash`.
* Materialized `join_predicates` remain mandatory for every join.
* Exact `sp_describe_first_result_set` invocation design.
* SQL Server parameter declaration builder.
* Parameter type mapping and unsupported-type policy.
* Metadata-only SQL Server fixtures beyond AdventureWorksLT.
* Restricted-permission fixture.
* Failure taxonomy constants.
* Audit event schema.
* Timeout and cancellation policy.
* No result-row storage guarantee.

## PMI / ERP Readiness

The planning spec explicitly covers:

* SQL Server 2012+, 2016, 2019, 2022, and Azure SQL Database;
* restricted metadata visibility;
* physical DB views as approved source objects;
* partial or unavailable view lineage;
* legacy identifiers and collation issues;
* composite company/document keys;
* missing and disabled FK scenarios;
* archive schemas and multi-schema same table names;
* status/document fields and mixed master tables;
* snapshot drift after compilation;
* weird identifiers;
* permission failures and metadata timeouts.

AdventureWorksLT remains a regression baseline only, not acceptance proof.

## Final Recommendation

Can Dry-Run Envelope V1 implementation start after this planning task?

```text
Yes, if the implementation task follows this planning document and includes the
listed hash binding, parameter binding, metadata validation, permission,
view-handling, timeout, audit, and PMI/ERP fixture requirements.
```

Can SQL execution start after this planning task?

```text
No.
```

Execution still requires a separate execution envelope and runtime result
validation. Dry-run planning does not authorize row-returning query execution.

## Verification Results

Documentation-only verification run:

```powershell
git diff -- docs
Select-String -Path docs/dev/controlled-dry-run-planning.md -Pattern "execution|dry-run|NOEXEC|SHOWPLAN|sp_describe_first_result_set|browse_information_mode|parameter|audit|AdventureWorks|PMI|join_predicates"
git status --short --branch
```

`Select-String` returned matches for the required dry-run, SQL Server metadata,
parameter, audit, anti-demo and `join_predicates` terms.

`git status --short --branch` showed only the two newly created documentation
files as untracked changes. Because the files are new and not staged,
`git diff -- docs` does not display their content yet.

Runtime test suites were intentionally not part of this task.
