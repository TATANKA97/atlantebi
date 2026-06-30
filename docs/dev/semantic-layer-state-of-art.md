# Semantic Layer State of the Art / Anti-Demo Audit

## 1. Executive Summary

Audit context: `origin/main only`.

The audit was performed on branch `codex/semantic-layer-state-of-art`, created from `origin/main` after PR #54 was merged. `origin/main` is at `6930840 Merge pull request #54 from TATANKA97/codex/queryability-hardening-test-report`, and includes the Queryability Graph hardening coverage report and tests. Therefore Queryability Graph hardening guarantees are active code in this audit, not only read-only context.

Final recommendation: **Proceed only after specific blockers are fixed**.

The Semantic Layer V1 is solid enough for Query Intent Resolver V1 on the AdventureWorksLT path. It is not yet solid enough to let a Query Compiler V1 generate SQL safely against real PMI/ERP schemas. The architecture is directionally correct: stable keys, server-side canonical builder, quality profile synthesis, deterministic validator, explicit provenance, policy hash, graph hash, and quality gate are all real. The weak point is generalization. A lot of the current success is protected by the AdventureWorks quality profile and clean schema shape, not by demonstrated robustness on ugly schemas, missing FK schemas, mixed party tables, bridge hierarchies, multiple amount columns, or view-based business logic.

| Question | Answer |
| --- | --- |
| Ready for Resolver V1? | yes |
| Ready for Compiler V1? | no |
| Overfitting risk | high |
| Quality profile dependency | high for AdventureWorks acceptance, medium-high for current generation reliability |
| Required next step | Semantic Layer anti-demo hardening and invariant validator before compiler |

Architecturally solid:

- AI output is structured and advisory; server owns grain, joins, currency, eligibility, hashes, provenance, and validation.
- Quality profile synthesis is explicit and auditable through `provenance_detail=quality_profile` and `source_spec_key`.
- Header/detail grain safety is implemented and tested for AdventureWorks.
- Policy hash, graph hash, freshness, activation gate, and DB immutability exist.
- Query Intent Resolver can consume active/fresh Semantic Layer and pass deterministic/advisory suites.

Immediate blockers before compiler:

- No Semantic Layer invariant validator equivalent to the Queryability Graph invariant validator.
- No anti-demo semantic fixture suite beyond AdventureWorks-heavy tests.
- Quality profile can mask AI/discovery weakness by synthesizing the required demo metrics.
- Missing-FK, ugly ERP naming, bridge/many-to-many, multiple business dates, multiple amount columns, and view-business-logic scenarios are not proven.
- Compiler-facing contract for status scope, filterability, and allocation/no-allocation is not yet validated end to end.

Backlog, not compiler blocker:

- Better AI prompt tuning for labels and annotations.
- Background semantic generation jobs.
- More polished UI for audit/provenance display.
- North Star triangulation and result validation beyond foundation CRUD.

## 2. Current Architecture

Current flow:

```text
Technical Snapshot
-> Queryability Graph
-> Semantic Discovery Input
-> AI candidates / deterministic seed
-> Canonical Builder
-> Semantic Layer specs
-> Quality Gate
-> Active Semantic Layer version
-> Query Intent Resolver
-> future Query Compiler
```

Main files and responsibilities:

| Area | Current source |
| --- | --- |
| Semantic contracts | `services/query-engine/app/models.py`, `packages/contracts/src/index.ts` |
| Seed, validation, hash, review, rebase | `services/query-engine/app/semantic.py` |
| AI discovery input, provider adapters, canonical compilation, quality profile synthesis | `services/query-engine/app/semantic_discovery.py` |
| API endpoints | `services/query-engine/app/main.py` |
| Web lifecycle/persistence service | `apps/web/lib/semantic-layer/service.ts` |
| Web presentation/outcome messages | `apps/web/lib/semantic-layer/presentation.ts`, `apps/web/lib/semantic-layer/generation-outcome.ts` |
| Persistence and lifecycle | `supabase/migrations/20260614172852_semantic_layer_v1_lifecycle.sql`, `supabase/migrations/20260620020000_semantic_canonical_quality_gate.sql` |
| North Star foundation | `supabase/migrations/20260615223915_north_star_benchmarks.sql`, `apps/web/lib/north-star-benchmarks/service.ts` |

Important functions and classes:

