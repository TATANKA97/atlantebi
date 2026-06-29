# Queryability Graph - State of the Art

Date: 2026-06-30

Scope: static technical audit of the current Queryability Graph implementation and its downstream use by Semantic Layer and Query Intent Resolver. This report intentionally does not introduce functional changes.

## 1. Executive Summary

**Recommendation: Do not proceed to Query Compiler V1 yet as a general product compiler.**

The Queryability Graph is a solid V1 foundation for databases with explicit, trusted SQL Server foreign keys. It is deterministic, versioned, persisted immutably, and correctly treats view lineage as provenance rather than join evidence. It is not an AdventureWorks-name hardcode at the graph-builder level.

The problem is different: the Graph is still not enough by itself to protect a real SQL compiler on messy PMI/ERP schemas. Several important guarantees currently live in the Semantic Layer builder, Query Intent Resolver, quality profile, or test fixtures rather than in reusable graph invariants. That is acceptable for Resolver V1. It is not enough for a compiler that will generate executable SQL.

### Readiness

| Question | Answer |
| --- | --- |
| Ready to support Semantic Layer V1? | Yes, with explicit FK schemas and the current validator gates. |
| Ready to support Query Intent Resolver V1? | Yes for the current narrow scope, because Resolver has its own safety checks and tests. |
| Ready to support Query Compiler V1? | Not yet. Add graph hardening and compiler-facing path invariants first. |
| Overfitted to AdventureWorksLT? | Medium. The graph builder is generic; the exercised evidence and downstream assumptions are still demo-heavy. |

### Blockers Before Compiler

1. Add a Queryability Graph invariant validator and anti-demo graph test suite.
2. Make compiler-facing path selection fail closed on ambiguous paths, fanout, bridge/many-to-many, disabled/untrusted FK, and lineage-as-join.
3. Formalize dimension/filter privacy policy. Today `pii` columns can remain queryable, while Resolver blocks some sensitive cases with additional heuristics.
4. Formalize technical date vs business date semantics. The Graph carries `technical_role = date`, but does not distinguish `OrderDate` from `ModifiedDate` as a compiler-safe business default.
5. Add missing-FK behavior tests. V1 can choose to require explicit FK metadata, but then missing-FK schemas must clearly degrade to blocked/no-join, not accidental inference.
6. Add compiler requirements to the Graph contract or a compiler gate: join direction, join type policy, aliases, quoted physical identifiers, edge-path provenance, and row-cap/read-only safety checks.

### Backlog, Not Blocker

- Name/index-based relationship inference, as untrusted evidence only.
- Richer PII classifier and locale-specific fiscal identifiers.
- View SQL lineage enrichment.
- Data profiling or redacted samples.
- Better UI labels for ID dimensions.
- Row-count/selectivity estimates for cost-aware planning.

## 2. Current Architecture

Current flow:

```txt
DB metadata / Technical Snapshot
-> Queryability Graph
-> Semantic Layer
-> Query Intent Resolver
-> future Query Compiler
```

### Main Files

| Area | File | Notes |
| --- | --- | --- |
| Technical Snapshot models | `services/query-engine/app/models.py` | `SchemaIntrospectionResponse`, table/column/FK/index/view lineage contracts. |
| Queryability Graph builder | `services/query-engine/app/queryability.py` | `build_queryability_graph`, `_build_node`, `_build_column`, `_build_fk_edge`, `_build_lineage_edges`, `_mark_bridge_candidates`. |
| Queryability path finder | `services/query-engine/app/queryability.py` | `find_queryability_paths`, 1 to 4 hop BFS over eligible FK edges. |
| Queryability API | `services/query-engine/app/main.py` | `POST /queryability/compile`, `POST /queryability/paths`. |
| Shared contracts | `services/query-engine/app/models.py`, `packages/contracts/src/*` | Python/Pydantic and TS/Zod contracts. |
| Web import/orchestration | `apps/web/lib/schema-introspection/service.ts` | Runs introspection, compiles graph, persists import. |
| Web graph parsing | `apps/web/lib/queryability/persisted-artifacts.ts` | Parses persisted graph/snapshot artifacts. |
| Web graph presentation | `apps/web/lib/queryability/presentation.ts` | FK detail, schema flags, lineage labels. |
| Supabase persistence | `supabase/migrations/20260612010000_queryability_graph_v1.sql` | Graph tables, immutability, shape checks, import RPC. |
| Graph derivations | `supabase/migrations/20260612193000_queryability_graph_derivations.sql` | Snapshot-to-graph derivation table and automatic join guard. |
| Semantic usage | `services/query-engine/app/semantic_discovery.py` | Seed, AI input, canonical builder, path/date/dimension enrichment, validation. |
| Resolver usage | `services/query-engine/app/query_intent.py` | Stale check, metric selection, dimension/filter safety, path validation. |

