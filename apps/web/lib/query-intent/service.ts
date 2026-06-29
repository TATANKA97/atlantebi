import "server-only";

import {
  type QueryabilityGraphArtifact,
  QueryIntentResultSchema,
  type QueryIntentResult,
  QueryIntentTestSuiteReportSchema,
  type QueryIntentTestAIMode,
  type QueryIntentTestSuiteId,
  type QueryIntentTestSuiteReport,
  type SemanticLayer
} from "@atlantebi/contracts";

import { postQueryEngine } from "../query-engine/client";
import {
  graphForSemanticService,
  readCurrentQueryabilityGraph,
  readCurrentSemanticLayer
} from "../semantic-layer/service";
import type { ActiveTenantContext } from "../tenant";

export class QueryIntentServiceError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status = 500
  ) {
    super(message);
    this.name = "QueryIntentServiceError";
  }
}

export type QueryIntentResolution = {
  result: QueryIntentResult;
  semanticLayer: SemanticLayer;
  graph: QueryabilityGraphArtifact;
};

export async function resolveQueryIntent({
  connectionId,
  context,
  question
}: {
  connectionId: string;
  context: ActiveTenantContext;
  question: string;
}): Promise<QueryIntentResolution> {
  const [semanticLayer, graph] = await Promise.all([
    readCurrentSemanticLayer({ connectionId, context }),
    readCurrentQueryabilityGraph({ connectionId, context })
  ]);
  if (!semanticLayer) {
    throw new QueryIntentServiceError(
      "semantic_layer_not_found",
      "Semantic Layer corrente non trovato.",
      404
    );
  }
  const graphArtifact = graphForSemanticService(graph.graph);

  const result = await postQueryEngine(
    "/query/intent/resolve",
    {
      tenant_id: context.tenantId,
      connection_id: connectionId,
      user_id: context.userId,
      question,
      semantic_layer: semanticLayer.artifact,
      graph: graphArtifact,
      ai_enabled: false
    },
    QueryIntentResultSchema,
    30_000
  );
  return {
    result,
    semanticLayer: semanticLayer.artifact,
    graph: graphArtifact
  };
}

export async function runQueryIntentTestSuite({
  aiMode = "disabled",
  connectionId,
  connectionName,
  context,
  environment = process.env.VERCEL_ENV ?? process.env.NODE_ENV ?? "unknown",
  suiteId = "adventureworks_v1"
}: {
  aiMode?: QueryIntentTestAIMode;
  connectionId: string;
  connectionName?: string | null;
  context: ActiveTenantContext;
  environment?: string;
  suiteId?: QueryIntentTestSuiteId;
}): Promise<QueryIntentTestSuiteReport> {
  const [semanticLayer, graph] = await Promise.all([
    readCurrentSemanticLayer({ connectionId, context }),
    readCurrentQueryabilityGraph({ connectionId, context })
  ]);
  if (!semanticLayer) {
    throw new QueryIntentServiceError(
      "semantic_layer_not_found",
      "Semantic Layer corrente non trovato.",
      404
    );
  }
  const graphArtifact = graphForSemanticService(graph.graph);
  return postQueryEngine(
    "/query/intent/test-suite/run",
    {
      tenant_id: context.tenantId,
      connection_id: connectionId,
      user_id: context.userId,
      connection_name: connectionName ?? connectionId,
      environment,
      suite_id: suiteId,
      ai_mode: aiMode,
      semantic_layer: semanticLayer.artifact,
      graph: graphArtifact
    },
    QueryIntentTestSuiteReportSchema,
    120_000
  );
}
