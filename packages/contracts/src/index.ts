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
export const SchemaCoverageStatusSchema = z.enum([
  "ok",
  "partial",
  "warning",
  "blocked"
]);
export type SchemaCoverageStatus = z.infer<typeof SchemaCoverageStatusSchema>;

export const SchemaTechnicalRoleSchema = z.enum([
  "identifier",
  "date",
  "boolean",
  "quantity_candidate",
  "money_candidate",
  "numeric",
  "text",
  "binary",
  "xml",
  "unknown"
]);
export type SchemaTechnicalRole = z.infer<typeof SchemaTechnicalRoleSchema>;

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
  declared_type_available: z.boolean(),
  technical_role: SchemaTechnicalRoleSchema,
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
  is_single_column_unique: z.boolean().default(false),
  is_composite_unique_member: z.boolean().default(false),
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
  constraint_name: z.string().min(1).max(255),
  from_schema: z.string().min(1).max(255),
  from_table: z.string().min(1).max(255),
  from_columns: z.array(z.string().min(1).max(255)).min(1),
  to_schema: z.string().min(1).max(255),
  to_table: z.string().min(1).max(255),
  to_columns: z.array(z.string().min(1).max(255)).min(1),
  delete_rule: z.string().min(1).max(40),
  update_rule: z.string().min(1).max(40),
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
  object_type: z.enum(["table", "view"]),
  is_unique: z.boolean(),
  is_primary_key: z.boolean(),
  index_type: z.string().min(1).max(80),
  key_columns: z.array(SchemaIndexColumnMetadataSchema).default([]),
  included_columns: z.array(SchemaIndexColumnMetadataSchema).default([]),
  filter_definition: z.string().min(1).optional(),
  is_disabled: z.boolean().default(false)
});
export type SchemaIndexMetadata = z.infer<typeof SchemaIndexMetadataSchema>;

export const SCHEMA_COVERAGE_WARNING_CODES = [
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
] as const;
export const SchemaCoverageWarningCodeSchema = z.enum(
  SCHEMA_COVERAGE_WARNING_CODES
);
export type SchemaCoverageWarningCode = z.infer<
  typeof SchemaCoverageWarningCodeSchema
>;

export const SchemaCoverageWarningSchema = z.strictObject({
  code: SchemaCoverageWarningCodeSchema,
  severity: z.enum(["info", "warning"]),
  message: z.string().min(1).max(500),
  object_schema: z.string().min(1).max(255).optional(),
  object_name: z.string().min(1).max(255).optional()
});
export type SchemaCoverageWarning = z.infer<typeof SchemaCoverageWarningSchema>;

export const SchemaImportSummarySchema = z.strictObject({
  database_name: z.string().min(1).max(255),
  engine: EngineSchema,
  engine_version: z.string().min(1).max(500),
  schema_hash: z.string().length(64),
  coverage_status: SchemaCoverageStatusSchema,
  captured_at: z.string().datetime({ offset: true }),
  duration_ms: z.number().int().min(0),
  total_objects: z.number().int().min(0),
  total_tables: z.number().int().min(0),
  total_views: z.number().int().min(0),
  total_columns: z.number().int().min(0),
  queryable_objects: z.number().int().min(0),
  non_queryable_objects: z.number().int().min(0),
  queryable_columns: z.number().int().min(0),
  non_queryable_columns: z.number().int().min(0),
  primary_keys_count: z.number().int().min(0),
  foreign_keys_count: z.number().int().min(0),
  unique_constraints_count: z.number().int().min(0),
  check_constraints_count: z.number().int().min(0),
  default_constraints_count: z.number().int().min(0),
  indexes_total_count: z.number().int().min(0),
  table_indexes_count: z.number().int().min(0),
  view_indexes_count: z.number().int().min(0),
  unique_indexes_count: z.number().int().min(0),
  filtered_indexes_count: z.number().int().min(0),
  included_columns_indexes_count: z.number().int().min(0),
  views_total: z.number().int().min(0),
  views_with_definition_count: z.number().int().min(0),
  views_without_definition_count: z.number().int().min(0),
  views_with_lineage_count: z.number().int().min(0),
  views_with_partial_lineage_count: z.number().int().min(0),
  views_without_lineage_count: z.number().int().min(0),
  view_lineage_dependencies_count: z.number().int().min(0),
  columns_with_declared_type_count: z.number().int().min(0),
  columns_without_declared_type_count: z.number().int().min(0),
  columns_with_default_count: z.number().int().min(0),
  computed_columns_count: z.number().int().min(0),
  identity_columns_count: z.number().int().min(0),
  pii_columns_count: z.number().int().min(0),
  excluded_columns_count: z.number().int().min(0),
  sensitive_columns_count: z.number().int().min(0),
  coverage_warnings_count: z.number().int().min(0),
  coverage_warnings_by_code: z.record(
    z.string().min(1).max(100),
    z.number().int().min(1)
  )
});
export type SchemaImportSummary = z.infer<typeof SchemaImportSummarySchema>;

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
  snapshot_hash: z.string().length(64).optional(),
  coverage_status: SchemaCoverageStatusSchema,
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

export const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);

export const QueryabilityStatusSchema = z.enum([
  "queryable",
  "excluded"
]);
export type QueryabilityStatus = z.infer<typeof QueryabilityStatusSchema>;

export const QueryabilitySensitivitySchema = z.enum([
  "none",
  "pii",
  "sensitive"
]);
export type QueryabilitySensitivity = z.infer<
  typeof QueryabilitySensitivitySchema
>;

export const QueryabilityCandidateKeySchema = z.strictObject({
  key_type: z.enum(["primary_key", "unique_constraint", "unique_index"]),
  name: z.string().min(1).max(255),
  columns: z.array(z.string().min(1).max(255)).min(1),
  eligible_for_cardinality: z.boolean()
});
export type QueryabilityCandidateKey = z.infer<
  typeof QueryabilityCandidateKeySchema
>;

export const QueryabilityColumnSchema = z.strictObject({
  column_key: Sha256Schema,
  name: z.string().min(1).max(255),
  ordinal_position: z.number().int().min(1),
  native_type: z.string().min(1).max(255).optional(),
  normalized_type: z.string().min(1).max(255).optional(),
  technical_role: SchemaTechnicalRoleSchema,
  nullable: z.boolean(),
  queryability_status: QueryabilityStatusSchema,
  sensitivity: QueryabilitySensitivitySchema,
  reason_codes: z.array(z.string().min(1).max(100)).max(20)
});
export type QueryabilityColumn = z.infer<typeof QueryabilityColumnSchema>;

export const QueryabilityNodeSchema = z.strictObject({
  node_key: Sha256Schema,
  database_name: z.string().min(1).max(255),
  schema_name: z.string().min(1).max(255),
  object_name: z.string().min(1).max(255),
  object_type: z.enum(["table", "view"]),
  queryability_status: QueryabilityStatusSchema,
  reason_codes: z.array(z.string().min(1).max(100)).max(100),
  bridge_candidate: z.boolean(),
  candidate_keys: z.array(QueryabilityCandidateKeySchema).max(10_000),
  columns: z.array(QueryabilityColumnSchema).max(50_000),
  view_definition_available: z.boolean().optional(),
  view_lineage_status: z
    .enum(["complete", "partial", "unavailable"])
    .optional(),
  view_column_lineage_status: z
    .enum(["complete", "partial", "unavailable"])
    .optional()
});
export type QueryabilityNode = z.infer<typeof QueryabilityNodeSchema>;

export const QueryabilityColumnPairSchema = z.strictObject({
  ordinal_position: z.number().int().min(1),
  from_column: z.string().min(1).max(255),
  from_column_key: Sha256Schema,
  to_column: z.string().min(1).max(255),
  to_column_key: Sha256Schema
});
export type QueryabilityColumnPair = z.infer<
  typeof QueryabilityColumnPairSchema
>;

export const QueryabilityForeignKeyEdgeSchema = z.strictObject({
  edge_key: Sha256Schema,
  edge_type: z.literal("fk_join"),
  constraint_name: z.string().min(1).max(255),
  from_node_key: Sha256Schema,
  to_node_key: Sha256Schema,
  column_pairs: z.array(QueryabilityColumnPairSchema).min(1),
  relationship_shape: z.enum(["one_to_one", "many_to_one"]),
  child_to_parent: z.enum(["zero_or_one", "exactly_one"]),
  parent_to_child: z.enum(["zero_or_one", "zero_or_many"]),
  nullable_fk: z.boolean(),
  self_reference: z.boolean(),
  verified_by_db: z.boolean(),
  enforcement_status: z.enum(["enabled", "disabled"]),
  validation_status: z.enum(["trusted", "untrusted"]),
  automatic_join_allowed: z.boolean(),
  reason_codes: z.array(z.string().min(1).max(100)).max(100)
});
export type QueryabilityForeignKeyEdge = z.infer<
  typeof QueryabilityForeignKeyEdgeSchema
