import asyncio

from app.drivers.base import (
    ConnectionMetadata,
    DatabaseCredentials,
    ConnectionTestResult,
    DatabaseDriver,
    DriverConfigurationError,
    DriverIntrospectionError,
    DriverNotImplementedError,
    ReadonlyQueryResult,
    SchemaColumnMetadata,
    SchemaForeignKeyMetadata,
    SchemaIntrospectionResult,
    SchemaPrimaryKeyMetadata,
    SchemaTableMetadata,
)
from app.models import Engine


AZURE_SQL_DOMAIN_SUFFIX = ".database.windows.net"

SQLSERVER_TABLES_QUERY = """
select
    t.TABLE_SCHEMA,
    t.TABLE_NAME,
    t.TABLE_TYPE
from INFORMATION_SCHEMA.TABLES as t
where t.TABLE_TYPE in ('BASE TABLE', 'VIEW')
  and t.TABLE_SCHEMA not in ('INFORMATION_SCHEMA', 'sys')
order by t.TABLE_SCHEMA, t.TABLE_NAME
"""

SQLSERVER_COLUMNS_QUERY = """
select
    c.TABLE_SCHEMA,
    c.TABLE_NAME,
    c.COLUMN_NAME,
    c.ORDINAL_POSITION,
    c.DATA_TYPE,
    c.IS_NULLABLE,
    c.CHARACTER_MAXIMUM_LENGTH,
    c.NUMERIC_PRECISION,
    c.NUMERIC_SCALE,
    c.DATETIME_PRECISION,
    cast(columnproperty(
        object_id(quotename(c.TABLE_SCHEMA) + '.' + quotename(c.TABLE_NAME)),
        c.COLUMN_NAME,
        'IsIdentity'
    ) as int) as IS_IDENTITY,
    cast(columnproperty(
        object_id(quotename(c.TABLE_SCHEMA) + '.' + quotename(c.TABLE_NAME)),
        c.COLUMN_NAME,
        'IsComputed'
    ) as int) as IS_COMPUTED
from INFORMATION_SCHEMA.COLUMNS as c
inner join INFORMATION_SCHEMA.TABLES as t
    on t.TABLE_SCHEMA = c.TABLE_SCHEMA
   and t.TABLE_NAME = c.TABLE_NAME
where t.TABLE_TYPE in ('BASE TABLE', 'VIEW')
  and c.TABLE_SCHEMA not in ('INFORMATION_SCHEMA', 'sys')
order by c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION
"""

SQLSERVER_PRIMARY_KEYS_QUERY = """
select
    tc.TABLE_SCHEMA,
    tc.TABLE_NAME,
    tc.CONSTRAINT_NAME,
    kcu.COLUMN_NAME,
    kcu.ORDINAL_POSITION
from INFORMATION_SCHEMA.TABLE_CONSTRAINTS as tc
inner join INFORMATION_SCHEMA.KEY_COLUMN_USAGE as kcu
    on kcu.CONSTRAINT_CATALOG = tc.CONSTRAINT_CATALOG
   and kcu.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
   and kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
where tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
order by tc.TABLE_SCHEMA, tc.TABLE_NAME, tc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION
"""

SQLSERVER_FOREIGN_KEYS_QUERY = """
select
    fk.name as FK_NAME,
    parent_schema.name as FROM_SCHEMA,
    parent_table.name as FROM_TABLE,
    parent_column.name as FROM_COLUMN,
    referenced_schema.name as TO_SCHEMA,
    referenced_table.name as TO_TABLE,
    referenced_column.name as TO_COLUMN,
    fkc.constraint_column_id,
    fk.delete_referential_action_desc,
    fk.update_referential_action_desc
from sys.foreign_keys as fk
inner join sys.foreign_key_columns as fkc
    on fkc.constraint_object_id = fk.object_id
inner join sys.tables as parent_table
    on parent_table.object_id = fk.parent_object_id
inner join sys.schemas as parent_schema
    on parent_schema.schema_id = parent_table.schema_id
inner join sys.columns as parent_column
    on parent_column.object_id = parent_table.object_id
   and parent_column.column_id = fkc.parent_column_id
inner join sys.tables as referenced_table
    on referenced_table.object_id = fk.referenced_object_id
inner join sys.schemas as referenced_schema
    on referenced_schema.schema_id = referenced_table.schema_id
inner join sys.columns as referenced_column
    on referenced_column.object_id = referenced_table.object_id
   and referenced_column.column_id = fkc.referenced_column_id
order by parent_schema.name, parent_table.name, fk.name, fkc.constraint_column_id
"""