| Function/class | Purpose |
| --- | --- |
| `build_semantic_seed` | Converts Queryability Graph into seed, preserving graph authority. |
| `validate_semantic_layer` | Main deterministic validator and quality gate entrypoint. |
| `_validate_metric` | Per-metric structural, grain, date, edge, dimension, currency validation. |
| `_evaluate_quality_gate` | Required specs, eligible counts, activation requirements. |
| `_apply_metric_eligibility` | Computes compiler eligibility and reasons. |
| `build_semantic_discovery_input` | Allowlisted input for AI discovery. |
| `generate_semantic_layer` | Provider call, fallback, compile, validate, provenance. |
| `compile_semantic_proposal` | Canonical builder from AI proposals and quality specs. |
| `_compile_metric` / `_synthesize_metric` | Build metrics from AI candidate or quality profile. |
| `_derive_default_date` | Derives default date, including parent date for detail metrics. |
| `_derive_common_dimensions` | Builds common dimensions and safety. |
| `_resolved_ai_ambiguity` | Normalizes policy/graph-resolved AI ambiguities. |

Hash/freshness:

- `compute_metric_definition_hash`, `compute_semantic_hash`, and `compute_semantic_policy_hash` are in `semantic.py`.
- `SemanticLayer` carries `base_graph_hash`, `base_policy_hash`, and `semantic_policy_snapshot`.
- DB effective freshness checks graph hash and policy hash through `semantic_layer_effective_freshness`.
- Web summary also computes `effective_freshness` against current graph/policy.

Activation:

- `validate_semantic_layer` sets validation report and quality report.
- DB activation is gated by `enforce_semantic_activation_quality`.
- Web auto-activation uses `activation_policy=auto_validated` but still routes through DB RPC activation.

Eligibility:

- Initial generated metrics are compiled with `not_eligible`.
- Validator applies eligibility:
  - human verified valid -> `eligible`;
  - quality profile valid -> `eligible_with_disclosure`;
  - AI proposed valid/high -> `eligible_with_disclosure`;
  - material ambiguity -> `clarification_required`;
  - blocking technical issue -> `not_eligible`.

## 3. Current Semantic Layer Contents

| Area | State | Notes |
| --- | --- | --- |
| Business concepts | Implemented | Concepts have stable UUID keys, canonical names, display names, synonyms, provenance, optional default metric. |
| Metric specs | Implemented | Metrics include canonical name, opaque key, definition hash, source, aggregation, measure, grain, date, dimensions, filters, format, confidence, eligibility, provenance. |
| Metric variants | Implemented | Variants are explicit and linked to concepts. AdventureWorks has `net_header`, `document_total`, `line_detail`, `line_quantity`, `header_count`, `order_customers`, `customer_master`. |
| Display names | Implemented but profile-dependent | Required metrics normalize display names from quality specs. AI labels can still be noisy outside profile coverage. |
| Formulas | Implemented as structured aggregation + measure | No raw SQL in contract. |
| Source columns | Implemented | Stable column keys, validated against Semantic Layer and Graph. |
| Grain | Implemented | Required, validated against graph candidate keys. |
| Date columns | Partial | Default date keys exist and are validated, including parent date path. General multiple-date business semantics are not proven beyond tests. |
| Required edge paths | Implemented | Stored as stable edge keys, validated for automatic/trusted path. |
| Dimension compatibility | Implemented but narrow | Common dimensions with `safe/forbidden`; strong for AdventureWorks product/category, not proven on bridge/multiple hierarchy schemas. |
| Filters | Contract implemented, generation limited | Structured filters exist in metric contract, but AI candidate filters are out of candidate contract and compiler filter semantics are not mature. |
| Currency | Implemented | Comes from policy. Missing currency can become clarification/blocking by policy. |
| Warnings | Implemented | Validation warnings, quality issues, metric warnings, ambiguity severity. |
| Ambiguities | Implemented | Material/minor/info, open/resolved, provenance. Needs anti-demo coverage for ERP ambiguity cases. |
| Validation state | Implemented | `not_validated`, `valid`, `valid_with_warnings`, `blocked`. |
| Quality gate state | Implemented | `not_evaluated`, `passed`, `blocked`. |
| North Star links | Partial by design | North Star persistence and CRUD exist, linked by metric key; no triangulation/result validator yet. |

## 4. AdventureWorks Dependency Analysis

What works because AdventureWorksLT is clean:

- Header/detail names are obvious: `SalesOrderHeader`, `SalesOrderDetail`.
- Amount columns are semantically readable: `SubTotal`, `TotalDue`, `LineTotal`, `TaxAmt`, `Freight`.
- Product/category path is explicit and simple.
- Customer/order/customer master split is visible.
- `OrderDate` is a clear business date.

What works because FK are explicit:

- Detail -> header date derivation.
- Detail -> product -> category dimension path.
- Header/customer parent paths.
- Required edge paths and common dimension safety.

What works because the AdventureWorks quality profile exists:

