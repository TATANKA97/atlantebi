# Schema Retrieval / Technical Snapshot - State of the Art

Date: 2026-06-30

Branch/context audited: `main` at `945d34d` (`Merge pull request #55 from TATANKA97/codex/semantic-layer-invariants`). The Queryability Graph hardening from PR #54 and Semantic Layer invariant diagnostics from PR #55 are present in this branch.

Scope: report-only audit of SQL Server schema introspection and Technical Snapshot V1. No runtime code, SQL compiler, execution, UI, AI prompt/provider, Queryability Graph builder, Semantic Layer generator, or Resolver changes are introduced by this report.

## 1. Executive Summary

**Recommendation: Proceed to compiler-facing preflight gate. Do not proceed directly to Query Compiler V1 yet.**

The Technical Snapshot layer is strong enough to support Queryability Graph V1 and the current Semantic Layer V1 on explicit-FK SQL Server schemas. It captures substantially more than a minimal `INFORMATION_SCHEMA` snapshot: objects, columns, types, PK/FK metadata, FK trust/disabled flags, unique constraints, indexes, computed/default/check constraints, view definitions, view lineage, row-count estimates, stable hashes, and coverage warnings.

That is not the same as being compiler-ready. For a SQL compiler, the snapshot must be treated as trusted technical evidence only when coverage is adequate. Missing FKs, partial metadata visibility, view lineage gaps, filtered unique indexes, and ambiguous business semantics must fail closed in a compiler preflight gate. The snapshot should not infer joins from names, should not choose business dates, and should not turn view lineage into join evidence.

| Question | Answer |
| --- | --- |
| Ready for Queryability Graph V1? | Yes, with explicit SQL Server metadata and current coverage warnings. |
| Ready for Semantic Layer V1? | Yes for current V1, with graph/semantic diagnostics and demo-profile caveats. |
| Ready for Query Compiler V1? | No. Add a compiler-facing preflight gate first. |
| Overfitting risk | Medium. Driver is generic SQL Server catalog-based, but live evidence is still demo/fixture-heavy. |
| Required next step | Implement Technical Snapshot compiler preflight/invariants and anti-demo snapshot tests. |

### Compiler blockers

| Blocker | Why it blocks compiler | Affected layer | Suggested PR/task | Effort | Risk if ignored |
| --- | --- | --- | --- | --- | --- |
| No compiler-facing snapshot preflight gate | Compiler needs a single yes/no gate for snapshot coverage before generating joins and filters. | Schema Retrieval -> Graph -> Compiler | Add snapshot preflight validator over `coverage_status`, FK coverage, lineage coverage, object limits, and metadata visibility. | M | SQL generated from incomplete metadata. |
| Missing-FK schemas are only diagnostic | This is safe for Graph V1, but many PMI/ERP schemas omit declared FKs. Compiler must explicitly block or require manual mapping. | Snapshot/Graph | Add anti-demo missing-FK tests and UI/debug messaging for no trusted paths. | M | Compiler may appear broken or be tempted to infer unsafe joins later. |
| Live SQL Server integration is skipped locally | The real-catalog integration test exists but needs `SQLSERVER_INTEGRATION_HOST`; local confidence is not full end-to-end. | Schema Retrieval | Run SQL Server fixture in CI or document environment gate in release checklist. | S/M | Catalog-query regressions may be caught only in targeted CI. |
| View lineage is partial by nature | Snapshot preserves lineage as provenance, but views can hide business logic. | Snapshot/Graph/Semantic | Preflight: view-backed metrics require explicit policy or semantic validation; lineage never proves joins. | M | Compiler could double-count or miss filters embedded in views. |
| Business meaning is outside snapshot | Snapshot marks technical roles but does not pick revenue/date/status semantics. | Semantic/Compiler | Keep business decisions in Semantic Layer and require compiler-readiness diagnostics. | S | Compiler might treat `ModifiedDate` or `TotalDue` incorrectly. |

Backlog, not blocker: richer relationship inference as untrusted evidence, stored procedure/synonym discovery, temporal-table metadata, extended value profiling, selectivity statistics, and broader locale-specific PII classification.

## 2. Current Architecture

Current flow:

```text
SQL Server metadata queries
-> SchemaIntrospectionResponse / Technical Snapshot
-> schema_hash / snapshot_hash
-> persisted schema_snapshots artifact
-> Queryability Graph compilation
-> Semantic Layer discovery input
```

