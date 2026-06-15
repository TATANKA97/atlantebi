import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import RFC_4122, UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    FiniteFloat,
    field_validator,
    model_validator,
)


NonEmptyString = Annotated[str, Field(min_length=1)]
JsonUUID = Annotated[UUID, Field(strict=False)]
_CANONICAL_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-"
    r"[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_RFC3339_DATETIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _validate_canonical_uuid(value: object) -> object:
    if isinstance(value, UUID):
        if value.variant != RFC_4122:
            raise ValueError("UUID must use the RFC 4122 variant")
        return value
    if not isinstance(value, str) or not _CANONICAL_UUID_PATTERN.fullmatch(value):
        raise ValueError("UUID must use canonical hyphenated RFC form")
    parsed = UUID(value)
    if parsed.variant != RFC_4122:
        raise ValueError("UUID must use the RFC 4122 variant")
    return value


CanonicalJsonUUID = Annotated[
    UUID,
    BeforeValidator(_validate_canonical_uuid),
    Field(strict=False),
]


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


class SchemaCoverageStatus(StrEnum):
    ok = "ok"
    partial = "partial"
    warning = "warning"
    blocked = "blocked"


class SchemaTechnicalRole(StrEnum):
    identifier = "identifier"
    date = "date"
    boolean = "boolean"
    quantity_candidate = "quantity_candidate"
    money_candidate = "money_candidate"
    numeric = "numeric"
    text = "text"
    binary = "binary"
    xml = "xml"
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
    declared_type_available: bool
    technical_role: SchemaTechnicalRole = Field(strict=False)
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
    is_single_column_unique: bool = False
    is_composite_unique_member: bool = False
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
    constraint_name: str = Field(min_length=1, max_length=255)
    from_schema: str = Field(min_length=1, max_length=255)
    from_table: str = Field(min_length=1, max_length=255)
    from_columns: list[NonEmptyString] = Field(min_length=1)
    to_schema: str = Field(min_length=1, max_length=255)
    to_table: str = Field(min_length=1, max_length=255)
    to_columns: list[NonEmptyString] = Field(min_length=1)
    delete_rule: str = Field(min_length=1, max_length=40)
    update_rule: str = Field(min_length=1, max_length=40)
    is_disabled: bool = False
    is_not_trusted: bool = False
    source: Literal["db_fk"] = "db_fk"
    verified_by_db: Literal[True] = True


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
    object_type: Literal["table", "view"]
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


class SchemaImportSummary(StrictModel):
    database_name: str = Field(min_length=1, max_length=255)
    engine: Engine = Field(strict=False)
    engine_version: str = Field(min_length=1, max_length=500)
    schema_hash: str = Field(min_length=64, max_length=64)
    coverage_status: SchemaCoverageStatus = Field(strict=False)
    captured_at: str
    duration_ms: int = Field(ge=0)
    total_objects: int = Field(ge=0)
    total_tables: int = Field(ge=0)
    total_views: int = Field(ge=0)
    total_columns: int = Field(ge=0)
    queryable_objects: int = Field(ge=0)
    non_queryable_objects: int = Field(ge=0)
    queryable_columns: int = Field(ge=0)
    non_queryable_columns: int = Field(ge=0)
    primary_keys_count: int = Field(ge=0)
    foreign_keys_count: int = Field(ge=0)
    unique_constraints_count: int = Field(ge=0)
    check_constraints_count: int = Field(ge=0)
    default_constraints_count: int = Field(ge=0)
    indexes_total_count: int = Field(ge=0)
    table_indexes_count: int = Field(ge=0)
    view_indexes_count: int = Field(ge=0)
    unique_indexes_count: int = Field(ge=0)
    filtered_indexes_count: int = Field(ge=0)
    included_columns_indexes_count: int = Field(ge=0)
    views_total: int = Field(ge=0)
    views_with_definition_count: int = Field(ge=0)
    views_without_definition_count: int = Field(ge=0)
    views_with_lineage_count: int = Field(ge=0)
    views_with_partial_lineage_count: int = Field(ge=0)
    views_without_lineage_count: int = Field(ge=0)
    view_lineage_dependencies_count: int = Field(ge=0)
    columns_with_declared_type_count: int = Field(ge=0)
    columns_without_declared_type_count: int = Field(ge=0)
    columns_with_default_count: int = Field(ge=0)
    computed_columns_count: int = Field(ge=0)
    identity_columns_count: int = Field(ge=0)
    pii_columns_count: int = Field(ge=0)
    excluded_columns_count: int = Field(ge=0)
    sensitive_columns_count: int = Field(ge=0)
    coverage_warnings_count: int = Field(ge=0)
    coverage_warnings_by_code: dict[
        Annotated[str, Field(min_length=1, max_length=100)],
        Annotated[int, Field(ge=1)],
    ]

    @field_validator("captured_at")
    @classmethod
    def validate_captured_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("captured_at must be an ISO 8601 datetime") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("captured_at must include a UTC offset")
        return value