>;

export const QueryabilityViewDependencyEdgeSchema = z.strictObject({
  edge_key: Sha256Schema,
  edge_type: z.literal("view_depends_on"),
  from_node_key: Sha256Schema,
  to_node_key: Sha256Schema.optional(),
  source: z.enum([
    "dm_sql_referenced_entities",
    "sql_expression_dependencies"
  ]),
  referenced_server_name: z.string().min(1).max(255).optional(),
  referenced_database_name: z.string().min(1).max(255).optional(),
  referenced_schema_name: z.string().min(1).max(255).optional(),
  referenced_object_name: z.string().min(1).max(255).optional(),
  resolution_status: z.enum(["resolved", "external", "unresolved"]),
  automatic_join_allowed: z.literal(false),
  reason_codes: z.array(z.string().min(1).max(100)).max(100)
});
export type QueryabilityViewDependencyEdge = z.infer<
  typeof QueryabilityViewDependencyEdgeSchema
>;

export const QueryabilityViewColumnEdgeSchema = z.strictObject({
  edge_key: Sha256Schema,
  edge_type: z.literal("view_column_derives_from"),
  from_node_key: Sha256Schema,
  from_column_key: Sha256Schema,
  to_node_key: Sha256Schema.optional(),
  to_column_key: Sha256Schema.optional(),
  source: z.enum([
    "dm_sql_referenced_entities",
    "sql_expression_dependencies"
  ]),
  referenced_server_name: z.string().min(1).max(255).optional(),
  referenced_database_name: z.string().min(1).max(255).optional(),
  referenced_schema_name: z.string().min(1).max(255).optional(),
  referenced_object_name: z.string().min(1).max(255).optional(),
  referenced_column_name: z.string().min(1).max(255).optional(),
  resolution_status: z.enum(["resolved", "external", "unresolved"]),
  lineage_status: z.enum(["complete", "partial"]),
  automatic_join_allowed: z.literal(false),
  reason_codes: z.array(z.string().min(1).max(100)).max(100)
});
export type QueryabilityViewColumnEdge = z.infer<
  typeof QueryabilityViewColumnEdgeSchema
>;

export const QueryabilityEdgeSchema = z.discriminatedUnion("edge_type", [
  QueryabilityForeignKeyEdgeSchema,
  QueryabilityViewDependencyEdgeSchema,
  QueryabilityViewColumnEdgeSchema
]);
export type QueryabilityEdge = z.infer<typeof QueryabilityEdgeSchema>;

export const QueryabilityGraphStatusSchema = z.enum([
  "complete",
  "partial",
  "blocked"
]);
export type QueryabilityGraphStatus = z.infer<
  typeof QueryabilityGraphStatusSchema
>;

export const QueryabilityGraphArtifactSchema = z.strictObject({
  contract_version: z.literal("queryability_graph.v1"),
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid(),
  schema_snapshot_id: z.string().uuid(),
  engine: z.literal("sqlserver"),
  schema_hash: Sha256Schema,
  snapshot_hash: Sha256Schema,
  graph_input_hash: Sha256Schema,
  derivation_key: Sha256Schema,
  graph_hash: Sha256Schema,
  builder_version: z.string().min(1).max(100),
  policy_version: z.string().min(1).max(100),
  status: QueryabilityGraphStatusSchema,
  status_reasons: z.array(z.string().min(1).max(100)).max(100),
  semantic_status: z.literal("not_initialized"),
  nodes: z.array(QueryabilityNodeSchema).max(5_000),
  edges: z.array(QueryabilityEdgeSchema).max(250_000)
});
export type QueryabilityGraphArtifact = z.infer<
  typeof QueryabilityGraphArtifactSchema
>;

export const QueryabilityGraphVersionSchema = z.strictObject({
  graph_version_id: z.string().uuid(),
  graph_version: z.number().int().positive(),
  created_at: z.string().datetime({ offset: true }),
  graph: QueryabilityGraphArtifactSchema
});
export type QueryabilityGraphVersion = z.infer<
  typeof QueryabilityGraphVersionSchema
>;

export const QueryabilityCompileRequestSchema = z.strictObject({
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid(),
  schema_snapshot_id: z.string().uuid(),
  snapshot: SchemaIntrospectionResponseSchema
});
export type QueryabilityCompileRequest = z.infer<
  typeof QueryabilityCompileRequestSchema
>;

export const QueryabilityPathStepSchema = z.strictObject({
  edge_key: Sha256Schema,
  from_node_key: Sha256Schema,
  to_node_key: Sha256Schema,
  traversal: z.enum(["child_to_parent", "parent_to_child"]),
  cardinality: z.enum([
    "zero_or_one",
    "exactly_one",
    "zero_or_many"
  ])
});
export type QueryabilityPathStep = z.infer<
  typeof QueryabilityPathStepSchema
>;

export const QueryabilityPathSchema = z.strictObject({
  steps: z.array(QueryabilityPathStepSchema).min(1).max(4),
  fanout_warning: z.boolean()
});
export type QueryabilityPath = z.infer<typeof QueryabilityPathSchema>;

export const QueryabilityPathResultSchema = z.strictObject({
  status: z.enum(["found", "not_found", "ambiguous", "blocked"]),
  paths: z.array(QueryabilityPathSchema).max(100),
  reason_codes: z.array(z.string().min(1).max(100)).max(100)
});
export type QueryabilityPathResult = z.infer<
  typeof QueryabilityPathResultSchema
>;

export const QueryabilityPathRequestSchema = z.strictObject({
  graph: QueryabilityGraphArtifactSchema,
  from_node_key: Sha256Schema,
  to_node_key: Sha256Schema,
  max_hops: z.number().int().min(1).max(4).default(4)
});
export type QueryabilityPathRequest = z.infer<
  typeof QueryabilityPathRequestSchema
>;

export const SemanticElementStatusSchema = z.enum([
  "system_seeded",
  "ai_proposed",
  "human_verified",
  "rejected",
  "disabled",
  "stale"
]);
export type SemanticElementStatus = z.infer<
  typeof SemanticElementStatusSchema
>;

export const SemanticConfidenceLabelSchema = z.enum([
  "high",
  "medium",
  "low",
  "blocked"
]);
export type SemanticConfidenceLabel = z.infer<
  typeof SemanticConfidenceLabelSchema
>;

export const CompilerEligibilitySchema = z.enum([
  "eligible",
  "eligible_with_disclosure",
  "clarification_required",
  "not_eligible"
]);
export type CompilerEligibility = z.infer<
  typeof CompilerEligibilitySchema
>;

export const SemanticAmbiguitySeveritySchema = z.enum([
  "material_ambiguity",
  "minor_ambiguity",
  "info"
]);

export const SemanticConceptPolicySchema = z.strictObject({
  concept_ref: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  preferred_variants: z
    .array(z.string().regex(/^[a-z][a-z0-9_]{1,99}$/))
    .max(100)
    .default([]),
  required: z.boolean().default(false),
  required_for_activation: z.boolean().default(false)
});

export const SemanticDimensionExpectationSchema = z.strictObject({
  dimension_column_key: Sha256Schema,
  expected_safety: z.enum(["safe", "forbidden"])
});

export const SemanticRequiredMetricSpecSchema = z.strictObject({
  spec_key: z.string().regex(/^[a-z][a-z0-9_.-]{1,99}$/),
  intent_key: z.string().regex(/^[a-z][a-z0-9_.-]{1,99}$/),
  business_concept_ref: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  expected_variant: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  canonical_name: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  name: z.string().min(1).max(255),
  description: z.string().min(1).max(2_000).nullish(),
  source_table_key: Sha256Schema,
  aggregation: z.enum(["count", "count_distinct", "sum", "avg", "min", "max"]),
  measure_column_key: Sha256Schema.nullable(),
  grain_column_keys: z.array(Sha256Schema).min(1).max(100),
  default_date_column_key: Sha256Schema.nullable(),
  value_type: z.enum(["currency", "number", "percentage", "count", "duration"]),
  default_for_concept: z.boolean().default(false),
  required_for_activation: z.boolean().default(false),
  allowed_eligibility: z.array(CompilerEligibilitySchema).min(1).max(4),
  dimension_expectations: z
    .array(SemanticDimensionExpectationSchema)
    .max(100)
    .default([]),
  synonyms: z.array(z.string().min(1).max(255)).max(100).default([])
});

