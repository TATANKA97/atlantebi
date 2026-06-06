import { z } from "zod";

export const ENGINE_VALUES = ["sqlserver", "mysql"] as const;
export const EngineSchema = z.enum(ENGINE_VALUES);
export type Engine = z.infer<typeof EngineSchema>;

export const NETWORK_MODE_VALUES = ["public_allowlist", "vpn"] as const;
export const NetworkModeSchema = z.enum(NETWORK_MODE_VALUES);
export type NetworkMode = z.infer<typeof NetworkModeSchema>;

export const CONNECTION_STATUS_VALUES = ["draft", "ready", "failed", "disabled"] as const;
export const ConnectionStatusSchema = z.enum(CONNECTION_STATUS_VALUES);
export type ConnectionStatus = z.infer<typeof ConnectionStatusSchema>;

export const CONNECTION_TEST_STATUS_VALUES = ["ok", "failed", "engine_error"] as const;
export const ConnectionTestStatusSchema = z.enum(CONNECTION_TEST_STATUS_VALUES);
export type ConnectionTestStatus = z.infer<typeof ConnectionTestStatusSchema>;

export const GcpSecretRefSchema = z
  .string()
  .regex(
    /^gcp-secret-manager:\/\/projects\/[^/]+\/secrets\/[^/]+(\/versions\/[^/]+)?$/,
    "Secret reference must point to GCP Secret Manager"
  );
export type GcpSecretRef = z.infer<typeof GcpSecretRefSchema>;

export const ConnectionMetadataSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid(),
  name: z.string().min(2).max(160),
  engine: EngineSchema,
  network_mode: NetworkModeSchema,
  host: z.string().min(1).max(255),
  port: z.number().int().min(1).max(65535),
  database_name: z.string().min(1).max(255),
  username: z.string().min(1).max(255),
  tls_required: z.boolean(),
  trust_server_certificate: z.boolean().default(false),
  tls_server_name: z.string().min(1).max(255).nullable().optional(),
  secret_ref: GcpSecretRefSchema,
  status: ConnectionStatusSchema
});
export type ConnectionMetadata = z.infer<typeof ConnectionMetadataSchema>;

export const DatabaseCredentialsSchema = z.strictObject({
  password: z.string().min(1)
});
export type DatabaseCredentials = z.infer<typeof DatabaseCredentialsSchema>;

export const ConnectionTestRequestSchema = z.strictObject({
  connection: ConnectionMetadataSchema,
  timeout_ms: z.number().int().min(1000).max(120000)
});
export type ConnectionTestRequest = z.infer<typeof ConnectionTestRequestSchema>;

export const ConnectionTestResponseSchema = z.strictObject({
  status: ConnectionTestStatusSchema,
  message: z.string().min(1).max(500),
  checked_at: z.string().datetime({ offset: true }),
  duration_ms: z.number().int().min(0),
  sanitized_error: z.string().min(1).max(500).optional()
});
export type ConnectionTestResponse = z.infer<typeof ConnectionTestResponseSchema>;

export const SCHEMA_INTROSPECTION_STATUS_VALUES = ["ok", "failed", "engine_error"] as const;
export const SchemaIntrospectionStatusSchema = z.enum(
  SCHEMA_INTROSPECTION_STATUS_VALUES
);
export type SchemaIntrospectionStatus = z.infer<
  typeof SchemaIntrospectionStatusSchema
>;
export const SchemaCoverageStateSchema = z.enum([
  "complete",
  "partial",
  "unknown"
]);
export type SchemaCoverageState = z.infer<typeof SchemaCoverageStateSchema>;