| Area | Primary source | Notes |
| --- | --- | --- |
| Driver interface and snapshot dataclasses | `services/query-engine/app/drivers/base.py` | `SchemaIntrospectionResult`, table/column/FK/index/lineage metadata. |
| SQL Server introspection | `services/query-engine/app/drivers/sqlserver.py` | Catalog queries, row/byte limits, hash construction, coverage warnings. |
| API endpoint | `services/query-engine/app/main.py` | `POST /schema/introspect`, secret resolution, response size limit, sanitized errors. |
| Python contracts | `services/query-engine/app/models.py` | Pydantic request/response models and aliases. |
| Zod contracts | `packages/contracts/src/index.ts` | TS parity for Schema Introspection and import summary. |
| Web orchestration | `apps/web/lib/schema-introspection/service.ts` | Reads connection, calls query-engine, compiles graph, persists via RPC. |
| Web API | `apps/web/app/api/schema/introspect/route.ts` | Admin/debug route wrapper over service. |
| Persistence | Supabase migrations listed below | `schema_snapshots`, graph versions, derivations, semantic lifecycle/freshness. |
| Downstream Graph | `services/query-engine/app/queryability.py` | Builds nodes, columns, FK edges, lineage edges, graph hashes. |
| Downstream Semantic | `services/query-engine/app/semantic_discovery.py` and `semantic_invariants.py` | Uses graph-derived evidence, not raw SQL Server catalog directly. |

The web import path currently does all three steps in sequence: introspect snapshot, compile Queryability Graph, persist both together via `persist_queryability_graph_import`. A blocked graph aborts the import result.

Error handling:

- Driver configuration and unsupported engine errors produce sanitized API responses.
- Core SQL Server introspection query failures become `DriverIntrospectionError`.
- Optional index and row-count metadata failures become coverage warnings.
- View lineage attempts `sys.dm_sql_referenced_entities` first and falls back to `sys.sql_expression_dependencies`.
- Oversized metadata rows, metadata bytes, or response payloads fail closed.

## 3. Current Snapshot Contents

| Area | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Database name/version | Implemented | `SQLSERVER_DATABASE_QUERY`; `SchemaIntrospectionResult.database_name`, `engine_version` | Captured from `db_name()` and `serverproperty('ProductVersion')`. |
| Schemas | Implemented | object/column queries join `sys.schemas` | Stored per table/view as `schema`. |
| Tables | Implemented | `SQLSERVER_OBJECTS_QUERY` over `sys.objects` type `U` | Excludes system objects. |
| Views | Implemented | `SQLSERVER_OBJECTS_QUERY` over `sys.objects` type `V`; `sys.sql_modules` | Definition captured when visible. |
| Columns | Implemented | `SQLSERVER_COLUMNS_QUERY` | Includes order, type, nullability, collation, identity, computed/default metadata. |
| Data types | Implemented | `sys.types`, `type_name`, user-defined type fields | Declared-type visibility is tracked separately from native type. |
| Nullability | Implemented | `sys.columns.is_nullable` | Used downstream for FK cardinality. |
| Identity columns | Implemented | `sys.identity_columns` | Seed/increment captured. |
| Computed columns | Implemented | `sys.computed_columns` | Expression captured. |
| Primary keys | Implemented | `sys.key_constraints`, `sys.index_columns` | Composite order preserved. |
| Foreign keys | Implemented | `sys.foreign_keys`, `sys.foreign_key_columns` | Includes disabled/untrusted flags and referential actions. |
| Unique constraints | Implemented | `sys.key_constraints` type `UQ` | Composite order preserved. |
| Indexes | Implemented | `sys.indexes`, `sys.index_columns` | Table and indexed-view indexes captured, including included columns and filters. |
| Filtered unique index handling | Partial | Snapshot captures `filter_definition`; Graph marks filtered unique index not eligible for cardinality | Good downstream behavior, but compiler preflight should assert this centrally. |
| Check constraints | Implemented | `sys.check_constraints` | Captures definition and trust/disabled flags. |
| Default constraints | Implemented | `sys.default_constraints` via column query | Captures name and definition. |
| View dependencies | Implemented | DMF and expression dependency fallback | Good provenance, but not always precise. |
| View column lineage | Partial | `referencing_minor_id` mapping and fallback | DMF can be complete; fallback is partial and may lose column precision. |
| Technical roles | Partial | `_technical_role` | Deterministic name/type heuristic; not business semantics. |
| Sensitivity hints | Missing at snapshot level | `_column_sensitivity` is in Queryability Graph builder | PII/exclusion is downstream, not in raw snapshot. |
| Unsupported types | Partial | `technical_role` marks binary/xml; Graph excludes them | Snapshot classifies, Graph enforces. JSON/geography are not explicitly rich-modeled. |
| Row counts/statistics | Partial | `sys.dm_db_partition_stats` best effort | Row counts are excluded from `schema_hash`; permission failure is warning. |
| Coverage warnings/errors | Implemented | `_build_coverage_warnings`, `_coverage_status` | Status can be `ok`, `partial`, `warning`, `blocked`. |
| Hashes | Implemented | `_schema_hash`, `_snapshot_hash` | Stable DDL vs full technical snapshot split. |