export const SemanticPolicySnapshotSchema = z
  .strictObject({
    policy_version: z.string().min(1).max(100),
    policy_hash: Sha256Schema,
    default_currency: z.string().regex(/^[A-Z]{3}$/).nullable(),
    missing_currency_behavior: z.enum(["clarification_required", "blocked"]),
    activation_policy: z.enum(["auto_validated", "manual_review"]),
    minimum_eligible_metrics: z.number().int().min(0).max(100_000).default(1),
    required_concepts: z.array(SemanticConceptPolicySchema).max(1_000),
    required_metric_specs: z
      .array(SemanticRequiredMetricSpecSchema)
      .max(10_000)
      .default([])
  })
  .superRefine((policy, context) => {
    const concepts = new Map(
      policy.required_concepts.map((concept) => [concept.concept_ref, concept])
    );
    if (concepts.size !== policy.required_concepts.length) {
      context.addIssue({
        code: "custom",
        path: ["required_concepts"],
        message: "semantic policy concept_ref values must be unique"
      });
    }
    const specKeys = new Set<string>();
    const defaultConcepts = new Set<string>();
    policy.required_metric_specs.forEach((spec, index) => {
      if (specKeys.has(spec.spec_key)) {
        context.addIssue({
          code: "custom",
          path: ["required_metric_specs", index, "spec_key"],
          message: "semantic quality spec_key values must be unique"
        });
      }
      specKeys.add(spec.spec_key);
      const concept = concepts.get(spec.business_concept_ref);
      if (!concept) {
        context.addIssue({
          code: "custom",
          path: ["required_metric_specs", index, "business_concept_ref"],
          message: "quality spec references a concept outside the allowlist"
        });
      } else if (
        concept.preferred_variants.length > 0 &&
        !concept.preferred_variants.includes(spec.expected_variant)
      ) {
        context.addIssue({
          code: "custom",
          path: ["required_metric_specs", index, "expected_variant"],
          message: "quality spec variant is not allowed by its concept"
        });
      }
      if (spec.default_for_concept) {
        if (defaultConcepts.has(spec.business_concept_ref)) {
          context.addIssue({
            code: "custom",
            path: ["required_metric_specs", index, "default_for_concept"],
            message: "semantic concept has multiple default metric specs"
          });
        }
        defaultConcepts.add(spec.business_concept_ref);
      }
    });
  });
export type SemanticPolicySnapshot = z.infer<typeof SemanticPolicySnapshotSchema>;

export const SemanticQualityIssueSchema = z.strictObject({
  code: z.string().regex(/^[A-Z][A-Z0-9_]{1,99}$/),
  severity: z.enum(["blocking", "warning", "info"]),
  message: z.string().min(1).max(500),
  spec_key: z.string().min(1).max(100).nullish(),
  metric_key: z.string().uuid().nullish()
});

export const SemanticRejectedCandidateSchema = z.strictObject({
  canonical_name: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  business_concept_ref: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  metric_variant: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  source_table_key: Sha256Schema,
  measure_column_key: Sha256Schema.nullable(),
  reason_code: z.string().regex(/^[A-Z][A-Z0-9_]{1,99}$/)
});

export const SemanticQualityReportSchema = z.strictObject({
  status: z.enum(["not_evaluated", "passed", "blocked"]),
  issues: z.array(SemanticQualityIssueSchema).max(10_000).default([]),
  required_specs_count: z.number().int().nonnegative().default(0),
  satisfied_specs_count: z.number().int().nonnegative().default(0),
  compiler_eligible_required_count: z.number().int().nonnegative().default(0),
  rejected_candidates: z
    .array(SemanticRejectedCandidateSchema)
    .max(10_000)
    .default([])
});

export const SemanticTableSchema = z.strictObject({
  node_key: Sha256Schema,
  schema_name: z.string().min(1).max(255),
  object_name: z.string().min(1).max(255),
  object_type: z.enum(["table", "view"]),
  display_name: z.string().min(1).max(255).nullish(),
  description: z.string().min(1).max(2_000).nullish(),
  business_domain: z.string().min(1).max(255).nullish(),
  synonyms: z.array(z.string().min(1).max(255)).max(100).default([]),
  status: SemanticElementStatusSchema,
  included: z.boolean(),
  queryability_status: QueryabilityStatusSchema
});
export type SemanticTable = z.infer<typeof SemanticTableSchema>;

export const SemanticColumnSchema = z.strictObject({
  column_key: Sha256Schema,
  node_key: Sha256Schema,
  physical_name: z.string().min(1).max(255),
  display_name: z.string().min(1).max(255).nullish(),
  description: z.string().min(1).max(2_000).nullish(),
  synonyms: z.array(z.string().min(1).max(255)).max(100).default([]),
  native_type: z.string().min(1).max(255).nullish(),
  normalized_type: z.string().min(1).max(255).nullish(),
  technical_role: SchemaTechnicalRoleSchema,
  semantic_role: z.string().min(1).max(100).nullish(),
  format_hint: z
    .enum([
      "text",
      "integer",
      "decimal",
      "currency",
      "percentage",
      "date",
      "datetime",
      "boolean",
      "identifier"
    ])
    .nullish(),
  nullable: z.boolean(),
  status: SemanticElementStatusSchema,
  included: z.boolean(),
  queryability_status: QueryabilityStatusSchema,
  inherited_sensitivity: QueryabilitySensitivitySchema,
  sensitivity: QueryabilitySensitivitySchema
});
export type SemanticColumn = z.infer<typeof SemanticColumnSchema>;

export const SemanticRelationshipSchema = z.strictObject({
  edge_key: Sha256Schema,
  from_node_key: Sha256Schema,
  to_node_key: Sha256Schema,
  status: SemanticElementStatusSchema,
  enabled: z.boolean(),
  relationship_shape: z.enum(["one_to_one", "many_to_one"]),
  child_to_parent: z.enum(["zero_or_one", "exactly_one"]),
  parent_to_child: z.enum(["zero_or_one", "zero_or_many"]),
  nullable_fk: z.boolean(),
  self_reference: z.boolean()
});
export type SemanticRelationship = z.infer<
  typeof SemanticRelationshipSchema
>;

export const SemanticBusinessConceptSchema = z.strictObject({
  business_concept_key: z.string().uuid(),
  canonical_name: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  display_name: z.string().min(1).max(255),
  description: z.string().min(1).max(2_000).nullish(),
  synonyms: z.array(z.string().min(1).max(255)).max(100).default([]),
  status: SemanticElementStatusSchema,
  provenance: z.enum(["system", "ai", "human"]),
  default_metric_key: z.string().uuid().nullish()
});
export type SemanticBusinessConcept = z.infer<
  typeof SemanticBusinessConceptSchema
>;

export const SemanticAmbiguitySchema = z.strictObject({
  ambiguity_key: z.string().uuid(),
  code: z.string().regex(/^[A-Z][A-Z0-9_]{1,99}$/),
  target_type: z.enum([
    "table",
    "column",
    "business_concept",
    "metric"
  ]),
  target_key: z.string().min(1).max(255),
  summary: z.string().min(1).max(500),
  clarification_question: z.string().min(1).max(500),
  status: z.enum(["open", "resolved"]),
  provenance: z.enum(["system", "ai", "human"]),
  severity: SemanticAmbiguitySeveritySchema
});
export type SemanticAmbiguity = z.infer<typeof SemanticAmbiguitySchema>;

const SemanticFilterValueSchema = z.union([
  z.string(),
  z.number().finite(),
  z.boolean(),
  z.array(z.union([z.string(), z.number().finite(), z.boolean()])).min(1)
]);

export const SemanticFilterSchema = z.strictObject({
  column_key: Sha256Schema,
  operator: z.enum([
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
    "is_not_null"
  ]),
  value: SemanticFilterValueSchema.nullish(),
  value_type: z.enum([
    "string",
    "integer",
    "decimal",
    "boolean",
    "date",
    "datetime"
  ])
});
export type SemanticFilter = z.infer<typeof SemanticFilterSchema>;

export const SemanticDimensionCompatibilitySchema = z.strictObject({
  dimension_column_key: Sha256Schema,
  edge_path: z.array(Sha256Schema).max(4).default([]),
  safety: z.enum(["safe", "forbidden"]),
  reason_code: z.string().min(1).max(100)
});
export type SemanticDimensionCompatibility = z.infer<
  typeof SemanticDimensionCompatibilitySchema
