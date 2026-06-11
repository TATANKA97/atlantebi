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
    database_name: str
    engine_version: str
    schema_hash: str
    coverage_status: Literal["ok", "partial", "warning", "blocked"]
    tables: list["SchemaTableMetadata"]
    foreign_keys: list["SchemaForeignKeyMetadata"]
    unique_constraints: list["SchemaUniqueConstraintMetadata"] = field(default_factory=list)
    check_constraints: list["SchemaCheckConstraintMetadata"] = field(default_factory=list)
    default_constraints: list["SchemaDefaultConstraintMetadata"] = field(default_factory=list)
    indexes: list["SchemaIndexMetadata"] = field(default_factory=list)
    coverage_warnings: list["SchemaCoverageWarning"] = field(default_factory=list)


@dataclass(frozen=True)
class SchemaColumnMetadata:
    name: str
    data_type: str
    ordinal_position: int
    is_nullable: bool
    native_type: str | None = None
    normalized_type: str | None = None
    declared_type_schema: str | None = None
    declared_type_name: str | None = None
    declared_type_is_user_defined: bool | None = None
    declared_type_is_assembly: bool | None = None
    declared_type_available: bool = False
    technical_role: Literal[
        "identifier",
        "date",
        "boolean",
        "quantity_candidate",
        "money_candidate",
        "numeric",
        "text",
        "binary",
        "xml",
        "unknown",
    ] = "unknown"
    max_length: int | None = None
    numeric_precision: int | None = None
    numeric_scale: int | None = None
    datetime_precision: int | None = None
    is_identity: bool = False
    is_computed: bool = False
    declared_type: str | None = None
    default_value: str | None = None
    collation: str | None = None
    identity_seed: str | None = None
    identity_increment: str | None = None
    computed_expression: str | None = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_unique_member: bool = False
    comment: str | None = None


@dataclass(frozen=True)
class SchemaPrimaryKeyMetadata:
    name: str
    columns: list[str]


@dataclass(frozen=True)
class SchemaViewLineageDependency:
    source: Literal["dm_sql_referenced_entities", "sql_expression_dependencies"]
    referenced_class: str
    referencing_column: str | None = None
    referenced_server_name: str | None = None
    referenced_database_name: str | None = None
    referenced_schema_name: str | None = None
    referenced_entity_name: str | None = None
    referenced_column_name: str | None = None
    is_selected: bool | None = None
    is_updated: bool | None = None
    is_select_all: bool | None = None
    is_all_columns_found: bool | None = None
    is_caller_dependent: bool | None = None
    is_ambiguous: bool | None = None
    is_incomplete: bool | None = None
    is_schema_bound_reference: bool | None = None


@dataclass(frozen=True)
class SchemaTableMetadata:
    table_schema: str
    name: str
    table_type: Literal["base_table", "view"]
    columns: list[SchemaColumnMetadata] = field(default_factory=list)
    primary_key: SchemaPrimaryKeyMetadata | None = None
    database_name: str | None = None
    object_id: int | None = None
    is_system_object: bool = False
    row_count_estimate: int | None = None
    comment: str | None = None
    view_definition_available: bool | None = None
    view_definition: str | None = None
    definition_hash: str | None = None
    lineage_available: bool | None = None
    view_lineage: list[SchemaViewLineageDependency] = field(default_factory=list)


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
    is_disabled: bool = False
    is_not_trusted: bool = False
    source: Literal["db_fk"] = "db_fk"
    verified_by_db: bool = True


@dataclass(frozen=True)
class SchemaUniqueConstraintMetadata:
    name: str
    schema_name: str
    table_name: str
    columns: list[str]


@dataclass(frozen=True)
class SchemaCheckConstraintMetadata:
    name: str
    schema_name: str
    table_name: str
    definition: str | None
    is_disabled: bool = False
    is_not_trusted: bool = False


@dataclass(frozen=True)
class SchemaDefaultConstraintMetadata:
    name: str
    schema_name: str
    table_name: str
    column_name: str
    definition: str | None


@dataclass(frozen=True)
class SchemaIndexColumnMetadata:
    name: str
    ordinal_position: int
    is_descending: bool
    is_included: bool = False


@dataclass(frozen=True)
class SchemaIndexMetadata:
    name: str
    schema_name: str
    table_name: str
    object_type: Literal["table", "view"]
    is_unique: bool
    is_primary_key: bool
    index_type: str
    key_columns: list[SchemaIndexColumnMetadata]
    included_columns: list[SchemaIndexColumnMetadata] = field(default_factory=list)
    filter_definition: str | None = None
    is_disabled: bool = False


@dataclass(frozen=True)
class SchemaCoverageWarning:
    code: Literal[
        "ROW_COUNT_ESTIMATE_UNAVAILABLE",
        "VIEW_DEFINITION_MISSING",
        "VIEW_DEFINITION_PERMISSION_DENIED",
        "NO_VIEW_DEFINITION_PERMISSION",
        "PARTIAL_METADATA_VISIBILITY_POSSIBLE",
        "INDEX_METADATA_UNAVAILABLE",
        "NO_FOREIGN_KEYS_FOUND",
        "VIEW_LINEAGE_NOT_AVAILABLE",
        "VIEW_LINEAGE_PARTIAL",
        "VIEW_LINEAGE_PERMISSION_DENIED",
        "VIEW_LINEAGE_UNRESOLVED_REFERENCE",
        "COLUMN_DECLARED_TYPE_UNAVAILABLE",
        "COLUMN_DECLARED_TYPE_SCHEMA_UNAVAILABLE",
        "COLUMN_OBJECT_MAPPING_MISSING",
    ]
    severity: Literal["info", "warning"]
    message: str
    object_schema: str | None = None
    object_name: str | None = None


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
