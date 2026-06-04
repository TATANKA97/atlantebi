import asyncio
import hashlib
import json
import logging

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
    SchemaCoverageWarning,
    SchemaCheckConstraintMetadata,
    SchemaDefaultConstraintMetadata,
    SchemaForeignKeyMetadata,
    SchemaIndexColumnMetadata,
    SchemaIndexMetadata,
    SchemaIntrospectionResult,
    SchemaPrimaryKeyMetadata,
    SchemaTableMetadata,
    SchemaUniqueConstraintMetadata,
)
from app.models import Engine


AZURE_SQL_DOMAIN_SUFFIX = ".database.windows.net"
logger = logging.getLogger(__name__)

SQLSERVER_DATABASE_QUERY = """
select
    db_name() as DATABASE_NAME,
    cast(serverproperty('ProductVersion') as nvarchar(128)) as ENGINE_VERSION
"""

SQLSERVER_OBJECTS_QUERY = """
select
    object_schema.name as SCHEMA_NAME,
    object_item.name as OBJECT_NAME,
    case
        when object_item.type = 'V' then 'view'
        else 'base_table'
    end as OBJECT_TYPE,
    object_item.object_id,
    cast(object_item.is_ms_shipped as int) as IS_MS_SHIPPED,
    cast(object_description.value as nvarchar(max)) as OBJECT_DESCRIPTION,
    view_module.definition as VIEW_DEFINITION
from sys.objects as object_item
inner join sys.schemas as object_schema
    on object_schema.schema_id = object_item.schema_id
left join sys.extended_properties as object_description
    on object_description.major_id = object_item.object_id
   and object_description.minor_id = 0
   and object_description.name = 'MS_Description'
left join sys.sql_modules as view_module
    on view_module.object_id = object_item.object_id
   and object_item.type = 'V'
where object_item.type in ('U', 'V')
  and object_schema.name not in ('INFORMATION_SCHEMA', 'sys')
  and object_item.is_ms_shipped = 0
order by object_schema.name, object_item.name
"""

SQLSERVER_COLUMNS_QUERY = """
select
    object_schema.name as SCHEMA_NAME,
    object_item.name as OBJECT_NAME,
    column_item.name as COLUMN_NAME,
    column_item.column_id as ORDINAL_POSITION,
    coalesce(system_type.name, user_type.name) as NATIVE_TYPE,
    user_type.name as DECLARED_TYPE,
    cast(column_item.is_nullable as int) as IS_NULLABLE,
    case
        when system_type.name in ('nchar', 'nvarchar') and column_item.max_length > 0
            then column_item.max_length / 2
        else column_item.max_length
    end as MAX_LENGTH,
    column_item.precision as NUMERIC_PRECISION,
    column_item.scale as NUMERIC_SCALE,
    case
        when system_type.name in ('date', 'datetime', 'datetime2', 'datetimeoffset', 'smalldatetime', 'time')
            then column_item.scale
        else null
    end as DATETIME_PRECISION,
    column_item.collation_name,
    cast(column_item.is_identity as int) as IS_IDENTITY,
    cast(column_item.is_computed as int) as IS_COMPUTED,
    cast(identity_column.seed_value as nvarchar(80)) as IDENTITY_SEED,
    cast(identity_column.increment_value as nvarchar(80)) as IDENTITY_INCREMENT,
    default_constraint.name as DEFAULT_CONSTRAINT_NAME,
    default_constraint.definition as DEFAULT_DEFINITION,
    computed_column.definition as COMPUTED_DEFINITION,
    cast(column_description.value as nvarchar(max)) as COLUMN_DESCRIPTION
from sys.objects as object_item
inner join sys.schemas as object_schema
    on object_schema.schema_id = object_item.schema_id
inner join sys.columns as column_item
    on column_item.object_id = object_item.object_id
inner join sys.types as user_type
    on user_type.user_type_id = column_item.user_type_id
left join sys.types as system_type
    on system_type.system_type_id = column_item.system_type_id
   and system_type.user_type_id = system_type.system_type_id
left join sys.default_constraints as default_constraint
    on default_constraint.parent_object_id = column_item.object_id
   and default_constraint.parent_column_id = column_item.column_id
left join sys.computed_columns as computed_column
    on computed_column.object_id = column_item.object_id
   and computed_column.column_id = column_item.column_id
left join sys.identity_columns as identity_column
    on identity_column.object_id = column_item.object_id
   and identity_column.column_id = column_item.column_id
left join sys.extended_properties as column_description
    on column_description.major_id = column_item.object_id
   and column_description.minor_id = column_item.column_id
   and column_description.name = 'MS_Description'
where object_item.type in ('U', 'V')
  and object_item.is_ms_shipped = 0
  and object_schema.name not in ('INFORMATION_SCHEMA', 'sys')
order by object_schema.name, object_item.name, column_item.column_id
"""