### Hashes and Freshness

| Hash | Where | Purpose |
| --- | --- | --- |
| `schema_hash` | Technical Snapshot | Stable observable DDL. Excludes permission-dependent and volatile metadata. |
| `snapshot_hash` | Technical Snapshot | Full technical snapshot hash, including lineage/coverage/technical classifications. |
| `graph_input_hash` | `queryability.py` | Canonical graph input payload derived from snapshot metadata. |
| `derivation_key` | `queryability.py` | Graph input hash plus builder/policy versions. Used for deduplication. |
| `graph_hash` | `queryability.py` | Canonical graph artifact hash. Used by Semantic Layer freshness. |
| `base_graph_hash` | Semantic Layer | Must match current graph for fresh semantic layer. |
| `base_policy_hash` | Semantic Layer | Must match current semantic policy for fresh semantic layer. |

The Graph itself has immutable persisted versions. Semantic freshness is evaluated by comparing `base_graph_hash` and `base_policy_hash` against the current graph/policy. The Resolver blocks stale semantic layers.

### Persistence

The graph is persisted in:

- `queryability_graph_versions`: canonical JSONB graph plus counts and hashes.
- `queryability_graph_nodes`: normalized node projection.
- `queryability_graph_columns`: normalized column projection.
- `queryability_graph_edges`: normalized edge projection.
- `queryability_graph_derivations`: links schema snapshot to graph version.

Graph rows are immutable after insert. Import RPC validates shape, duplicate keys, maximum sizes, graph/snapshot consistency, and automatic-join eligibility.

## 3. Current Graph Contents

| Area | Status | Evidence | Comment |
| --- | --- | --- | --- |
| Tables/entities | Implemented | `QueryabilityNode` | Includes database, schema, object name, type, stable `node_key`. |
| Columns | Implemented | `QueryabilityColumn` | Includes stable `column_key`, type, ordinal, technical role, queryability, sensitivity. |
| Queryable columns | Implemented | `_build_column` | Queryable unless excluded by sensitivity/type rules. |
| Excluded columns | Partial | `_build_column` | Sensitive secrets/binary/xml excluded. Policy is name/type based. |
| Sensitive columns | Partial | `_column_sensitivity` | Heuristic classifier only. `pii` remains queryable. |
| Candidate keys | Implemented | `_candidate_keys` | Primary keys, unique constraints, eligible unique indexes. |
| Composite keys | Implemented | tests cover composite FK and composite uniqueness flags | Pair order and candidate-key matching are covered. |
| Explicit FK edges | Implemented | `_build_fk_edge` | Stores constraint name, column pairs, nullability, cardinality, trust state. |
| Disabled/untrusted edges | Implemented | tests cover disabled/untrusted | Kept as evidence, not automatic joins. |
| Trusted join edges | Implemented | `automatic_join_allowed` | Requires enabled, trusted, DB-verified FK and queryable FK columns. |
| Inferred relationships | Missing | no naming/index inference | This is safe for V1 but weak for real ERP schemas with missing FKs. |
| View lineage | Implemented as provenance | `_build_lineage_edges` | `view_depends_on` and `view_column_derives_from` never allow joins. |
| Grain/fanout | Partial | `relationship_shape`, parent/child cardinality, path fanout warning | Basic FK direction/cardinality exists. Compound fanout/m2m safety is not fully centralized. |
| Bridge detection | Partial | `_mark_bridge_candidates` | Structural bridge candidates are marked, but compiler-facing m2m policy is not complete. |
| Warnings/status | Partial | `status_reasons` | Partial graph captures warnings; downstream gates do not treat every severe warning as blocking. |
| Stable keys | Implemented | SHA-256 style keys | Stable technical identity avoids physical names as identifiers. |
| Policy decisions | Partial | `policy_version`, graph input hash | Builder has policy version, but rich graph policy is not modeled. |

## 4. Dependency on Schema Retrieval

The Queryability Graph is only as strong as the Technical Snapshot. Current behavior:

| Scenario | Current behavior | Risk |
| --- | --- | --- |
| DB has explicit trusted FKs | Good. Graph creates automatic FK join edges. | Low. |
| DB has disabled/untrusted FKs | Edge is preserved but not automatic. | Low. Correct fail-closed behavior. |
| DB has no FKs | No trusted join edge. | High for real PMI/ERP DBs if many relationships are implicit. |
| Naming suggests FK but DB has no FK | No inference. | Safe, but product may look weak unless surfaced clearly. |
| PK surrogate exists | Captured through primary key metadata. | Low. |
| Unique constraints/indexes | Captured when eligible; filtered unique index excluded. | Low/Medium. Good, but more tests on ERP edge cases would help. |
| Composite keys | Supported. | Medium. Covered but should remain in anti-demo suite. |
| Multiple schemas | Included in stable node identity. | Medium. Needs more multi-schema tests beyond simple cases. |
| Views | Captured as nodes and lineage provenance. | Medium. Correctly cautious, but real DBs often hide business logic in views. |
| Table without PK | Node exists, but no candidate key/grain confidence. | High for compiler if not blocked or downgraded. |
| Technical dates | `technical_role = date` exists, but business vs audit date is not graph-level. | High if compiler chooses dates without semantic guidance. |
| ModifiedDate/CreatedAt/RowGuid | Captured, not necessarily excluded. | Medium/High. Semantic builder avoids audit dates, Graph does not enforce business-date policy. |

The key weakness is not that the snapshot is wrong. It is strict and deterministic. The weakness is that real customer databases may not expose the FK and business-date metadata the Graph needs to be safe.

## 5. Grain and Path Safety

### What the Graph Supports

- FK direction: child table to parent table through `from_node_key -> to_node_key`.
- Relationship shape: `many_to_one` or `one_to_one`.
- Cardinality by direction:
  - child to parent: `exactly_one` or `zero_or_one`;
  - parent to child: `zero_or_many` or `zero_or_one`.
- Enabled/trusted/DB-verified FK gating.
- Self-reference detection.
- Structural bridge-candidate marking.
- 1 to 4 hop path search.
- Ambiguous shortest path detection.
- Basic fanout warning when traversing parent-to-child zero-or-many.

### What Is Still Partial

| Need | Current state | Compiler implication |
| --- | --- | --- |
| Header/detail grain | Mostly in Semantic Layer metrics, not the Graph alone. | Compiler must consume semantic grain, not just path output. |
| Header metric grouped by detail dimension | Blocked by Semantic Layer/Resolver compatibility, not a standalone graph rule. | Compiler needs a mandatory guard. |
| Many-to-many/bridge paths | Bridge candidate exists; safe traversal excludes bridge in Semantic builder with `safe_only`. | Compiler needs explicit bridge/m2m fail-closed behavior. |
| Shortest vs safest path | Path API returns shortest eligible FK paths and ambiguous when parallel. Semantic builder has its own safe path logic. | Compiler must not choose a shortest path if multiple safe paths or any unsafe alternative is material. |
| Compound fanout | Basic warning only. | SQL can still multiply rows if multiple one-to-many expansions are composed. |
| Allocation | Not supported. Correct. | Compiler must block allocation-shaped requests. |

### Critical Finding

The Resolver does not simply ask the Graph path API for everything. It uses Semantic Layer metric compatibility and its own `_safe_child_to_parent_path` logic for some cases. That is fine for Resolver V1, but the Compiler must have a single authoritative join/path gate. Otherwise, one layer can be safe while the SQL generator reintroduces fanout.

## 6. Queryable, Sensitive, and Excluded Columns

### Current Classification

| Classification | Current support | Notes |
| --- | --- | --- |
| `queryable` | Implemented | Default for regular columns. |
| `excluded` | Partial | Sensitive secrets and unsupported technical types are excluded. |
| `sensitive` | Partial | Secret/token/password/card approval style names. Excluded. |
| `pii` | Partial | Email, phone, name, address-like fields. Still queryable. |
| `technical` | Partial | Technical role from snapshot. Not enough for business semantics. |
| candidate dimension | Missing as graph field | Semantic builder derives common dimensions. |
| candidate filter | Missing as graph field | Resolver has safe filter logic for known cases. |
| candidate date | Partial | Date role exists. Business-date quality is outside graph. |
| candidate measure | Partial | Money/numeric role exists. Business measure is outside graph. |

### Can the Graph Prevent These?