export const SchemaColumnMetadataSchema = z.strictObject({
  name: z.string().min(1).max(255),
  data_type: z.string().min(1).max(255),
  declared_type: z.string().min(1).max(255).optional(),
  native_type: z.string().min(1).max(255).optional(),
  normalized_type: z.string().min(1).max(255).optional(),
  declared_type_schema: z.string().min(1).max(255).optional(),
  declared_type_name: z.string().min(1).max(255).optional(),
  declared_type_is_user_defined: z.boolean().optional(),
  declared_type_is_assembly: z.boolean().optional(),
  ordinal_position: z.number().int().min(1),
  is_nullable: z.boolean(),
  max_length: z.number().int().min(-1).optional(),
  numeric_precision: z.number().int().min(0).optional(),
  numeric_scale: z.number().int().min(0).optional(),
  datetime_precision: z.number().int().min(0).optional(),
  is_identity: z.boolean().default(false),
  is_computed: z.boolean().default(false),
  default_value: z.string().min(1).optional(),
  collation: z.string().min(1).max(255).optional(),
  identity_seed: z.string().min(1).max(80).optional(),
  identity_increment: z.string().min(1).max(80).optional(),
  computed_expression: z.string().min(1).optional(),
  is_primary_key: z.boolean().default(false),
  is_foreign_key: z.boolean().default(false),
  is_unique_member: z.boolean().default(false),
  comment: z.string().min(1).optional()
});
export type SchemaColumnMetadata = z.infer<typeof SchemaColumnMetadataSchema>;

export const SchemaPrimaryKeyMetadataSchema = z.strictObject({
  name: z.string().min(1).max(255),
  columns: z.array(z.string().min(1).max(255)).min(1)
});
export type SchemaPrimaryKeyMetadata = z.infer<typeof SchemaPrimaryKeyMetadataSchema>;

export const SchemaViewLineageDependencySchema = z.strictObject({
  source: z.enum(["dm_sql_referenced_entities", "sql_expression_dependencies"]),
  referencing_column: z.string().min(1).max(255).optional(),
  referenced_server_name: z.string().min(1).max(255).optional(),
  referenced_database_name: z.string().min(1).max(255).optional(),
  referenced_schema_name: z.string().min(1).max(255).optional(),
  referenced_entity_name: z.string().min(1).max(255).optional(),
  referenced_column_name: z.string().min(1).max(255).optional(),
  referenced_class: z.string().min(1).max(80),
  is_selected: z.boolean().optional(),
  is_updated: z.boolean().optional(),
  is_select_all: z.boolean().optional(),
  is_all_columns_found: z.boolean().optional(),
  is_caller_dependent: z.boolean().optional(),
  is_ambiguous: z.boolean().optional(),
  is_incomplete: z.boolean().optional(),
  is_schema_bound_reference: z.boolean().optional()
});
export type SchemaViewLineageDependency = z.infer<
  typeof SchemaViewLineageDependencySchema
>;

export const SchemaTableMetadataSchema = z.strictObject({
  schema: z.string().min(1).max(255),
  name: z.string().min(1).max(255),
  table_type: z.enum(["base_table", "view"]),
  columns: z.array(SchemaColumnMetadataSchema).max(50_000),
  primary_key: SchemaPrimaryKeyMetadataSchema.optional(),
  database_name: z.string().min(1).max(255).optional(),
  object_id: z.number().int().min(1).optional(),
  is_system_object: z.boolean().default(false),
  row_count_estimate: z.number().int().min(0).optional(),
  comment: z.string().min(1).optional(),
  view_definition_available: z.boolean().optional(),
  view_definition: z.string().min(1).optional(),
  definition_hash: z.string().length(64).optional(),
  lineage_available: z.boolean().optional(),
  view_lineage: z
    .array(SchemaViewLineageDependencySchema)
    .max(100_000)
    .default([])
});
export type SchemaTableMetadata = z.infer<typeof SchemaTableMetadataSchema>;

