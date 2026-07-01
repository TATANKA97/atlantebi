# PRD v1.2 Update Report

## Summary

Updated PRD file: `docs/PRD.md`.

The PRD is now aligned to Atlante BI v1.2:

```txt
Versione 1.2 — Preflight-Gated Deterministic Query Pipeline
Aggiornato al 1 luglio 2026
```

The update is documentation-only. No runtime code, API contract, DB schema, Zod
contract, UI, or migration was changed.

## Major Sections Changed

* Section 0: added global AI/SQL invariant and anti-demo PMI/ERP readiness rule.
* Section 1: updated the product flow to include preflight, compiler and result
  contract validation before dry-run/execution.
* Section 5: added the v1.2 pipeline caveat and engineering evidence report list.
* Section 12: clarified that `query.manual_sql` is reserved future/admin scope and
  does not enable raw SQL execution in V1.
* Section 13: updated conceptual widget and query run artifacts from
  `generated_sql` to `compiled_sql`, compiler trace, preflight report and result
  contract fields.
* Section 14: updated the mandatory artifact pipeline through Result Validator,
  dry-run and execution envelope.
* Section 16: rewrote the query pipeline into Resolver, Preflight, Compiler,
  Result Validator, controlled dry-run planning, dry-run envelope, execution
  envelope, runtime result validation and chart compiler.
* Section 19: updated widget wording to deterministic compiled SQL and result
  contract metadata.
* Section 23: split pre-execution Result Validator V1 from future runtime result
  validation.
* Section 28: added testing principles and hardcoding guard examples.
* Section 31: replaced milestone model with completed, in-progress and next
  milestones.
* Section 32: updated MVP success criteria.
* Section 33: extended non-negotiable product rules.
* Section 35: replaced next implementation section with current state and next
  sequence.

## Milestone Changes

Milestone 9 was split into:

* Milestone 9A — Query Compiler Preflight Gate — completed.
* Milestone 9A-debug — Preflight post-merge debug pass — completed.
* Milestone 9B — Query Compiler V1 Narrow — completed.
* Milestone 9B-debug — Compiler post-merge debug pass — completed.
* Milestone 9C — Result Validator V1 / Compiled Query Contract Validator — in
  progress.

Execution was moved out of Query Compiler V1 and into future dry-run/execution
envelope milestones.

## Contradictions Removed

Removed or clarified statements implying:

* AI writes final SQL.
* Query Compiler V1 includes execution.
* Result Validator V1 validates real DB rows.
* AdventureWorksLT alone proves readiness.
* Manual/native SQL is active V1 functionality.
* View lineage is join evidence.
* North Star changes metric definitions.

## Anti-Demo / PMI-ERP Readiness Rule

The PRD now states that no milestone is complete if it only works on
AdventureWorksLT or clean demo schemas. Acceptance must include PMI/ERP-style
risks such as missing FK, disabled/untrusted FK, composite keys, multi-schema
same table names, bridge/many-to-many, PII, weird identifiers, multiple amount
columns and status/cancelled fields.

## Post-Merge Report References Added

The PRD now treats these reports as implementation evidence:

```txt
docs/dev/schema-retrieval-state-of-art.md
docs/dev/semantic-layer-state-of-art.md
docs/dev/semantic-layer-hardening-runtime-test-report.md
docs/dev/query-compiler-preflight-gate-report.md
docs/dev/query-compiler-preflight-gate-runtime-debug-report.md
docs/dev/query-compiler-v1-narrow-report.md
docs/dev/query-compiler-v1-narrow-runtime-debug-report.md
docs/dev/query-result-validator-v1-report.md -- expected after current PR
```

## Remaining PRD Limitations

* This update does not add migrations for the conceptual `query_runs` fields.
* Runtime result validation remains future work.
* Dry-run and execution envelopes remain future work.
* FieldProfile, SemanticSegments, durable policy and confirmed examples memory
  remain future milestones.
* Result Validator V1 is still a compiled query contract validator, not proof of
  business correctness.

## Verification

Executed lightweight checks:

```powershell
git diff -- docs
Select-String -Path docs/PRD.md -Pattern "AI.*generate.*SQL|manual_sql|AdventureWorks|execution read-only|Result Validator|lineage|North Star"
```

The `Select-String` output is reviewed for correctness rather than used as a
blind deletion list, because some references are valid when they state explicit
limitations.

Result:

* `git diff -- docs` shows documentation-only changes.
* `Select-String` still finds expected legitimate references to AI/SQL
  invariants, reserved `query.manual_sql`, AdventureWorks regression baseline,
  Result Validator split, lineage limitations and North Star runtime checks.
* No remaining `generated_sql`, `query_source text -- ai | manual`,
  `SQL generato` or Query Compiler `execution read-only` contradiction remains.
* `docs/PRD.md` was verified without UTF-8 BOM after edit.
* `git diff --check -- docs/PRD.md docs/dev/prd-v1.2-update-report.md` passed.

## Final Recommendation

Result Validator V1 is the current implementation task.

Controlled dry-run planning can start only after Result Validator V1 and its
post-merge debug pass.

Execution cannot start yet.

Broad compiler, FieldProfile, SemanticSegments and durable policy are future
milestones, not blockers for the current Result Validator task.
