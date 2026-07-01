# SQL Server Dry-Run Adapter V1 Report

## Summary

Implemented the internal Live SQL Server Metadata Adapter V1 for Controlled
Dry-Run.

The adapter is intentionally narrow:

* it calls only `EXEC sys.sp_describe_first_result_set @tsql = ?, @params = ?, @browse_information_mode = ?`;
* compiled business SQL is passed only as the `@tsql` bound parameter;
* no business rows are returned;
* no dashboard refresh or execution envelope is implemented;
* `controlled_dry_run.py` remains no-driver and no-execution.

## Files

Created:

* `services/query-engine/app/adapters/sqlserver_dry_run_adapter.py`
* `services/query-engine/app/adapters/__init__.py`
* `services/query-engine/tests/test_sqlserver_dry_run_adapter.py`
* `docs/dev/sqlserver-dry-run-adapter-v1-report.md`

## Metadata Procedure

The adapter executes exactly one constant command string:

```text
EXEC sys.sp_describe_first_result_set @tsql = ?, @params = ?, @browse_information_mode = ?
```

The command is not formatted, concatenated, templated, or interpolated.

`@browse_information_mode = 0` is fixed for V1. The adapter validates the
exposed output contract. Source table/source column metadata, when returned by
SQL Server, is retained only as safe diagnostic metadata and is never treated as
join evidence.

Microsoft documents that `sp_describe_first_result_set` returns first result-set
metadata, accepts parameter declarations via `@params`, and can fail when
metadata cannot be statically determined:

<https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-describe-first-result-set-transact-sql>

## Connection Policy

The adapter reuses the existing SQL Server connection model:

* `ConnectionMetadata`;
* `DatabaseCredentials`;
* ODBC Driver 18 connection-string construction from `app.drivers.sqlserver`;
* endpoint resolution through the existing network boundary.

Additional adapter-level policy gates:

* database name is required;
* TLS is required by default;
* `TrustServerCertificate=True` blocks unless explicit adapter policy allows it;
* `UseFMTONLY=No` is appended for this metadata path;
* connection timeout and metadata timeout are forwarded;
* connection and cursor cleanup happens in `finally`.

Microsoft documents ODBC Driver 18 encryption behavior, `TrustServerCertificate`,
and `UseFMTONLY=No` using `sp_describe_first_result_set` when available:

<https://learn.microsoft.com/en-us/sql/connect/odbc/dsn-connection-string-attribute>

## Parameter Declaration Policy

The adapter never interpolates parameter values into SQL.

Rules implemented:

* compiled SQL is passed as the `@tsql` bound parameter;
* parameter declarations are passed as the `@params` bound parameter;
* `@browse_information_mode` is passed as a bound integer;
* if the compiled SQL has no parameters, `@params` is passed as `None`;
* no fake parameter declaration is synthesized;
* declarations must be deterministic and gap-free;
* unsupported declaration types block before DB IO.

Dry-Run V1 allowed declaration types:

```text
int
bigint
decimal(38,10)
date
datetime
datetime2
bit
nvarchar(4000)
varchar(n)
uniqueidentifier
```

Result metadata may include numeric SQL Server types such as `money`,
`smallmoney`, `float`, and `real`; compatibility is still enforced by the
Controlled Dry-Run core metadata contract.

Raw parameter values are not stored in adapter reports. Existing
`DryRunParameterBinding.value_fingerprint` remains the audit/debug handle.

## Metadata Normalization

SQL Server rows are normalized into adapter rows with:

```text
column_ordinal
name
is_nullable
system_type_name
system_type_id
precision
scale
max_length
collation_name
is_case_sensitive
source_schema
source_table
source_column
```

The adapter passes only the V1 contract fields to
`validate_controlled_dry_run_metadata(...)`:

* ordinal;
* alias/name;
* SQL type;
* nullability.

Name matching is exact. The adapter does not normalize case, accents, spaces,
reserved words, closing brackets, or mixed-case aliases.

## Error Mapping

The adapter maps driver and SQL Server errors to stable dry-run categories.

Mapping prefers structured driver data where available:

* SQLSTATE from exception args;
* SQL Server numeric error from exception args;
* SQL Server numeric error parsed from ODBC message only as fallback.

Message substring matching is used only as a best-effort fallback for driver
messages that do not expose structured details.

Covered categories:

```text
authentication_error
tls_error
connection_error
permission_error
object_not_found
column_not_found
parameter_binding_error
syntax_error
unsupported_sql_shape
sqlserver_metadata_error
timeout
cancelled
driver_error
```

The adapter returns safe category-specific messages. It does not expose raw
secret values or raw parameter values.

## Timeout And Cleanup

Implemented:

* connection timeout forwarded to pyodbc connect;
* metadata timeout applied to connection/cursor where available;
* `asyncio.wait_for` wraps the sync metadata call;
* cursor and connection close in `finally`;
* no retry on logical SQL Server metadata errors;
* no retry on parameter declaration or permission errors.

Unit tests cover cleanup on:

* success;
* SQL Server metadata error;
* timeout;
* unexpected driver exception;
* validation failure after metadata fetch.