>;

export const SemanticDimensionPolicySchema = z.strictObject({
  same_grain: z.literal("safe"),
  parent_many_to_one: z.literal("safe"),
  child_one_to_many: z.literal("forbidden"),
  bridge_or_many_to_many: z.literal("forbidden"),
  self_reference: z.literal("conditional")
});
export type SemanticDimensionPolicy = z.infer<
  typeof SemanticDimensionPolicySchema
>;

export const SemanticMetricFormatSchema = z.strictObject({
  value_type: z.enum([
    "currency",
    "number",
    "percentage",
    "count",
    "duration"
  ]),
  currency: z.string().regex(/^[A-Z]{3}$/).nullish(),
  decimals: z.number().int().min(0).max(6).nullish()
});
export type SemanticMetricFormat = z.infer<
  typeof SemanticMetricFormatSchema
>;

export const SemanticMetricSchema = z.strictObject({
  metric_key: z.string().uuid(),
  canonical_name: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  metric_definition_hash: Sha256Schema,
  business_concept_key: z.string().uuid(),
  metric_variant: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  name: z.string().min(1).max(255),
  description: z.string().min(1).max(2_000).nullish(),
  status: SemanticElementStatusSchema,
  source_table_key: Sha256Schema,
  aggregation: z.enum([
    "count",
    "count_distinct",
    "sum",
    "avg",
    "min",
    "max"
  ]),
  measure_column_key: Sha256Schema.nullish(),
  grain_table_key: Sha256Schema,
  grain_column_keys: z.array(Sha256Schema).min(1).max(100),
  aggregation_level: z.enum(["row", "entity", "period"]),
  additivity: z.enum(["additive", "semi_additive", "non_additive"]),
  default_date_column_key: Sha256Schema.nullish(),
  required_join_edge_keys: z.array(Sha256Schema).max(4).default([]),
  common_dimension_compatibility: z
    .array(SemanticDimensionCompatibilitySchema)
    .max(500)
    .default([]),
  dimension_policy: SemanticDimensionPolicySchema,
  preferred_for_grains: z
    .array(z.string().min(1).max(100))
    .max(100)
    .default([]),
  preferred_for_dimensions: z.array(Sha256Schema).max(100).default([]),
  filters: z.array(SemanticFilterSchema).max(100).default([]),
  format: SemanticMetricFormatSchema,
  synonyms: z.array(z.string().min(1).max(255)).max(100).default([]),
  confidence_score: z.number().min(0).max(1),
  confidence_label: SemanticConfidenceLabelSchema,
  compiler_eligibility: CompilerEligibilitySchema,
  eligibility_reasons: z
    .array(z.string().min(1).max(100))
    .max(100)
    .default([]),
  reasoning_summary: z.string().min(1).max(1_000).nullish(),
  validation_warnings: z
    .array(z.string().min(1).max(100))
    .max(100)
    .default([]),
  provenance: z.enum(["system", "ai", "human"]),
  provenance_detail: z.enum([
    "system_seed",
    "ai_generation",
    "quality_profile",
    "human_override"
  ]),
  source_spec_key: z.string().min(1).max(100).nullish(),
  enabled: z.boolean()
}).superRefine((metric, context) => {
  if (
    metric.provenance_detail === "quality_profile" &&
    (metric.provenance !== "system" || !metric.source_spec_key)
  ) {
    context.addIssue({
      code: "custom",
      path: ["source_spec_key"],
      message: "quality-profile metrics require system provenance and source_spec_key"
    });
  }
  if (
    metric.provenance_detail !== "quality_profile" &&
    metric.source_spec_key != null
  ) {
    context.addIssue({
      code: "custom",
      path: ["source_spec_key"],
      message: "source_spec_key is only valid for quality-profile metrics"
    });
  }
  if (metric.provenance === "ai" && metric.provenance_detail !== "ai_generation") {
    context.addIssue({
      code: "custom",
      path: ["provenance_detail"],
      message: "AI metrics require ai_generation provenance detail"
    });
  }
  if (metric.provenance === "human" && metric.provenance_detail !== "human_override") {
    context.addIssue({
      code: "custom",
      path: ["provenance_detail"],
      message: "human metrics require human_override provenance detail"
    });
  }
  if (
    metric.provenance === "system" &&
    !["system_seed", "quality_profile"].includes(metric.provenance_detail)
  ) {
    context.addIssue({
      code: "custom",
      path: ["provenance_detail"],
      message: "system metrics require system provenance detail"
    });
  }
});
export type SemanticMetric = z.infer<typeof SemanticMetricSchema>;

export const SemanticValidationIssueSchema = z.strictObject({
  code: z.string().regex(/^[A-Z][A-Z0-9_]{1,99}$/),
  severity: z.enum(["blocking", "warning", "info"]),
  target_type: z.enum([
    "layer",
    "table",
    "column",
    "relationship",
    "business_concept",
    "ambiguity",
    "metric"
  ]),
  target_key: z.string().min(1).max(255),
  message: z.string().min(1).max(500),
  evidence: z
    .record(
      z.string().min(1).max(100),
      z.union([z.string(), z.number().finite(), z.boolean()])
    )
    .default({})
});
export type SemanticValidationIssue = z.infer<
  typeof SemanticValidationIssueSchema
>;

export const SemanticValidationReportSchema = z.strictObject({
  status: z.enum([
    "not_validated",
    "valid",
    "valid_with_warnings",
    "blocked"
  ]),
  blocking_errors: z
    .array(SemanticValidationIssueSchema)
    .max(10_000)
    .default([]),
  warnings: z.array(SemanticValidationIssueSchema).max(10_000).default([]),
  info: z.array(SemanticValidationIssueSchema).max(10_000).default([]),
  validated_revision: z.number().int().positive().nullish(),
  validated_at: z
    .string()
    .datetime({ offset: true })
    .regex(
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/
    )
    .nullish(),
  validator_version: z.string().min(1).max(100)
});
export type SemanticValidationReport = z.infer<
  typeof SemanticValidationReportSchema
>;

export const SemanticLayerSchema = z.strictObject({
  contract_version: z.literal("semantic_layer.v1"),
  tenant_id: z.string().uuid(),
  connection_id: z.string().uuid(),
  semantic_version_id: z.string().uuid(),
  queryability_graph_version_id: z.string().uuid(),
  base_graph_hash: Sha256Schema,
  base_policy_hash: Sha256Schema,
  semantic_policy_snapshot: SemanticPolicySnapshotSchema,
  version: z.number().int().positive(),
  status: z.enum(["draft", "proposed", "active", "archived"]),
  freshness: z.enum(["fresh", "stale"]),
  builder_version: z.string().min(1).max(100),
  ai_model_version: z.string().min(1).max(255).nullish(),
  ai_prompt_version: z.string().min(1).max(100).nullish(),
  validator_version: z.string().min(1).max(100),
  policy_version: z.string().min(1).max(100),
  revision: z.number().int().positive(),
  semantic_hash: Sha256Schema,
  tables: z.array(SemanticTableSchema).max(5_000),
  columns: z.array(SemanticColumnSchema).max(250_000),
  relationships: z.array(SemanticRelationshipSchema).max(250_000),
  business_concepts: z.array(SemanticBusinessConceptSchema).max(10_000),
  ambiguities: z.array(SemanticAmbiguitySchema).max(10_000),
  metrics: z.array(SemanticMetricSchema).max(100_000),
  quality_report: SemanticQualityReportSchema,
  validation_report: SemanticValidationReportSchema
});
export type SemanticLayer = z.infer<typeof SemanticLayerSchema>;

export const SemanticSeedRequestSchema = z
  .strictObject({
    graph: QueryabilityGraphArtifactSchema,
    semantic_version_id: z.string().uuid(),
    queryability_graph_version_id: z.string().uuid(),
    version: z.number().int().positive(),
    semantic_policy: SemanticPolicySnapshotSchema
  })
  .superRefine((request, context) => {
    if (request.graph.status === "blocked") {
      context.addIssue({
        code: "custom",
        path: ["graph", "status"],
        message: "blocked graphs cannot seed a semantic layer"
      });
    }
  });
export type SemanticSeedRequest = z.infer<typeof SemanticSeedRequestSchema>;

