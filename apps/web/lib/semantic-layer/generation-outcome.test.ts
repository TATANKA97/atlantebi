import { describe, expect, it } from "vitest";

import { SemanticLayerSchema } from "@atlantebi/contracts";
import semanticFixture from "../../../../packages/contracts/src/fixtures/semantic-layer-v1.json";
import { semanticGenerationMessage } from "./generation-outcome";

const base = SemanticLayerSchema.parse(semanticFixture);

describe("semantic generation outcome", () => {
  it("does not report blocked validation as validated", () => {
    expect(
      semanticGenerationMessage({
        ...base,
        status: "draft",
        quality_report: { ...base.quality_report, status: "blocked" },
        validation_report: {
          ...base.validation_report,
          status: "blocked"
        }
      })
    ).toBe("semantic_proposal_generated_blocked");
  });

  it("distinguishes warning and activation outcomes", () => {
    expect(
      semanticGenerationMessage({ ...base, status: "proposed" })
    ).toBe("semantic_proposal_generated_with_warnings");
    expect(semanticGenerationMessage({ ...base, status: "active" })).toBe(
      "semantic_proposal_activated_with_warnings"
    );
  });

  it("surfaces non-blocking quality-profile mismatches as warnings", () => {
    expect(
      semanticGenerationMessage({
        ...base,
        status: "active",
        quality_report: {
          ...base.quality_report,
          status: "passed",
          issues: [
            {
              code: "AI_REQUIRED_METRIC_MISMATCH",
              severity: "warning",
              message: "Candidate replaced by the configured quality profile.",
              spec_key: "adventureworks.revenue.net_header"
            }
          ]
        },
        validation_report: {
          ...base.validation_report,
          status: "valid",
          warnings: []
        }
      })
    ).toBe("semantic_proposal_activated_with_warnings");
  });
});
