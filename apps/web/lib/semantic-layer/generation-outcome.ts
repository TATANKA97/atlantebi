import type { SemanticLayer } from "@atlantebi/contracts";

export type SemanticGenerationMessage =
  | "semantic_proposal_activated"
  | "semantic_proposal_activated_with_warnings"
  | "semantic_proposal_generated_blocked"
  | "semantic_proposal_generated_with_warnings"
  | "semantic_proposal_validated_not_activated";

export function semanticGenerationMessage(
  artifact: SemanticLayer
): SemanticGenerationMessage {
  if (
    artifact.validation_report.status === "blocked" ||
    artifact.quality_report.status === "blocked"
  ) {
    return "semantic_proposal_generated_blocked";
  }
  const warning =
    artifact.validation_report.status === "valid_with_warnings" ||
    artifact.quality_report.issues.some((issue) => issue.severity === "warning");
  if (artifact.status === "active") {
    return warning
      ? "semantic_proposal_activated_with_warnings"
      : "semantic_proposal_activated";
  }
  return warning
    ? "semantic_proposal_generated_with_warnings"
    : "semantic_proposal_validated_not_activated";
}