export const SemanticRebaseRequestSchema = z
  .strictObject({
    source_layer: SemanticLayerSchema,
    target_graph: QueryabilityGraphArtifactSchema,
    semantic_version_id: z.string().uuid(),
    queryability_graph_version_id: z.string().uuid(),
    version: z.number().int().positive(),
    semantic_policy: SemanticPolicySnapshotSchema
  })
  .superRefine((request, context) => {
    if (
      request.source_layer.tenant_id !== request.target_graph.tenant_id ||
      request.source_layer.connection_id !== request.target_graph.connection_id
    ) {
      context.addIssue({
        code: "custom",
        path: ["target_graph"],
        message: "source layer and target graph must share tenant and connection"
      });
    }
    if (
      request.semantic_version_id === request.source_layer.semantic_version_id
    ) {
      context.addIssue({
        code: "custom",
        path: ["semantic_version_id"],
        message: "rebase must create a new semantic version"
      });
    }
    if (request.version <= request.source_layer.version) {
      context.addIssue({
        code: "custom",
        path: ["version"],
        message: "rebase version must be newer than the source version"
      });
    }
    if (
      !["active", "archived"].includes(request.source_layer.status) ||
      !["valid", "valid_with_warnings"].includes(
        request.source_layer.validation_report.status
      ) ||
      request.source_layer.validation_report.blocking_errors.length > 0 ||
      request.source_layer.validation_report.validated_revision !==
        request.source_layer.revision
    ) {
      context.addIssue({
        code: "custom",
        path: ["source_layer"],
        message:
          "rebase source must be an active or archived successfully validated version"
      });
    }
    if (request.target_graph.status === "blocked") {
      context.addIssue({
        code: "custom",
        path: ["target_graph", "status"],
        message: "blocked graphs cannot receive a semantic rebase"
      });
    }
  });
export type SemanticRebaseRequest = z.infer<
  typeof SemanticRebaseRequestSchema
>;

export const SemanticRebaseDropReasonCodeSchema = z.enum([
  "TARGET_KEY_MISSING",
  "TARGET_NOT_QUERYABLE",
  "TARGET_EDGE_NOT_TRUSTED",
  "DEPENDENCY_DROPPED",
  "DEFINITION_CHANGED",
  "INVALID_AFTER_REBASE"
]);
export type SemanticRebaseDropReasonCode = z.infer<
  typeof SemanticRebaseDropReasonCodeSchema
>;

const SemanticRebaseDropReasonCodesSchema = z
  .array(SemanticRebaseDropReasonCodeSchema)
  .min(1)
  .max(20);

export const SemanticRebaseDroppedTableSchema = z.strictObject({
  item_type: z.literal("table"),
  item_key: Sha256Schema,
  reason_codes: SemanticRebaseDropReasonCodesSchema
});
export type SemanticRebaseDroppedTable = z.infer<
  typeof SemanticRebaseDroppedTableSchema
>;

export const SemanticRebaseDroppedColumnSchema = z.strictObject({
  item_type: z.literal("column"),
  item_key: Sha256Schema,
  reason_codes: SemanticRebaseDropReasonCodesSchema
});
export type SemanticRebaseDroppedColumn = z.infer<
  typeof SemanticRebaseDroppedColumnSchema
>;

export const SemanticRebaseDroppedBusinessConceptSchema = z.strictObject({
  item_type: z.literal("business_concept"),
  item_key: z.string().uuid(),
  reason_codes: SemanticRebaseDropReasonCodesSchema
});
export type SemanticRebaseDroppedBusinessConcept = z.infer<
  typeof SemanticRebaseDroppedBusinessConceptSchema
>;

export const SemanticRebaseDroppedMetricSchema = z.strictObject({
  item_type: z.literal("metric"),
  item_key: z.string().uuid(),
  reason_codes: SemanticRebaseDropReasonCodesSchema
});
export type SemanticRebaseDroppedMetric = z.infer<
  typeof SemanticRebaseDroppedMetricSchema
>;

export const SemanticRebaseDroppedItemSchema = z.discriminatedUnion(
  "item_type",
  [
    SemanticRebaseDroppedTableSchema,
    SemanticRebaseDroppedColumnSchema,
    SemanticRebaseDroppedBusinessConceptSchema,
    SemanticRebaseDroppedMetricSchema
  ]
);
export type SemanticRebaseDroppedItem = z.infer<
  typeof SemanticRebaseDroppedItemSchema
>;

export const SemanticRebaseReportSchema = z.strictObject({
  carried_table_keys: z.array(Sha256Schema).max(5_000),
  dropped_tables: z.array(SemanticRebaseDroppedTableSchema).max(5_000),
  carried_column_keys: z.array(Sha256Schema).max(250_000),
  dropped_columns: z.array(SemanticRebaseDroppedColumnSchema).max(250_000),
  carried_business_concept_keys: z.array(z.string().uuid()).max(10_000),
  dropped_business_concepts: z
    .array(SemanticRebaseDroppedBusinessConceptSchema)
    .max(10_000),
  carried_metric_keys: z.array(z.string().uuid()).max(100_000),
  dropped_metrics: z.array(SemanticRebaseDroppedMetricSchema).max(100_000)
});
export type SemanticRebaseReport = z.infer<
  typeof SemanticRebaseReportSchema
>;

export const SemanticRebaseResultSchema = z.strictObject({
  semantic_layer: SemanticLayerSchema,
  rebase_report: SemanticRebaseReportSchema
});
export type SemanticRebaseResult = z.infer<
  typeof SemanticRebaseResultSchema
>;

export const SemanticDiscoveryCandidateKeySchema = z.strictObject({
  key_type: z.enum(["primary_key", "unique_constraint", "unique_index"]),
  column_keys: z.array(Sha256Schema).min(1).max(100)
});
export type SemanticDiscoveryCandidateKey = z.infer<
  typeof SemanticDiscoveryCandidateKeySchema
>;

export const SemanticDiscoveryTableInputSchema = z.strictObject({
  node_key: Sha256Schema,
  schema_name: z.string().min(1).max(255),
  object_name: z.string().min(1).max(255),
  object_type: z.enum(["table", "view"]),
  queryability_status: QueryabilityStatusSchema,
  bridge_candidate: z.boolean(),
  candidate_keys: z.array(SemanticDiscoveryCandidateKeySchema).max(100),
  view_lineage_status: z
    .enum(["complete", "partial", "unavailable"])
    .nullish()
});
export type SemanticDiscoveryTableInput = z.infer<
  typeof SemanticDiscoveryTableInputSchema
>;

export const SemanticDiscoveryColumnInputSchema = z.strictObject({
  column_key: Sha256Schema,
  node_key: Sha256Schema,
  physical_name: z.string().min(1).max(255),
  native_type: z.string().min(1).max(255).nullish(),
  normalized_type: z.string().min(1).max(255).nullish(),
  technical_role: SchemaTechnicalRoleSchema,
  nullable: z.boolean(),
  queryability_status: QueryabilityStatusSchema,
  sensitivity: QueryabilitySensitivitySchema
});
export type SemanticDiscoveryColumnInput = z.infer<
  typeof SemanticDiscoveryColumnInputSchema
>;

export const SemanticDiscoveryColumnPairInputSchema = z.strictObject({
  from_column_key: Sha256Schema,
  from_column_name: z.string().min(1).max(255),
  to_column_key: Sha256Schema,
  to_column_name: z.string().min(1).max(255)
});
export type SemanticDiscoveryColumnPairInput = z.infer<
  typeof SemanticDiscoveryColumnPairInputSchema
>;

export const SemanticDiscoveryRelationshipInputSchema = z.strictObject({
  edge_key: Sha256Schema,
  constraint_name: z.string().min(1).max(255),
  from_node_key: Sha256Schema,
  to_node_key: Sha256Schema,
  column_pairs: z
    .array(SemanticDiscoveryColumnPairInputSchema)
    .min(1)
    .max(100),
  relationship_shape: z.enum(["one_to_one", "many_to_one"]),
  child_to_parent: z.enum(["zero_or_one", "exactly_one"]),
  parent_to_child: z.enum(["zero_or_one", "zero_or_many"]),
  nullable_fk: z.boolean(),
  self_reference: z.boolean()
});
export type SemanticDiscoveryRelationshipInput = z.infer<
  typeof SemanticDiscoveryRelationshipInputSchema
>;

export const SemanticDiscoveryInputSchema = z.strictObject({
  contract_version: z.literal("semantic_discovery_input.v1"),
  engine: z.literal("sqlserver"),
  base_graph_hash: Sha256Schema,
  graph_status: z.enum(["complete", "partial"]),
  tables: z.array(SemanticDiscoveryTableInputSchema).max(5_000),
  columns: z.array(SemanticDiscoveryColumnInputSchema).max(250_000),
  relationships: z
    .array(SemanticDiscoveryRelationshipInputSchema)
    .max(250_000)
});
export type SemanticDiscoveryInput = z.infer<
  typeof SemanticDiscoveryInputSchema
