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

Milestone 3C.4 adds the tenant-scoped API routes and AI-first workspace on top
of these lifecycle guarantees.

## Milestone 3C.4 API and Workspace

The web BFF exposes:

- `GET /api/semantic/current`;
- `GET /api/semantic/versions`;
- `GET /api/semantic/versions/:id`;
- `POST /api/semantic/drafts`;
- `PATCH /api/semantic/drafts/:id`;
- `POST /api/semantic/drafts/:id/generate-ai-draft`;
- `POST /api/semantic/drafts/:id/validate`;
- `POST /api/semantic/drafts/:id/activate`;
- `POST /api/semantic/drafts/:id/rebase`;
- `POST /api/semantic/versions/:id/archive`.

All mutations require an active owner/admin membership. The BFF uses the
service role only after tenant and role verification; browser clients never
receive it and cannot write semantic tables directly.

Semantic edits are not applied in Next.js. The query-engine receives the
current graph, canonical source artifact, and an allowlisted structured patch.
It applies the patch, advances the revision, recalculates metric and semantic
hashes, runs the deterministic validator, and returns the next canonical
artifact. Unknown stable keys and raw SQL are rejected.

AI generation is serialized per connection through a distributed operation
lease and rate-limited per tenant actor. Re-generating a proposed version
creates a new immutable version rather than overwriting reviewed work.

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
