import {
  QueryabilityGraphArtifactSchema,
  SchemaIntrospectionResponseSchema,
  type QueryabilityGraphArtifact,
  type SchemaIntrospectionResponse
} from "@atlantebi/contracts";

export function parsePersistedQueryabilityGraph(
  value: unknown
): QueryabilityGraphArtifact | null {
  const parsed = QueryabilityGraphArtifactSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

export function parsePersistedTechnicalSnapshot(
  value: unknown
): SchemaIntrospectionResponse | null {
  const parsed = SchemaIntrospectionResponseSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}