## 4. SQL Server Metadata Coverage

| Metadata source | Read today? | How | Notes |
| --- | --- | --- | --- |
| `sys.objects` | Yes | object and column queries | Primary object discovery for tables/views. |
| `sys.tables` | Partial | FK and row-count joins | Not the main object list. |
| `sys.views` | No direct query | Uses `sys.objects` type `V` and `sys.sql_modules` | Functionally discovers views, but not `sys.views`-specific fields. |
| `sys.schemas` | Yes | object/type/FK/index queries | Schema-qualified identity supported. |
| `sys.columns` | Yes | column, FK, index, key queries | Core column source. |
| `sys.types` | Yes | column type query | Native and declared user-defined type details. |
| `sys.key_constraints` | Yes | key constraints query | PK/UQ. |
| `sys.indexes` | Yes | indexes query | Includes unique, filter, disabled, object type. |
| `sys.index_columns` | Yes | key/index queries | Preserves key order/included columns. |
| `sys.foreign_keys` | Yes | FK query | Disabled/untrusted captured. |
| `sys.foreign_key_columns` | Yes | FK query | Composite order preserved by `constraint_column_id`. |
| `sys.sql_expression_dependencies` | Yes | view lineage fallback | Partial lineage fallback. |
| `sys.dm_sql_referenced_entities` | Yes | primary view lineage path | Better lineage, permission sensitive. |
| `sys.sql_modules` | Yes | view definition | Definition can be unavailable. |
| `sys.computed_columns` | Yes | column query | Computed expression captured. |
| `sys.default_constraints` | Yes | column query | Default expression captured. |
| `sys.check_constraints` | Yes | check constraints query | Disabled/untrusted captured. |
| `sys.identity_columns` | Yes | column query | Identity metadata captured. |
| `sys.extended_properties` | Yes | object and column descriptions | `MS_Description` only. |
| `sys.dm_db_partition_stats` | Yes, best effort | row count estimates | Permission failure warning. |
| Stored procedures | No | Not in V1 scope | Backlog for future discovery, not compiler blocker if compiler is table/view only. |
| Synonyms | No | Not in V1 scope | Risk for ERP systems that use synonyms. |
| Temporal table metadata | No explicit support | Not read from temporal-specific catalog fields | Backlog unless target customers rely on system-versioned tables. |

## 5. FK / PK / Index Robustness

| Case | Current behavior | Downstream risk |
| --- | --- | --- |
| Explicit trusted FK | Captured as `verified_by_db=true`, not disabled, trusted. Graph can set `automatic_join_allowed=true`. | Low. |
| Disabled FK | Captured as `is_disabled=true`; Graph stores evidence but disables automatic join. | Low. Correct fail-closed behavior. |
| Untrusted FK | Captured as `is_not_trusted=true`; Graph stores evidence but disables automatic join. | Low. |
| Composite FK | Pair order preserved by `constraint_column_id`; integration test covers composite FK. | Medium confidence locally because live test is skipped unless SQL Server fixture is available. |
| Composite PK | Captured through key constraint order. | Low/Medium. Tested in unit and integration fixture. |
| Unique constraints | Captured and used as candidate keys. | Low. |
| Unique indexes | Captured and used as candidate keys only if global, enabled, unfiltered. | Low/Medium. Good behavior, but compiler should assert it. |
| Filtered unique indexes | Captured with `filter_definition`; not eligible for cardinality in Graph. | Medium. Needs compiler preflight test. |
| Missing PK | Table is present, but no candidate key. | High for compiler if aggregate grain depends on row identity. |
| Table without FK | No trusted edges invented. | High for real PMI/ERP if relationships are implicit. Correct but product needs explicit mapping story. |
| FK across schemas | Schema names included in FK metadata and stable graph identity. | Medium. Needs more anti-demo tests. |
| Self-reference | Graph detects `self_reference` and path finder excludes ordinary routing. | Low. |
| Circular FK | Edges can exist; path finder tracks visited nodes and hop limits. | Medium. Needs compiler preflight around cycles/fanout. |
| Multiple FK paths | Path finder returns ambiguous for parallel shortest paths. | Medium. Good start; compiler must not silently choose. |