class SchemaIntrospectionResponse(StrictModel):
    status: SchemaIntrospectionStatus = Field(strict=False)
    message: str = Field(min_length=1, max_length=500)
    introspected_at: str
    duration_ms: int = Field(ge=0)
    engine: Engine | None = Field(default=None, strict=False)
    database_name: str | None = Field(default=None, min_length=1, max_length=255)
    engine_version: str | None = Field(default=None, min_length=1, max_length=500)
    schema_hash: str | None = Field(default=None, min_length=64, max_length=64)
    snapshot_hash: str | None = Field(default=None, min_length=64, max_length=64)
    coverage_status: SchemaCoverageStatus = Field(strict=False)
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


Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class QueryabilityCandidateKey(StrictModel):
    key_type: Literal["primary_key", "unique_constraint", "unique_index"]
    name: str = Field(min_length=1, max_length=255)
    columns: list[NonEmptyString] = Field(min_length=1)
    eligible_for_cardinality: bool


class QueryabilityColumn(StrictModel):
    column_key: Sha256
    name: str = Field(min_length=1, max_length=255)
    ordinal_position: int = Field(ge=1)
    native_type: str | None = Field(default=None, min_length=1, max_length=255)
    normalized_type: str | None = Field(default=None, min_length=1, max_length=255)
    technical_role: SchemaTechnicalRole = Field(strict=False)
    nullable: bool
    queryability_status: Literal["queryable", "excluded"]
    sensitivity: Literal["none", "pii", "sensitive"]
    reason_codes: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        max_length=20
    )


class QueryabilityNode(StrictModel):
    node_key: Sha256
    database_name: str = Field(min_length=1, max_length=255)
    schema_name: str = Field(min_length=1, max_length=255)
    object_name: str = Field(min_length=1, max_length=255)
    object_type: Literal["table", "view"]
    queryability_status: Literal["queryable", "excluded"]
    reason_codes: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        max_length=100
    )
    bridge_candidate: bool
    candidate_keys: list[QueryabilityCandidateKey] = Field(max_length=10_000)
    columns: list[QueryabilityColumn] = Field(max_length=50_000)
    view_definition_available: bool | None = None
    view_lineage_status: Literal["complete", "partial", "unavailable"] | None = None
    view_column_lineage_status: (
        Literal["complete", "partial", "unavailable"] | None
    ) = None


class QueryabilityColumnPair(StrictModel):
    ordinal_position: int = Field(ge=1)
    from_column: str = Field(min_length=1, max_length=255)
    from_column_key: Sha256
    to_column: str = Field(min_length=1, max_length=255)
    to_column_key: Sha256


class QueryabilityForeignKeyEdge(StrictModel):
    edge_key: Sha256
    edge_type: Literal["fk_join"]
    constraint_name: str = Field(min_length=1, max_length=255)
    from_node_key: Sha256
    to_node_key: Sha256
    column_pairs: list[QueryabilityColumnPair] = Field(min_length=1)
    relationship_shape: Literal["one_to_one", "many_to_one"]
    child_to_parent: Literal["zero_or_one", "exactly_one"]
    parent_to_child: Literal["zero_or_one", "zero_or_many"]
    nullable_fk: bool
    self_reference: bool
    verified_by_db: bool
    enforcement_status: Literal["enabled", "disabled"]
    validation_status: Literal["trusted", "untrusted"]
    automatic_join_allowed: bool
    reason_codes: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        max_length=100
    )


