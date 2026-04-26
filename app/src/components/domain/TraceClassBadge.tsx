import { classifyTraceId } from '@/src/types/api';

interface TraceClassBadgeProps {
  traceId: string | null | undefined;
}

/**
 * Renders an MLflow trace id alongside its class:
 *
 *   - `live`      — non-null, no `local::` prefix → real MLflow trace.
 *   - `synthetic` — `local::<facility_id>::<run_uuid>` → ran without MLflow.
 *   - `missing`   — null / empty → no trace recorded.
 *
 * The classifier is the JS mirror of
 * `seahealth.agents.facility_audit_builder.classify_trace_id` so the UI and
 * the backend stay aligned.
 */
export function TraceClassBadge({ traceId }: TraceClassBadgeProps) {
  const klass = classifyTraceId(traceId);
  if (klass === 'live') {
    return (
      <span
        title="Live MLflow trace — copy the id to open the span timeline in MLflow."
        className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-800"
      >
        <span aria-hidden>●</span> live trace
        <code className="ml-1 font-mono text-[10px] opacity-70">{traceId}</code>
      </span>
    );
  }
  if (klass === 'synthetic') {
    return (
      <span
        title="Trace not available — extraction ran without MLflow. The synthetic id groups capabilities from the same run."
        className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-800"
      >
        <span aria-hidden>○</span> trace unavailable (offline run)
      </span>
    );
  }
  return (
    <span
      title="No trace recorded for this audit."
      className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium bg-neutral-200 text-neutral-700"
    >
      <span aria-hidden>—</span> no trace
    </span>
  );
}