- Required metric specs guarantee key metrics:
  - net revenue: `SUM(SalesOrderHeader.SubTotal)`;
  - document total: `SUM(SalesOrderHeader.TotalDue)`;
  - line revenue: `SUM(SalesOrderDetail.LineTotal)`;
  - quantity sold: `SUM(SalesOrderDetail.OrderQty)`;
  - order count: `COUNT(SalesOrderHeader.SalesOrderID)`;
  - order customers: `COUNT_DISTINCT(SalesOrderHeader.CustomerID)`;
  - customer master: `COUNT(Customer.CustomerID)`.
- Bad AI candidates can be rejected while profile synthesis creates correct metrics.
- Display names for required metrics are normalized from quality specs.
- Revenue variant ambiguity is resolved by policy.

What likely still works if physical names change:

- Stable key integrity, queryability preservation, sensitivity inheritance, hash validation, provenance, and DB lifecycle.
- Existing quality profile specs still work only if rewritten with the new stable keys.
- Generic discovery without profile is not proven on ugly names.

What likely fails or becomes weak if FK are missing:

- No trusted join paths should be invented. That is good for safety but means no detail/header dimension/date enrichment.
- Metrics needing parent dates or product/category dimensions should become blocked or clarification rather than compiler-ready.
- Semantic generation may produce fewer useful metrics without profile specs.

Multiple candidate tables:

- Customer master vs order customers is modeled for AdventureWorks.
- Supplier/customer mixed party tables, duplicated customer tables, or ERP account master tables are not covered.

Views:

- Queryability Graph treats lineage as provenance, not join evidence.
- Semantic Layer can include view nodes/columns, but business logic inside views is not parsed into trusted semantic formulas.
- Compiler readiness for view-heavy schemas is not proven.

## 5. Quality Profile / Required Specs Risk

Quality profile role:

- It defines required concepts, preferred variants, required metric specs, default currency, activation policy, minimum eligible metrics, and dimension expectations.
- It can synthesize required metrics when AI omits or misidentifies them.
- It can reject AI candidates as mismatches without blocking the layer if synthesis satisfies the profile.

Metrics guaranteed by AdventureWorks profile:

| Spec | Calculation | Activation relevance |
| --- | --- | --- |
| `adventureworks.revenue.net_header` | `SUM(SubTotal)` | required |
| `adventureworks.revenue.document_total` | `SUM(TotalDue)` | required |
| `adventureworks.revenue.line_detail` | `SUM(LineTotal)` | profile variant |
| `adventureworks.quantity_sold.line_quantity` | `SUM(OrderQty)` | required |
| `adventureworks.orders.header_count` | `COUNT(SalesOrderID)` | required |
| `adventureworks.customers.order_customers` | `COUNT_DISTINCT(SalesOrderHeader.CustomerID)` | allowed eligible/clarification |
| `adventureworks.customers.customer_master` | `COUNT(Customer.CustomerID)` | allowed eligible/clarification |

Risk assessment:

- The profile absolutely improves demo reliability.
- It is useful and necessary for eval/enterprise overrides.
- It also hides whether generic semantic discovery can find the same metrics from metadata alone.
- Current tests prove profile synthesis and AI candidate rejection. They do not prove profile-free onboarding quality.

Without profile:

- The generic policy still allows concepts and variants, but no stable-key required specs force exact source columns, names, dates, or dimensions.
- Expected result: fewer guaranteed metrics, more reliance on AI candidate quality, more ambiguity, no strict AdventureWorks acceptance.
- Recommended test: generate AdventureWorks with `required_metric_specs=[]`, AI fake/offline and AI advisory, then compare metrics, eligibility, ambiguities, and activation.

Profile is not silent:

- Profile-synthesized metrics carry `provenance=system`, `provenance_detail=quality_profile`, `source_spec_key`, and reasoning summary.
- Rejected candidates are stored in `quality_report.rejected_candidates`.
- DB projects provenance detail into `semantic_layer_metrics`.

## 6. Metric Generation Robustness