SQLSERVER_KEY_CONSTRAINTS_QUERY = """
select
    object_schema.name as SCHEMA_NAME,
    object_item.name as TABLE_NAME,
    key_constraint.name as CONSTRAINT_NAME,
    key_constraint.type as CONSTRAINT_TYPE,
    column_item.name as COLUMN_NAME,
    index_column.key_ordinal as KEY_ORDINAL
from sys.key_constraints as key_constraint
inner join sys.objects as object_item
    on object_item.object_id = key_constraint.parent_object_id
inner join sys.schemas as object_schema
    on object_schema.schema_id = object_item.schema_id
inner join sys.index_columns as index_column
    on index_column.object_id = key_constraint.parent_object_id
   and index_column.index_id = key_constraint.unique_index_id
inner join sys.columns as column_item
    on column_item.object_id = index_column.object_id
   and column_item.column_id = index_column.column_id
where object_item.is_ms_shipped = 0
  and index_column.key_ordinal > 0
order by object_schema.name, object_item.name, key_constraint.name, index_column.key_ordinal
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
    fk.update_referential_action_desc,
    cast(fk.is_disabled as int) as IS_DISABLED,
    cast(fk.is_not_trusted as int) as IS_NOT_TRUSTED
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

SQLSERVER_CHECK_CONSTRAINTS_QUERY = """
select
    object_schema.name as SCHEMA_NAME,
    object_item.name as TABLE_NAME,
    check_constraint.name as CONSTRAINT_NAME,
    check_constraint.definition,
    cast(check_constraint.is_disabled as int) as IS_DISABLED,
    cast(check_constraint.is_not_trusted as int) as IS_NOT_TRUSTED
from sys.check_constraints as check_constraint
inner join sys.objects as object_item
    on object_item.object_id = check_constraint.parent_object_id
inner join sys.schemas as object_schema
    on object_schema.schema_id = object_item.schema_id
where object_item.is_ms_shipped = 0
order by object_schema.name, object_item.name, check_constraint.name
"""

SQLSERVER_INDEXES_QUERY = """
select
    object_schema.name as SCHEMA_NAME,
    object_item.name as TABLE_NAME,
    index_item.name as INDEX_NAME,
    cast(index_item.is_unique as int) as IS_UNIQUE,
    cast(index_item.is_primary_key as int) as IS_PRIMARY_KEY,
    index_item.type_desc as INDEX_TYPE,
    column_item.name as COLUMN_NAME,
    index_column.key_ordinal,
    index_column.index_column_id,
    cast(index_column.is_descending_key as int) as IS_DESCENDING,
    cast(index_column.is_included_column as int) as IS_INCLUDED,
    index_item.filter_definition,
    cast(index_item.is_disabled as int) as IS_DISABLED
from sys.indexes as index_item
inner join sys.objects as object_item
    on object_item.object_id = index_item.object_id
inner join sys.schemas as object_schema
    on object_schema.schema_id = object_item.schema_id
inner join sys.index_columns as index_column
    on index_column.object_id = index_item.object_id
   and index_column.index_id = index_item.index_id
inner join sys.columns as column_item
    on column_item.object_id = index_column.object_id
   and column_item.column_id = index_column.column_id
where object_item.type = 'U'
  and object_item.is_ms_shipped = 0
  and index_item.index_id > 0
  and index_item.is_hypothetical = 0
order by object_schema.name, object_item.name, index_item.name, index_column.key_ordinal, index_column.index_column_id
"""

SQLSERVER_ROW_COUNTS_QUERY = """
select
    object_schema.name as SCHEMA_NAME,
    object_item.name as TABLE_NAME,
    sum(partition_stats.row_count) as ROW_COUNT_ESTIMATE
from sys.dm_db_partition_stats as partition_stats
inner join sys.tables as object_item
    on object_item.object_id = partition_stats.object_id
inner join sys.schemas as object_schema
    on object_schema.schema_id = object_item.schema_id
where partition_stats.index_id in (0, 1)
  and object_item.is_ms_shipped = 0