>;

const Rfc3339DateTimeSchema = z
  .string()
  .datetime({ offset: true })
  .regex(
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/
  );

export const AIProviderSchema = z.enum(["openai", "anthropic"]);
export type AIProvider = z.infer<typeof AIProviderSchema>;

export const OpenAISemanticModelSchema = z.enum(["gpt-5.5"]);
export type OpenAISemanticModel = z.infer<typeof OpenAISemanticModelSchema>;

export const AnthropicSemanticModelSchema = z.enum([
  "claude-sonnet-4-6",
  "claude-opus-4-8"
]);
export type AnthropicSemanticModel = z.infer<
  typeof AnthropicSemanticModelSchema
>;

export const OpenAIReasoningEffortSchema = z.enum([
  "none",
  "low",
  "medium",
  "high",
  "xhigh"
]);
export type OpenAIReasoningEffort = z.infer<
  typeof OpenAIReasoningEffortSchema
>;

export const AnthropicEffortSchema = z.enum([
  "low",
  "medium",
  "high",
  "xhigh",
  "max"
]);
export type AnthropicEffort = z.infer<typeof AnthropicEffortSchema>;

export const OpenAIThinkingConfigSchema = z.strictObject({
  type: z.literal("openai_reasoning"),
  effort: OpenAIReasoningEffortSchema
});
export type OpenAIThinkingConfig = z.infer<typeof OpenAIThinkingConfigSchema>;

export const AnthropicThinkingConfigSchema = z
  .strictObject({
    type: z.literal("anthropic_adaptive"),
    enabled: z.boolean(),
    effort: AnthropicEffortSchema
  })
  .superRefine((value, context) => {
    if (!value.enabled && value.effort !== "medium") {
      context.addIssue({
        code: "custom",
        message: "Disabled adaptive thinking must use medium effort."
      });
    }
  });
export type AnthropicThinkingConfig = z.infer<
  typeof AnthropicThinkingConfigSchema
>;

export const AISemanticProviderConfigSchema = z.discriminatedUnion("provider", [
  z.strictObject({
    provider: z.literal("openai"),
    setting_id: z.string().uuid(),
    model_id: OpenAISemanticModelSchema,
    thinking: OpenAIThinkingConfigSchema,
    secret_ref: z.string().min(1).max(2_000)
  }),
  z
    .strictObject({
      provider: z.literal("anthropic"),
      setting_id: z.string().uuid(),
      model_id: AnthropicSemanticModelSchema,
      thinking: AnthropicThinkingConfigSchema,
      secret_ref: z.string().min(1).max(2_000)
    })
    .superRefine((value, context) => {
      if (
        value.model_id === "claude-sonnet-4-6" &&
        ["xhigh", "max"].includes(value.thinking.effort)
      ) {
        context.addIssue({
          code: "custom",
          message: "Claude Sonnet 4.6 supports low, medium, or high effort."
        });
      }
    })
]);
export type AISemanticProviderConfig = z.infer<
  typeof AISemanticProviderConfigSchema
>;

export const SemanticGenerationRequestSchema = z
  .strictObject({
    graph: QueryabilityGraphArtifactSchema,
    seed: SemanticLayerSchema,
    provider_config: AISemanticProviderConfigSchema,
    semantic_policy: SemanticPolicySnapshotSchema
  })
  .superRefine((request, context) => {
    if (request.graph.status === "blocked") {
      context.addIssue({
        code: "custom",
        path: ["graph", "status"],
        message: "blocked graphs cannot enter semantic generation"
      });
    }
    if (
      request.seed.tenant_id !== request.graph.tenant_id ||
      request.seed.connection_id !== request.graph.connection_id
    ) {
      context.addIssue({
        code: "custom",
        path: ["seed"],
        message: "seed tenant and connection must match graph"
      });
    }
    if (request.seed.base_graph_hash !== request.graph.graph_hash) {
      context.addIssue({
        code: "custom",
        path: ["seed", "base_graph_hash"],
        message: "seed must be based on the supplied graph"
      });
    }
    if (
      request.seed.base_policy_hash !== request.semantic_policy.policy_hash ||
      JSON.stringify(request.seed.semantic_policy_snapshot) !==
        JSON.stringify(request.semantic_policy)
    ) {
      context.addIssue({
        code: "custom",
        path: ["semantic_policy"],
        message: "seed must be based on the supplied semantic policy"
      });
    }
    if (request.seed.status !== "draft" || request.seed.freshness !== "fresh") {
      context.addIssue({
        code: "custom",
        path: ["seed"],
        message: "seed must be a fresh draft"
      });
    }
  });
export type SemanticGenerationRequest = z.infer<
  typeof SemanticGenerationRequestSchema
>;

export const AIProviderSettingSummarySchema = z.strictObject({
  id: z.string().uuid(),
  tenant_id: z.string().uuid(),
  provider: AIProviderSchema,
  model_id: z.union([OpenAISemanticModelSchema, AnthropicSemanticModelSchema]),
  display_name: z.string().min(1).max(160),
  thinking: z.union([OpenAIThinkingConfigSchema, AnthropicThinkingConfigSchema]),
  status: z.enum(["ready", "disabled", "failed"]),
  is_default: z.boolean(),
  last_test_status: z.enum(["ok", "failed"]).nullable(),
  last_tested_at: Rfc3339DateTimeSchema.nullable(),
  created_at: Rfc3339DateTimeSchema,
  updated_at: Rfc3339DateTimeSchema
});
export type AIProviderSettingSummary = z.infer<
  typeof AIProviderSettingSummarySchema
>;

export const AISemanticTableProposalSchema = z.strictObject({
  node_key: Sha256Schema,
  display_name: z.string().min(1).max(255),
  description: z.string().min(1).max(2_000),
  business_domain: z.string().min(1).max(255),
  synonyms: z.array(z.string().min(1).max(255)).max(100)
});
export type AISemanticTableProposal = z.infer<
  typeof AISemanticTableProposalSchema
>;

export const AISemanticColumnProposalSchema = z.strictObject({
  column_key: Sha256Schema,
  display_name: z.string().min(1).max(255),
  description: z.string().min(1).max(2_000),
  synonyms: z.array(z.string().min(1).max(255)).max(100),
  semantic_role: z.string().min(1).max(100),
  format_hint: z.enum([
    "text",
    "integer",
    "decimal",
    "currency",
    "percentage",
    "date",
    "datetime",
    "boolean",
    "identifier"
  ])
});
export type AISemanticColumnProposal = z.infer<
  typeof AISemanticColumnProposalSchema
>;

export const AISemanticBusinessConceptProposalSchema = z.strictObject({
  concept_ref: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  display_name: z.string().min(1).max(255),
  description: z.string().min(1).max(2_000),
  synonyms: z.array(z.string().min(1).max(255)).max(100)
});
export type AISemanticBusinessConceptProposal = z.infer<
  typeof AISemanticBusinessConceptProposalSchema
>;

export const AISemanticDimensionProposalSchema = z.strictObject({
  dimension_column_key: Sha256Schema,
  edge_path: z.array(Sha256Schema).max(4)
});
export type AISemanticDimensionProposal = z.infer<
  typeof AISemanticDimensionProposalSchema
>;

export const AISemanticMetricFormatHintSchema = z.strictObject({
  value_type: z.enum(["currency", "number", "percentage", "count", "duration"]),
  decimals: z.number().int().min(0).max(6).nullish()
});

export const AISemanticMetricProposalSchema = z.strictObject({
  canonical_name: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  business_concept_ref: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  metric_variant: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  name: z.string().min(1).max(255),
  description: z.string().min(1).max(2_000),
  source_table_key: Sha256Schema,
  aggregation: z.enum([
    "count",
    "count_distinct",
    "sum",
    "avg",
    "min",
    "max"
  ]),
  measure_column_key: Sha256Schema.nullable(),
  default_date_column_key: Sha256Schema.nullable(),
  format_hint: AISemanticMetricFormatHintSchema,
  synonyms: z.array(z.string().min(1).max(255)).max(100),
  reasoning_summary: z.string().min(1).max(1_000)
});
export type AISemanticMetricProposal = z.infer<
  typeof AISemanticMetricProposalSchema
>;

