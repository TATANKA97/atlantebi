export type SemanticColumnDisplay = {
  id: string;
  semantic_table_id: string;
  physical_name: string;
  data_type: string;
  role: string;
  pii: boolean;
  metadata: {
    is_nullable?: boolean;
    is_primary_key?: boolean;
    is_sensitive?: boolean;
    pii_reason?: string;
    queryable?: boolean;
    sensitive_reason?: string;
  };
};

export function isSemanticColumnQueryable(column: SemanticColumnDisplay) {
  return column.metadata.queryable !== false && column.role !== "unknown";
}

export function splitSemanticColumns(columns: SemanticColumnDisplay[]) {
  return {
    excludedColumns: columns.filter((column) => !isSemanticColumnQueryable(column)),
    queryableColumns: columns.filter(isSemanticColumnQueryable)
  };
}

export function semanticColumnFlags(column: SemanticColumnDisplay) {
  const flags: string[] = [];

  if (column.metadata.is_primary_key) {
    flags.push("PK");
  }

  flags.push(column.metadata.is_nullable ? "nullable" : "not null");

  if (column.pii) {
    flags.push("PII");
  }

  if (column.metadata.queryable === false) {
    flags.push("excluded");
  }

  return flags;
}