export const SchemaForeignKeyMetadataSchema = z.strictObject({
  name: z.string().min(1).max(255),
  from_schema: z.string().min(1).max(255),
  from_table: z.string().min(1).max(255),
  from_columns: z.array(z.string().min(1).max(255)).min(1),
  to_schema: z.string().min(1).max(255),
  to_table: z.string().min(1).max(255),
  to_columns: z.array(z.string().min(1).max(255)).min(1),
  on_delete: z.string().min(1).max(40),
  on_update: z.string().min(1).max(40),
  is_disabled: z.boolean().default(false),
  is_not_trusted: z.boolean().default(false),
  source: z.literal("db_fk").default("db_fk"),
  verified_by_db: z.literal(true).default(true)
});
export type SchemaForeignKeyMetadata = z.infer<typeof SchemaForeignKeyMetadataSchema>;

export const SchemaUniqueConstraintMetadataSchema = z.strictObject({
  name: z.string().min(1).max(255),
  schema_name: z.string().min(1).max(255),
  table_name: z.string().min(1).max(255),
  columns: z.array(z.string().min(1).max(255)).min(1)
});
export type SchemaUniqueConstraintMetadata = z.infer<
  typeof SchemaUniqueConstraintMetadataSchema
>;

export const SchemaCheckConstraintMetadataSchema = z.strictObject({
  name: z.string().min(1).max(255),
  schema_name: z.string().min(1).max(255),
  table_name: z.string().min(1).max(255),
  definition: z.string().min(1).optional(),
  is_disabled: z.boolean().default(false),
  is_not_trusted: z.boolean().default(false)
});
export type SchemaCheckConstraintMetadata = z.infer<
  typeof SchemaCheckConstraintMetadataSchema
>;

export const SchemaDefaultConstraintMetadataSchema = z.strictObject({
  name: z.string().min(1).max(255),
  schema_name: z.string().min(1).max(255),
  table_name: z.string().min(1).max(255),
  column_name: z.string().min(1).max(255),
  definition: z.string().min(1).optional()
});
export type SchemaDefaultConstraintMetadata = z.infer<
  typeof SchemaDefaultConstraintMetadataSchema
>;

export const SchemaIndexColumnMetadataSchema = z.strictObject({
  name: z.string().min(1).max(255),
  ordinal_position: z.number().int().min(1),
  is_descending: z.boolean(),
  is_included: z.boolean().default(false)
});
export type SchemaIndexColumnMetadata = z.infer<
  typeof SchemaIndexColumnMetadataSchema
>;

export const SchemaIndexMetadataSchema = z.strictObject({
  name: z.string().min(1).max(255),
  schema_name: z.string().min(1).max(255),
  table_name: z.string().min(1).max(255),
  is_unique: z.boolean(),
  is_primary_key: z.boolean(),
  index_type: z.string().min(1).max(80),
  key_columns: z.array(SchemaIndexColumnMetadataSchema).default([]),
  included_columns: z.array(SchemaIndexColumnMetadataSchema).default([]),
  filter_definition: z.string().min(1).optional(),
  is_disabled: z.boolean().default(false)
});
export type SchemaIndexMetadata = z.infer<typeof SchemaIndexMetadataSchema>;

export const SchemaCoverageWarningSchema = z.strictObject({
  code: z.enum([
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
    "COLUMN_OBJECT_MAPPING_MISSING"
  ]),
  severity: z.enum(["info", "warning"]),
  message: z.string().min(1).max(500),
  object_schema: z.string().min(1).max(255).optional(),
  object_name: z.string().min(1).max(255).optional()
});
export type SchemaCoverageWarning = z.infer<typeof SchemaCoverageWarningSchema>;

export const SchemaIntrospectionRequestSchema = z.strictObject({
  connection: ConnectionMetadataSchema,
  timeout_ms: z.number().int().min(1000).max(120000)
});
export type SchemaIntrospectionRequest = z.infer<typeof SchemaIntrospectionRequestSchema>;