| Area | Current state | Risk | Needed before compiler |
| --- | --- | --- | --- |
| Revenue header metric | Good for AdventureWorks via profile and validation | High outside profile | Anti-demo multiple amount tests |
| Document total | Good for AdventureWorks | Medium | Ensure total due/gross/document total naming across ERP schemas |
| Line revenue | Good for AdventureWorks | Medium-high | Test line amount, discount, tax included/excluded variants |
| Quantity | Good for AdventureWorks | Medium | Test returns/negative quantities/uom |
| Orders | Good for AdventureWorks | Medium | Status/cancelled scope test |
| Customers in master | Good for AdventureWorks | High | Mixed party/customer-supplier fixture |
| Customers with orders | Good for AdventureWorks | Medium | More schemas with invoices/orders/shipments |
| Average/ratio/calculated metrics | Mostly out of scope | Medium | Keep compiler blocked until explicit derived metric support |
| Duplicate candidate metrics | Partially handled | Medium | More anti-demo candidate collision tests |
| Multiple amount columns | Partially handled by profile | High | PMI amount fixture: imponibile/totale/iva/sconto/trasporto |
| Negative quantities/returns | Missing | High | Returns fixture and disclosure/status policy |
| Taxes/discount/freight | Partially handled by prompt/profile | High | Test distinct variants and no accidental revenue default |
| Status/cancelled/voided | Warning/disclosure in resolver, not fully semantic | High | Status scope policy in Semantic Layer |
| Currency | Implemented by policy | Medium | Multi-currency DB tests |
| Date selection | Good for AdventureWorks | High | Multiple business date fixture |

## 7. Grain and Dimension Compatibility

Current behavior:

- Grain is required for every metric.
- `_derive_grain_column_keys` uses graph candidate keys.
- Validator rejects metric grain missing or not matching eligible graph candidate key.
- Header/detail safety is enforced through dimension compatibility and required join path evaluation.
- `evaluate_dimension_compatibility` computes safe/forbidden dimension paths using graph edges.
- Header metric + product/category detail dimension is forbidden in AdventureWorks tests.
- Detail metric + parent date and product/category dimensions are safe in AdventureWorks tests.

Where compatibility lives:

- Graph owns technical relationships and cardinality evidence.
- Semantic Layer stores metric grain, required joins, and common dimension compatibility.
- Resolver consumes semantic metric/dimension compatibility and has its own guards.
- Compiler does not exist yet.

Concern:

- There is no single compiler-facing Semantic Layer invariant validator yet.
- Some safety is validated in Semantic Layer, some in Resolver, some in Graph helpers. That is acceptable before compiler, but dangerous for SQL generation unless centralized.
- Required edge keys are validated as trusted/enabled/automatic, but compiler must still check path direction, join ordering, fanout, and no bridge/m2m unless policy exists.

Answer:

- The Semantic Layer contains enough information for simple AdventureWorks-safe plans.
- The compiler should not blindly trust `required_join_edge_keys` yet.
- A compiler-facing gate must re-check metric grain, edge paths, graph validation status, dimension compatibility, filter safety, and allocation absence.

## 8. Date Semantics

AdventureWorks:

- `OrderDate` is selected because profile specs and derivation identify it as a reachable business event date.
- Detail metrics use `SalesOrderHeader.OrderDate` through trusted detail -> header FK.
- Tests assert detail metrics do not use `ModifiedDate` when a parent business date exists.

General behavior:

- AI prompt instructs not to choose audit dates if business event dates exist.
- Server derives date and treats audit dates as fallback candidates.
- Graph hardening now flags multiple date columns as requiring semantic selection, but Graph does not choose business dates.

Risks:

- Multiple plausible dates such as document date, posting date, invoice date, due date, shipment date are not proven.
- Semantic Layer could theoretically become active with a technically valid date that is semantically wrong if profile/policy does not constrain it and validator sees no technical violation.
- Audit date default is guarded by prompt/tests for known cases, but anti-demo coverage is still insufficient.

Needed before compiler:

- Semantic invariant: eligible metric with audit date default requires warning/disclosure and cannot be silently compiler-ready when other event dates exist.
- Anti-demo multiple-date fixture.

## 9. Ambiguity Handling

| Ambiguity | Current handling |
| --- | --- |
| Customer population | System ambiguity exists; generic `customers` remains clarification in Resolver; specific variants can be eligible. |
| Order status scope | Mostly disclosure/warning; all statuses default in Resolver unless policy says clarification. Semantic status scope remains under-specified. |
| Date ambiguity | Policy/graph-resolved date ambiguity can be resolved/info; multiple date anti-demo not proven. |
| Amount ambiguity | Revenue variants resolved by AdventureWorks profile. Generic multiple amount ambiguity not proven. |
| Revenue net/gross/document/line | Strong in AdventureWorks profile; weak generically. |
| Product/category ambiguity | Strong for AdventureWorks product/category path; bridge/multiple hierarchy not proven. |
| Multiple paths | Semantic discovery has test for multiple shortest safe paths becoming material metric ambiguity. |
| Multiple schemas | Contract supports schema names; semantic anti-demo not proven. |
| Duplicate concepts | Some duplicate proposal handling exists; real ERP duplicate concept fixtures missing. |

Ambiguity states:

- `resolved deterministically`: policy-resolved revenue variants, graph-resolved detail date.
- `exposed as warning/info`: minor/status/disclosure ambiguities.
- `clarification_required`: customer population, multiple shortest safe paths for affected metric.
- `hidden/ignored`: no evidence of intentional hidden critical ambiguities, but missing test coverage makes this unknown for ERP-style schemas.

## 10. Validator and Quality Gate

| Check | State |
| --- | --- |
| Metric without grain | blocking validation / contract |
| Metric without source column | blocking for aggregations requiring measure; count can have null measure |
| Source column not queryable | blocking |
| Sensitive source column | blocking through semantic column usability |
| Missing date when needed | partial; date is optional in contract, semantics depend on metric/use |
| Invalid FK path | blocking |
| Untrusted/disabled edge | blocking |
| View lineage as join | blocking indirectly because only automatic trusted FK edges are accepted |
| Duplicate metric | blocking/warning depending collision type; quality issues exist |
| Unsafe dimension compatibility | blocking when declared safe but computed forbidden |
| Stale graph/policy | validation and DB activation gate check freshness |
| Invented AI stable keys | rejected as quality candidate issue |
| Raw SQL | absent from contracts; AI prompt forbids; structured schema rejects unknown fields |
| Activation with critical warnings | DB activation blocks quality_report blocked, stale, unsatisfied specs, insufficient eligible metrics |

Quality gate is meaningful but profile-centered. It checks required specs and minimum eligible metrics. Without required specs, it is much less demanding.

## 11. AI Candidate Safety

AI can propose:

- table/column annotations;
- business concept labels/synonyms;
- metric candidates with allowlisted concept refs, source table key, measure column key, aggregation, default date candidate, format, synonyms, reasoning, ambiguity notes.

AI cannot authoritatively propose:

- UUIDs;
- hashes;
- status;
- provenance;
- sensitivity;
- queryability;
- compiler eligibility;
- dimension safety;
- raw SQL;
- join paths;
- grain.

Safety controls:

- Pydantic and Zod strict schemas reject server-owned fields and unknown payload shape.
- `_validate_proposal_references` rejects invented/disallowed refs.
- `compile_semantic_proposal` rejects mismatched required metric candidates and synthesizes missing specs.
- Rejected candidates are audit-visible.
- Provider errors can fallback to quality profile for required specs, except rate-limit/model-unavailable cases depending error class.

Need:

- A Semantic Layer AI adversarial suite similar to Query Intent AI advisory:
  - invented stable key;
  - unsafe header metric + detail dimension;
  - wrong revenue default;
  - audit date default;
  - sensitive column;
  - duplicate concepts;
  - ambiguous multiple paths.

## 12. Relationship With Queryability Graph

Current consumption:

- Semantic discovery input includes stable keys, queryability, sensitivity, candidate keys, trusted paths, and lineage status.
- It includes trusted FK edges and explicitly excludes lineage as join evidence.
- Validator checks semantic relationships against graph enabled/trusted/automatic FK conditions.
- Metric validation checks graph node candidate keys for grain.
- Dimension compatibility uses graph edge paths and bridge/fanout traits.
- Graph blocked status prevents seed/discovery.

Current gaps:

- The new Queryability Graph invariant validator exists, but Semantic Layer generation does not currently require a valid graph validation report as input.
- Bridge/m2m warnings from graph validation do not automatically fail Semantic Layer generation unless the semantic path itself crosses bridge/fanout and validator sees it.
- Multiple dates produce graph diagnostics, but Semantic Layer still owns business date choice.
- Missing FK correctly prevents trusted paths, but no anti-demo semantic tests show the resulting behavior.

## 13. Relationship With Resolver

Resolver assumes from Semantic Layer:

- active/fresh/validated artifact;
- metric eligibility;
- concept and variant;
- display name and structured formula;
- default date key;
- common dimension compatibility;
- required edge paths;
- disclosures and ambiguity metadata;
- stable source/dimension/filter keys.

Robust assumptions:

- Active/fresh validation is enforced by contracts and tests.
- `not_eligible` metrics are blocked by Resolver tests.
- Header metric grouped by product/category is avoided by resolver tests.
- Customer generic ambiguity is handled.

Demo-specific assumptions:

- Revenue variants and labels come from AdventureWorks quality specs.
- Product/category mapping is specific to the AdventureWorks semantic artifact.
- Status scope is mostly resolver policy/disclosure, not deeply semantic.
- Filterability is still light and not fully semantic-policy driven.

## 14. Requirements Before Query Compiler