## 6. Views and Lineage

Views are discovered as first-class objects and can be queryability nodes. Their definitions are captured when `sys.sql_modules.definition` is visible. Lineage is gathered per view:

1. Primary: `sys.dm_sql_referenced_entities([schema].[view], 'OBJECT')`.
2. Fallback: `sys.sql_expression_dependencies`.

Lineage can include object-level and column-level dependencies. The code marks lineage as partial when it comes from fallback, `SELECT *`, caller-dependent references, ambiguous references, incomplete metadata, or unresolved dependencies.

Important: lineage is provenance, not join evidence. Queryability Graph builds `view_depends_on` and `view_column_derives_from` edges with `automatic_join_allowed=false`. The persistence layer also checks non-FK edges cannot be automatic joins.

Current risk: a real compiler can query views, but it cannot assume view lineage is a safe join path. If a semantic metric is view-backed, compiler readiness must verify whether the view is accepted as a source table or requires explicit policy because business logic may be embedded in the view SQL.

## 7. Technical Role and Sensitivity Classification

The snapshot itself assigns `technical_role` using type/name heuristics:

- identifiers: PK, FK, identity, `uniqueidentifier`, or ID-like names;
- date/time types: `date`, `datetime`, `datetime2`, `datetimeoffset`, `smalldatetime`, `time`;
- boolean: `bit`;
- unsupported technical types: binary/varbinary/image/rowversion/timestamp and XML;
- money candidates: money/smallmoney or numeric names such as amount, balance, cost, freight, price, revenue, subtotal, tax, total;
- quantity candidates: numeric names with quantity/qty/count;
- text/numeric/unknown fallback.

Sensitivity is not a raw snapshot field. It is derived in Queryability Graph via `_column_sensitivity`:

- password/hash/salt/secret/token/api key style names -> `sensitive`, excluded;
- email/phone/telefono -> `pii`, still queryable;
- codice fiscale, fiscal code, tax code, IBAN, partita IVA, VAT number -> `pii`;
- first/middle/last/full name and address line -> `pii`.

This is good enough for V1 diagnostics and Resolver safety, but not enough alone for compiler filter/group-by policy. A compiler preflight must decide whether PII can be selected, grouped, filtered, or only used behind explicit tenant policy.

## 8. Hashing and Freshness

`schema_hash` represents stable observable DDL:

- tables/views and definition hash;
- column shape including type, nullability, defaults, identity, computed expression;
- PK/FK metadata including disabled/untrusted state;
- unique/check/default constraints;
- indexes including filters and disabled state.

`schema_hash` intentionally excludes unstable/permission-dependent details such as object IDs, row counts, view lineage, technical roles, and declared-type visibility.

`snapshot_hash` represents the full technical payload:

- engine version and database name;
- coverage status and warnings;
- object IDs, row counts, comments;
- view definitions and lineage;
- all column dataclass details including technical roles and declared type visibility;
- constraints and indexes.

Downstream freshness:

- Queryability Graph stores `schema_hash`, `snapshot_hash`, `graph_input_hash`, `derivation_key`, and `graph_hash`.
- Semantic Layer stores `base_graph_hash`, and after quality-gate hardening also `base_policy_hash`.
- `semantic_layer_effective_freshness` compares the semantic version against latest graph derivation and current connection policy hash.

Policy/classification changes do not change `schema_hash`; they belong to graph/policy hash layers. This separation is correct.

## 9. Error Handling and Partial Coverage

| Scenario | Current behavior | Classification |
| --- | --- | --- |
| Secret resolution fails | Sanitized schema introspection error. | Blocking. |
| pyodbc missing | Configuration error. | Blocking. |
| Core catalog query fails | `DriverIntrospectionError`. | Blocking. |
| Timeout | `DriverIntrospectionError` timeout. | Blocking. |
| Metadata row limit exceeded | `DriverIntrospectionError`. | Blocking. |
| Metadata byte limit exceeded | `DriverIntrospectionError`. | Blocking. |
| Response payload too large | `DriverIntrospectionError`. | Blocking. |
| Index metadata unavailable | Coverage warning. | Partial/warning. |
| Row count unavailable | Coverage warning. | Partial. |
| No foreign keys found | Coverage info, `coverage_status=partial`. | Partial diagnostic, not a trusted relationship inference. |
| View definition unavailable | Coverage warning and permission warning. | Warning. |
| View lineage unavailable/partial | Coverage warning. | Partial/warning. |
| Unresolved lineage | Coverage warning. | Partial. |
| Declared type metadata unavailable | Coverage warning. | Partial. |
| Column returned for invisible object | `COLUMN_OBJECT_MAPPING_MISSING`, coverage blocked. | Blocking. |
| Unsupported SQL Server version | Not explicitly version-gated. | Unknown. |
| Read-only metadata-only permission | Supported if catalog views are visible; partial warnings when not. | Partial. |

