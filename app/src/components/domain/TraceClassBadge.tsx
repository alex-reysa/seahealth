import { classifyTraceId, type TraceClass } from '@/src/types/api';

interface TraceClassBadgeProps {
  /**
   * Either pass a single `traceId` (legacy API mirror — uses the `local::`
   * prefix to discriminate live vs synthetic), or pass the split pair from
   * `QueryResult`: `mlflowTraceId` (live) takes precedence, `queryTraceId`
   * (synthetic) is the fallback. If both are null, the badge says "missing".
   */
  traceId?: string | null;
  mlflowTraceId?: string | null;
  queryTraceId?: string | null;
}

function resolveClass(
  traceId: string | null | undefined,
  mlflowTraceId: string | null | undefined,
  queryTraceId: string | null | undefined,
): { klass: TraceClass; display: string | null } {
  // Pair-style call (planner). MLflow wins; query trace is the synthetic
  // correlation id; both null is "missing".
  if (mlflowTraceId !== undefined || queryTraceId !== undefined) {
    if (mlflowTraceId) return { klass: 'live', display: mlflowTraceId };
    if (queryTraceId) return { klass: 'synthetic', display: queryTraceId };
    return { klass: 'missing', display: null };
  }
  // Single-id call (facility audit). Use the existing prefix classifier.
  return { klass: classifyTraceId(traceId), display: traceId ?? null };
}

/**
 * Renders the trace state of a query or audit:
 *
 *   - `live`      — `mlflow_trace_id` present (or non-`local::` single id) →
 *     real MLflow trace; show the id.
 *   - `synthetic` — only `query_trace_id` present (or `local::*` single id)
 *     → ran without MLflow; correlation id only.
 *   - `missing`   — both null / empty → no trace recorded.
 */
export function TraceClassBadge({
  traceId,
  mlflowTraceId,
  queryTraceId,
}: TraceClassBadgeProps) {
  const { klass, display } = resolveClass(traceId, mlflowTraceId, queryTraceId);

  if (klass === 'live') {
    return (
      <span
        title="Live MLflow trace — copy the id to open the span timeline in MLflow."
        className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-800"
      >
        <span aria-hidden>●</span> live trace
        {display && <code className="ml-1 font-mono text-[10px] opacity-70">{display}</code>}
      </span>
    );
  }
  if (klass === 'synthetic') {
    return (
      <span
        title="Synthetic correlation id — query ran without MLflow tracking. The id still groups every step of this run."
        className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-800"
      >
        <span aria-hidden>○</span> synthetic trace
        {display && <code className="ml-1 font-mono text-[10px] opacity-70">{display}</code>}
      </span>
    );
  }
  return (
    <span
      title="No trace recorded for this run."
      className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium bg-neutral-200 text-neutral-700"
    >
      <span aria-hidden>—</span> no trace
    </span>
  );
}