| Case | Current answer | Comment |
| --- | --- | --- |
| Group by email/phone/fiscal id | Not fully by graph alone. | `pii` is queryable. Resolver blocks email through extra checks, not all PII. |
| Filter on sensitive columns | Yes for `sensitive`; partial for `pii`. | `sensitive` excluded, but `pii` remains technically queryable. |
| Use `ModifiedDate` as business date | No graph-level block. | Semantic builder prefers non-audit dates. Compiler needs to preserve that. |
| Use wrong descriptive column | No. | Graph does not select labels; UI/semantic layer must help. |
| Expose technical ID dimensions | Not blocked. | Some ID dimensions are safe technically but poor UX/business defaults. |

This separation is defensible: queryability is not business semantics. But the Compiler must not treat `queryable` as "safe to expose or group by".

## 7. Relationship With Semantic Layer

The Semantic Layer currently uses the Graph in a disciplined way:

- `build_semantic_discovery_input` only sends queryable nodes and columns, excluding `sensitive` columns.
- AI gets stable keys, not free physical-name identifiers.
- Only automatic, DB-verified, enabled, trusted FK relationships are sent as relationships.
- View lineage is not sent as join evidence.
- The deterministic seed inherits queryability, sensitivity, FK shape, lineage status, and graph hash.
- The canonical builder derives:
  - grain columns;
  - default date and parent date paths;
  - common dimensions;
  - dimension compatibility;
  - required join edge keys;
  - currency and eligibility.
- The validator checks stable references, excluded/sensitive use, trusted FK use, raw SQL absence, grain/path rules, and semantic hash.

### Gaps

| Question | Current answer |
| --- | --- |
| Do metrics use only queryable source columns? | Yes by validator/builder intent. |
| Are effective dates validated against graph? | Yes, but business-date quality is semantic logic, not graph logic. |
| Are dimensions validated against graph? | Yes for common dimensions and resolver-selected dimensions. |
| Do ambiguities derive from graph? | Partially. Path/date ambiguity can derive from graph; many business ambiguities come from policy/AI. |
| Does quality gate block if graph is unreliable? | Partially. Required specs and graph references are checked, but a `partial` graph can still produce an active semantic layer if no blocking validation error is raised. |
| Can Semantic Layer become active with graph warnings? | Yes, if validation/quality gates pass. This is acceptable for lineage partial warnings, risky if future warnings indicate missing FK coverage. |

The Semantic Layer is doing real safety work. That is good. The risk is that the future Compiler may need the same checks in a stricter, compiler-facing form.

## 8. Relationship With Query Intent Resolver

After Milestone 8, the Resolver is significantly safer than before:

- Blocks stale semantic layer when active/fresh/hash/validation do not match.
- Selects only one primary metric in V1.
- Uses metric eligibility.
- Uses semantic dimension compatibility first, then safe child-to-parent graph paths.
- Blocks unsafe header metric grouped by product/category detail dimensions.
- Blocks sensitive email-like requests.
- Produces structured filters only for safe known columns.
- Records forbidden alternatives in audit.
- Has deterministic, AI-disabled acceptance tests and bulk runner.
- Has invariant/advisory test infrastructure.

### Demo Assumptions Still Present

| Area | Dependency |
| --- | --- |
| Product/category selection | Resolver knows AdventureWorks object/column names for product/category labels. |
| Online/offline filter | Resolver maps `OnlineOrderFlag` by physical object/column name. |
| Product color filter | Resolver maps `Product.Color` by physical object/column name. |
| Customer email block | Resolver looks for email terms and sensitive email availability. |
| Business date | Mostly inherited from Semantic Layer default date, not Graph alone. |

These are acceptable for Milestone 8 debug tooling. They should not be confused with general compiler readiness.

## 9. Requirements for Query Compiler V1

The compiler will need all of the following to be explicit, not inferred ad hoc:

| Requirement | Current source | Current readiness |
| --- | --- | --- |
| Stable table identifiers | Graph node keys plus physical names | Good. |
| Stable column identifiers | Graph column keys plus physical names | Good. |
| Schema-qualified names | Graph nodes include database/schema/object | Good, needs quoting policy. |
| Metric source table | Semantic metric | Good. |
| Date path | Semantic metric required edges/default date | Good for current cases. |
| Dimension path | Semantic compatibility and plan edge path | Good for current cases, needs compiler invariant. |
| Filter path | Partial | Filters currently simple and local/known. Cross-table filters need path policy. |
| Join ordering | Missing as compiler contract | Can be derived, but needs deterministic algorithm and tests. |
| Join type | Partial | FK nullability exists; compiler policy not defined. |
| FK direction/cardinality | Graph | Good. |
| Fanout risk | Partial | Basic fanout warning exists; compound safety incomplete. |
| Aliases | Missing | Needed to avoid collisions. |
| SQL Server quoting | Missing in compiler scope | Needed before generating SQL. |
| Max row caps | Outside graph | Needed for execution safety. |
| Read-only safety | Outside graph | Needed before execution. |
| No cross-tenant leakage | App/RLS/service boundary | Needs compiler/execution audit. |
| View lineage handling | Graph provenance only | Good, compiler must continue to reject lineage-as-join. |
| Ambiguous paths | Graph path API can return ambiguous | Compiler must hard-block. |

