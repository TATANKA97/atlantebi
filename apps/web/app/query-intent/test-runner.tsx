"use client";

import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import type {
  QueryIntentTestResult,
  QueryIntentTestSuiteReport
} from "@atlantebi/contracts";

import {
  queryIntentReportSummary,
  queryIntentReportToMarkdown,
  readableActual,
  text
} from "../../lib/query-intent/test-suite-report";

type RunnerStatus = "idle" | "running" | "completed" | "failed";

export function QueryIntentTestRunner({
  connectionId,
  tenantId
}: {
  connectionId: string;
  tenantId: string;
}) {
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<QueryIntentTestSuiteReport | null>(null);
  const [status, setStatus] = useState<RunnerStatus>("idle");
  const markdown = useMemo(
    () => (report ? queryIntentReportToMarkdown(report) : ""),
    [report]
  );

  async function runSuite() {
    if (!connectionId) {
      return;
    }
    setStatus("running");
    setError(null);
    setReport(null);
    try {
      const response = await fetch("/api/query-intent/test-suite", {
        body: JSON.stringify({
          ai_mode: "disabled",
          connection_id: connectionId,
          suite_id: "adventureworks_v1",
          tenant_id: tenantId
        }),
        headers: { "content-type": "application/json" },
        method: "POST"
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.message ?? payload.error ?? "Test suite failed.");
      }
      setReport(payload as QueryIntentTestSuiteReport);
      setStatus("completed");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Test suite failed.");
      setStatus("failed");
    }
  }

  return (
    <section className="flex flex-col gap-4 border border-[color:var(--border)] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Resolver Test Runner</h2>
          <p className="mt-1 text-sm text-[color:var(--muted)]">
            Suite AdventureWorksLT, AI disabled, nessun SQL e nessuna esecuzione.
          </p>
        </div>
        <button
          className="border border-[color:var(--accent)] px-4 py-2 text-sm disabled:opacity-50"
          disabled={!connectionId || status === "running"}
          onClick={runSuite}
          type="button"
        >
          {status === "running" ? "Running..." : "Run AdventureWorks resolver suite"}
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-5">
        <SummaryPill label="Status" value={status} />
        <SummaryPill label="Total" value={String(report?.summary.total ?? 0)} />
        <SummaryPill label="Passed" value={String(report?.summary.passed ?? 0)} />
        <SummaryPill label="Failed" value={String(report?.summary.failed ?? 0)} />
        <SummaryPill label="Skipped" value={String(report?.summary.skipped ?? 0)} />
      </div>

      {error ? (
        <div className="border border-red-500/40 p-3 text-sm">{error}</div>
      ) : null}

      {report ? (
        <>
          <div className="flex flex-wrap gap-2">
            <button
              className="border border-[color:var(--border)] px-3 py-2 text-sm"
              onClick={() =>
                downloadText(
                  `query-intent-${report.run_id}.json`,
                  JSON.stringify(report, null, 2),
                  "application/json"
                )
              }
              type="button"
            >
              Download JSON report
            </button>
            <button
              className="border border-[color:var(--border)] px-3 py-2 text-sm"
              onClick={() =>
                downloadText(
                  `query-intent-${report.run_id}.md`,
                  markdown,
                  "text/markdown"
                )
              }
              type="button"
            >
              Download Markdown report
            </button>
            <button
              className="border border-[color:var(--border)] px-3 py-2 text-sm"
              onClick={() =>
                navigator.clipboard.writeText(queryIntentReportSummary(report))
              }
              type="button"
            >
              Copy summary
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[1400px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-[color:var(--border)] text-left">
                  <HeaderCell>Status</HeaderCell>
                  <HeaderCell>Test id</HeaderCell>
                  <HeaderCell>Domanda</HeaderCell>
                  <HeaderCell>Expected result</HeaderCell>
                  <HeaderCell>Actual result</HeaderCell>
                  <HeaderCell>Expected concept/variant</HeaderCell>
                  <HeaderCell>Actual concept/variant</HeaderCell>
                  <HeaderCell>Expected formula/metric</HeaderCell>
                  <HeaderCell>Actual formula/metric</HeaderCell>
                  <HeaderCell>Expected group by</HeaderCell>
                  <HeaderCell>Actual group by</HeaderCell>
                  <HeaderCell>Unsupported reason</HeaderCell>
                  <HeaderCell>Disclosure</HeaderCell>
                  <HeaderCell>Audit summary</HeaderCell>
                </tr>
              </thead>
              <tbody>
                {report.results.map((result) => (
                  <ResultRow key={result.id} result={result} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </section>
  );
}

function ResultRow({ result }: { result: QueryIntentTestResult }) {
  const actual = result.actual;
  const expected = result.expected.description as Record<string, unknown> | undefined;
  const actualConceptVariant = joinNonEmpty([
    text(actual.concept),
    text(actual.variant)
  ], "/");

  return (
    <>
      <tr className="border-b border-[color:var(--border)] align-top">
        <Cell>
          <span
            className={
              result.passed
                ? "border border-emerald-500/50 px-2 py-1 text-xs"
                : "border border-red-500/50 px-2 py-1 text-xs"
            }
          >
            {result.passed ? "pass" : "fail"}
          </span>
        </Cell>
        <Cell>{result.id}</Cell>
        <Cell>{result.question}</Cell>
        <Cell>{text(expected?.result_status_equals ?? expected?.result_status_in)}</Cell>
        <Cell>{text(actual.status)}</Cell>
        <Cell>
          {joinNonEmpty([
            text(expected?.concept_equals),
            text(expected?.variant_equals)
          ], "/")}
        </Cell>
        <Cell>{actualConceptVariant || "-"}</Cell>
        <Cell>
          {joinNonEmpty([
            text(expected?.formula_contains),
            text(expected?.must_not_formula_contains)
              ? `not ${text(expected?.must_not_formula_contains)}`
              : ""
          ], ", ")}
        </Cell>
        <Cell>{text(actual.metric_formula)}</Cell>
        <Cell>{text(expected?.group_by_contains)}</Cell>
        <Cell>{labels(actual.group_by).join(", ") || "-"}</Cell>
        <Cell>{text(actual.unsupported_reason)}</Cell>
        <Cell>{listText(actual.disclosures)}</Cell>
        <Cell>{listText(actual.audit_summary)}</Cell>
      </tr>
      <tr className="border-b border-[color:var(--border)]">
        <td className="p-2" colSpan={14}>
          <details>
            <summary className="cursor-pointer text-xs text-[color:var(--muted)]">
              Details, actual JSON, expected and diffs
            </summary>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <DetailBlock title="Readable actual" value={readableActual(result)} />
              <DetailBlock title="Mismatch details" value={result.diffs} />
              <DetailBlock title="Expected" value={result.expected} />
              <DetailBlock title="Actual full QueryIntentResult" value={actual.raw_result} />
              <DetailBlock title="Audit trail raw" value={actual.audit_trail} />
            </div>
          </details>
        </td>
      </tr>
    </>
  );
}

function SummaryPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-[color:var(--border)] p-3">
      <div className="text-xs uppercase text-[color:var(--muted)]">{label}</div>
      <div className="mt-1 text-sm">{value}</div>
    </div>
  );
}

function HeaderCell({ children }: { children: ReactNode }) {
  return <th className="p-2 text-xs font-semibold uppercase">{children}</th>;
}

function Cell({ children }: { children: ReactNode }) {
  return <td className="max-w-[240px] break-words p-2">{children}</td>;
}

function DetailBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="border border-[color:var(--border)] p-3">
      <div className="text-xs uppercase text-[color:var(--muted)]">{title}</div>
      <pre className="mt-2 max-h-80 overflow-auto text-xs">
        {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

function downloadText(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function labels(value: unknown) {
  return Array.isArray(value)
    ? value.map((item) =>
        item && typeof item === "object" && "label" in item
          ? text(item.label)
          : text(item)
      )
    : [];
}

function listText(value: unknown) {
  if (!Array.isArray(value)) {
    return "-";
  }
  return value.map((item) => text(item)).join("; ") || "-";
}

function joinNonEmpty(values: string[], separator: string) {
  return values.filter(Boolean).join(separator);
}
