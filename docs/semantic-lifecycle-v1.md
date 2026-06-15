# Semantic Lifecycle V1

## Scope

Milestone 3C.3 introduces the canonical persistence and lifecycle for
`semantic_layer.v1`.

It includes:

- immutable versioned artifacts;
- optimistic concurrency for draft/proposed updates;
- deterministic freshness against the current Queryability Graph;
- stable-key-only rebase;
- atomic activation and archival;
- tenant-scoped RPCs, RLS and audit records.

API routes and the AI-first workspace are Milestone 3C.4.

## Breaking Change

The previous `semantic_*` schema was a technical import projection and is not
compatible with `semantic_layer.v1`. It used physical names and allowed free
SQL metric expressions.

The lifecycle migration therefore:

- purges the empty demo semantic domain;
- replaces legacy child tables with `semantic_layer_*` projections;
- preserves application foreign keys to the renamed semantic version registry;
- removes direct authenticated and service-role DML;
- exposes mutations only through controlled lifecycle RPCs.

There is no legacy artifact conversion or name-based fallback.

The production project was checked before implementation: the legacy semantic
tables, related widgets and related query-history references contained zero
rows.

## Lifecycle Invariants

- A connection has at most one active semantic version.
- Active and archived versions are immutable.
- A draft update requires the current revision.
- Activation requires a fresh proposed artifact with a successful validation
  report for the same revision.
- Effective freshness compares `base_graph_hash` with the current
  Queryability Graph derivation.
- New draft/proposed artifacts can only be persisted against that current
  derivation; an obsolete graph cannot be declared `fresh`.
- Rebase carries data only through exact graph stable keys.
- Rebase accepts only successfully validated active/archived sources and always
  creates a newer semantic version.
- Graph identity and rebase provenance cannot be changed by later draft edits.
- A removed or unsafe dependency drops the affected metric instead of guessing.