group by object_schema.name, object_item.name
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
                database_row = await _fetch_one(sql_connection, SQLSERVER_DATABASE_QUERY)
                object_rows = await _fetch_all(sql_connection, SQLSERVER_OBJECTS_QUERY)
                column_rows = await _fetch_all(sql_connection, SQLSERVER_COLUMNS_QUERY)
                key_constraint_rows = await _fetch_all(
                    sql_connection,
                    SQLSERVER_KEY_CONSTRAINTS_QUERY,
                )
                foreign_key_rows = await _fetch_all(
                    sql_connection,
                    SQLSERVER_FOREIGN_KEYS_QUERY,
                )
                check_constraint_rows = await _fetch_all(
                    sql_connection,
                    SQLSERVER_CHECK_CONSTRAINTS_QUERY,
                )
                index_rows, indexes_available = await _fetch_all_best_effort(
                    sql_connection,
                    SQLSERVER_INDEXES_QUERY,
                    pyodbc.Error,
                )
                row_count_rows, row_counts_available = await _fetch_all_best_effort(
                    sql_connection,
                    SQLSERVER_ROW_COUNTS_QUERY,
                    pyodbc.Error,
                )
            finally:
                await asyncio.to_thread(sql_connection.close)
        except pyodbc.Error as exc:
            logger.exception("SQL Server schema introspection query failed.")
            raise DriverIntrospectionError("SQL Server schema introspection failed.") from exc

        database_name = str(database_row[0])
        engine_version = str(database_row[1])
        primary_keys_by_table, unique_constraints = _build_key_constraints(
            key_constraint_rows
        )
        foreign_keys = _build_foreign_keys(foreign_key_rows)
        indexes = _build_indexes(index_rows)
        row_counts = _build_row_counts(row_count_rows)
        tables = _build_tables(
            database_name,
            object_rows,
            column_rows,
            primary_keys_by_table,
            unique_constraints,
            foreign_keys,
            indexes,
            row_counts,
        )
        check_constraints = _build_check_constraints(check_constraint_rows)
        default_constraints = _build_default_constraints(column_rows)
        coverage_warnings = _build_coverage_warnings(
            tables=tables,
            foreign_keys=foreign_keys,
            indexes_available=indexes_available,
            row_counts_available=row_counts_available,
        )
        schema_hash = _schema_hash(
            tables=tables,
            foreign_keys=foreign_keys,
            unique_constraints=unique_constraints,
            check_constraints=check_constraints,
            default_constraints=default_constraints,
            indexes=indexes,
        )

        return SchemaIntrospectionResult(
            engine=Engine.sqlserver,
            database_name=database_name,
            engine_version=engine_version,
            schema_hash=schema_hash,
            tables=tables,
            foreign_keys=foreign_keys,
            unique_constraints=unique_constraints,
            check_constraints=check_constraints,
            default_constraints=default_constraints,
            indexes=indexes,
            coverage_warnings=coverage_warnings,
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


async def _fetch_one(sql_connection, query: str):
    rows = await _fetch_all(sql_connection, query)
    if not rows:
        raise DriverIntrospectionError("SQL Server metadata query returned no rows.")
    return rows[0]


async def _fetch_all_best_effort(sql_connection, query: str, error_type):
    try:
        return await _fetch_all(sql_connection, query), True
    except error_type:
        logger.warning("Optional SQL Server metadata query failed.", exc_info=True)
        return [], False


def _build_tables(
    database_name: str,
    object_rows,
    column_rows,
    primary_keys_by_table: dict[tuple[str, str], SchemaPrimaryKeyMetadata],
    unique_constraints: list[SchemaUniqueConstraintMetadata],
    foreign_keys: list[SchemaForeignKeyMetadata],
    indexes: list[SchemaIndexMetadata],
    row_counts: dict[tuple[str, str], int],
) -> list[SchemaTableMetadata]:
    table_map: dict[tuple[str, str], dict] = {}

    primary_key_columns = {
        (schema, table, column.lower())
        for (schema, table), primary_key in primary_keys_by_table.items()
        for column in primary_key.columns
    }
    foreign_key_columns = {
        (foreign_key.from_schema, foreign_key.from_table, column.lower())
        for foreign_key in foreign_keys
        for column in foreign_key.from_columns
    }
    unique_columns = {
        (unique.schema_name, unique.table_name, column.lower())
        for unique in unique_constraints
        for column in unique.columns
    }
    unique_columns.update(
        (index.schema_name, index.table_name, column.name.lower())
        for index in indexes
        if index.is_unique
        for column in index.key_columns
    )

    for row in object_rows:
        table_schema, table_name, table_type = str(row[0]), str(row[1]), str(row[2])
        key = (table_schema, table_name)
        view_definition = _optional_string(row[6])
        table_map[key] = {
            "table_schema": table_schema,
            "name": table_name,
            "table_type": table_type,
            "columns": [],
            "primary_key": primary_keys_by_table.get(key),
            "database_name": database_name,
            "object_id": int(row[3]),
            "is_system_object": bool(row[4]),
            "row_count_estimate": row_counts.get(key),
            "comment": _optional_string(row[5]),
            "view_definition_available": (
                view_definition is not None if table_type == "view" else None
            ),
            "view_definition": view_definition,
            "definition_hash": (
                _hash_string(view_definition) if view_definition is not None else None
            ),
            "lineage_available": False if table_type == "view" else None,
        }

    for row in column_rows:
        table_schema, table_name = str(row[0]), str(row[1])
        table = table_map.get((table_schema, table_name))
        if table is None:
            continue
        native_type = str(row[4])
        declared_type = str(row[5])
        column_name = str(row[2])

        table["columns"].append(
            SchemaColumnMetadata(
                name=column_name,
                ordinal_position=int(row[3]),
                data_type=native_type,
                native_type=native_type,
                normalized_type=native_type,
                declared_type=_declared_type(native_type, declared_type),
                is_nullable=bool(row[6]),
                max_length=_optional_int(row[7]),
                numeric_precision=_optional_int(row[8]),
                numeric_scale=_optional_int(row[9]),
                datetime_precision=_optional_int(row[10]),
                collation=_optional_string(row[11]),
                is_identity=bool(row[12]),
                is_computed=bool(row[13]),
                identity_seed=_optional_string(row[14]),
                identity_increment=_optional_string(row[15]),
                default_value=_optional_string(row[17]),
                computed_expression=_optional_string(row[18]),
                comment=_optional_string(row[19]),
                is_primary_key=(table_schema, table_name, column_name.lower())
                in primary_key_columns,
                is_foreign_key=(table_schema, table_name, column_name.lower())
                in foreign_key_columns,
                is_unique_member=(table_schema, table_name, column_name.lower())
                in unique_columns,
            )
        )

    return [
        SchemaTableMetadata(**table)
        for _, table in sorted(table_map.items(), key=lambda item: item[0])
    ]


def _build_key_constraints(
    key_constraint_rows,
) -> tuple[
    dict[tuple[str, str], SchemaPrimaryKeyMetadata],
    list[SchemaUniqueConstraintMetadata],
]:
    grouped: dict[tuple[str, str, str, str], list[tuple[int, str]]] = {}
    for row in key_constraint_rows:
        key = (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
        grouped.setdefault(key, []).append((int(row[5]), str(row[4])))

    primary_keys_by_table: dict[tuple[str, str], SchemaPrimaryKeyMetadata] = {}
    unique_constraints: list[SchemaUniqueConstraintMetadata] = []
    for (schema_name, table_name, constraint_name, constraint_type), columns in sorted(
        grouped.items()
    ):
        ordered_columns = [column for _, column in sorted(columns)]
        if constraint_type == "PK":
            primary_keys_by_table[(schema_name, table_name)] = SchemaPrimaryKeyMetadata(
                name=constraint_name,
                columns=ordered_columns,
            )
        elif constraint_type == "UQ":
            unique_constraints.append(
                SchemaUniqueConstraintMetadata(
                    name=constraint_name,
                    schema_name=schema_name,
                    table_name=table_name,
                    columns=ordered_columns,
                )
            )

    return primary_keys_by_table, unique_constraints


def _build_foreign_keys(foreign_key_rows) -> list[SchemaForeignKeyMetadata]:
    foreign_key_map: dict[
        tuple[str, str, str, str, str, str, str, bool, bool],
        list[tuple[int, str, str]],
    ] = {}

    for row in foreign_key_rows:
        key = (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[4]),
            str(row[5]),
            str(row[8]),
            str(row[9]),
            bool(row[10]),
            bool(row[11]),
        )
        foreign_key_map.setdefault(key, []).append((int(row[7]), str(row[3]), str(row[6])))

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
            is_disabled,
            is_not_trusted,
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
                is_disabled=is_disabled,
                is_not_trusted=is_not_trusted,
                source="db_fk",
                verified_by_db=True,
            )
        )

    return foreign_keys