The overall behavior is conservative. The missing piece is a compiler-facing rule that decides which partial states still allow executable SQL.

## 10. Relationship With Queryability Graph

The Graph depends directly on snapshot fields:

- objects -> nodes;
- columns -> graph columns and stable column keys;
- primary keys, unique constraints, and eligible unique indexes -> candidate keys;
- foreign keys -> FK join edges;
- disabled/untrusted flags -> `automatic_join_allowed=false`;
- view lineage -> provenance-only lineage edges;
- technical roles -> date/amount/identifier hints;
- snapshot hashes -> graph input and artifact freshness.

The Graph hardening can catch incoherent snapshot references, duplicate graph keys, lineage-as-join, untrusted automatic joins, and missing safe paths. It cannot recover metadata the snapshot never captured. If SQL Server metadata visibility hides FKs, view definitions, or key constraints, Graph correctly degrades but cannot infer business relationships safely.

## 11. Relationship With Semantic Layer

Semantic Layer consumes snapshot evidence indirectly through Graph:

- date candidates are graph columns with `technical_role=date`;
- measure candidates are graph columns with numeric/money/quantity roles;
- source table and source column keys come from graph nodes/columns;
- FK paths for parent dates and dimensions come from graph FK edges;
- view lineage is kept as provenance and must not be used as joins;
- sensitivity and queryability are graph-derived;
- grain candidate keys are graph candidate keys.

Semantic Layer can be strong only when the Graph has enough reliable metadata. If the snapshot has no trusted FK, Semantic Layer should not synthesize a detail metric with parent date path as compiler-ready unless profile/manual evidence provides a safe path. The new semantic invariant diagnostics are the right place to enforce this before compiler.

## 12. Overfitting / Real PMI Risk Assessment

| Risk area | Risk | Rationale |
| --- | --- | --- |
| AdventureWorks clean naming | Medium | Driver does not hardcode AdventureWorks, but many tests and semantic expectations do. |
| Explicit FK availability | High | Snapshot/Graph are safest with real FKs; many ERP/PMI DBs lack them. |
| Missing FK ERP schemas | High | Current fail-closed behavior is correct but product needs mapping/manual policy. |
| Ugly table names | Medium | Snapshot handles names technically; Semantic Layer may need AI/profile evidence. |
| Multiple schemas | Medium | Technical identity supports schemas; coverage should be expanded in tests. |
| Composite keys | Medium | Supported and tested, but live integration is environment-gated. |
| Views with logic | High | Views discovered, lineage partial, business logic not modeled. |
| Permissions-limited users | Medium/High | Coverage warnings exist; compiler gate must decide allowed partial states. |
| Huge database | Medium | Object/column/row/byte limits exist; UX and incremental import are future needs. |
| Stored procedures ignored | Medium | Not a blocker for table/view-only compiler, but many ERP reports live in procs. |
| Synonyms | Medium | Not discovered; could hide object indirection. |
| Temporal tables | Medium | Not explicitly modeled. |
| Computed columns | Medium | Captured, but determinism/persisted status is not deeply modeled. |
| JSON/XML columns | Medium | XML excluded downstream; JSON is not SQL Server-native JSON type and may appear as text. |
| Fiscal/Italian PII detection | Medium | Basic codice fiscale/partita IVA/IBAN coverage exists in Graph, not snapshot. |
| ERP-specific status/code tables | High | Snapshot captures columns/tables, not business meaning. |

## 13. Anti-Demo Tests Needed