class QueryabilityViewDependencyEdge(StrictModel):
    edge_key: Sha256
    edge_type: Literal["view_depends_on"]
    from_node_key: Sha256
    to_node_key: Sha256 | None = None
    source: Literal["dm_sql_referenced_entities", "sql_expression_dependencies"]
    referenced_server_name: str | None = Field(default=None, min_length=1, max_length=255)
    referenced_database_name: str | None = Field(
        default=None, min_length=1, max_length=255
    )
    referenced_schema_name: str | None = Field(default=None, min_length=1, max_length=255)
    referenced_object_name: str | None = Field(default=None, min_length=1, max_length=255)
    resolution_status: Literal["resolved", "external", "unresolved"]
    automatic_join_allowed: Literal[False]
    reason_codes: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        max_length=100
    )


class QueryabilityViewColumnEdge(StrictModel):
    edge_key: Sha256
    edge_type: Literal["view_column_derives_from"]
    from_node_key: Sha256
    from_column_key: Sha256
    to_node_key: Sha256 | None = None
    to_column_key: Sha256 | None = None
    source: Literal["dm_sql_referenced_entities", "sql_expression_dependencies"]
    referenced_server_name: str | None = Field(default=None, min_length=1, max_length=255)
    referenced_database_name: str | None = Field(
        default=None, min_length=1, max_length=255
    )
    referenced_schema_name: str | None = Field(default=None, min_length=1, max_length=255)
    referenced_object_name: str | None = Field(default=None, min_length=1, max_length=255)
    referenced_column_name: str | None = Field(default=None, min_length=1, max_length=255)
    resolution_status: Literal["resolved", "external", "unresolved"]
    lineage_status: Literal["complete", "partial"]
    automatic_join_allowed: Literal[False]
    reason_codes: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        max_length=100
    )


QueryabilityEdge = Annotated[
    QueryabilityForeignKeyEdge
    | QueryabilityViewDependencyEdge
    | QueryabilityViewColumnEdge,
    Field(discriminator="edge_type"),
]


class QueryabilityGraphArtifact(StrictModel):
    contract_version: Literal["queryability_graph.v1"]
    tenant_id: JsonUUID
    connection_id: JsonUUID
    schema_snapshot_id: JsonUUID
    engine: Literal["sqlserver"]
    schema_hash: Sha256
    snapshot_hash: Sha256
    graph_input_hash: Sha256
    derivation_key: Sha256
    graph_hash: Sha256
    builder_version: str = Field(min_length=1, max_length=100)
    policy_version: str = Field(min_length=1, max_length=100)
    status: Literal["complete", "partial", "blocked"]
    status_reasons: list[
        Annotated[str, Field(min_length=1, max_length=100)]
    ] = Field(max_length=100)
    semantic_status: Literal["not_initialized"]
    nodes: list[QueryabilityNode] = Field(max_length=5_000)
    edges: list[QueryabilityEdge] = Field(max_length=250_000)


class QueryabilityGraphVersion(StrictModel):
    graph_version_id: JsonUUID
    graph_version: int = Field(gt=0)
    created_at: str
    graph: QueryabilityGraphArtifact

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("created_at must be an ISO 8601 datetime") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("created_at must include a UTC offset")
        return value


class QueryabilityPathStep(StrictModel):
    edge_key: Sha256
    from_node_key: Sha256
    to_node_key: Sha256
    traversal: Literal["child_to_parent", "parent_to_child"]
    cardinality: Literal["zero_or_one", "exactly_one", "zero_or_many"]


class QueryabilityPath(StrictModel):
    steps: list[QueryabilityPathStep] = Field(min_length=1, max_length=4)
    fanout_warning: bool


class QueryabilityPathResult(StrictModel):
    status: Literal["found", "not_found", "ambiguous", "blocked"]
    paths: list[QueryabilityPath] = Field(max_length=100)
    reason_codes: list[
        Annotated[str, Field(min_length=1, max_length=100)]
    ] = Field(max_length=100)