export const AISemanticAmbiguitySchema = z.strictObject({
  code: z.string().regex(/^[A-Z][A-Z0-9_]{1,99}$/),
  target_type: z.enum([
    "table",
    "column",
    "business_concept",
    "metric"
  ]),
  target_ref: z.string().min(1).max(255),
  summary: z.string().min(1).max(500),
  clarification_question: z.string().min(1).max(500),
  severity: SemanticAmbiguitySeveritySchema
});
export type AISemanticAmbiguity = z.infer<
  typeof AISemanticAmbiguitySchema
>;

export const AISemanticDraftProposalSchema = z.strictObject({
  contract_version: z.literal("semantic_ai_draft.v1"),
  tables: z.array(AISemanticTableProposalSchema).max(5_000),
  columns: z.array(AISemanticColumnProposalSchema).max(250_000),
  business_concepts: z
    .array(AISemanticBusinessConceptProposalSchema)
    .max(10_000),
  metrics: z.array(AISemanticMetricProposalSchema).max(10_000),
  ambiguities: z.array(AISemanticAmbiguitySchema).max(10_000)
});
export type AISemanticDraftProposal = z.infer<
  typeof AISemanticDraftProposalSchema
>;

export const SemanticGenerationProvenanceSchema = z.strictObject({
  provider: AIProviderSchema,
  model_version: z.string().min(1).max(255),
  thinking_config: z
    .union([OpenAIThinkingConfigSchema, AnthropicThinkingConfigSchema])
    .nullable(),
  prompt_version: z.string().min(1).max(100),
  generated_at: Rfc3339DateTimeSchema,
  input_hash: Sha256Schema,
  proposal_hash: Sha256Schema,
  response_id: z.string().min(1).max(255)
});
export type SemanticGenerationProvenance = z.infer<
  typeof SemanticGenerationProvenanceSchema
>;

export const SemanticGenerationResultSchema = z.strictObject({
  proposal: AISemanticDraftProposalSchema,
  provenance: SemanticGenerationProvenanceSchema,
  semantic_layer: SemanticLayerSchema
});
export type SemanticGenerationResult = z.infer<
  typeof SemanticGenerationResultSchema
>;

export const NorthStarValueTypeSchema = z.enum([
  "currency",
  "number",
  "percentage",
  "count"
]);
export type NorthStarValueType = z.infer<typeof NorthStarValueTypeSchema>;

export const NorthStarPeriodTypeSchema = z.enum([
  "day",
  "week",
  "month",
  "quarter",
  "year",
  "rolling_12_months",
  "custom"
]);
export type NorthStarPeriodType = z.infer<typeof NorthStarPeriodTypeSchema>;

export const NorthStarToleranceModeSchema = z.enum([
  "percentage",
  "absolute",
  "range"
]);
export type NorthStarToleranceMode = z.infer<
  typeof NorthStarToleranceModeSchema
>;

export const NorthStarSeveritySchema = z.enum([
  "low",
  "medium",
  "high",
  "critical"
]);
export type NorthStarSeverity = z.infer<typeof NorthStarSeveritySchema>;

export const NorthStarBenchmarkSchema = z
  .strictObject({
    benchmark_key: z.string().uuid(),
    tenant_id: z.string().uuid(),
    connection_id: z.string().uuid(),
    dashboard_id: z.string().uuid().nullable(),
    semantic_version_id: z.string().uuid().nullable(),
    metric_key: z.string().uuid().nullable(),
    name: z.string().min(1).max(255),
    description: z.string().max(2_000).nullable(),
    expected_value: z.number().finite(),
    value_type: NorthStarValueTypeSchema,
    currency: z.string().regex(/^[A-Z]{3}$/).nullable(),
    period_type: NorthStarPeriodTypeSchema,
    period_start: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/)
      .nullable(),
    period_end: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/)
      .nullable(),
    tolerance_mode: NorthStarToleranceModeSchema,
    tolerance_percentage: z.number().finite().positive().nullable(),
    min_value: z.number().finite().nullable(),
    max_value: z.number().finite().nullable(),
    severity: NorthStarSeveritySchema,
    enabled: z.boolean(),
    created_by: z.string().uuid(),
    updated_by: z.string().uuid(),
    created_at: Rfc3339DateTimeSchema,
    updated_at: Rfc3339DateTimeSchema
  })
  .superRefine((benchmark, context) => {
    if (benchmark.value_type === "currency" && !benchmark.currency) {
      context.addIssue({
        code: "custom",
        path: ["currency"],
        message: "currency benchmarks require an ISO currency code"
      });
    }
    if (benchmark.value_type !== "currency" && benchmark.currency !== null) {
      context.addIssue({
        code: "custom",
        path: ["currency"],
        message: "non-currency benchmarks must not include currency"
      });
    }
    if (benchmark.period_type === "custom") {
      if (!benchmark.period_start || !benchmark.period_end) {
        context.addIssue({
          code: "custom",
          path: ["period_start"],
          message: "custom periods require start and end dates"
        });
      } else if (benchmark.period_start > benchmark.period_end) {
        context.addIssue({
          code: "custom",
          path: ["period_end"],
          message: "period_end must be on or after period_start"
        });
      }
    }
    if (benchmark.tolerance_mode === "percentage") {
      if (
        benchmark.tolerance_percentage === null ||
        benchmark.min_value !== null ||
        benchmark.max_value !== null
      ) {
        context.addIssue({
          code: "custom",
          path: ["tolerance_percentage"],
          message:
            "percentage tolerance requires tolerance_percentage and no range"
        });
      }
    } else if (
      benchmark.tolerance_percentage !== null ||
      benchmark.min_value === null ||
      benchmark.max_value === null ||
      benchmark.min_value > benchmark.max_value
    ) {
      context.addIssue({
        code: "custom",
        path: ["min_value"],
        message:
          "absolute/range tolerance requires a valid min_value and max_value"
      });
    }
    if (
      (benchmark.metric_key === null) !==
      (benchmark.semantic_version_id === null)
    ) {
      context.addIssue({
        code: "custom",
        path: ["metric_key"],
        message: "metric benchmarks require semantic_version_id and metric_key"
      });
    }
  });
export type NorthStarBenchmark = z.infer<typeof NorthStarBenchmarkSchema>;

export const NorthStarBenchmarkInputSchema = z
  .strictObject({
    connection_id: z.string().uuid(),
    dashboard_id: z.string().uuid().nullable().optional(),
    semantic_version_id: z.string().uuid().nullable().optional(),
    metric_key: z.string().uuid().nullable().optional(),
    name: z.string().trim().min(1).max(255),
    description: z.string().trim().max(2_000).nullable().optional(),
    expected_value: z.number().finite(),
    value_type: NorthStarValueTypeSchema,
    currency: z.string().trim().regex(/^[A-Z]{3}$/).nullable().optional(),
    period_type: NorthStarPeriodTypeSchema,
    period_start: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/)
      .nullable()
      .optional(),
    period_end: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/)
      .nullable()
      .optional(),
    tolerance_mode: NorthStarToleranceModeSchema,
    tolerance_percentage: z.number().finite().positive().nullable().optional(),
    min_value: z.number().finite().nullable().optional(),
    max_value: z.number().finite().nullable().optional(),
    severity: NorthStarSeveritySchema,
    enabled: z.boolean().optional()
  })
  .superRefine((input, context) => {
    const metricKey = input.metric_key ?? null;
    const semanticVersionId = input.semantic_version_id ?? null;
    if ((metricKey === null) !== (semanticVersionId === null)) {
      context.addIssue({
        code: "custom",
        path: ["metric_key"],
        message: "metric benchmarks require semantic_version_id and metric_key"
      });
    }
    if (input.value_type === "currency" && !input.currency) {
      context.addIssue({
        code: "custom",
        path: ["currency"],
        message: "currency benchmarks require an ISO currency code"
      });
    }
    if (input.value_type !== "currency" && input.currency != null) {
      context.addIssue({
        code: "custom",
        path: ["currency"],
        message: "non-currency benchmarks must not include currency"
      });
    }
    if (input.period_type === "custom") {
      if (!input.period_start || !input.period_end) {
        context.addIssue({
          code: "custom",
          path: ["period_start"],
          message: "custom periods require start and end dates"
        });
      } else if (input.period_start > input.period_end) {
        context.addIssue({
          code: "custom",
          path: ["period_end"],
          message: "period_end must be on or after period_start"
        });
      }
    }
    if (input.tolerance_mode === "percentage") {
      if (
        input.tolerance_percentage == null ||
        input.min_value != null ||
        input.max_value != null
      ) {
        context.addIssue({
          code: "custom",
          path: ["tolerance_percentage"],
          message:
            "percentage tolerance requires tolerance_percentage and no range"
        });
      }
    } else if (
      input.tolerance_percentage != null ||
      input.min_value == null ||
      input.max_value == null ||
      input.min_value > input.max_value
    ) {
      context.addIssue({
        code: "custom",
        path: ["min_value"],
        message:
          "absolute/range tolerance requires a valid min_value and max_value"
      });
    }
  });
