from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


NonEmptyString = Annotated[str, Field(min_length=1)]
JsonUUID = Annotated[UUID, Field(strict=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(*args, **kwargs)

    def model_dump_json(self, *args: Any, **kwargs: Any) -> str:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump_json(*args, **kwargs)


class Engine(StrEnum):
    sqlserver = "sqlserver"
    mysql = "mysql"


class NetworkMode(StrEnum):
    public_allowlist = "public_allowlist"
    vpn = "vpn"


class ConnectionStatus(StrEnum):
    draft = "draft"
    ready = "ready"
    failed = "failed"
    disabled = "disabled"


class ConnectionTestStatus(StrEnum):
    ok = "ok"
    failed = "failed"
    engine_error = "engine_error"


class ConnectionMetadataInput(StrictModel):
    tenant_id: JsonUUID
    connection_id: JsonUUID
    name: str = Field(min_length=2, max_length=160)
    engine: Engine = Field(strict=False)
    network_mode: NetworkMode = Field(strict=False)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    database_name: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=255)
    tls_required: bool
    trust_server_certificate: bool = False
    tls_server_name: str | None = Field(default=None, min_length=1, max_length=255)
    secret_ref: str = Field(
        pattern=r"^gcp-secret-manager://projects/[^/]+/secrets/[^/]+(/versions/[^/]+)?$"
    )
    status: ConnectionStatus = Field(strict=False)


class DatabaseCredentialsInput(StrictModel):
    password: str = Field(min_length=1)


class ConnectionTestRequest(StrictModel):
    connection: ConnectionMetadataInput
    timeout_ms: int = Field(ge=1000, le=120000)


class ConnectionTestResponse(StrictModel):
    status: ConnectionTestStatus = Field(strict=False)
    message: str = Field(min_length=1, max_length=500)
    checked_at: str
    duration_ms: int = Field(ge=0)
    sanitized_error: str = Field(default=None, min_length=1, max_length=500)


class SchemaIntrospectionStatus(StrEnum):
    ok = "ok"
    failed = "failed"
    engine_error = "engine_error"


class SchemaCoverageState(StrEnum):
    complete = "complete"
    partial = "partial"
    unknown = "unknown"


class SchemaIntrospectionRequest(StrictModel):
    connection: ConnectionMetadataInput
    timeout_ms: int = Field(ge=1000, le=120000)


class SchemaColumnMetadata(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    data_type: str = Field(min_length=1, max_length=255)
    declared_type: str | None = Field(default=None, min_length=1, max_length=255)
    native_type: str | None = Field(default=None, min_length=1, max_length=255)
    normalized_type: str | None = Field(default=None, min_length=1, max_length=255)
    declared_type_schema: str | None = Field(default=None, min_length=1, max_length=255)
    declared_type_name: str | None = Field(default=None, min_length=1, max_length=255)
    declared_type_is_user_defined: bool | None = None
    declared_type_is_assembly: bool | None = None
    ordinal_position: int = Field(ge=1)
    is_nullable: bool
    max_length: int | None = Field(default=None, ge=-1)
    numeric_precision: int | None = Field(default=None, ge=0)
    numeric_scale: int | None = Field(default=None, ge=0)
    datetime_precision: int | None = Field(default=None, ge=0)
    is_identity: bool = False
    is_computed: bool = False
    default_value: str | None = Field(default=None, min_length=1)
    collation: str | None = Field(default=None, min_length=1, max_length=255)
    identity_seed: str | None = Field(default=None, min_length=1, max_length=80)
    identity_increment: str | None = Field(default=None, min_length=1, max_length=80)
    computed_expression: str | None = Field(default=None, min_length=1)
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_unique_member: bool = False
    comment: str | None = Field(default=None, min_length=1)


class SchemaPrimaryKeyMetadata(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    columns: list[NonEmptyString] = Field(min_length=1)


class SchemaViewLineageDependency(StrictModel):
    source: Literal["dm_sql_referenced_entities", "sql_expression_dependencies"]
    referencing_column: str | None = Field(default=None, min_length=1, max_length=255)
    referenced_server_name: str | None = Field(default=None, min_length=1, max_length=255)
    referenced_database_name: str | None = Field(default=None, min_length=1, max_length=255)
    referenced_schema_name: str | None = Field(default=None, min_length=1, max_length=255)
    referenced_entity_name: str | None = Field(default=None, min_length=1, max_length=255)
    referenced_column_name: str | None = Field(default=None, min_length=1, max_length=255)
    referenced_class: str = Field(min_length=1, max_length=80)
    is_selected: bool | None = None
    is_updated: bool | None = None
    is_select_all: bool | None = None
    is_all_columns_found: bool | None = None
    is_caller_dependent: bool | None = None
    is_ambiguous: bool | None = None
    is_incomplete: bool | None = None
    is_schema_bound_reference: bool | None = None


class SchemaTableMetadata(StrictModel):
    table_schema: str = Field(alias="schema", min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    table_type: Literal["base_table", "view"]
    columns: list[SchemaColumnMetadata] = Field(max_length=50_000)
    primary_key: SchemaPrimaryKeyMetadata | None = None
    database_name: str | None = Field(default=None, min_length=1, max_length=255)
    object_id: int | None = Field(default=None, ge=1)
    is_system_object: bool = False
    row_count_estimate: int | None = Field(default=None, ge=0)
    comment: str | None = Field(default=None, min_length=1)
    view_definition_available: bool | None = None
    view_definition: str | None = Field(default=None, min_length=1)
    definition_hash: str | None = Field(default=None, min_length=64, max_length=64)
    lineage_available: bool | None = None
    view_lineage: list[SchemaViewLineageDependency] = Field(
        default_factory=list,
        max_length=100_000,
    )


class SchemaForeignKeyMetadata(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    from_schema: str = Field(min_length=1, max_length=255)
    from_table: str = Field(min_length=1, max_length=255)
    from_columns: list[NonEmptyString] = Field(min_length=1)
    to_schema: str = Field(min_length=1, max_length=255)
    to_table: str = Field(min_length=1, max_length=255)
    to_columns: list[NonEmptyString] = Field(min_length=1)
    on_delete: str = Field(min_length=1, max_length=40)
    on_update: str = Field(min_length=1, max_length=40)
    is_disabled: bool = False
    is_not_trusted: bool = False
    source: Literal["db_fk"] = "db_fk"
    verified_by_db: bool = True


class SchemaUniqueConstraintMetadata(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    schema_name: str = Field(min_length=1, max_length=255)
    table_name: str = Field(min_length=1, max_length=255)
    columns: list[NonEmptyString] = Field(min_length=1)


class SchemaCheckConstraintMetadata(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    schema_name: str = Field(min_length=1, max_length=255)
    table_name: str = Field(min_length=1, max_length=255)
    definition: str | None = Field(default=None, min_length=1)
    is_disabled: bool = False
    is_not_trusted: bool = False


class SchemaDefaultConstraintMetadata(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    schema_name: str = Field(min_length=1, max_length=255)
    table_name: str = Field(min_length=1, max_length=255)
    column_name: str = Field(min_length=1, max_length=255)
    definition: str | None = Field(default=None, min_length=1)


class SchemaIndexColumnMetadata(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    ordinal_position: int = Field(ge=1)
    is_descending: bool
    is_included: bool = False


class SchemaIndexMetadata(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    schema_name: str = Field(min_length=1, max_length=255)
    table_name: str = Field(min_length=1, max_length=255)
    is_unique: bool
    is_primary_key: bool
    index_type: str = Field(min_length=1, max_length=80)
    key_columns: list[SchemaIndexColumnMetadata] = Field(default_factory=list)
    included_columns: list[SchemaIndexColumnMetadata] = Field(default_factory=list)
    filter_definition: str | None = Field(default=None, min_length=1)
    is_disabled: bool = False


class SchemaCoverageWarning(StrictModel):
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
    message: str = Field(min_length=1, max_length=500)
    object_schema: str | None = Field(default=None, min_length=1, max_length=255)
    object_name: str | None = Field(default=None, min_length=1, max_length=255)


class SchemaIntrospectionResponse(StrictModel):
    status: SchemaIntrospectionStatus = Field(strict=False)
    message: str = Field(min_length=1, max_length=500)
    introspected_at: str
    duration_ms: int = Field(ge=0)
    engine: Engine | None = Field(default=None, strict=False)
    database_name: str | None = Field(default=None, min_length=1, max_length=255)
    engine_version: str | None = Field(default=None, min_length=1, max_length=500)
    schema_hash: str | None = Field(default=None, min_length=64, max_length=64)
    coverage_state: SchemaCoverageState | None = Field(default=None, strict=False)
    tables: list[SchemaTableMetadata] = Field(default_factory=list, max_length=5_000)
    foreign_keys: list[SchemaForeignKeyMetadata] = Field(
        default_factory=list,
        max_length=100_000,
    )
    unique_constraints: list[SchemaUniqueConstraintMetadata] = Field(
        default_factory=list,
        max_length=100_000,
    )
    check_constraints: list[SchemaCheckConstraintMetadata] = Field(
        default_factory=list,
        max_length=100_000,
    )
    default_constraints: list[SchemaDefaultConstraintMetadata] = Field(
        default_factory=list,
        max_length=100_000,
    )
    indexes: list[SchemaIndexMetadata] = Field(
        default_factory=list,
        max_length=100_000,
    )
    coverage_warnings: list[SchemaCoverageWarning] = Field(
        default_factory=list,
        max_length=20_000,
    )
    sanitized_error: str = Field(default=None, min_length=1, max_length=500)


class ChartType(StrEnum):
    table = "table"
    kpi_number = "kpi_number"
    bar = "bar"
    horizontal_bar = "horizontal_bar"
    grouped_bar = "grouped_bar"
    stacked_bar = "stacked_bar"
    line = "line"
    area = "area"
    combo_bar_line = "combo_bar_line"
    pie = "pie"
    donut = "donut"
    scatter = "scatter"


class ColumnFormat(StrictModel):
    type: Literal[
        "text",
        "integer",
        "decimal",
        "currency",
        "percentage",
        "date",
        "date_bucket",
        "identifier",
    ]
    currency: Literal["EUR"] = None
    decimals: int = Field(default=None, ge=0, le=6)


class ChartDisplay(StrictModel):
    show_legend: bool = True
    show_data_labels: bool = False
    sort: Literal["x_asc", "x_desc", "y_asc", "y_desc", "none"] = "none"
    limit: int = Field(default=20, ge=1, le=100)


class ChartSpec(StrictModel):
    type: ChartType = Field(strict=False)
    title: str = Field(min_length=1, max_length=160)
    x: NonEmptyString = None
    y: list[NonEmptyString] = Field(default=None, max_length=8)
    series: NonEmptyString = None
    formatting: dict[NonEmptyString, ColumnFormat] = Field(default_factory=dict)
    display: ChartDisplay = Field(default_factory=ChartDisplay)


class VerificationStatus(StrEnum):
    pass_ = "pass"
    warn = "warn"
    fail = "fail"
    skip = "skip"
    engine_error = "engine_error"


class VerificationCheck(StrictModel):
    type: Literal[
        "static_validation",
        "tables_in_layer",
        "columns_in_layer",
        "dry_run",
        "row_count_sanity",
        "null_negative_sanity",
        "duplicate_output_rows",
        "join_amplification",
        "total_vs_breakdown",
        "header_detail_reconciliation",
        "business_anchor_plausibility",
        "metric_consistency",
        "historical_plausibility",
        "privacy",
    ]
    status: VerificationStatus = Field(strict=False)
    message: str = Field(min_length=1, max_length=500)
    evidence: dict[NonEmptyString, str | int | float | bool] = Field(default_factory=dict)


class VerificationSummary(StrictModel):
    status: VerificationStatus = Field(strict=False)
    checks: list[VerificationCheck]
    confidence_label: Literal["high", "medium", "low", "blocked"]
    result_visible: bool


class Relationship(StrictModel):
    id: JsonUUID
    from_table: str = Field(min_length=1)
    from_columns: list[NonEmptyString] = Field(min_length=1)
    to_table: str = Field(min_length=1)
    to_columns: list[NonEmptyString] = Field(min_length=1)
    cardinality: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"]
    semantic_status: Literal["confirmed", "suggested", "rejected"]
    source: Literal["database_fk", "user_validated", "ai_suggested"]


class SemanticColumn(StrictModel):
    name: str = Field(min_length=1)
    data_type: str = Field(min_length=1)
    business_name: NonEmptyString = None
    role: Literal["dimension", "measure", "date", "identifier", "unknown"]
    format: ColumnFormat = None
    pii: bool = False


class SemanticTable(StrictModel):
    name: str = Field(min_length=1)
    table_schema: str = Field(default="dbo", alias="schema", min_length=1)
    business_name: NonEmptyString = None
    active: bool
    columns: list[SemanticColumn]


class SemanticMetric(StrictModel):
    id: JsonUUID
    name: str = Field(min_length=1)
    expression: str = Field(min_length=1)
    grain: list[NonEmptyString] = Field(default_factory=list)
    format: ColumnFormat


class ExpectedRange(StrictModel):
    min: float = None
    max: float = None


class BusinessAnchor(StrictModel):
    id: JsonUUID
    name: str = Field(min_length=1)
    metric_id: JsonUUID
    expected_range: ExpectedRange
    period: Literal["daily", "monthly", "quarterly", "yearly"]


class SemanticLayer(StrictModel):
    tenant_id: JsonUUID
    version_id: JsonUUID
    version: int = Field(gt=0)
    status: Literal["draft", "active", "archived"]
    engine: Engine = Field(strict=False)
    tables: list[SemanticTable]
    relationships: list[Relationship]
    metrics: list[SemanticMetric]
    business_anchors: list[BusinessAnchor]


class QueryPermission(StrictModel):
    can_view_sql: bool
    can_save_widget: bool


class QueryExecutionOptions(StrictModel):
    mode: Literal["plan_only", "run"]
    row_limit: int = Field(ge=1, le=5000)
    timeout_ms: int = Field(ge=1000, le=120000)


class QueryRequest(StrictModel):
    tenant_id: JsonUUID
    connection_id: JsonUUID
    user_id: JsonUUID
    question: str = Field(min_length=1, max_length=1000)
    semantic_layer: SemanticLayer
    permissions: QueryPermission
    execution: QueryExecutionOptions


class ResultColumn(StrictModel):
    name: str = Field(min_length=1)
    data_type: str = Field(min_length=1)
    format: ColumnFormat


class ResultMetadata(StrictModel):
    columns: list[ResultColumn]
    row_count: int = Field(ge=0)
    truncated: bool


class SqlOutput(StrictModel):
    dialect: Engine = Field(strict=False)
    statement: str = Field(min_length=1)
    visible_to_user: bool


class QueryResponse(StrictModel):
    query_id: JsonUUID
    status: Literal["completed", "needs_clarification", "failed"]
    sql: SqlOutput = None
    result_metadata: ResultMetadata
    chart: ChartSpec = None
    verification: VerificationSummary
    sanitized_error: str = Field(default=None, min_length=1, max_length=500)


class HealthResponse(StrictModel):
    service: str
    status: Literal["ok"]
    version: str