class QueryabilityCompileRequest(StrictModel):
    tenant_id: JsonUUID
    connection_id: JsonUUID
    schema_snapshot_id: JsonUUID
    snapshot: SchemaIntrospectionResponse


class QueryabilityPathRequest(StrictModel):
    graph: QueryabilityGraphArtifact
    from_node_key: Sha256
    to_node_key: Sha256
    max_hops: int = Field(default=4, ge=1, le=4)


SemanticElementStatus = Literal[
    "system_seeded",
    "ai_proposed",
    "human_verified",
    "rejected",
    "disabled",
    "stale",
]
SemanticConfidenceLabel = Literal["high", "medium", "low", "blocked"]
CompilerEligibility = Literal[
    "eligible",
    "eligible_with_disclosure",
    "clarification_required",
    "not_eligible",
]


class SemanticTable(StrictModel):
    node_key: Sha256
    schema_name: str = Field(min_length=1, max_length=255)
    object_name: str = Field(min_length=1, max_length=255)
    object_type: Literal["table", "view"]
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=2_000)
    business_domain: str | None = Field(default=None, min_length=1, max_length=255)
    synonyms: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(
        default_factory=list,
        max_length=100,
    )
    status: SemanticElementStatus
    included: bool
    queryability_status: Literal["queryable", "excluded"]


class SemanticColumn(StrictModel):
    column_key: Sha256
    node_key: Sha256
    physical_name: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=2_000)
    synonyms: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(
        default_factory=list,
        max_length=100,
    )
    native_type: str | None = Field(default=None, min_length=1, max_length=255)
    normalized_type: str | None = Field(default=None, min_length=1, max_length=255)
    technical_role: SchemaTechnicalRole = Field(strict=False)
    semantic_role: str | None = Field(default=None, min_length=1, max_length=100)
    format_hint: Literal[
        "text",
        "integer",
        "decimal",
        "currency",
        "percentage",
        "date",
        "datetime",
        "boolean",
        "identifier",
    ] | None = None
    nullable: bool
    status: SemanticElementStatus
    included: bool
    queryability_status: Literal["queryable", "excluded"]
    inherited_sensitivity: Literal["none", "pii", "sensitive"]
    sensitivity: Literal["none", "pii", "sensitive"]


class SemanticRelationship(StrictModel):
    edge_key: Sha256
    from_node_key: Sha256
    to_node_key: Sha256
    status: SemanticElementStatus
    enabled: bool
    relationship_shape: Literal["one_to_one", "many_to_one"]
    child_to_parent: Literal["zero_or_one", "exactly_one"]
    parent_to_child: Literal["zero_or_one", "zero_or_many"]
    nullable_fk: bool
    self_reference: bool


class SemanticBusinessConcept(StrictModel):
    business_concept_key: CanonicalJsonUUID
    canonical_name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
    display_name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=2_000)
    synonyms: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(
        default_factory=list,
        max_length=100,
    )
    status: SemanticElementStatus
    provenance: Literal["system", "ai", "human"]


class SemanticAmbiguity(StrictModel):
    ambiguity_key: CanonicalJsonUUID
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,99}$")
    target_type: Literal["table", "column", "business_concept", "metric"]
    target_key: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=500)
    clarification_question: str = Field(min_length=1, max_length=500)
    status: Literal["open", "resolved"]
    provenance: Literal["ai", "human"]


class SemanticFilter(StrictModel):
    column_key: Sha256
    operator: Literal[
        "eq",
        "neq",
        "in",
        "not_in",
        "gt",
        "gte",
        "lt",
        "lte",
        "between",
        "is_null",
        "is_not_null",
    ]
    value: (
        str
        | int
        | FiniteFloat
        | bool
        | Annotated[
            list[str | int | FiniteFloat | bool],
            Field(min_length=1),
        ]
        | None
    ) = None
    value_type: Literal[
        "string",
        "integer",
        "decimal",
        "boolean",
        "date",
        "datetime",
    ]


class SemanticDimensionCompatibility(StrictModel):
    dimension_column_key: Sha256
    edge_path: list[Sha256] = Field(default_factory=list, max_length=4)
    safety: Literal["safe", "forbidden"]
    reason_code: str = Field(min_length=1, max_length=100)


