from app.drivers.base import (
    ConnectionMetadata,
    ConnectionTestResult,
    DatabaseDriver,
    ReadonlyQueryResult,
    SchemaIntrospectionResult,
)
from app.models import Engine


class MySqlDriver(DatabaseDriver):
    engine = Engine.mysql

    async def test_connection(
        self, connection: ConnectionMetadata
    ) -> ConnectionTestResult:
        return ConnectionTestResult(
            status="not_implemented",
            message="MySQL live connection is scheduled for the connection milestone.",
        )

    async def introspect_schema(
        self, connection: ConnectionMetadata
    ) -> SchemaIntrospectionResult:
        return SchemaIntrospectionResult(engine=self.engine, tables=[])

    async def execute_readonly(
        self, connection: ConnectionMetadata, sql: str, row_limit: int
    ) -> ReadonlyQueryResult:
        return ReadonlyQueryResult(columns=[], row_count=0, truncated=False)
