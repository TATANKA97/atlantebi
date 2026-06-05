# Security Notes

## SQL Server Read-Only Metadata Permissions

Atlante BI stores only technical metadata for customer databases. It does not store raw
customer rows or query result caches.

For a SQL Server schema used by Atlante BI, the minimum data permission is:

```sql
GRANT SELECT ON SCHEMA::[SalesLT] TO [atlante_bi_ro];
```

For complete technical schema coverage, the recommended metadata permission is:

```sql
GRANT VIEW DEFINITION ON SCHEMA::[SalesLT] TO [atlante_bi_ro];
```

Without `VIEW DEFINITION`, SQL Server can hide or return partial metadata depending on
metadata visibility rules. The snapshot remains best-effort, but coverage is weaker:

- view definitions may be unavailable;
- view lineage from `sys.dm_sql_referenced_entities` may be partial or unavailable;
- computed column definitions may be unavailable;
- default and check constraint definitions may be unavailable;
- coverage warnings will indicate partial metadata visibility.

View definitions and extended properties are treated as tenant-scoped sensitive
metadata. They are saved in `schema_snapshots.snapshot` for deterministic technical
coverage, but they must not be logged in clear text or sent to AI workflows by default.

## Application Metadata Boundaries

- Authenticated users can read only explicit safe columns from `schema_snapshots`;
  the full `snapshot` JSON is server-only.
- Connection and technical snapshot writes run through RPCs executable only by the
  Supabase `service_role`. The RPCs independently verify the actor membership and role.
- Changing a connection host, port, database, username, or TLS server name requires a
  new database password. An existing `secret_ref` is never rebound to a new endpoint.
- Technical imports are one PostgreSQL transaction protected by a per-connection
  advisory lock. Snapshot, version, tables, columns, relationships, and audit metadata
  either all commit or all roll back.
- Query-engine endpoints fail closed unless either an internal token is configured or
  Cloud Run IAM mode is explicitly enabled.