| Compiler requirement | State |
| --- | --- |
| selected metric physical source | available |
| aggregation type | available |
| source column key | available |
| source table grain | available |
| default date key | partial |
| required joins | partial |
| compatible dimensions | partial |
| filterable columns | missing/partial |
| semantic disclosures | available |
| status scope | partial |
| currency | available for policy default; partial for multi-currency |
| no allocation unless explicit | partial |
| no calculated metrics unless compiled explicitly | available by absence/out-of-scope, needs compiler gate |
| no inactive/not_eligible metrics | available |
| graph validation status consumed by semantic/compiler gate | missing |
| bridge/m2m explicit policy | missing |
| anti-demo semantic proof | missing |

## 15. Overfitting Risk Assessment

| Area | Risk | Notes |
| --- | --- | --- |
| Metric discovery | high | Profile can synthesize demo metrics. |
| Grain detection | medium | Candidate-key based and sound, but missing-FK/table-without-PK behavior needs semantic tests. |
| Date selection | high | AdventureWorks `OrderDate` is easy; ERP multiple dates are not proven. |
| Amount selection | high | `SubTotal/TotalDue/LineTotal` are clean and profile-backed. |
| Customer population | medium-high | AdventureWorks has clear Customer and SalesOrderHeader.CustomerID. |
| Product/category dimensions | medium-high | Simple hierarchy and FK path. |
| Status/cancelled logic | high | Not deeply modeled in Semantic Layer. |
| Missing FK schemas | high | Safe fail-closed but usefulness drops; no semantic anti-demo. |
| Ugly ERP naming | high | No semantic fixture proves `DOTES/DORIG/ANACLI/...`. |
| Views | high | Lineage is safe as provenance but business semantics in views are not parsed. |
| Multiple schemas | medium-high | Contract supports; behavior not proven. |
| Duplicate concepts | medium-high | Some duplicate handling, not enough real-schema coverage. |
| Quality profile dependence | high | Central to AdventureWorks success. |
| AI fallback dependence | medium | Fallback can produce demo metrics if profile complete; generic case weaker. |
| Currency | medium | Policy-based default works, multi-currency not proven. |

## 16. Suggested Anti-Demo Tests

| Test | Input schema shape | Expected Semantic Layer behavior | Activate? | Expected warnings/ambiguities | Downstream impact |
| --- | --- | --- | --- | --- | --- |
| AdventureWorks profile disabled | Same graph, `required_metric_specs=[]` | Metrics only if AI/deterministic proposal finds them | likely no/depends | Missing required concepts/low eligible count | Exposes quality profile dependency |
| AdventureWorks AI disabled seed only | Seed without AI proposal | No business metrics unless quality profile fallback allowed | only if profile synthesis allowed | AI_PROVIDER_FALLBACK_USED if provider failure path | Shows synthesis vs discovery |
| Ugly PMI schema | `DOTES`, `DORIG`, `ANACLI`, `ARTICO`, `CATART` with explicit FK | No invented meaning; concepts/metrics only with policy or AI evidence | no unless specs configured | Missing/ambiguous business concepts | Prevent demo overfitting |
| Missing FK header/detail | Header/detail columns but no FK | No trusted paths, no detail parent date | no | Missing FK/path ambiguity | Avoid unsafe joins |
| Multiple amount columns | imponibile, totale, iva, sconto, trasporto | Distinct variants or clarification | no until resolved | Amount/revenue ambiguity | Avoid wrong revenue SQL |
| Multiple dates | data_documento, data_registrazione, data_modifica | No audit-date default; require semantic selection | maybe no | Date ambiguity | Avoid wrong time filters |
| Returns/negative quantities | lines with qty sign/return status | Disclosure/clarification for sales vs returns | no until policy | Return/status scope | Avoid inflated revenue/quantity |
| Status/cancelled/voided | order status and cancel flags | All-status disclosure or clarification policy | maybe | Status scope ambiguity | Avoid canceled orders in metrics |
| Mixed party table | one table for customers/suppliers/vendors | customer concept clarification | no until resolved | Party role ambiguity | Avoid wrong population |
| Product/category bridge | multiple hierarchies/bridge table | Bridge path forbidden unless policy | no | Bridge/m2m ambiguity | Avoid fanout |
| Sensitive/PII columns | email, phone, tax code, IBAN | PII never eligible dimension/filter without policy | maybe | Privacy diagnostic | Avoid privacy leak |
| Views with business logic | sales view with computed totals | View columns can be annotated, lineage not joins | no unless base semantics clear | View logic opaque | Avoid hidden formulas |
| Table without PK | fact-like table no key | Metrics not eligible without explicit grain | no | Grain ambiguity | Avoid duplicate aggregation |
| Composite keys | header/detail composite PK/FK | Preserve grain/path if trusted | yes if unambiguous | none/warning | Ensure compiler join condition correct |
| Duplicate semantic concepts | orders/invoices/documents tables | Clarify or distinct concepts | no until resolved | Duplicate concept ambiguity | Avoid wrong metric selection |

