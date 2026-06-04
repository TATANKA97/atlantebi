from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.models import Engine

ConnectionTestStatus = Literal["ok", "failed", "engine_error"]


class DriverNotImplementedError(RuntimeError):
    pass


class DriverConfigurationError(RuntimeError):
    pass


class DriverIntrospectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConnectionMetadata:
    tenant_id: str
    connection_id: str
    name: str
    engine: Engine
    network_mode: str
    host: str
    port: int
    database_name: str
    username: str
    secret_ref: str
    tls_required: bool
    trust_server_certificate: bool
    tls_server_name: str | None


@dataclass(frozen=True)
class DatabaseCredentials:
    password: str


@dataclass(frozen=True)
class ConnectionTestResult:
    status: ConnectionTestStatus
    message: str


@dataclass(frozen=True)
class SchemaIntrospectionResult:
    engine: Engine
    tables: list["SchemaTableMetadata"]
    foreign_keys: list["SchemaForeignKeyMetadata"]


@dataclass(frozen=True)
class SchemaColumnMetadata:
    name: str
    data_type: str
    ordinal_position: int
    is_nullable: bool
    max_length: int | None = None
    numeric_precision: int | None = None
    numeric_scale: int | None = None
    datetime_precision: int | None = None
    is_identity: bool = False
    is_computed: bool = False


@dataclass(frozen=True)
class SchemaPrimaryKeyMetadata:
    name: str
    columns: list[str]


@dataclass(frozen=True)
class SchemaTableMetadata:
    table_schema: str
    name: str
    table_type: Literal["base_table", "view"]
    columns: list[SchemaColumnMetadata] = field(default_factory=list)
    primary_key: SchemaPrimaryKeyMetadata | None = None


@dataclass(frozen=True)
class SchemaForeignKeyMetadata:
    name: str
    from_schema: str
    from_table: str
    from_columns: list[str]
    to_schema: str
    to_table: str
    to_columns: list[str]
    on_delete: str
    on_update: str


@dataclass(frozen=True)
class ReadonlyQueryResult:
    columns: list[str]
    row_count: int
    truncated: bool


class DatabaseDriver(ABC):
    engine: Engine

    @abstractmethod
    async def test_connection(
        self,
        connection: ConnectionMetadata,
        credentials: DatabaseCredentials,
        timeout_ms: int,
    ) -> ConnectionTestResult:
        raise NotImplementedError

    @abstractmethod
    async def introspect_schema(
        self,
        connection: ConnectionMetadata,
        credentials: DatabaseCredentials,
        timeout_ms: int,
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
