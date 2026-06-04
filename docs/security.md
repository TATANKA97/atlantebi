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
- computed column definitions may be unavailable;
- default and check constraint definitions may be unavailable;
- coverage warnings will indicate partial metadata visibility.

View definitions and extended properties are treated as tenant-scoped sensitive
metadata. They are saved in `schema_snapshots.snapshot` for deterministic technical
coverage, but they must not be logged in clear text or sent to AI workflows by default.