| Fixture | Input shape | Expected Technical Snapshot behavior | Downstream impact | Priority |
| --- | --- | --- | --- | --- |
| AdventureWorks baseline | Current clean SQL Server demo | Match expected object/FK/index/view counts and hashes. | Regression baseline. | Blocker |
| Missing FK header/detail | Header/detail names and columns but no FK | `foreign_keys=[]`, `NO_FOREIGN_KEYS_FOUND`, no trusted path. | Graph/Semantic/Compiler fail closed. | Blocker |
| Disabled/untrusted FK | FK exists with disabled or not trusted flag | Flags captured; Graph evidence only. | No automatic join. | Blocker |
| Composite PK/FK | Multi-column key and FK order | Pair order preserved. | Safe joins only if trusted. | Blocker |
| Multi-schema FK | FK crosses schemas | Schema-qualified refs preserved. | No node collision. | Blocker |
| Self-reference | Employee manager FK | FK captured, self-reference flagged downstream. | Excluded from ordinary routing. | Backlog/Compiler |
| Circular FK | A->B and B->A | Snapshot captures both; Graph path avoids infinite traversal. | Compiler must require explicit path. | Backlog |
| Table without PK | Fact-like object with no PK | Table present, no candidate key. | Grain warning/preflight block. | Blocker |
| Filtered unique index | Unique index with `WHERE active=1` | Filter definition captured. | Not cardinality proof. | Blocker |
| View with dependency | Simple view over table | Definition/lineage captured if visible. | Provenance only. | Blocker |
| View unresolved lineage | Dynamic SQL/cross-db/no permission | Coverage warning. | View not compiler-clean without policy. | Blocker |
| Computed columns | Computed expression and default | Expression captured. | Compiler decides if selectable/filterable. | Backlog |
| Unsupported types | xml, varbinary, rowversion, geography-like names | Technical roles/warnings and downstream exclusion. | No unsafe filters/dimensions. | Blocker |
| Italian PII columns | email, telefono, codice fiscale, partita IVA, IBAN, PEC | Snapshot captures names; Graph tags PII/sensitive where known. | Compiler PII policy required. | Blocker |
| ERP ugly schema | `DOTES`, `DORIG`, `ANACLI`, `ARTICO`, `CATART` | Technical identities only; no invented business meaning. | Semantic requires evidence. | Blocker |
| Permissions partial failure | No VIEW DEFINITION / limited metadata | Coverage warnings and partial status. | Preflight blocks affected compiler paths. | Blocker |
| Huge schema limit | >5000 objects or >50000 columns | Introspection fails with limit. | Needs product UX/partitioned import later. | Backlog |

## 14. Technical Snapshot Invariant Proposal

Add a pure snapshot/preflight validator before compiler work:

- Every table/view has stable schema-qualified identity.
- Every column has stable object identity and ordinal.
- PK/FK column refs resolve to discovered columns.
- Composite PK/FK order is preserved.
- Disabled/untrusted FK is represented and cannot become automatic join evidence.
- Filtered unique index cannot prove full-table uniqueness.
- View lineage is provenance only, never join evidence.
- Unresolved lineage creates warning and blocks compiler-clean view usage unless policy permits.
- Unsupported types are carried as technical evidence and excluded downstream.
- PII/sensitive classification is deterministic and compiler policy-aware.
- `schema_hash` changes for schema-significant DDL.
- `snapshot_hash` changes for coverage/lineage/technical classification changes.
- Permission gaps surface as coverage warnings.
- No silent metadata loss: blocked coverage for dangling columns or incoherent object mapping.
- Missing FKs never create trusted relationships from naming.
- Large-schema limits fail clearly.

This validator should produce `valid`, `valid_with_warnings`, or `invalid_for_compiler`, separate from the existing snapshot API status.

## 15. Migration Audit

| Migration | Area | Finding |
| --- | --- | --- |
| `20260602221445_init_app_metadata.sql` | Initial `schema_snapshots`, RLS | Created JSONB snapshot storage, initial RLS read/insert policies, legacy semantic tables. |
| `20260602221552_harden_foundation.sql` | Tenant FKs / service grants | Added composite tenant constraints and service-role access. |
| `20260604082514_harden_schema_introspection_snapshots.sql` | Metadata-only guard | Added `snapshot_version`, `introspected_at`, forbidden metadata key guard, summary view. |
| `20260604153000_technical_snapshot_v1_relationships.sql` | Technical FK fields | Added relationship metadata fields and summary projection. |
| `20260605090707_milestone_zero_hardening.sql` | Service-role RPC / hash | Added `schema_hash`, revoked direct authenticated DML, introduced private persist function. |
| `20260611120000_persist_schema_import_summary.sql` | V1 summary | Replaced legacy `coverage_state` with `coverage_status`, strict import summary, guarded schema summary view. |
| `20260612010000_queryability_graph_v1.sql` | Graph persistence | Required `snapshot_hash`, made snapshots/graphs immutable, created graph tables/RPC and shape checks. |
| `20260612193000_queryability_graph_derivations.sql` | Derivation mapping | Added snapshot-to-graph derivations and automatic join guard for trusted DB FKs only. |
| `20260613092517_deduplicate_queryability_snapshot_by_hash.sql` | Snapshot dedupe | Deduplicates imports by `snapshot_hash` with collision checks. |
| `20260614172852_semantic_layer_v1_lifecycle.sql` | Semantic lifecycle | Semantic layers now reference graph versions and `base_graph_hash`, with freshness/status lifecycle. |
| `20260615102531_semantic_layer_workspace_hardening.sql` | Semantic graph refs | Adds graph topology/reference triggers and stale marking on graph change. |
| `20260620020000_semantic_canonical_quality_gate.sql` | Policy hash/freshness | Adds `base_policy_hash`, policy snapshot checks, activation quality gate, policy stale marking. |