def _build_check_constraints(check_constraint_rows) -> list[SchemaCheckConstraintMetadata]:
    return [
        SchemaCheckConstraintMetadata(
            name=str(row[2]),
            schema_name=str(row[0]),
            table_name=str(row[1]),
            definition=_optional_string(row[3]),
            is_disabled=bool(row[4]),
            is_not_trusted=bool(row[5]),
        )
        for row in check_constraint_rows
    ]


def _build_default_constraints(column_rows) -> list[SchemaDefaultConstraintMetadata]:
    constraints: list[SchemaDefaultConstraintMetadata] = []
    for row in column_rows:
        constraint_name = _optional_string(row[16])
        if constraint_name is None:
            continue
        constraints.append(
            SchemaDefaultConstraintMetadata(
                name=constraint_name,
                schema_name=str(row[0]),
                table_name=str(row[1]),
                column_name=str(row[2]),
                definition=_optional_string(row[17]),
            )
        )
    return constraints


def _build_indexes(index_rows) -> list[SchemaIndexMetadata]:
    grouped: dict[tuple[str, str, str, bool, bool, str, str | None, bool], list] = {}
    for row in index_rows:
        key = (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            bool(row[3]),
            bool(row[4]),
            str(row[5]).lower(),
            _optional_string(row[11]),
            bool(row[12]),
        )
        grouped.setdefault(key, []).append(row)

    indexes: list[SchemaIndexMetadata] = []
    for (
        schema_name,
        table_name,
        index_name,
        is_unique,
        is_primary_key,
        index_type,
        filter_definition,
        is_disabled,
    ), rows in sorted(grouped.items()):
        key_columns: list[SchemaIndexColumnMetadata] = []
        included_columns: list[SchemaIndexColumnMetadata] = []
        for row in sorted(rows, key=lambda item: (int(item[7]), int(item[8]))):
            column = SchemaIndexColumnMetadata(
                name=str(row[6]),
                ordinal_position=int(row[7]) if int(row[7]) > 0 else int(row[8]),
                is_descending=bool(row[9]),
                is_included=bool(row[10]),
            )
            if column.is_included:
                included_columns.append(column)
            else:
                key_columns.append(column)

        indexes.append(
            SchemaIndexMetadata(
                name=index_name,
                schema_name=schema_name,
                table_name=table_name,
                is_unique=is_unique,
                is_primary_key=is_primary_key,
                index_type=index_type,
                key_columns=key_columns,
                included_columns=included_columns,
                filter_definition=filter_definition,
                is_disabled=is_disabled,
            )
        )
    return indexes