export type NorthStarBenchmarkInput = z.infer<
  typeof NorthStarBenchmarkInputSchema
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
    "north_star_plausibility",
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

export const QueryPermissionSchema = z.strictObject({
  can_view_sql: z.boolean(),
  can_save_widget: z.boolean()
});
export type QueryPermission = z.infer<typeof QueryPermissionSchema>;

export const QueryIntentUnsupportedReasonSchema = z.enum([
  "multi_metric_not_supported",
  "unsafe_dimension_for_metric",
  "semantic_layer_stale",
  "metric_not_eligible",
  "sensitive_filter_not_allowed",
  "unsupported_time_expression",
  "unsupported_calculated_metric",
  "unsupported_comparison"
]);
export type QueryIntentUnsupportedReason = z.infer<
  typeof QueryIntentUnsupportedReasonSchema
>;

export const QueryIntentPolicySchema = z.strictObject({
  order_status_scope: z
    .enum(["all_statuses_with_disclosure", "clarification_required"])
    .default("all_statuses_with_disclosure")
});
export type QueryIntentPolicy = z.infer<typeof QueryIntentPolicySchema>;

export const QueryIntentAICandidateSchema = z.strictObject({
  primary_metric_key: z.string().uuid().nullable().default(null),
  dimension_column_key: Sha256Schema.nullable().default(null),
  filter_column_keys: z.array(Sha256Schema).max(10).default([])
});
export type QueryIntentAICandidate = z.infer<typeof QueryIntentAICandidateSchema>;

export const QueryIntentRequestSchema = z
  .strictObject({
    tenant_id: z.string().uuid(),
    connection_id: z.string().uuid(),
    user_id: z.string().uuid(),
    question: z.string().min(1).max(1000),
    semantic_layer: SemanticLayerSchema,
    graph: QueryabilityGraphArtifactSchema,
    policy: QueryIntentPolicySchema.default({
      order_status_scope: "all_statuses_with_disclosure"
    }),
    ai_enabled: z.boolean().default(false),
    ai_candidate: QueryIntentAICandidateSchema.nullish()
  })
  .superRefine((request, context) => {
    if (
      request.semantic_layer.tenant_id !== request.tenant_id ||
      request.semantic_layer.connection_id !== request.connection_id ||
      request.graph.tenant_id !== request.tenant_id ||
      request.graph.connection_id !== request.connection_id
    ) {
      context.addIssue({
        code: "custom",
        path: ["semantic_layer"],
        message:
          "semantic_layer and graph tenant/connection must match the request"
      });
    }
  });
export type QueryIntentRequest = z.infer<typeof QueryIntentRequestSchema>;

export const QueryIntentTimeRangeSchema = z.strictObject({
  kind: z.enum(["year", "month", "custom"]),
  start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  end_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  label: z.string().min(1).max(100)
});
export type QueryIntentTimeRange = z.infer<typeof QueryIntentTimeRangeSchema>;

export const QueryIntentGroupByDimensionSchema = z.strictObject({
  column_key: Sha256Schema,
  edge_path: z.array(Sha256Schema).max(4).default([]),
  safety: z.literal("safe")
});
export type QueryIntentGroupByDimension = z.infer<
  typeof QueryIntentGroupByDimensionSchema
>;

export const QueryIntentRejectedAlternativeSchema = z.strictObject({
  reason: QueryIntentUnsupportedReasonSchema,
  metric_key: z.string().uuid().nullish(),
  dimension_column_key: Sha256Schema.nullish(),
  message: z.string().min(1).max(500)
});
export type QueryIntentRejectedAlternative = z.infer<
  typeof QueryIntentRejectedAlternativeSchema
>;

export const QueryIntentAuditEventSchema = z.strictObject({
  code: z.string().regex(/^[A-Z][A-Z0-9_]{1,99}$/),
  message: z.string().min(1).max(500),
  metadata: z
    .record(z.string().min(1).max(100), z.union([z.string(), z.number(), z.boolean()]))
    .default({})
});
export type QueryIntentAuditEvent = z.infer<typeof QueryIntentAuditEventSchema>;

export const QueryIntentClarificationOptionSchema = z.strictObject({
  label: z.string().min(1).max(255),
  value: z.string().min(1).max(100),
  metric_key: z.string().uuid().nullish(),
  business_concept_ref: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/).nullish(),
  metric_variant: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/).nullish()
});
export type QueryIntentClarificationOption = z.infer<
  typeof QueryIntentClarificationOptionSchema
>;

export const QueryIntentClarificationSchema = z.strictObject({
  reason_code: z.string().regex(/^[A-Z][A-Z0-9_]{1,99}$/),
  question: z.string().min(1).max(500),
  options: z.array(QueryIntentClarificationOptionSchema).min(1).max(10)
});
export type QueryIntentClarification = z.infer<
  typeof QueryIntentClarificationSchema
>;

export const QueryIntentPlanSchema = z.strictObject({
  primary_metric_key: z.string().uuid(),
  requested_concept_ref: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  selected_variant: z.string().regex(/^[a-z][a-z0-9_]{1,99}$/),
  effective_date_column_key: Sha256Schema.nullish(),
  time_range: QueryIntentTimeRangeSchema.nullish(),
  group_by_dimensions: z.array(QueryIntentGroupByDimensionSchema).max(1).default([]),
  required_edge_path_keys: z.array(Sha256Schema).max(4).default([]),
  grain_safety_decision: z.literal("safe"),
  filters: z.array(SemanticFilterSchema).max(10).default([]),
  rejected_alternatives: z
    .array(QueryIntentRejectedAlternativeSchema)
    .max(20)
    .default([]),
  disclosures: z.array(z.string().min(1).max(500)).max(20).default([]),
  audit_trail: z.array(QueryIntentAuditEventSchema).max(100).default([])
});
export type QueryIntentPlan = z.infer<typeof QueryIntentPlanSchema>;

export const QueryIntentResultSchema = z
  .strictObject({
    status: z.enum(["ready", "needs_clarification", "blocked"]),
    unsupported_reason: QueryIntentUnsupportedReasonSchema.nullish(),
    plan: QueryIntentPlanSchema.nullish(),
    clarification: QueryIntentClarificationSchema.nullish(),
    audit_trail: z.array(QueryIntentAuditEventSchema).max(100).default([]),
    message: z.string().min(1).max(500)
  })
  .superRefine((result, context) => {
    if (
      result.status === "ready" &&
      (result.plan == null ||
        result.clarification != null ||
        result.unsupported_reason != null)
    ) {
      context.addIssue({
        code: "custom",
        message: "ready intent results require only a plan"
      });
    }
    if (
      result.status === "needs_clarification" &&
      (result.clarification == null ||
        result.plan != null ||
        result.unsupported_reason != null)
    ) {
      context.addIssue({
        code: "custom",
        message: "needs_clarification intent results require only clarification"
      });
    }
    if (
      result.status === "blocked" &&
      (result.plan != null ||
        result.clarification != null ||
        result.unsupported_reason == null)
    ) {
      context.addIssue({
        code: "custom",
        message: "blocked intent results require unsupported_reason only"
      });
    }
  });
export type QueryIntentResult = z.infer<typeof QueryIntentResultSchema>;

export const QueryRequestSchema = z
  .strictObject({
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
  })
  .superRefine((request, context) => {
    if (
      request.semantic_layer.tenant_id !== request.tenant_id ||
      request.semantic_layer.connection_id !== request.connection_id
    ) {
      context.addIssue({
        code: "custom",
        path: ["semantic_layer"],
        message:
          "semantic_layer tenant and connection must match the request"
      });
    }
    if (
      request.semantic_layer.status !== "active" ||
      request.semantic_layer.freshness !== "fresh" ||
      !["valid", "valid_with_warnings"].includes(
      request.semantic_layer.validation_report.status
      ) ||
      request.semantic_layer.validation_report.blocking_errors.length > 0 ||
      request.semantic_layer.validation_report.validated_revision !==
        request.semantic_layer.revision ||
      request.semantic_layer.validation_report.validated_at == null ||
      request.semantic_layer.validation_report.validator_version !==
        request.semantic_layer.validator_version
    ) {
      context.addIssue({
        code: "custom",
        path: ["semantic_layer"],
        message:
          "semantic_layer must be active, fresh, and successfully validated"
      });
    }
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
