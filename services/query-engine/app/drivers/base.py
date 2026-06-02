from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Protocol

from app.models import Engine

ConnectionTestStatus = Literal["ok", "failed", "not_implemented"]


class DriverNotImplementedError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConnectionMetadata:
    tenant_id: str
    connection_id: str
    engine: Engine
    host: str
    port: int
    database_name: str
    secret_ref: str
    tls_required: bool
    tls_server_name: str | None


@dataclass(frozen=True)
class ConnectionTestResult:
    status: ConnectionTestStatus
    message: str


@dataclass(frozen=True)
class SchemaIntrospectionResult:
    engine: Engine
    tables: list[str]


@dataclass(frozen=True)
class ReadonlyQueryResult:
    columns: list[str]
    row_count: int
    truncated: bool


class DatabaseDriver(ABC):
    engine: Engine

    @abstractmethod
    async def test_connection(
        self, connection: ConnectionMetadata
    ) -> ConnectionTestResult:
        raise NotImplementedError

    @abstractmethod
    async def introspect_schema(
        self, connection: ConnectionMetadata
    ) -> SchemaIntrospectionResult:
        raise NotImplementedError

    @abstractmethod
    async def execute_readonly(
        self,
        connection: ConnectionMetadata,
        sql: str,
        row_limit: int,
        timeout_ms: int,
    ) -> ReadonlyQueryResult:
        raise NotImplementedError


class DriverFactory(Protocol):
    def __call__(self) -> DatabaseDriver:
        raise NotImplementedError