class SemanticDimensionPolicy(StrictModel):
    same_grain: Literal["safe"]
    parent_many_to_one: Literal["safe"]
    child_one_to_many: Literal["forbidden"]
    bridge_or_many_to_many: Literal["forbidden"]
    self_reference: Literal["conditional"]


class SemanticMetricFormat(StrictModel):
    value_type: Literal["currency", "number", "percentage", "count", "duration"]
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    decimals: int | None = Field(default=None, ge=0, le=6)


class SemanticMetric(StrictModel):
    metric_key: CanonicalJsonUUID
    canonical_name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
    metric_definition_hash: Sha256
    business_concept_key: CanonicalJsonUUID
    metric_variant: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=2_000)
    status: SemanticElementStatus
    source_table_key: Sha256
    aggregation: Literal["count", "count_distinct", "sum", "avg", "min", "max"]
    measure_column_key: Sha256 | None = None
    grain_table_key: Sha256
    grain_column_keys: list[Sha256] = Field(min_length=1, max_length=100)
    aggregation_level: Literal["row", "entity", "period"]
    additivity: Literal["additive", "semi_additive", "non_additive"]
    default_date_column_key: Sha256 | None = None
    required_join_edge_keys: list[Sha256] = Field(default_factory=list, max_length=4)
    common_dimension_compatibility: list[SemanticDimensionCompatibility] = Field(
        default_factory=list,
        max_length=500,
    )
    dimension_policy: SemanticDimensionPolicy
    preferred_for_grains: list[Annotated[str, Field(min_length=1, max_length=100)]] = (
        Field(default_factory=list, max_length=100)
    )
    preferred_for_dimensions: list[Sha256] = Field(default_factory=list, max_length=100)
    filters: list[SemanticFilter] = Field(default_factory=list, max_length=100)
    format: SemanticMetricFormat
    synonyms: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(
        default_factory=list,
        max_length=100,
    )
    confidence_score: float = Field(ge=0, le=1)
    confidence_label: SemanticConfidenceLabel
    compiler_eligibility: CompilerEligibility
    eligibility_reasons: list[
        Annotated[str, Field(min_length=1, max_length=100)]
    ] = Field(default_factory=list, max_length=100)
    reasoning_summary: str | None = Field(default=None, min_length=1, max_length=1_000)
    validation_warnings: list[
        Annotated[str, Field(min_length=1, max_length=100)]
    ] = Field(default_factory=list, max_length=100)
    provenance: Literal["system", "ai", "human"]
    enabled: bool


class SemanticValidationIssue(StrictModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,99}$")
    severity: Literal["blocking", "warning", "info"]
    target_type: Literal[
        "layer",
        "table",
        "column",
        "relationship",
        "business_concept",
        "ambiguity",
        "metric",
    ]
    target_key: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1, max_length=500)
    evidence: dict[
        Annotated[str, Field(min_length=1, max_length=100)],
        str | int | FiniteFloat | bool,
    ] = Field(default_factory=dict)


class SemanticValidationReport(StrictModel):
    status: Literal[
        "not_validated",
        "valid",
        "valid_with_warnings",
        "blocked",
    ]
    blocking_errors: list[SemanticValidationIssue] = Field(
        default_factory=list,
        max_length=10_000,
    )
    warnings: list[SemanticValidationIssue] = Field(
        default_factory=list,
        max_length=10_000,
    )
    info: list[SemanticValidationIssue] = Field(
        default_factory=list,
        max_length=10_000,
    )
    validated_revision: int | None = Field(default=None, ge=1)
    validated_at: str | None = None
    validator_version: str = Field(min_length=1, max_length=100)

    @field_validator("validated_at")
    @classmethod
    def validate_validated_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _RFC3339_DATETIME_PATTERN.fullmatch(value):
            raise ValueError("validated_at must use RFC 3339 date-time syntax")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("validated_at must be an ISO 8601 datetime") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("validated_at must include a UTC offset")
        return value