class SqlServerDriver(DatabaseDriver):
    engine = Engine.sqlserver

    async def test_connection(
        self,
        connection: ConnectionMetadata,
        credentials: DatabaseCredentials,
        timeout_ms: int,
    ) -> ConnectionTestResult:
        try:
            import pyodbc
        except ImportError as exc:
            raise DriverConfigurationError("SQL Server ODBC driver is not installed.") from exc

        timeout_seconds = max(1, timeout_ms // 1000)
        parts = _connection_string_parts(connection, credentials, timeout_seconds)

        try:
            sql_connection = await _connect(pyodbc, parts, timeout_seconds)
            try:
                await asyncio.to_thread(
                    sql_connection.cursor().execute,
                    "select 1",
                )
            finally:
                await asyncio.to_thread(sql_connection.close)
        except pyodbc.Error:
            return ConnectionTestResult(
                status="failed",
                message="SQL Server connection failed.",
            )

        return ConnectionTestResult(status="ok", message="SQL Server connection verified.")

    async def introspect_schema(
        self,
        connection: ConnectionMetadata,
        credentials: DatabaseCredentials,
        timeout_ms: int,
    ) -> SchemaIntrospectionResult:
        try:
            import pyodbc
        except ImportError as exc:
            raise DriverConfigurationError("SQL Server ODBC driver is not installed.") from exc

        timeout_seconds = max(1, timeout_ms // 1000)
        parts = _connection_string_parts(connection, credentials, timeout_seconds)

        try:
            sql_connection = await _connect(pyodbc, parts, timeout_seconds)
            try:
                table_rows = await _fetch_all(sql_connection, SQLSERVER_TABLES_QUERY)
                column_rows = await _fetch_all(sql_connection, SQLSERVER_COLUMNS_QUERY)
                primary_key_rows = await _fetch_all(
                    sql_connection,
                    SQLSERVER_PRIMARY_KEYS_QUERY,
                )
                foreign_key_rows = await _fetch_all(
                    sql_connection,
                    SQLSERVER_FOREIGN_KEYS_QUERY,
                )
            finally:
                await asyncio.to_thread(sql_connection.close)
        except pyodbc.Error as exc:
            raise DriverIntrospectionError("SQL Server schema introspection failed.") from exc

        return SchemaIntrospectionResult(
            engine=Engine.sqlserver,
            tables=_build_tables(table_rows, column_rows, primary_key_rows),
            foreign_keys=_build_foreign_keys(foreign_key_rows),
        )

    async def execute_readonly(
        self,
        connection: ConnectionMetadata,
        sql: str,
        row_limit: int,
        timeout_ms: int,
    ) -> ReadonlyQueryResult:
        raise DriverNotImplementedError(
            "SQL Server readonly execution is scheduled for the connection milestone."
        )


def _login_username(connection: ConnectionMetadata) -> str:
    if (
        "@" not in connection.username
        and "\\" not in connection.username
        and connection.tls_server_name is not None
        and connection.tls_server_name.endswith(AZURE_SQL_DOMAIN_SUFFIX)
        and connection.host != connection.tls_server_name
    ):
        server_name = connection.tls_server_name.removesuffix(AZURE_SQL_DOMAIN_SUFFIX)
        return f"{connection.username}@{server_name}"

    return connection.username


def _connection_string_parts(
    connection: ConnectionMetadata,
    credentials: DatabaseCredentials,
    timeout_seconds: int,
) -> list[str]:
    encrypt = "yes" if connection.tls_required else "no"
    parts = [
        "Driver={ODBC Driver 18 for SQL Server}",
        f"Server=tcp:{connection.host},{connection.port}",
        f"Database={connection.database_name}",
        f"UID={_login_username(connection)}",
        f"PWD={credentials.password}",
        f"Encrypt={encrypt}",
        f"TrustServerCertificate={'yes' if connection.trust_server_certificate else 'no'}",
        f"Connection Timeout={timeout_seconds}",
    ]
    if connection.tls_server_name:
        parts.append(f"HostNameInCertificate={connection.tls_server_name}")

    return parts


async def _connect(pyodbc, parts: list[str], timeout_seconds: int):
    return await asyncio.to_thread(
        pyodbc.connect,
        ";".join(parts),
        autocommit=True,
        timeout=timeout_seconds,
    )


async def _fetch_all(sql_connection, query: str):
    cursor = sql_connection.cursor()
    try:
        await asyncio.to_thread(cursor.execute, query)
        return await asyncio.to_thread(cursor.fetchall)
    finally:
        await asyncio.to_thread(cursor.close)


def _build_tables(
    table_rows,
    column_rows,
    primary_key_rows,
) -> list[SchemaTableMetadata]:
    table_map: dict[tuple[str, str], dict] = {}

    for row in table_rows:
        table_schema, table_name, table_type = row[0], row[1], row[2]
        key = (table_schema, table_name)
        table_map[key] = {
            "table_schema": table_schema,
            "name": table_name,
            "table_type": "view" if table_type == "VIEW" else "base_table",
            "columns": [],
            "primary_key": None,
        }

    for row in column_rows:
        table_schema, table_name = row[0], row[1]
        table = table_map.get((table_schema, table_name))
        if table is None:
            continue

        table["columns"].append(
            SchemaColumnMetadata(
                name=row[2],
                ordinal_position=int(row[3]),
                data_type=row[4],
                is_nullable=row[5] == "YES",
                max_length=_optional_int(row[6]),
                numeric_precision=_optional_int(row[7]),
                numeric_scale=_optional_int(row[8]),
                datetime_precision=_optional_int(row[9]),
                is_identity=bool(row[10]),
                is_computed=bool(row[11]),
            )
        )

    primary_key_map: dict[tuple[str, str, str], list[tuple[int, str]]] = {}
    for row in primary_key_rows:
        key = (row[0], row[1], row[2])
        primary_key_map.setdefault(key, []).append((int(row[4]), row[3]))

    for (table_schema, table_name, constraint_name), columns in primary_key_map.items():
        table = table_map.get((table_schema, table_name))
        if table is None:
            continue

        table["primary_key"] = SchemaPrimaryKeyMetadata(
            name=constraint_name,
            columns=[column for _, column in sorted(columns)],
        )

    return [
        SchemaTableMetadata(**table)
        for _, table in sorted(table_map.items(), key=lambda item: item[0])
    ]


def _build_foreign_keys(foreign_key_rows) -> list[SchemaForeignKeyMetadata]:
    foreign_key_map: dict[
        tuple[str, str, str, str, str, str, str],
        list[tuple[int, str, str]],
    ] = {}

    for row in foreign_key_rows:
        key = (row[0], row[1], row[2], row[4], row[5], row[8], row[9])
        foreign_key_map.setdefault(key, []).append((int(row[7]), row[3], row[6]))

    foreign_keys: list[SchemaForeignKeyMetadata] = []
    for key, columns in sorted(
        foreign_key_map.items(),
        key=lambda item: (item[0][1], item[0][2], item[0][0]),
    ):
        (
            name,
            from_schema,
            from_table,
            to_schema,
            to_table,
            on_delete,
            on_update,
        ) = key
        ordered_columns = sorted(columns)
        foreign_keys.append(
            SchemaForeignKeyMetadata(
                name=name,
                from_schema=from_schema,
                from_table=from_table,
                from_columns=[column[1] for column in ordered_columns],
                to_schema=to_schema,
                to_table=to_table,
                to_columns=[column[2] for column in ordered_columns],
                on_delete=on_delete.lower(),
                on_update=on_update.lower(),
            )
        )

    return foreign_keys


def _optional_int(value) -> int | None:
    if value is None:
        return None
    return int(value)
