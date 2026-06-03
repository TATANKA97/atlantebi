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


AZURE_SQL_DOMAIN_SUFFIX = ".database.windows.net"


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

        try:
            sql_connection = await asyncio.to_thread(
                pyodbc.connect,
                ";".join(parts),
                autocommit=True,
                timeout=timeout_seconds,
            )
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
        self, connection: ConnectionMetadata
    ) -> SchemaIntrospectionResult:
        raise DriverNotImplementedError(
            "SQL Server schema introspection is scheduled for the introspection milestone."
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
