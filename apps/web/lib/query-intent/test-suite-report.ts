import type {
  QueryIntentTestResult,
  QueryIntentTestSuiteReport
} from "@atlantebi/contracts";

export function queryIntentReportSummary(report: QueryIntentTestSuiteReport) {
  return `Query Intent ${report.suite_id}: ${report.summary.passed}/${report.summary.total} passed, ${report.summary.failed} failed, invariants ${report.summary.invariants.failed} failed, advisory regressions ${report.summary.ai_advisory.regressions} (${report.connection.name})`;
}

export function queryIntentReportToMarkdown(report: QueryIntentTestSuiteReport) {
  const rows = report.results
    .map(
      (result) =>
        `| ${result.passed ? "PASS" : "FAIL"} | ${result.id} | ${escapeMd(result.question)} | ${escapeMd(text(result.actual.status))} | ${escapeMd(text(result.actual.concept))}/${escapeMd(text(result.actual.variant))} | ${escapeMd(text(result.actual.unsupported_reason))} |`
    )
    .join("\n");
  const failed = report.results
    .filter((result) => !result.passed)
    .map(
      (result) =>
        `### ${result.id}\n\nQuestion: ${result.question}\n\nDiffs:\n\n\`\`\`json\n${JSON.stringify(result.diffs, null, 2)}\n\`\`\`\n\nActual:\n\n\`\`\`json\n${JSON.stringify(readableActual(result), null, 2)}\n\`\`\``
    )
    .join("\n\n");
  const invariantFailures = report.results
    .filter((result) => result.invariant_diffs.length > 0)
    .map(
      (result) =>
        `### ${result.id}\n\n\`\`\`json\n${JSON.stringify(result.invariant_diffs, null, 2)}\n\`\`\``
    )
    .join("\n\n");
  const advisoryRegressions = report.results
    .filter((result) => result.ai_advisory_diffs.length > 0)
    .map(
      (result) =>
        `### ${result.id}\n\nDecision: ${result.ai_candidate_decision}\n\nReason: ${result.ai_candidate_decision_reason ?? "-"}\n\n\`\`\`json\n${JSON.stringify(result.ai_advisory_diffs, null, 2)}\n\`\`\``
    )
    .join("\n\n");
  const candidateDecisions = report.results
    .filter((result) => result.ai_candidate_decision !== "not_applicable")
    .map(
      (result) =>
        `| ${result.id} | ${result.ai_candidate_decision} | ${escapeMd(result.ai_candidate_decision_reason ?? "-")} |`
    )
    .join("\n");
  const allDetails = report.results
    .map(
      (result) =>
        `### ${result.id}\n\n\`\`\`json\n${JSON.stringify(readableActual(result), null, 2)}\n\`\`\``
    )
    .join("\n\n");

  return `# Query Intent Test Suite Report

- Run: ${report.run_id}
- Created: ${report.created_at}
- Environment: ${report.environment}
- Connection: ${report.connection.name} (${report.connection.id})
- Semantic Layer: ${report.semantic_layer.version}, ${report.semantic_layer.status}, ${report.semantic_layer.freshness}
- Summary: ${report.summary.passed}/${report.summary.total} passed, ${report.summary.failed} failed, ${report.summary.skipped} skipped
- Fixture assertions: ${report.summary.fixture_assertions.passed} passed, ${report.summary.fixture_assertions.failed} failed
- Invariants: ${report.summary.invariants.passed} passed, ${report.summary.invariants.failed} failed
- AI advisory: enabled=${report.summary.ai_advisory.enabled}, regressions=${report.summary.ai_advisory.regressions}, candidate rejections=${report.summary.ai_advisory.candidate_rejections}

| Status | Test | Question | Actual result | Concept/variant | Unsupported reason |
|---|---|---|---|---|---|
${rows}

## Failed Details

${failed || "No failed tests."}

## Failed Invariants

${invariantFailures || "No invariant failures."}

## AI Advisory Regressions

${advisoryRegressions || "No AI advisory regressions."}

## AI Candidate Decisions

| Test | Decision | Reason |
|---|---|---|
${candidateDecisions || "| - | - | - |"}

## Full Details

${allDetails}
`;
}

export function readableActual(result: QueryIntentTestResult) {
  const actual = result.actual;
  return {
    audit_summary: actual.audit_summary,
    concept_variant: joinNonEmpty([text(actual.concept), text(actual.variant)], "/"),
    date: {
      key: actual.date_key,
      label: actual.date_display_name
    },
    disclosures: actual.disclosures,
    edges: actual.edges,
    group_by: actual.group_by,
    metric: {
      display_name: actual.metric_display_name,
      formula: actual.metric_formula,
      key: actual.metric_key
    },
    ai_advisory: {
      decision: result.ai_candidate_decision,
      decision_reason: result.ai_candidate_decision_reason,
      fake_candidate: result.fake_ai_candidate,
      summary: result.ai_candidate_summary
    },
    deterministic_result: result.deterministic_result,
    time_range: actual.time_range,
    unsupported_reason: actual.unsupported_reason
  };
}

export function text(value: unknown) {
  if (value == null) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}

function joinNonEmpty(values: string[], separator: string) {
  return values.filter(Boolean).join(separator);
}

function escapeMd(value: string) {
  return value.replaceAll("|", "\\|").replaceAll("\n", " ");
}
