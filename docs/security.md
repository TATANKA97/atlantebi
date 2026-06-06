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
- Connection tests and schema imports acquire server-only PostgreSQL leases with
  tenant, actor, concurrency, per-resource, and time-window limits. Rejected attempts
  do not reach the query-engine.
- Public database destinations are resolved before ODBC connection. Every resolved
  address must be globally routable, and the selected address is pinned for the
  connection to prevent DNS rebinding. Private destinations require both `vpn` mode
  and the explicit runtime opt-in `QUERY_ENGINE_ALLOW_PRIVATE_NETWORKS=true`.
  The V1 web application creates only `public_allowlist` connections; enabling VPN
  connections is a separate deployment decision and must include private egress.
- Database password secrets are bound to tenant, connection, and endpoint metadata
  through the secret name and labels. The query-engine validates that binding before
  reading the secret payload.
- The query-engine runtime uses a custom Secret Manager role containing only
  `secretmanager.secrets.get` and `secretmanager.versions.access`, conditionally
  restricted to `atlantebi-*` resources.

## Deployment Controls

- GitHub Actions dependencies are pinned to immutable commit SHAs.
- Production deploy workflows run only after the exact `main` SHA passes CI and then
  enter the protected `production` environment.
- The GitHub OIDC provider accepts only
  `repo:TATANKA97/atlantebi:environment:production`.
- Cloud Run receives only the environment required by each service. Query-engine
  authentication and public-network policy are configured explicitly and fail closed.

Supabase hosted Auth settings are not deployed by `supabase db push`.
`minimum_password_length`, secure password changes, and leaked-password protection
must be verified separately in the hosted project Auth configuration.
