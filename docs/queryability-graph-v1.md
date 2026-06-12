# SQL Server Queryability Graph V1

## Boundary

```text
Technical Snapshot V1
-> Queryability Graph V1
-> Semantic Layer
-> Query Compiler
```

Snapshot and graph are deterministic technical metadata. The Semantic Layer is
absent after import and reports `not_initialized`.

## Hashes

- `schema_hash`: stable observable DDL. It excludes permissions-dependent
  declared-type visibility, lineage, warnings, row estimates and Atlante
  classifications.
- `snapshot_hash`: canonical full-fidelity technical snapshot.
- `graph_input_hash`: only metadata consumed by the graph builder, including FK
  trust/disabled state, nullability, eligible keys, object type, queryability,
  technical role and view-lineage coverage.
- `graph_hash`: canonical graph nodes and edges.
- `derivation_key`: hash of `graph_input_hash`, `builder_version` and
  `policy_version`.

The Semantic Layer will use `base_graph_hash` for freshness. `schema_hash` is
not sufficient because a builder or policy change can alter the graph without a
DDL change.

## Status

- `complete`: technical routing is fully usable.
- `partial`: routing is usable, but non-blocking metadata is incomplete.
- `blocked`: routing is unreliable. Snapshot and graph persistence roll back.

AdventureWorksLT is expected to be `partial` while
`VIEW_LINEAGE_PARTIAL` is present.

## Nodes And Edges

Nodes represent SQL Server tables and views. Candidate keys come from primary
keys, unique constraints, and enabled non-filtered unique indexes.
System objects are preserved as technical evidence but excluded from automatic
routing.

Edge types:

- `fk_join`: database FK evidence usable by the path engine when enabled and
  trusted.
- `view_depends_on`: object-level provenance only.
- `view_column_derives_from`: column-level provenance only.

Lineage edges never authorize joins. Indexed-view keys apply only to the view
node and are not propagated to source tables.

FK direction is canonical:

```text
child/referencing -> parent/referenced
```

An FK retains ordered column pairs, nullability, directional cardinality,
self-reference, enforcement state and validation state. Disabled and untrusted
FKs remain visible but are excluded from automatic paths.

`bridge_candidate` is a structural node trait, not a business classification.

## Path V1

- direct paths and paths up to four hops;
- bidirectional traversal over eligible FK edges;
- parallel shortest paths return `ambiguous`;
- no hidden lexical tie-break;
- parent-to-child expansion produces a basic fanout warning;
- self-reference is represented but excluded from ordinary routing.

Advanced many-to-many and compound fanout reasoning remain future policy work.

## Persistence

The atomic import RPC stores:

- `schema_snapshots`;
- `queryability_graph_versions` full JSONB;
- normalized nodes, columns and edges.

`complete` and `partial` graphs are persisted. `blocked` graphs are rejected.
The same derivation key and graph hash are deduplicated. Changed input, builder,
policy or output creates a new immutable graph version.

Manual rebuild reads an existing protected snapshot server-side. It reuses the
snapshot, deduplicates identical derivations, and creates a new immutable graph
version only when input, builder, policy or output changes.

The import does not write `semantic_versions`, `semantic_tables`,
`semantic_columns` or `semantic_relationships`.

Full graph payloads are server-controlled and are not directly granted to
authenticated browser clients.

Admin API:

- `GET /api/queryability/graphs/current`;
- `GET /api/queryability/graphs/:graphId`;
- `POST /api/queryability/rebuild`;
- `POST /api/queryability/paths`.