## 17. Semantic Layer Invariant Validator Proposal

Add `validate_semantic_layer_invariants(layer, graph, graph_validation_report, policy)` before compiler work.

Minimum invariants:

- no active/compiler-ready layer if graph stale or graph validation invalid;
- no active/compiler-ready layer if quality gate blocked;
- every metric has valid source table and source/measure columns;
- every metric has explicit grain matching candidate key or explicit grain policy;
- every eligible metric has compatible date strategy or explicit no-date policy;
- no eligible metric uses sensitive/excluded source;
- no eligible metric uses untrusted/disabled/unverified edge;
- no lineage edge can appear in metric path;
- no header metric compatible with detail/product/category dimension unless allocation strategy exists;
- no line/detail metric needing time without trusted parent/local business date;
- no AI-invented key accepted;
- no duplicate concept/variant/source metric unless explicitly versioned;
- no business date defaults to audit date without warning/disclosure;
- status/cancelled ambiguity recorded for order/document metrics;
- customer population ambiguity recorded or resolved by specific variant;
- currency explicit, policy-sourced, or clearly clarification-required;
- profile-synthesized metrics have `provenance=system`, `provenance_detail=quality_profile`, `source_spec_key`;
- quality profile requirements cannot be the only reason to mark a generic onboarding layer compiler-ready unless profile type is demo/eval/enterprise override.

## 18. Recommended Next Step

Recommendation: **Proceed only after specific blockers are fixed**.

| Blocker | Why it blocks compiler | Affected layer | Suggested PR/task | Effort | Risk if ignored |
| --- | --- | --- | --- | --- | --- |
| No Semantic Layer invariant validator | Compiler needs a single gate that re-checks semantic + graph + policy safety before SQL | Semantic Layer / Compiler gate | Add `validate_semantic_layer_invariants` and tests | M | Compiler may trust an artifact that passed demo validation but is unsafe for SQL |
| No semantic anti-demo fixture suite | AdventureWorks success is not enough evidence for ERP schemas | Semantic Discovery / Validator | Add anti-demo semantic fixtures listed above | M/L | Wrong metrics look valid because demo profile hid discovery gaps |
| Quality profile dependency not quantified by tests | Required specs can synthesize correctness and mask AI/generic discovery weakness | Semantic Discovery / Quality Gate | Add profile-disabled and AI-disabled evals | M | Onboarding real customers may produce empty/noisy semantic layers |
| Date semantics under-tested | Compiler time filters depend on correct business date | Semantic Layer / Compiler | Add multiple-date and audit-date invariant tests | M | SQL filters by ModifiedDate/PostingDate when user means document date |
| Status/cancelled scope under-modeled | Revenue/order metrics often require inclusion/exclusion policy | Semantic Layer / Resolver / Compiler | Add status scope policy and fixture tests | M | Metrics include canceled/voided documents silently |
| Missing FK and view-heavy schemas not semantically tested | Compiler cannot invent joins and views hide logic | Graph/Semantic boundary | Add missing-FK and view-business-logic semantic tests | M | Either unsafe joins or unusable layers in real PMI DBs |
| Filterability/privacy not semantically gated enough | Compiler will support filters and dimensions over columns | Semantic Layer / Compiler | Add semantic filterability policy and PII invariant tests | M | PII or unsupported filters leak into generated SQL |

Suggested PR sequence:

1. Semantic Layer invariant validator and reportable diagnostics. Effort M.
2. Semantic anti-demo fixtures: profile-disabled, ugly PMI, missing FK, multiple amount/date/status. Effort M/L.
3. Profile dependency eval: AdventureWorks with/without quality specs, with AI disabled/fake/adversarial. Effort M.
4. Compiler-facing preflight gate consuming Graph validation + Semantic invariants + Query Intent plan. Effort M.
5. Only then start Query Compiler V1 for a narrow scope.

## 19. Evidence Matrix

