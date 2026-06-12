# SQL Server Technical Snapshot V1

## Breaking change

Technical Snapshot V1 does not support schema imports created before this
milestone. `coverage_state` is removed and replaced by the required
`coverage_status` field:

```text
ok | partial | warning | blocked
```

Old snapshots and semantic drafts must be purged and reimported. There is no
runtime fallback or compatibility adapter. `snapshot_hash` is required and the
database migration intentionally fails if legacy snapshot rows still exist.

## Demo rollout

Run the demo purge before applying the breaking database migration:

```powershell
pnpm db:purge-demo-schema -- --tenant-id <tenant-uuid> --connection-id <connection-uuid> --confirm AdventureWorksLT
```

The command is restricted to demo/test environments, requires an explicit
tenant and connection, and verifies the expected database name. It removes
schema snapshots, semantic versions and their technical projections for that
connection. Demo widgets or query history linked to the removed versions are
also removed so the reimport starts from a coherent state.

After the migration and service deployment, import AdventureWorksLT again and
run:

```powershell
pnpm schema:audit:adventureworks
```

The audit is development-only. It compares the live SQL Server catalog with the
persisted snapshot and emits a sanitized JSON report.

## Expected demo baseline

```text
objects=13
tables=10
views=3
columns=129
foreign_keys=12
table_indexes=30
view_indexes=1
indexes_total=31
view_definitions=3/3
view_lineage=3/3
coverage_status=partial
```

The indexed view index
`SalesLT.vProductAndDescription.IX_vProductAndDescription` is part of the
technical snapshot.

## Downstream artifact

Technical Snapshot V1 is the only input for
[Queryability Graph V1](./queryability-graph-v1.md). The snapshot does not
create a Semantic Layer directly.

`schema_hash` now represents stable observable DDL only. The full technical
payload has a separate `snapshot_hash`; view-lineage coverage and technical
classifications can change `snapshot_hash` without changing `schema_hash`.
Permission-dependent declared-type visibility is also excluded from
`schema_hash` and retained in `snapshot_hash`.
