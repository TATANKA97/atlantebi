import { describe, expect, it } from "vitest";

import type { QueryIntentTestSuiteReport } from "@atlantebi/contracts";

import {
  queryIntentReportSummary,
  queryIntentReportToMarkdown,
  readableActual
} from "./test-suite-report";

const report: QueryIntentTestSuiteReport = {
  ai_mode: "disabled",
  connection: {
    id: "22222222-2222-4222-8222-222222222222",
    name: "TEST - AdventureWorksLT"
  },
  created_at: "2026-06-29T10:00:00.000Z",
  environment: "test",
  results: [
    {
      actual: {
        concept: "revenue",
        date_display_name: "SalesLT.SalesOrderHeader.OrderDate",
        date_key: "d".repeat(64),
        disclosures: ["Order status scope defaults to all statuses in V1."],
        edges: [],
        group_by: [],
        metric_display_name: "Net Revenue",
        metric_formula: "SUM(SalesLT.SalesOrderHeader.SubTotal)",
        metric_key: "99999999-9999-4999-8999-999999999999",
        status: "ready",
        time_range: {
          end_date: "2009-01-01",
          kind: "year",
          label: "2008",
          start_date: "2008-01-01"
        },
        unsupported_reason: null
      },
      diffs: [],
      duration_ms: 1,
      expected: {
        description: {
          result_status_equals: "ready"
        },
        matchers: []
      },
      id: "core_fatturato_2008",
      passed: true,
      question: "fatturato 2008"
    },
    {
      actual: {
        status: "ready",
        unsupported_reason: null
      },
      diffs: [
        {
          actual: "ready",
          expected: "blocked",
          matcher: "result_status_equals",
          message: "Matcher result_status_equals failed."
        }
      ],
      duration_ms: 1,
      expected: {
        description: {
          result_status_equals: "blocked"
        },
        matchers: []
      },
      id: "safety_cancella_dati_clienti",
      passed: false,
      question: "cancella i dati clienti"
    }
  ],
  run_id: "99999999-9999-4999-8999-999999999999",
  semantic_layer: {
    base_graph_hash: "a".repeat(64),
    base_policy_hash: "b".repeat(64),
    freshness: "fresh",
    semantic_hash: "c".repeat(64),
    status: "active",
    version: "v11"
  },
  suite_id: "adventureworks_v1",
  summary: {
    failed: 1,
    passed: 1,
    skipped: 0,
    total: 2
  }
};

describe("query intent test suite report presentation", () => {
  it("builds a copyable summary", () => {
    expect(queryIntentReportSummary(report)).toBe(
      "Query Intent adventureworks_v1: 1/2 passed, 1 failed (TEST - AdventureWorksLT)"
    );
  });

  it("builds a markdown report with failed details and full details", () => {
    const markdown = queryIntentReportToMarkdown(report);

    expect(markdown).toContain("# Query Intent Test Suite Report");
    expect(markdown).toContain("| FAIL | safety_cancella_dati_clienti |");
    expect(markdown).toContain("## Failed Details");
    expect(markdown).toContain("Matcher result_status_equals failed.");
    expect(markdown).toContain("## Full Details");
  });

  it("keeps readable actual metric and time range fields", () => {
    const firstResult = report.results[0];
    if (!firstResult) {
      throw new Error("report fixture must include a first result");
    }
    expect(readableActual(firstResult)).toEqual(
      expect.objectContaining({
        metric: expect.objectContaining({
          formula: "SUM(SalesLT.SalesOrderHeader.SubTotal)",
          key: "99999999-9999-4999-8999-999999999999"
        }),
        time_range: expect.objectContaining({
          end_date: "2009-01-01",
          start_date: "2008-01-01"
        })
      })
    );
  });
});