| Claim | Evidence source | Confidence | Notes |
| --- | --- | --- | --- |
| Audit includes PR #54 Queryability Graph hardening as active code | Git: `origin/main` at `6930840`, contains `bca48d1` | high | Verified with `git merge-base --is-ancestor bca48d1 origin/main`. |
| AI is instructed not to write SQL or invent joins | `services/query-engine/app/semantic_discovery.py`, `SEMANTIC_DISCOVERY_SYSTEM_PROMPT` | high | Prompt is not sufficient alone, but structured contracts add enforcement. |
| AI candidate contract rejects server-owned fields | `tests/test_semantic_discovery.py::test_ai_contract_rejects_server_owned_fields`, models strict schemas | high | Direct test. |
| AI stable key invention is rejected/audited | `compile_semantic_proposal`, `_validate_proposal_references`, `tests/test_semantic_discovery.py::test_proposal_rejects_disallowed_columns_unknown_edges_and_duplicates` | high | Direct tests for disallowed refs and rejected candidates. |
| Quality profile can synthesize required metrics | `_synthesize_metric`, `generate_semantic_layer`, `tests/test_semantic_discovery.py::test_provider_failure_uses_quality_profile_fallback_for_required_specs` | high | Direct test. |
| Quality profile can reject wrong AI candidate and synthesize correct metric | `tests/test_semantic_discovery.py::test_quality_profile_rejects_bad_ai_candidate_and_synthesizes_metric` | high | Direct test. |
| Profile-synthesized metrics are auditable | `SemanticMetric.validate_metric_provenance`, migration `semantic_layer_metrics_provenance_audit_check`, related tests | high | Contract + DB constraints. |
| Currency comes from policy, not AI | `_compile_metric`, `_synthesize_metric`, `SemanticPolicySnapshot.default_currency`, `tests/test_semantic_builder.py::semantic_policy` | high | Direct code path. |
| Header metric + detail/product dimension is forbidden | `evaluate_dimension_compatibility`, `_validate_dimension_compatibility`, `tests/test_semantic_builder.py::test_header_metric_cannot_claim_detail_dimension_is_safe`, `tests/test_semantic_discovery.py::test_server_computes_dimension_safety_and_blocks_header_detail_fanout` | high | Direct tests. |
| Detail metric can use parent business date via trusted FK | `_derive_default_date`, `tests/test_semantic_discovery.py::test_intent_readiness_uses_safe_metric_variants_and_business_dates` | high | Direct AdventureWorks test. |
| Multiple shortest safe paths become material ambiguity | `_unique_shortest_safe_path`, `tests/test_semantic_discovery.py::test_multiple_shortest_safe_paths_become_material_metric_ambiguity` | high | Direct test. |
| Active semantic layer requires quality gate and policy freshness at DB level | `supabase/migrations/20260620020000_semantic_canonical_quality_gate.sql`, `enforce_semantic_activation_quality`, `semantic_layer_effective_freshness` | high | Migration-level enforcement. |
| North Star is separate from metric definition | `north_star_benchmarks` migration/service, Semantic Layer metric contract has no benchmark value | high | Persistence separation. No triangulation yet. |
| Semantic Layer is ready for Resolver V1 | Query Intent tests and suite tests; `tests/test_query_intent.py`, `tests/test_query_intent_suite.py` | high | Automated tests pass. |
| Semantic Layer is not ready for Compiler V1 | Absence of compiler-facing semantic invariant validator and anti-demo fixtures | medium | Inference from code/test gaps. |
| Quality profile dependency is high | Required AdventureWorks specs in `adventureworks_quality_policy`, synthesis tests, fallback behavior | high | Direct evidence. |
| Generic ugly ERP onboarding is not proven | No semantic tests for `DOTES/DORIG/ANACLI/...` | high | Negative evidence from test inventory. |
| Missing-FK semantic behavior is not proven | Graph has tests, Semantic Layer anti-demo missing | high | Negative evidence from tests. |
| Status/cancelled scope is under-modeled | Resolver disclosure exists; no Semantic Layer status-scope invariant fixture | medium | Inference from tests and contract. |

## 20. Verification Results

Commands run on `codex/semantic-layer-state-of-art`:

```text
services/query-engine/.venv/Scripts/python.exe -m pytest tests/test_queryability.py -q
20 passed in 9.22s

services/query-engine/.venv/Scripts/python.exe -m pytest tests/test_query_intent.py -q
22 passed in 9.24s

services/query-engine/.venv/Scripts/python.exe -m pytest tests/test_semantic*.py -q
failed: pytest did not expand the wildcard and reported "file or directory not found"

Explicit semantic files executed:
- tests/test_semantic_api.py
- tests/test_semantic_builder.py
- tests/test_semantic_contracts.py
- tests/test_semantic_discovery.py
- tests/test_semantic_lifecycle.py

services/query-engine/.venv/Scripts/python.exe -m pytest tests/test_semantic_api.py tests/test_semantic_builder.py tests/test_semantic_contracts.py tests/test_semantic_discovery.py tests/test_semantic_lifecycle.py -q
96 passed in 15.99s

services/query-engine/.venv/Scripts/python.exe -m pytest -q
221 passed, 1 skipped in 26.20s

CI=true pnpm --filter @atlantebi/web test
67 passed across 19 test files

CI=true pnpm --filter @atlantebi/web typecheck
passed

CI=true pnpm lint
passed
```