export const SchemaIntrospectionResponseSchema = z.strictObject({
  status: SchemaIntrospectionStatusSchema,
  message: z.string().min(1).max(500),
  introspected_at: z.string().datetime({ offset: true }),
  duration_ms: z.number().int().min(0),
  engine: EngineSchema.optional(),
  database_name: z.string().min(1).max(255).optional(),
  engine_version: z.string().min(1).max(500).optional(),
  schema_hash: z.string().length(64).optional(),
  coverage_state: SchemaCoverageStateSchema.optional(),
  tables: z.array(SchemaTableMetadataSchema).max(5_000).default([]),
  foreign_keys: z
    .array(SchemaForeignKeyMetadataSchema)
    .max(100_000)
    .default([]),
  unique_constraints: z
    .array(SchemaUniqueConstraintMetadataSchema)
    .max(100_000)
    .default([]),
  check_constraints: z
    .array(SchemaCheckConstraintMetadataSchema)
    .max(100_000)
    .default([]),
  default_constraints: z
    .array(SchemaDefaultConstraintMetadataSchema)
    .max(100_000)
    .default([]),
  indexes: z.array(SchemaIndexMetadataSchema).max(100_000).default([]),
  coverage_warnings: z
    .array(SchemaCoverageWarningSchema)
    .max(20_000)
    .default([]),
  sanitized_error: z.string().min(1).max(500).optional()
});
export type SchemaIntrospectionResponse = z.infer<
  typeof SchemaIntrospectionResponseSchema
>;

export const CHART_TYPE_VALUES = [
  "table",
  "kpi_number",
  "bar",
  "horizontal_bar",
  "grouped_bar",
  "stacked_bar",
  "line",
  "area",
  "combo_bar_line",
  "pie",
  "donut",
  "scatter"
] as const;
export const ChartTypeSchema = z.enum(CHART_TYPE_VALUES);
export type ChartType = z.infer<typeof ChartTypeSchema>;

export const ColumnFormatSchema = z.strictObject({
  type: z.enum([
    "text",
    "integer",
    "decimal",
    "currency",
    "percentage",
    "date",
    "date_bucket",
    "identifier"
  ]),
  currency: z.literal("EUR").optional(),
  decimals: z.number().int().min(0).max(6).optional()
});
export type ColumnFormat = z.infer<typeof ColumnFormatSchema>;

export const ChartSpecSchema = z.strictObject({
  type: ChartTypeSchema,
  title: z.string().min(1).max(160),
  x: z.string().min(1).optional(),
  y: z.array(z.string().min(1)).max(8).optional(),
  series: z.string().min(1).optional(),
  formatting: z.record(z.string().min(1), ColumnFormatSchema).default({}),
  display: z
    .strictObject({
      show_legend: z.boolean().default(true),
      show_data_labels: z.boolean().default(false),
      sort: z.enum(["x_asc", "x_desc", "y_asc", "y_desc", "none"]).default("none"),
      limit: z.number().int().min(1).max(100).default(20)
    })
    .default({
      show_legend: true,
      show_data_labels: false,
      sort: "none",
      limit: 20
    })
});
export type ChartSpec = z.infer<typeof ChartSpecSchema>;

export const VerificationStatusSchema = z.enum([
  "pass",
  "warn",
  "fail",
  "skip",
  "engine_error"
]);
export type VerificationStatus = z.infer<typeof VerificationStatusSchema>;

export const VerificationCheckSchema = z.strictObject({
  type: z.enum([
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
    "privacy"
  ]),
  status: VerificationStatusSchema,
  message: z.string().min(1).max(500),
  evidence: z.record(z.string(), z.union([z.string(), z.number(), z.boolean()])).default({})
});
export type VerificationCheck = z.infer<typeof VerificationCheckSchema>;

export const VerificationSummarySchema = z.strictObject({
  status: VerificationStatusSchema,
  checks: z.array(VerificationCheckSchema),
  confidence_label: z.enum(["high", "medium", "low", "blocked"]),
  result_visible: z.boolean()
});
export type VerificationSummary = z.infer<typeof VerificationSummarySchema>;

