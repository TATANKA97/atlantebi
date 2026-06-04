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

export const SchemaColumnMetadataSchema = z.strictObject({
  name: z.string().min(1).max(255),
  data_type: z.string().min(1).max(255),
  declared_type: z.string().min(1).max(255).optional(),
  ordinal_position: z.number().int().min(1),
  is_nullable: z.boolean(),
  max_length: z.number().int().min(-1).optional(),
  numeric_precision: z.number().int().min(0).optional(),
  numeric_scale: z.number().int().min(0).optional(),
  datetime_precision: z.number().int().min(0).optional(),
  is_identity: z.boolean().default(false),
  is_computed: z.boolean().default(false)
});
export type SchemaColumnMetadata = z.infer<typeof SchemaColumnMetadataSchema>;

export const SchemaPrimaryKeyMetadataSchema = z.strictObject({
  name: z.string().min(1).max(255),
  columns: z.array(z.string().min(1).max(255)).min(1)
});
export type SchemaPrimaryKeyMetadata = z.infer<typeof SchemaPrimaryKeyMetadataSchema>;

export const SchemaTableMetadataSchema = z.strictObject({
  schema: z.string().min(1).max(255),
  name: z.string().min(1).max(255),
  table_type: z.enum(["base_table", "view"]),
  columns: z.array(SchemaColumnMetadataSchema),
  primary_key: SchemaPrimaryKeyMetadataSchema.optional()
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
  on_update: z.string().min(1).max(40)
});
export type SchemaForeignKeyMetadata = z.infer<typeof SchemaForeignKeyMetadataSchema>;

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
  tables: z.array(SchemaTableMetadataSchema).default([]),
  foreign_keys: z.array(SchemaForeignKeyMetadataSchema).default([]),
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
