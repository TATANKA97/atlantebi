import asyncio

from app.drivers.base import (
    ConnectionMetadata,
    DatabaseCredentials,
    ConnectionTestResult,
    DatabaseDriver,
    DriverConfigurationError,
    DriverNotImplementedError,
    ReadonlyQueryResult,
    SchemaIntrospectionResult,
)
from app.models import Engine


class MySqlDriver(DatabaseDriver):
    engine = Engine.mysql

    async def test_connection(
        self,
        connection: ConnectionMetadata,
        credentials: DatabaseCredentials,
        timeout_ms: int,
    ) -> ConnectionTestResult:
        try:
            import mysql.connector
            from mysql.connector import Error as MySqlError
        except ImportError as exc:
            raise DriverConfigurationError("MySQL connector is not installed.") from exc

        timeout_seconds = max(1, timeout_ms // 1000)

        try:
            mysql_connection = await asyncio.to_thread(
                mysql.connector.connect,
                host=connection.host,
                port=connection.port,
                database=connection.database_name,
                user=connection.username,
                password=credentials.password,
                connection_timeout=timeout_seconds,
                ssl_disabled=not connection.tls_required,
            )
            try:
                cursor = mysql_connection.cursor()
                try:
                    await asyncio.to_thread(cursor.execute, "select 1")
                finally:
                    await asyncio.to_thread(cursor.close)
            finally:
                await asyncio.to_thread(mysql_connection.close)
        except MySqlError:
            return ConnectionTestResult(
                status="failed",
                message="MySQL connection failed.",
            )

        return ConnectionTestResult(status="ok", message="MySQL connection verified.")

    async def introspect_schema(
        self, connection: ConnectionMetadata
    ) -> SchemaIntrospectionResult:
        raise DriverNotImplementedError(
            "MySQL schema introspection is scheduled for the introspection milestone."
        )

    async def execute_readonly(
        self,
        connection: ConnectionMetadata,
        sql: str,
        row_limit: int,
        timeout_ms: int,
    ) -> ReadonlyQueryResult:
        raise DriverNotImplementedError(
            "MySQL readonly execution is scheduled for the connection milestone."
        )
