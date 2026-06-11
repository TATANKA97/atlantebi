export type SemanticColumnDisplay = {
  id: string;
  semantic_table_id: string;
  physical_name: string;
  data_type: string;
  role: string;
  pii: boolean;
  metadata: {
    declared_type?: string;
    declared_type_schema?: string;
    declared_type_name?: string;
    declared_type_is_user_defined?: boolean;
    declared_type_is_assembly?: boolean;
    declared_type_available: boolean;
    technical_role: string;
    is_nullable?: boolean;
    is_primary_key?: boolean;
    is_sensitive: boolean;
    pii_reason?: string;
    queryable: boolean;
    exclusion_reason?: string;
    sensitive_reason?: string;
  };
};

export function isSemanticColumnQueryable(column: SemanticColumnDisplay) {
  return column.metadata.queryable === true;
}

export function splitSemanticColumns(columns: SemanticColumnDisplay[]) {
  return {
    excludedColumns: columns.filter((column) => !isSemanticColumnQueryable(column)),
    queryableColumns: columns.filter(isSemanticColumnQueryable)
  };
}

export function semanticColumnTypeLabel(column: SemanticColumnDisplay) {
  if (
    column.metadata.declared_type_name &&
    column.metadata.declared_type_name.toLowerCase() !== column.data_type.toLowerCase()
  ) {
    const schemaPrefix = column.metadata.declared_type_schema
      ? `${column.metadata.declared_type_schema}.`
      : "";
    return `${column.data_type} (${schemaPrefix}${column.metadata.declared_type_name})`;
  }

  if (
    column.metadata.declared_type &&
    column.metadata.declared_type.toLowerCase() !== column.data_type.toLowerCase()
  ) {
    return `${column.data_type} (${column.metadata.declared_type})`;
  }

  return column.data_type;
}

export function semanticColumnDatabaseFlags(column: SemanticColumnDisplay) {
  const flags: string[] = [];

  if (column.metadata.is_primary_key) {
    flags.push("PK");
  }

  flags.push(column.metadata.is_nullable ? "nullable" : "not null");
  return flags;
}

export function semanticColumnAtlanteFlags(column: SemanticColumnDisplay) {
  const flags: string[] = [];

  flags.push(column.metadata.queryable === true ? "queryable" : "excluded");

  if (column.pii) {
    flags.push("PII");
  }

  if (column.metadata.is_sensitive === true) {
    flags.push("sensitive");
  }

  if (column.metadata.exclusion_reason) {
    flags.push(column.metadata.exclusion_reason);
  }

  return flags;
}
