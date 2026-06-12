"use client";

import type { QueryabilityPathResult } from "@atlantebi/contracts";
import { useMemo, useState } from "react";

export function PathInspector({
  graphId,
  nodes,
  tenantId
}: {
  graphId: string;
  nodes: Array<{ key: string; label: string }>;
  tenantId: string;
}) {
  const orderedNodes = useMemo(
    () => [...nodes].sort((left, right) => left.label.localeCompare(right.label)),
    [nodes]
  );
  const [fromNode, setFromNode] = useState(orderedNodes[0]?.key ?? "");
  const [toNode, setToNode] = useState(orderedNodes[1]?.key ?? "");
  const [result, setResult] = useState<QueryabilityPathResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function inspectPath() {
    if (!fromNode || !toNode) {
      return;
    }
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const response = await fetch("/api/queryability/paths", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          graph_id: graphId,
          from_node_key: fromNode,
          to_node_key: toNode
        })
      });
      if (!response.ok) {
        throw new Error("Path search failed.");
      }
      setResult((await response.json()) as QueryabilityPathResult);
    } catch {
      setError("Ricerca path non disponibile.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="border-t border-[color:var(--border)] pt-6">
      <h2 className="text-base font-semibold">Path inspector</h2>
      <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1fr_auto]">
        <label className="grid gap-1 text-xs text-[color:var(--muted)]">
          Da
          <select
            className="h-10 border border-[color:var(--border)] bg-transparent px-3 text-sm text-[color:var(--foreground)]"
            onChange={(event) => setFromNode(event.target.value)}
            value={fromNode}
          >
            {orderedNodes.map((node) => (
              <option key={node.key} value={node.key}>
                {node.label}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs text-[color:var(--muted)]">
          A
          <select
            className="h-10 border border-[color:var(--border)] bg-transparent px-3 text-sm text-[color:var(--foreground)]"
            onChange={(event) => setToNode(event.target.value)}
            value={toNode}
          >
            {orderedNodes.map((node) => (
              <option key={node.key} value={node.key}>
                {node.label}
              </option>
            ))}
          </select>
        </label>
        <button
          className="self-end border border-[color:var(--accent)] px-4 py-2 text-sm"
          disabled={loading}
          onClick={inspectPath}
          type="button"
        >
          {loading ? "Analisi..." : "Analizza"}
        </button>
      </div>
      {result ? (
        <div className="mt-4 border-l-2 border-[color:var(--border)] pl-3 text-sm">
          <p>
            Stato: <strong>{result.status}</strong>
          </p>
          <p className="mt-1 text-xs text-[color:var(--muted)]">
            {result.paths.length} path
            {result.paths.some((path) => path.fanout_warning)
              ? " - fanout warning"
              : ""}
            {result.reason_codes.length > 0
              ? ` - ${result.reason_codes.join(", ")}`
              : ""}
          </p>
        </div>
      ) : null}
      {error ? (
        <p className="mt-4 text-sm text-[color:var(--muted)]">{error}</p>
      ) : null}
    </section>
  );
}