## No-Business-Execution Proof

Unit tests assert:

* cursor receives exactly the constant metadata command;
* compiled business SQL is the first bound parameter only;
* the adapter never calls cursor execution directly with compiled SQL;
* no SQL rewrite, re-introspection, or retry occurs after metadata failure.

The adapter has no execution path for business result rows.

## Anti-Demo / PMI Coverage

Automated unit coverage includes:

* scalar metadata validation;
* grouped metadata validation;
* physical view source metadata as exposed output contract;
* exact alias matching, including Unicode and weird source identifiers;
* case-sensitive alias mismatch;
* no parameters, one parameter, multiple parameters, IN-expanded parameters,
  BETWEEN parameters;
* SQL Server metadata shape mismatch;
* object missing, column missing, permission denied, parameter declaration
  failure and static metadata failure mapped from realistic SQL Server
  error codes/messages.

Fixture/demo literals are not used in adapter production code.

## Real SQL Server Acceptance Status

Were only mocked tests used?

```text
Yes for automated tests completed in this implementation pass.
```

Was a real SQL Server fixture used?

```text
No. The optional live AdventureWorksLT integration tests are present but skipped
unless ATLANTE_SQLSERVER_DRY_RUN_INTEGRATION=1 or
ADVENTUREWORKSLT_DRY_RUN_INTEGRATION=1 is set with live connection env vars.
```

Current readiness label:

```text
Unit-verified only.
```

The adapter can merge as V1 only with this caveat. It is not PMI-production-ready
until the optional integration tests or the manual checklist below are executed
against a real SQL Server instance.

After the request to use the available demo database, this pass added concrete
optional live tests for AdventureWorksLT and attempted to discover usable
credentials in the current CLI environment. The repository `.env.local` files
contain Supabase/GCP/query-engine settings only, not SQL Server credentials;
Process/User/Machine environment variables also do not contain
`ADVENTUREWORKSLT_*` or `ATLANTE_SQLSERVER_*`; and the local Supabase Docker
container is not running, so connection metadata could not be read from the
local database. Therefore no live SQL Server call was executed in this pass.

After demo credentials were supplied explicitly, the live test path was retried.
The first attempt did not reach SQL Server because this Windows environment had
`ODBC Driver 17 for SQL Server` installed but not `ODBC Driver 18 for SQL
Server`, which is the driver name used by the existing SQL Server connection
layer. Microsoft ODBC Driver 18.6.2.1 was then installed locally.

With ODBC Driver 18 installed, the adapter reached the driver path but still
failed before metadata validation with `engine_error / tls_error`. Direct
diagnostic probes through ODBC Driver 18 failed with SQLSTATE `08001` and the
Windows Schannel message `Nessuna credenziale disponibile nel pacchetto di
sicurezza` / `Encryption not supported on the client`, both against the supplied
`136.111.143.3:10002` endpoint and against `atlanteadmin.database.windows.net`
on 1433. TCP reachability is open, and a raw Python/OpenSSL TLS handshake to the
demo endpoint succeeds; the failure is therefore specific to the local Microsoft
ODBC Driver / Windows Schannel path, not to the adapter SQL text or the metadata
procedure contract.

No password or secret value was written to the repository or report. This is a
real limitation of the current verification environment, not a reason to skip
the demo gate. When the local Schannel/ODBC connectivity issue is resolved, the
tests below will execute the adapter against SQL Server using only
`sp_describe_first_result_set`.

## Optional Integration Path

The test suite includes skipped live AdventureWorksLT integration tests guarded
by either:

```text
ATLANTE_SQLSERVER_DRY_RUN_INTEGRATION=1
ADVENTUREWORKSLT_DRY_RUN_INTEGRATION=1
```

Supported environment prefixes:

```text
ATLANTE_SQLSERVER_HOST
ATLANTE_SQLSERVER_DATABASE
ATLANTE_SQLSERVER_USERNAME
ATLANTE_SQLSERVER_PASSWORD
ATLANTE_SQLSERVER_PORT optional, default 1433
ATLANTE_SQLSERVER_NETWORK_MODE optional, default public
ATLANTE_SQLSERVER_TLS_REQUIRED optional, default true
ATLANTE_SQLSERVER_TRUST_SERVER_CERTIFICATE optional, default false
ATLANTE_SQLSERVER_ALLOW_TRUST_SERVER_CERTIFICATE optional, default false
ATLANTE_SQLSERVER_TLS_SERVER_NAME optional

ADVENTUREWORKSLT_HOST
ADVENTUREWORKSLT_DATABASE optional, default AdventureWorksLT
ADVENTUREWORKSLT_USERNAME
ADVENTUREWORKSLT_PASSWORD
ADVENTUREWORKSLT_PORT optional, default 1433
ADVENTUREWORKSLT_NETWORK_MODE optional, default public_allowlist
ADVENTUREWORKSLT_TLS optional, default true
ADVENTUREWORKSLT_TLS_REQUIRED optional, default ADVENTUREWORKSLT_TLS
ADVENTUREWORKSLT_TRUST_SERVER_CERTIFICATE optional, default false
ADVENTUREWORKSLT_ALLOW_TRUST_SERVER_CERTIFICATE optional, default trust setting
ADVENTUREWORKSLT_TLS_SERVER_NAME optional
```