export const RelationshipSchema = z.strictObject({
  id: z.string().uuid(),
  from_table: z.string().min(1),
  from_columns: z.array(z.string().min(1)).min(1),
  to_table: z.string().min(1),
  to_columns: z.array(z.string().min(1)).min(1),
  cardinality: z.enum(["one_to_one", "one_to_many", "many_to_one", "many_to_many"]),
  semantic_status: z.enum(["confirmed", "suggested", "rejected"]),
  source: z.enum(["database_fk", "user_validated", "ai_suggested"])
});
export type Relationship = z.infer<typeof RelationshipSchema>;

export const SemanticColumnSchema = z.strictObject({
  name: z.string().min(1),
  data_type: z.string().min(1),
  business_name: z.string().min(1).optional(),
  role: z.enum(["dimension", "measure", "date", "identifier", "unknown"]),
  format: ColumnFormatSchema.optional(),
  pii: z.boolean().default(false)
});
export type SemanticColumn = z.infer<typeof SemanticColumnSchema>;

export const SemanticTableSchema = z.strictObject({
  name: z.string().min(1),
  schema: z.string().min(1).default("dbo"),
  business_name: z.string().min(1).optional(),
  active: z.boolean(),
  columns: z.array(SemanticColumnSchema)
});
export type SemanticTable = z.infer<typeof SemanticTableSchema>;

export const SemanticMetricSchema = z.strictObject({
  id: z.string().uuid(),
  name: z.string().min(1),
  expression: z.string().min(1),
  grain: z.array(z.string().min(1)).default([]),
  format: ColumnFormatSchema
});
export type SemanticMetric = z.infer<typeof SemanticMetricSchema>;

export const BusinessAnchorSchema = z.strictObject({
  id: z.string().uuid(),
  name: z.string().min(1),
  metric_id: z.string().uuid(),
  expected_range: z.strictObject({
    min: z.number().finite().optional(),
    max: z.number().finite().optional()
  }),
  period: z.enum(["daily", "monthly", "quarterly", "yearly"])
});
export type BusinessAnchor = z.infer<typeof BusinessAnchorSchema>;

export const SemanticLayerSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  version_id: z.string().uuid(),
  version: z.number().int().positive(),
  status: z.enum(["draft", "active", "archived"]),
  engine: EngineSchema,
  tables: z.array(SemanticTableSchema),
  relationships: z.array(RelationshipSchema),
  metrics: z.array(SemanticMetricSchema),
  business_anchors: z.array(BusinessAnchorSchema)
});
export type SemanticLayer = z.infer<typeof SemanticLayerSchema>;

export const QueryPermissionSchema = z.strictObject({
  can_view_sql: z.boolean(),
  can_save_widget: z.boolean()
});
export type QueryPermission = z.infer<typeof QueryPermissionSchema>;

export const QueryRequestSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid(),
  user_id: z.string().uuid(),
  question: z.string().min(1).max(1000),
  semantic_layer: SemanticLayerSchema,
  permissions: QueryPermissionSchema,
  execution: z.strictObject({
    mode: z.enum(["plan_only", "run"]),
    row_limit: z.number().int().min(1).max(5000),
    timeout_ms: z.number().int().min(1000).max(120000)
  })
});
export type QueryRequest = z.infer<typeof QueryRequestSchema>;

export const ResultColumnSchema = z.strictObject({
  name: z.string().min(1),
  data_type: z.string().min(1),
  format: ColumnFormatSchema
});
export type ResultColumn = z.infer<typeof ResultColumnSchema>;

export const QueryResponseSchema = z.strictObject({
  query_id: z.string().uuid(),
  status: z.enum(["completed", "needs_clarification", "failed"]),
  sql: z
    .strictObject({
      dialect: EngineSchema,
      statement: z.string().min(1),
      visible_to_user: z.boolean()
    })
    .optional(),
  result_metadata: z.strictObject({
    columns: z.array(ResultColumnSchema),
    row_count: z.number().int().min(0),
    truncated: z.boolean()
  }),
  chart: ChartSpecSchema.optional(),
  verification: VerificationSummarySchema,
  sanitized_error: z.string().min(1).max(500).optional()
});
export type QueryResponse = z.infer<typeof QueryResponseSchema>;