Bottom line: the physical metadata is mostly available, but the compiler-facing safety contract is not finished.

## 10. Overfitting Risk Assessment

| Area | Risk | Reason |
| --- | --- | --- |
| FK detection | Medium | Builder is generic, but requires explicit DB FK metadata. Many PMI schemas lack FKs. |
| Header/detail recognition | Medium | Semantic metrics carry grain; Graph has FK cardinality but not business role. |
| Product/category paths | Medium | AdventureWorks path is clean; real catalogs can have multiple hierarchies. |
| Date selection | High | Graph has date role, not business-event date semantics. |
| Sensitive columns | Medium/High | Heuristic PII/sensitive classifier is not enough for fiscal codes, IBAN, PEC, VAT, employee data. |
| Status/cancelled logic | High | Graph does not model lifecycle/status semantics. |
| Customer/supplier distinction | High | Graph cannot infer business populations safely. |
| Views | Medium/High | Correctly cautious, but many real DBs encode business semantics in views. |
| Composite keys | Medium | Supported, but needs more real-like tests. |
| Missing FKs | High | No inferred trusted edges. Safe but product-limiting. |
| ERP-style naming | High | Graph keys are stable, but meaning is not recoverable from ugly names without semantic/profile help. |
| Multiple schemas | Medium | Supported structurally; not enough multi-schema safety tests. |
| Duplicated concepts | High | Needs Semantic Layer/policy disambiguation, not Graph alone. |

## 11. Suggested Hardening Tests

| Test | Input | Expected graph behavior | Severity | Downstream impact |
| --- | --- | --- | --- | --- |
| AdventureWorks baseline | Current demo snapshot | 13 objects, 129 columns, 12 FK, partial only for lineage/coverage warnings. | Baseline | Regression guard. |
| AdventureWorks FK removed | Same tables, no FKs | No automatic joins; graph partial/warning for low join evidence if implemented. | Blocker before compiler | Compiler must not join by names. |
| Synthetic PMI ugly names | `DOTES`, `DORIG`, `ANACLI`, `ARTICO`, `CATART` | Stable graph nodes/columns; no invented trusted edges. | Blocker | Prevents name overfitting. |
| Ambiguous paths | Two distinct customer/address/order paths | Path result ambiguous; compiler must not choose shortest silently. | Blocker | Avoids wrong joins. |
| Header/detail no explicit FK | Header and line naming only | No trusted edge; possible untrusted candidate only in future. | Blocker | Avoids false header/detail joins. |
| Detail with multiple parents | Line table links to order and invoice | Multiple paths surfaced; no silent date/dimension default. | Blocker | Prevents wrong business date. |
| Bridge/many-to-many | CustomerProduct bridge | Bridge candidate true; automatic compiler path blocked unless approved. | Blocker | Prevents fanout multiplication. |
| Sensitive columns | Email, phone, codice fiscale, IBAN, password | Secret excluded; PII tagged; compiler dimension/filter policy blocks sensitive/PII as configured. | Blocker | Privacy. |
| Views with lineage | View columns derive from base columns | Lineage edges only; no automatic join. | Blocker | Prevents fake joins from lineage. |
| ModifiedDate vs business date | Header has OrderDate and ModifiedDate | Both technical date, but warning/disclosure if audit date selected. | Blocker | Prevents wrong time slicing. |
| Multiple date candidates | OrderDate, PostingDate, InvoiceDate | Ambiguity visible to Semantic Layer/Resolver. | Blocker | Avoids silent wrong date. |
| Customer/supplier mixed table | One party master table | Graph remains technical; semantic clarification required. | Backlog/semantic | Prevents customer/supplier confusion. |
| Status/cancelled fields | Status, CancelledFlag, Deleted | Graph exposes fields; semantic/status policy handles default. | Backlog pre-result | Prevents revenue scope ambiguity. |
| Composite keys | Header/line with composite PK/FK | Column pair order preserved; cardinality correct. | Blocker | SQL join correctness. |
| Table without PK | Large fact-like table no PK | Node exists but grain unavailable; semantic metric validation blocks unsafe metric unless grain supplied. | Blocker | Avoids unbounded/duplicated aggregation. |