The live tests validate:

* scalar aggregate metadata with date parameters on `SalesLT.SalesOrderHeader`;
* grouped metadata with joins across `SalesLT.SalesOrderDetail`,
  `SalesLT.Product`, and `SalesLT.ProductCategory`;
* physical DB view metadata through `SalesLT.vGetAllCategories`.

AdventureWorksLT remains a regression/demo baseline only. Passing these tests
would prove the adapter-to-driver-to-SQL-Server metadata path on a real SQL
Server fixture, but it would still not prove PMI/ERP readiness.

## Manual Real SQL Server Checklist

If CI cannot run SQL Server safely, run this checklist before claiming live PMI
readiness.

Create a dedicated database and schema:

```sql
create schema erp;
go

create table erp.[Document Head] (
    [Company Id] int not null,
    [Doc Id] bigint not null,
    [Data Doc] date not null,
    [Tipo Doc] nvarchar(20) not null,
    [Stato] nvarchar(20) null,
    constraint [PK Document Head] primary key ([Company Id], [Doc Id])
);

create table erp.[Document Rows] (
    [Company Id] int not null,
    [Doc Id] bigint not null,
    [Row Id] int not null,
    [Amount €] decimal(18,2) not null,
    [Qty] decimal(18,3) null,
    constraint [PK Document Rows] primary key ([Company Id], [Doc Id], [Row Id]),
    constraint [FK Rows Head] foreign key ([Company Id], [Doc Id])
        references erp.[Document Head] ([Company Id], [Doc Id])
);

create view erp.[BI View Safe] as
select
    h.[Tipo Doc] as [Dimension 0],
    cast(sum(r.[Amount €]) as decimal(38,10)) as [metric_value]
from erp.[Document Head] h
inner join erp.[Document Rows] r
    on r.[Company Id] = h.[Company Id]
   and r.[Doc Id] = h.[Doc Id]
group by h.[Tipo Doc];
go
```

Create a restricted user:

```sql
create user atlante_dryrun without login;
grant select on erp.[BI View Safe] to atlante_dryrun;
deny select on erp.[Document Head] to atlante_dryrun;
deny select on erp.[Document Rows] to atlante_dryrun;
```

Validate with `EXECUTE AS USER = 'atlante_dryrun'`:

```sql
EXEC sys.sp_describe_first_result_set
  @tsql = N'SELECT [Dimension 0] AS [dimension_0], [metric_value] AS [metric_value] FROM erp.[BI View Safe]',
  @params = NULL,
  @browse_information_mode = 0;
```

Expected:

```text
column_ordinal 1, name dimension_0
column_ordinal 2, name metric_value
no base-table lineage dependency for acceptance
```

Then test failure cases:

* remove SELECT on the view and expect permission_error;
* rename `[metric_value]` in the view and expect metadata_shape_mismatch;
* reference a dropped column and expect column_not_found;
* reference a dropped view and expect object_not_found;
* return a binary/variant-like type and expect metadata_shape_mismatch.

AdventureWorksLT may be used only as a regression baseline, not as acceptance.

## Verification Results

Run during this pass:

```text
tests/test_sqlserver_dry_run_adapter.py: 10 passed, 3 skipped
tests/test_sqlserver_dry_run_adapter.py with supplied AdventureWorksLT credentials: 10 passed, 3 failed
  failed before metadata validation due to local ODBC Driver 18 / Schannel TLS error
tests/test_controlled_dry_run.py: 11 passed
tests/test_query_result_validator.py: 15 passed
tests/test_query_compiler.py: 15 passed
tests/test_query_compiler_preflight.py: 15 passed
tests/test_queryability.py: 20 passed
tests/test_semantic_invariants.py: 10 passed
tests/test_query_intent.py: 22 passed
full query-engine suite: 297 passed, 4 skipped
```

Run from repo root:

```text
@atlantebi/contracts test: 5 files passed, 44 tests passed
@atlantebi/db test: 1 file passed, 35 tests passed
@atlantebi/web test: 19 files passed, 67 tests passed
@atlantebi/web typecheck: passed
pnpm lint: passed
@atlantebi/web build: passed
```

Static guards:

```text
controlled_dry_run.py no-driver/no-execution guard: no matches
controlled_dry_run.py demo literal guard: no matches
sqlserver_dry_run_adapter.py demo literal guard: no matches
adapter command text guard: cursor.execute(METADATA_COMMAND, tsql, params_declaration, 0)
```

## Final Recommendation

Can Runtime Result Validation planning start after this adapter?

```text
Yes, after adapter tests and full gates pass.
```

Can business SQL execution start?

```text
No.
```

Live metadata dry-run can exist after this adapter. Business query execution
remains blocked until audit persistence/envelope, runtime result validation, and
execution envelope are implemented and verified.