class SemanticLayer(StrictModel):
    contract_version: Literal["semantic_layer.v1"]
    tenant_id: CanonicalJsonUUID
    connection_id: CanonicalJsonUUID
    semantic_version_id: CanonicalJsonUUID
    queryability_graph_version_id: CanonicalJsonUUID
    base_graph_hash: Sha256
    version: int = Field(gt=0)
    status: Literal["draft", "proposed", "active", "archived"]
    freshness: Literal["fresh", "stale"]
    builder_version: str = Field(min_length=1, max_length=100)
    ai_model_version: str | None = Field(default=None, min_length=1, max_length=255)
    ai_prompt_version: str | None = Field(default=None, min_length=1, max_length=100)
    validator_version: str = Field(min_length=1, max_length=100)
    policy_version: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)
    semantic_hash: Sha256
    tables: list[SemanticTable] = Field(max_length=5_000)
    columns: list[SemanticColumn] = Field(max_length=250_000)
    relationships: list[SemanticRelationship] = Field(max_length=250_000)
    business_concepts: list[SemanticBusinessConcept] = Field(max_length=10_000)
    ambiguities: list[SemanticAmbiguity] = Field(max_length=10_000)
    metrics: list[SemanticMetric] = Field(max_length=100_000)
    validation_report: SemanticValidationReport


class SemanticSeedRequest(StrictModel):
    graph: QueryabilityGraphArtifact
    semantic_version_id: CanonicalJsonUUID
    queryability_graph_version_id: CanonicalJsonUUID
    version: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_target_graph(self) -> "SemanticSeedRequest":
        if self.graph.status == "blocked":
            raise ValueError("graph must not be blocked")
        return self


SemanticRebaseDropReasonCode = Literal[
    "TARGET_KEY_MISSING",
    "TARGET_NOT_QUERYABLE",
    "TARGET_EDGE_NOT_TRUSTED",
    "DEPENDENCY_DROPPED",
    "DEFINITION_CHANGED",
    "INVALID_AFTER_REBASE",
]


class SemanticRebaseDroppedTable(StrictModel):
    item_type: Literal["table"]
    item_key: Sha256
    reason_codes: list[SemanticRebaseDropReasonCode] = Field(
        min_length=1,
        max_length=20,
    )


class SemanticRebaseDroppedColumn(StrictModel):
    item_type: Literal["column"]
    item_key: Sha256
    reason_codes: list[SemanticRebaseDropReasonCode] = Field(
        min_length=1,
        max_length=20,
    )


class SemanticRebaseDroppedBusinessConcept(StrictModel):
    item_type: Literal["business_concept"]
    item_key: CanonicalJsonUUID
    reason_codes: list[SemanticRebaseDropReasonCode] = Field(
        min_length=1,
        max_length=20,
    )


class SemanticRebaseDroppedMetric(StrictModel):
    item_type: Literal["metric"]
    item_key: CanonicalJsonUUID
    reason_codes: list[SemanticRebaseDropReasonCode] = Field(
        min_length=1,
        max_length=20,
    )


class SemanticRebaseReport(StrictModel):
    carried_table_keys: list[Sha256] = Field(max_length=5_000)
    dropped_tables: list[SemanticRebaseDroppedTable] = Field(max_length=5_000)
    carried_column_keys: list[Sha256] = Field(max_length=250_000)
    dropped_columns: list[SemanticRebaseDroppedColumn] = Field(max_length=250_000)
    carried_business_concept_keys: list[CanonicalJsonUUID] = Field(
        max_length=10_000
    )
    dropped_business_concepts: list[SemanticRebaseDroppedBusinessConcept] = Field(
        max_length=10_000
    )
    carried_metric_keys: list[CanonicalJsonUUID] = Field(max_length=100_000)
    dropped_metrics: list[SemanticRebaseDroppedMetric] = Field(max_length=100_000)