def _build_row_counts(row_count_rows) -> dict[tuple[str, str], int]:
    return {
        (str(row[0]), str(row[1])): int(row[2])
        for row in row_count_rows
        if row[2] is not None
    }


def _build_coverage_warnings(
    *,
    tables: list[SchemaTableMetadata],
    foreign_keys: list[SchemaForeignKeyMetadata],
    indexes_available: bool,
    row_counts_available: bool,
) -> list[SchemaCoverageWarning]:
    warnings: list[SchemaCoverageWarning] = []
    if not row_counts_available:
        warnings.append(
            SchemaCoverageWarning(
                code="ROW_COUNT_ESTIMATE_UNAVAILABLE",
                severity="warning",
                message="SQL Server row count estimates were not readable with the current permissions.",
            )
        )
    if not indexes_available:
        warnings.append(
            SchemaCoverageWarning(
                code="INDEX_METADATA_UNAVAILABLE",
                severity="warning",
                message="SQL Server index metadata was not readable with the current permissions.",
            )
        )
    if not foreign_keys:
        warnings.append(
            SchemaCoverageWarning(
                code="NO_FOREIGN_KEYS_FOUND",
                severity="info",
                message="No database foreign keys were found in the visible SQL Server metadata.",
            )
        )

    missing_view_definition = False
    for table in tables:
        if table.table_type != "view":
            continue
        warnings.append(
            SchemaCoverageWarning(
                code="VIEW_LINEAGE_NOT_AVAILABLE",
                severity="info",
                object_schema=table.table_schema,
                object_name=table.name,
                message="View lineage is not extracted in Technical Snapshot V1.",
            )
        )
        if not table.view_definition_available:
            missing_view_definition = True
            warnings.append(
                SchemaCoverageWarning(
                    code="VIEW_DEFINITION_MISSING",
                    severity="warning",
                    object_schema=table.table_schema,
                    object_name=table.name,
                    message="SQL Server did not expose the view definition.",
                )
            )
            warnings.append(
                SchemaCoverageWarning(
                    code="VIEW_DEFINITION_PERMISSION_DENIED",
                    severity="warning",
                    object_schema=table.table_schema,
                    object_name=table.name,
                    message="VIEW DEFINITION may be missing for this SQL Server view.",
                )
            )

    if missing_view_definition:
        warnings.append(
            SchemaCoverageWarning(
                code="NO_VIEW_DEFINITION_PERMISSION",
                severity="warning",
                message="At least one view definition is unavailable; grant VIEW DEFINITION for full coverage.",
            )
        )
        warnings.append(
            SchemaCoverageWarning(
                code="PARTIAL_METADATA_VISIBILITY_POSSIBLE",
                severity="warning",
                message="SQL Server metadata visibility may be partial for the current read-only user.",
            )
        )

    return warnings