Migration posture is good: snapshots and graphs are immutable, direct authenticated writes are revoked, persistence happens through service-role RPCs, and semantic freshness is hash-based. The compiler gap is not persistence integrity; it is preflight interpretation of partial/coverage states.

## 16. Test Discovery and Verification

Discovery command searched for:

```text
schema_snapshot, introspect, SchemaIntrospection, sqlserver, foreign_keys, schema_hash, snapshot_hash
```

Directly relevant test files found:

| File | Why relevant | Run status |
| --- | --- | --- |
| `services/query-engine/tests/test_introspection.py` | Driver/API/contracts/hash/coverage unit tests. | Run directly: 31 passed. |
| `services/query-engine/tests/test_sqlserver_integration.py` | Real SQL Server catalog fixture for composite FK/index/view lineage. | Run directly: 1 skipped, no `SQLSERVER_INTEGRATION_HOST`. |
| `services/query-engine/tests/test_contracts.py` | Python contract strictness. | Run with queryability contract batch: passed. |
| `services/query-engine/tests/test_queryability_builder.py` | Snapshot-to-Graph behavior, FK/cardinality/lineage/hash. | Run directly in batch: passed. |
| `services/query-engine/tests/test_queryability_contracts.py` | Queryability endpoint/contract use of snapshots. | Run directly in batch: passed. |
| `services/query-engine/tests/test_queryability.py` | Graph invariant diagnostics. | Run directly: 20 passed. |
| `services/query-engine/tests/test_semantic_invariants.py` | Semantic compiler-readiness over graph/snapshot evidence. | Run directly: 10 passed. |
| `services/query-engine/tests/test_query_intent.py` | Resolver regression over semantic/graph artifacts. | Run directly: 22 passed. |
| `packages/contracts/src/index.test.ts` | Zod schema introspection contract and import summary. | Run via `pnpm --filter @atlantebi/contracts test`: passed. |
| `apps/web/lib/schema-introspection/service.test.ts` | Web import summary generated from schema+graph. | Run via `pnpm --filter @atlantebi/web test`: passed. |
| `packages/db/src/migration.test.ts` | Migration/RLS/RPC/static DB assertions. | Run via `pnpm --filter @atlantebi/db test`: passed. |
| `supabase/tests/*.sql` relevant files | Runtime DB tests for schema snapshots, graph import, semantic lifecycle. | Run via `npx -y supabase@2.104.0 test db`: 124 passed. |

Verification results:

| Command | Result |
| --- | --- |
| `(cwd services/query-engine) .\.venv\Scripts\python.exe -m pytest tests/test_introspection.py -q` | 31 passed |
| `(cwd services/query-engine) .\.venv\Scripts\python.exe -m pytest tests/test_sqlserver_integration.py -q` | 1 skipped: SQL Server integration fixture is not running |
| `(cwd services/query-engine) .\.venv\Scripts\python.exe -m pytest tests/test_contracts.py tests/test_queryability_builder.py tests/test_queryability_contracts.py -q` | 44 passed |
| `(cwd services/query-engine) .\.venv\Scripts\python.exe -m pytest tests/test_queryability.py -q` | 20 passed |
| `(cwd services/query-engine) .\.venv\Scripts\python.exe -m pytest tests/test_semantic_invariants.py -q` | 10 passed |
| `(cwd services/query-engine) .\.venv\Scripts\python.exe -m pytest tests/test_query_intent.py -q` | 22 passed |
| `(cwd services/query-engine) .\.venv\Scripts\python.exe -m pytest -q` | 231 passed, 1 skipped |
| `$env:CI='true'; pnpm --filter @atlantebi/contracts test` | 5 files, 44 tests passed |
| `$env:CI='true'; pnpm --filter @atlantebi/db test` | 1 file, 35 tests passed |
| `npx -y supabase@2.104.0 test db` | 6 files, 124 tests passed |
| `$env:CI='true'; pnpm --filter @atlantebi/web test` | 19 files, 67 tests passed |
| `$env:CI='true'; pnpm --filter @atlantebi/web typecheck` | Passed |
| `$env:CI='true'; pnpm lint` | Passed |