class SemanticRebaseRequest(StrictModel):
    source_layer: SemanticLayer
    target_graph: QueryabilityGraphArtifact
    semantic_version_id: CanonicalJsonUUID
    queryability_graph_version_id: CanonicalJsonUUID
    version: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_rebase_scope(self) -> "SemanticRebaseRequest":
        if (
            self.source_layer.tenant_id != self.target_graph.tenant_id
            or self.source_layer.connection_id != self.target_graph.connection_id
        ):
            raise ValueError(
                "source_layer tenant and connection must match target_graph"
            )
        if self.semantic_version_id == self.source_layer.semantic_version_id:
            raise ValueError(
                "semantic_version_id must differ from source semantic_version_id"
            )
        if self.version <= self.source_layer.version:
            raise ValueError("version must be newer than source_layer.version")
        if (
            self.source_layer.status not in {"active", "archived"}
            or self.source_layer.validation_report.status
            not in {"valid", "valid_with_warnings"}
            or self.source_layer.validation_report.blocking_errors
            or self.source_layer.validation_report.validated_revision
            != self.source_layer.revision
        ):
            raise ValueError(
                "source_layer must be active or archived and successfully validated"
            )
        if self.target_graph.status == "blocked":
            raise ValueError("target_graph must not be blocked")
        return self


class SemanticRebaseResult(StrictModel):
    semantic_layer: SemanticLayer
    rebase_report: SemanticRebaseReport


class SemanticDiscoveryCandidateKey(StrictModel):
    key_type: Literal["primary_key", "unique_constraint", "unique_index"]
    column_keys: list[Sha256] = Field(min_length=1, max_length=100)


class SemanticDiscoveryTableInput(StrictModel):
    node_key: Sha256
    schema_name: str = Field(min_length=1, max_length=255)
    object_name: str = Field(min_length=1, max_length=255)
    object_type: Literal["table", "view"]
    queryability_status: Literal["queryable", "excluded"]
    bridge_candidate: bool
    candidate_keys: list[SemanticDiscoveryCandidateKey] = Field(max_length=100)
    view_lineage_status: Literal["complete", "partial", "unavailable"] | None = None


class SemanticDiscoveryColumnInput(StrictModel):
    column_key: Sha256
    node_key: Sha256
    physical_name: str = Field(min_length=1, max_length=255)
    native_type: str | None = Field(default=None, min_length=1, max_length=255)
    normalized_type: str | None = Field(default=None, min_length=1, max_length=255)
    technical_role: SchemaTechnicalRole = Field(strict=False)
    nullable: bool
    queryability_status: Literal["queryable", "excluded"]
    sensitivity: Literal["none", "pii", "sensitive"]


class SemanticDiscoveryColumnPairInput(StrictModel):
    from_column_key: Sha256
    from_column_name: str = Field(min_length=1, max_length=255)
    to_column_key: Sha256
    to_column_name: str = Field(min_length=1, max_length=255)


class SemanticDiscoveryRelationshipInput(StrictModel):
    edge_key: Sha256
    constraint_name: str = Field(min_length=1, max_length=255)
    from_node_key: Sha256
    to_node_key: Sha256
    column_pairs: list[SemanticDiscoveryColumnPairInput] = Field(
        min_length=1,
        max_length=100,
    )
    relationship_shape: Literal["one_to_one", "many_to_one"]
    child_to_parent: Literal["zero_or_one", "exactly_one"]
    parent_to_child: Literal["zero_or_one", "zero_or_many"]
    nullable_fk: bool
    self_reference: bool


class SemanticDiscoveryInput(StrictModel):
    contract_version: Literal["semantic_discovery_input.v1"]
    engine: Literal["sqlserver"]
    base_graph_hash: Sha256
    graph_status: Literal["complete", "partial"]
    tables: list[SemanticDiscoveryTableInput] = Field(max_length=5_000)
    columns: list[SemanticDiscoveryColumnInput] = Field(max_length=250_000)
    relationships: list[SemanticDiscoveryRelationshipInput] = Field(
        max_length=250_000
    )


class AISemanticTableProposal(StrictModel):
    node_key: Sha256
    display_name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2_000)
    business_domain: str = Field(min_length=1, max_length=255)
    synonyms: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(
        max_length=100
    )


class AISemanticColumnProposal(StrictModel):
    column_key: Sha256
    display_name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2_000)
    synonyms: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(
        max_length=100
    )
    semantic_role: str = Field(min_length=1, max_length=100)
    format_hint: Literal[
        "text",
        "integer",
        "decimal",
        "currency",
        "percentage",
        "date",
        "datetime",
        "boolean",
        "identifier",
    ]


