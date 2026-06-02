from app.drivers.base import (
    ConnectionMetadata,
    ConnectionTestResult,
    DatabaseDriver,
    DriverNotImplementedError,
    ReadonlyQueryResult,
    SchemaIntrospectionResult,
)
from app.models import Engine


class SqlServerDriver(DatabaseDriver):
    engine = Engine.sqlserver

    async def test_connection(
        self, connection: ConnectionMetadata
    ) -> ConnectionTestResult:
        return ConnectionTestResult(
            status="not_implemented",
            message="SQL Server live connection is scheduled for the connection milestone.",
        )

    async def introspect_schema(
        self, connection: ConnectionMetadata
    ) -> SchemaIntrospectionResult:
        return SchemaIntrospectionResult(engine=self.engine, tables=[])

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