## 12. Invariant Validator Proposal

Add a pure Queryability Graph invariant validator, separate from Semantic Layer and Resolver tests.

### Structural Invariants

- Every node has unique `node_key`.
- Every column has unique `column_key`.
- Every edge has unique `edge_key`.
- Every edge references valid node keys.
- Every FK edge column pair references valid column keys on the correct nodes.
- No dangling `view_column_derives_from` column references when resolution is `resolved`.
- Graph counts match node/column/edge arrays.
- Graph hash changes when graph-significant schema or policy inputs change.

### Queryability Invariants

- Every queryable column has a stable key and valid node.
- Excluded columns cannot appear in automatic FK column pairs.
- Sensitive columns cannot be automatic dimensions or filters.
- `pii` columns require explicit downstream policy before grouping/filtering.
- Unsupported types stay excluded.

### Relationship Invariants

- `automatic_join_allowed = true` requires:
  - `edge_type = fk_join`;
  - `verified_by_db = true`;
  - `enforcement_status = enabled`;
  - `validation_status = trusted`;
  - queryable source and target columns;
  - no view-lineage edge.
- Disabled/untrusted/unverified FK edges are evidence only.
- View lineage cannot be treated as a trusted FK.
- Self-reference is excluded from ordinary routing unless explicitly requested.
- Bridge/many-to-many paths require explicit compiler policy approval.

### Path Invariants

- Path search must not silently choose among multiple shortest safe paths.
- Parent-to-child fanout must be surfaced as unsafe or warning depending on compiler context.
- Header metric to detail/product/category dimension must be blocked unless an explicit allocation strategy exists.
- Detail metric to parent date through trusted FK is allowed.
- Lineage path is never a join path.

### Freshness Invariants

- A graph whose hash differs from a Semantic Layer `base_graph_hash` makes that layer stale.
- Stale semantic layers block resolver/compiler.
- Policy hash changes make semantic layers stale even when graph hash is unchanged.

## 13. Recommended Next Milestone

**Decision: Do not proceed to Query Compiler yet.**

Proceeding now would be premature. The Compiler would be able to pass AdventureWorks and still be unsafe on realistic schemas with missing FKs, bridge tables, multiple date candidates, ambiguous paths, and PII fields.

### Immediate Pre-Compiler Work

| Task | Effort | Risk if ignored |
| --- | --- | --- |
| Add Queryability Graph invariant validator and test suite | M | Compiler may trust malformed or incomplete graph artifacts. |
| Add anti-demo graph fixtures | M | Demo remains green while real DBs fail or produce unsafe plans. |
| Add compiler path gate contract | M | SQL generator may bypass Resolver/Semantic safety. |
| Formalize PII dimension/filter policy | S/M | Privacy leaks through group-by/filter. |
| Formalize technical-date warnings | S | Compiler may use `ModifiedDate` as business date. |
| Add missing-FK degradation tests | S/M | Product may silently infer or fail unclearly. |
| Add bridge/m2m compiler-block tests | M | Aggregations may multiply rows. |

### Suggested Order

1. Queryability Graph invariant validator.
2. Anti-demo graph fixtures: missing FK, ambiguous path, bridge/m2m, table without PK, multiple dates.
3. Compiler-facing path gate using Graph plus Semantic metric grain.
4. Privacy/filter/dimension policy gate.
5. Only then start Query Compiler V1.

### What Can Stay Backlog

- Relationship inference from names/indexes.
- Profiling/sample-based semantic discovery.
- Advanced view SQL parsing.
- Row-estimate/cost-aware path selection.
- Rich ERP domain packs.

### Practical Compiler Entry Criterion

Start Compiler V1 only when these are true:

- Graph invariants pass on all baseline and anti-demo fixtures.
- Compiler path gate rejects ambiguous/fanout/bridge/lineage paths.
- Header/detail grain safety is enforced outside the Resolver UI path.
- Sensitive/PII dimension and filter policy is deterministic.
- Missing FK schemas fail closed with actionable warnings.

Until then, the correct next step is Queryability Graph hardening, not SQL generation.