class AISemanticBusinessConceptProposal(StrictModel):
    concept_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
    display_name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2_000)
    synonyms: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(
        max_length=100
    )


class AISemanticDimensionProposal(StrictModel):
    dimension_column_key: Sha256
    edge_path: list[Sha256] = Field(max_length=4)


class AISemanticMetricProposal(StrictModel):
    canonical_name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
    business_concept_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
    metric_variant: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2_000)
    source_table_key: Sha256
    aggregation: Literal["count", "count_distinct", "sum", "avg", "min", "max"]
    measure_column_key: Sha256 | None
    grain_table_key: Sha256
    grain_column_keys: list[Sha256] = Field(min_length=1, max_length=100)
    aggregation_level: Literal["row", "entity", "period"]
    additivity: Literal["additive", "semi_additive", "non_additive"]
    default_date_column_key: Sha256 | None
    required_join_edge_keys: list[Sha256] = Field(max_length=4)
    common_dimensions: list[AISemanticDimensionProposal] = Field(max_length=100)
    preferred_for_grains: list[
        Annotated[str, Field(min_length=1, max_length=100)]
    ] = Field(max_length=100)
    preferred_for_dimensions: list[Sha256] = Field(max_length=100)
    filters: list[SemanticFilter] = Field(max_length=100)
    format: SemanticMetricFormat
    synonyms: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(
        max_length=100
    )
    reasoning_summary: str = Field(min_length=1, max_length=1_000)


class AISemanticAmbiguity(StrictModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,99}$")
    target_type: Literal["table", "column", "business_concept", "metric"]
    target_ref: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=500)
    clarification_question: str = Field(min_length=1, max_length=500)


class AISemanticDraftProposal(StrictModel):
    contract_version: Literal["semantic_ai_draft.v1"]
    tables: list[AISemanticTableProposal] = Field(max_length=5_000)
    columns: list[AISemanticColumnProposal] = Field(max_length=250_000)
    business_concepts: list[AISemanticBusinessConceptProposal] = Field(
        max_length=10_000
    )
    metrics: list[AISemanticMetricProposal] = Field(max_length=10_000)
    ambiguities: list[AISemanticAmbiguity] = Field(max_length=10_000)


class SemanticGenerationProvenance(StrictModel):
    provider: Literal["openai"]
    model_version: str = Field(min_length=1, max_length=255)
    prompt_version: str = Field(min_length=1, max_length=100)
    generated_at: str
    input_hash: Sha256
    proposal_hash: Sha256
    response_id: str = Field(min_length=1, max_length=255)

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(cls, value: str) -> str:
        if not _RFC3339_DATETIME_PATTERN.fullmatch(value):
            raise ValueError("generated_at must use RFC 3339 date-time syntax")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("generated_at must include a UTC offset")
        return value


class SemanticGenerationResult(StrictModel):
    proposal: AISemanticDraftProposal
    provenance: SemanticGenerationProvenance
    semantic_layer: SemanticLayer

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", False)
        return BaseModel.model_dump(self, *args, **kwargs)

    def model_dump_json(self, *args: Any, **kwargs: Any) -> str:
        kwargs.setdefault("exclude_none", False)
        return BaseModel.model_dump_json(self, *args, **kwargs)


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

    @model_validator(mode="after")
    def validate_semantic_layer_scope_and_readiness(self) -> "QueryRequest":
        if (
            self.semantic_layer.tenant_id != self.tenant_id
            or self.semantic_layer.connection_id != self.connection_id
        ):
            raise ValueError(
                "semantic_layer tenant and connection must match the request"
            )
        if (
            self.semantic_layer.status != "active"
            or self.semantic_layer.freshness != "fresh"
            or self.semantic_layer.validation_report.status
            not in {"valid", "valid_with_warnings"}
            or self.semantic_layer.validation_report.blocking_errors
            or self.semantic_layer.validation_report.validated_revision
            != self.semantic_layer.revision
            or self.semantic_layer.validation_report.validated_at is None
            or self.semantic_layer.validation_report.validator_version
            != self.semantic_layer.validator_version
        ):
            raise ValueError(
                "semantic_layer must be active, fresh, and successfully validated"
            )
        return self


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
