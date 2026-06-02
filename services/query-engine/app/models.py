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