def _schema_hash(
    *,
    tables: list[SchemaTableMetadata],
    foreign_keys: list[SchemaForeignKeyMetadata],
    unique_constraints: list[SchemaUniqueConstraintMetadata],
    check_constraints: list[SchemaCheckConstraintMetadata],
    default_constraints: list[SchemaDefaultConstraintMetadata],
    indexes: list[SchemaIndexMetadata],
) -> str:
    canonical = {
        "tables": [
            {
                "schema": table.table_schema,
                "name": table.name,
                "type": table.table_type,
                "definition_hash": table.definition_hash,
                "primary_key": (
                    {
                        "name": table.primary_key.name,
                        "columns": table.primary_key.columns,
                    }
                    if table.primary_key
                    else None
                ),
                "columns": [
                    {
                        "name": column.name,
                        "ordinal": column.ordinal_position,
                        "native_type": column.native_type,
                        "normalized_type": column.normalized_type,
                        "declared_type": column.declared_type,
                        "max_length": column.max_length,
                        "precision": column.numeric_precision,
                        "scale": column.numeric_scale,
                        "nullable": column.is_nullable,
                        "default": column.default_value,
                        "collation": column.collation,
                        "identity": column.is_identity,
                        "identity_seed": column.identity_seed,
                        "identity_increment": column.identity_increment,
                        "computed": column.is_computed,
                        "computed_expression": column.computed_expression,
                    }
                    for column in sorted(
                        table.columns, key=lambda item: item.ordinal_position
                    )
                ],
            }
            for table in sorted(tables, key=lambda item: (item.table_schema, item.name))
        ],
        "foreign_keys": [
            {
                "name": foreign_key.name,
                "from_schema": foreign_key.from_schema,
                "from_table": foreign_key.from_table,
                "from_columns": foreign_key.from_columns,
                "to_schema": foreign_key.to_schema,
                "to_table": foreign_key.to_table,
                "to_columns": foreign_key.to_columns,
                "on_delete": foreign_key.on_delete,
                "on_update": foreign_key.on_update,
                "is_disabled": foreign_key.is_disabled,
                "is_not_trusted": foreign_key.is_not_trusted,
            }
            for foreign_key in sorted(
                foreign_keys,
                key=lambda item: (item.from_schema, item.from_table, item.name),
            )
        ],
        "unique_constraints": [
            unique.__dict__ for unique in sorted(
                unique_constraints,
                key=lambda item: (item.schema_name, item.table_name, item.name),
            )
        ],
        "check_constraints": [
            check.__dict__ for check in sorted(
                check_constraints,
                key=lambda item: (item.schema_name, item.table_name, item.name),
            )
        ],
        "default_constraints": [
            default.__dict__ for default in sorted(
                default_constraints,
                key=lambda item: (
                    item.schema_name,
                    item.table_name,
                    item.column_name,
                    item.name,
                ),
            )
        ],
        "indexes": [
            {
                "name": index.name,
                "schema_name": index.schema_name,
                "table_name": index.table_name,
                "is_unique": index.is_unique,
                "is_primary_key": index.is_primary_key,
                "index_type": index.index_type,
                "key_columns": [column.__dict__ for column in index.key_columns],
                "included_columns": [
                    column.__dict__ for column in index.included_columns
                ],
                "filter_definition": index.filter_definition,
                "is_disabled": index.is_disabled,
            }
            for index in sorted(
                indexes,
                key=lambda item: (item.schema_name, item.table_name, item.name),
            )
        ],
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _optional_int(value) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_string(value) -> str | None:
    if value is None:
        return None
    string_value = str(value)
    if string_value == "":
        return None
    return string_value


def _hash_string(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _declared_type(data_type: str, declared_type: str) -> str | None:
    if data_type.lower() == declared_type.lower():
        return None
    return declared_type