Integration-test confidence note: because `tests/test_sqlserver_integration.py` skipped without `SQLSERVER_INTEGRATION_HOST`, claims that depend on a live SQL Server catalog are medium confidence locally even though unit/static tests pass. CI should run this fixture for high confidence.

## 17. Evidence Matrix

| Claim | Evidence source | Confidence | Notes |
| --- | --- | --- | --- |
| SQL Server driver reads rich catalog metadata, not just information schema. | `services/query-engine/app/drivers/sqlserver.py`: catalog queries for objects, columns, keys, FKs, constraints, indexes, lineage. | High | Verified statically and by unit tests. |
| Snapshot captures disabled/untrusted FK flags. | `SchemaForeignKeyMetadata`; `SQLSERVER_FOREIGN_KEYS_QUERY`; `test_sqlserver_driver_reads_only_metadata_queries`. | High | Live integration skipped, but query and unit fixture cover shape. |
| Composite FK order is preserved. | `_build_foreign_keys`; `test_sqlserver_snapshot_v1_against_real_catalog_views`; queryability builder tests. | Medium | Logic/test present; live test skipped locally. |
| Filtered unique indexes are captured and not treated as global cardinality proof downstream. | `SchemaIndexMetadata.filter_definition`; `_eligible_unique_index`; `test_only_global_enabled_unique_keys_prove_one_to_one`. | High | Downstream Graph behavior tested. |
| View lineage is provenance, not join evidence. | `_fetch_view_lineage`; `_build_lineage_edges`; queryability contract tests; graph persistence checks. | High | Graph and DB tests enforce non-FK edges are not automatic joins. |
| `schema_hash` excludes unstable object ID/row counts and lineage. | `_schema_hash`; `test_sqlserver_schema_hash_ignores_unstable_object_id_and_row_count`; `test_schema_hash_excludes_lineage_and_technical_roles_but_snapshot_hash_tracks_them`. | High | Direct tests. |
| `snapshot_hash` tracks full technical/coverage payload. | `_snapshot_hash`; hash tests; `docs/schema-snapshot-v1.md`. | High | Direct tests. |
| Snapshot storage is metadata-only and rejects raw data keys. | `jsonb_has_forbidden_metadata_key`; migration tests. | High | Static DB tests and migration tests pass. |
| Direct authenticated DML on snapshots is removed after hardening. | `20260605090707_milestone_zero_hardening.sql`; migration tests. | High | Static DB tests pass. |
| Graph persistence validates automatic joins require enabled trusted DB-verified FKs. | `20260612193000_queryability_graph_derivations.sql`; Supabase DB tests. | High | DB tests pass. |
| Semantic freshness depends on graph and policy hash, not snapshot alone. | `semantic_layer_effective_freshness`; semantic quality gate migration. | High | DB tests pass. |
| Technical Snapshot is not compiler-ready by itself. | Absence of compiler preflight; business semantics live in Graph/Semantic/Resolver. | Medium | Inference from architecture, consistent with tests. |
| Missing FK schemas fail closed. | Graph builds no FK edges without snapshot FKs; `NO_FOREIGN_KEYS_FOUND` warning. | High for no inference; Medium for product behavior | Needs more anti-demo UI/flow tests. |
| PII classification is downstream Graph-derived, not raw snapshot. | `_column_sensitivity` in `queryability.py`; `buildSchemaImportSummary`. | High | Important separation for compiler policy. |

## 18. Final Recommendation

**Proceed to compiler-facing preflight gate. Do not proceed directly to Query Compiler V1.**

This is the right next move because the Technical Snapshot is good enough to be the evidence base, but not enough to decide compiler safety alone. The preflight gate should consume:

- Technical Snapshot `coverage_status` and warnings;
- Queryability Graph validation report;
- Semantic Layer compiler-readiness invariant report;
- tenant/user policy for PII, missing FK/manual mappings, view usage, business dates, and status scope.

The compiler should only start after that gate can produce a deterministic `compiler_ready | blocked | needs_policy` result with audit reasons. Ignoring this step would turn partial metadata into executable SQL risk.
