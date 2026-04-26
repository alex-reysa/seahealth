import React, { useState } from 'react';
import { Check, ChevronDown, ChevronUp, Clipboard, Terminal, Activity } from 'lucide-react';

import { Card } from '@/src/components/ui/Card';
import { cn } from '@/src/lib/utils';
import type { ExecutionStep } from '@/src/types/api';

/**
 * Legacy span shape — used by the not-yet-rewritten facility audit page.
 * Once Phase 3 wires `useFacilityAudit`, this can be deleted.
 */
export interface LegacySpan {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'complete' | 'failed' | 'unavailable';
  durationMs?: number;
  detail: string;
}

export interface TracePanelProps {
  /** Real MLflow trace id (live). When set, badge says "live trace". */
  mlflowTraceId?: string | null;
  /** Always-present synthetic correlation id (`q_<uuid>`). */
  queryTraceId?: string | null;
  /** Live execution steps from `QueryResult.execution_steps`. Preferred. */
  executionSteps?: ReadonlyArray<ExecutionStep>;
  /** Legacy four-stage span list — kept for existing facility-audit callers. */
  spans?: ReadonlyArray<LegacySpan>;
  className?: string;
}

const STATUS_DOT: Record<ExecutionStep['status'], string> = {
  ok: 'bg-emerald-500',
  fallback: 'bg-amber-500',
  error: 'bg-rose-600',
};

const STATUS_PILL: Record<ExecutionStep['status'], string> = {
  ok: 'bg-emerald-100 text-emerald-800',
  fallback: 'bg-amber-100 text-amber-800',
  error: 'bg-rose-100 text-rose-800',
};

function formatStepLabel(name: string): string {
  // 'parse_intent' -> 'Parse intent'
  return name.replace(/[_-]+/g, ' ').replace(/^./, (c) => c.toUpperCase());
}

function elapsedMs(started: string, finished: string): number | null {
  const a = Date.parse(started);
  const b = Date.parse(finished);
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  return Math.max(0, b - a);
}

export function TracePanel({
  mlflowTraceId,
  queryTraceId,
  executionSteps,
  spans,
  className,
}: TracePanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const hasTrace = !!(mlflowTraceId || queryTraceId);
  const copyTrace = async (id: string) => {
    try {
      if (!navigator.clipboard) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(id);
      setCopied(id);
      window.setTimeout(() => setCopied(null), 1200);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('Failed to copy trace ID', err);
    }
  };

  const useLiveSteps = (executionSteps?.length ?? 0) > 0;

  return (
    <Card
      variant="glass"
      className={cn('flex flex-col overflow-hidden transition-all duration-300', className)}
    >
      <button
        type="button"
        className={cn(
          'flex items-center justify-between p-3 select-none w-full text-left',
          hasTrace
            ? 'cursor-pointer hover:bg-surface-sunken/50 focus:outline-none focus:bg-surface-sunken'
            : 'opacity-60',
        )}
        onClick={() => hasTrace && setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2 text-content-secondary">
          <Activity className="w-4 h-4" />
          <span className="text-caption font-medium uppercase tracking-wider">
            {hasTrace ? 'View Trace' : 'Trace Unavailable'}
          </span>
        </div>
        {hasTrace &&
          (expanded ? (
            <ChevronUp className="w-4 h-4 text-content-tertiary" />
          ) : (
            <ChevronDown className="w-4 h-4 text-content-tertiary" />
          ))}
      </button>

      {expanded && hasTrace && (
        <div className="p-4 border-t border-border-subtle bg-surface-canvas/50 flex flex-col gap-4">
          {queryTraceId && (
            <div className="flex flex-col gap-1">
              <span className="text-caption text-content-secondary">Query Trace ID</span>
              <div className="flex items-center gap-2 bg-surface-sunken border border-border-default rounded px-3 py-2 text-mono text-content-primary">
                <Terminal className="w-4 h-4 text-content-tertiary" />
                <span className="flex-1 break-all">{queryTraceId}</span>
                <button
                  type="button"
                  aria-label="Copy query trace id"
                  onClick={() => copyTrace(queryTraceId)}
                  className="text-content-tertiary hover:text-content-primary"
                >
                  {copied === queryTraceId ? (
                    <Check className="w-4 h-4" />
                  ) : (
                    <Clipboard className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>
          )}
          {mlflowTraceId && (
            <div className="flex flex-col gap-1">
              <span className="text-caption text-content-secondary">MLflow Trace ID</span>
              <div className="flex items-center gap-2 bg-surface-sunken border border-border-default rounded px-3 py-2 text-mono text-content-primary">
                <Terminal className="w-4 h-4 text-content-tertiary" />
                <span className="flex-1 break-all">{mlflowTraceId}</span>
                <button
                  type="button"
                  aria-label="Copy MLflow trace id"
                  onClick={() => copyTrace(mlflowTraceId)}
                  className="text-content-tertiary hover:text-content-primary"
                >
                  {copied === mlflowTraceId ? (
                    <Check className="w-4 h-4" />
                  ) : (
                    <Clipboard className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>
          )}

          <div className="mt-2 flex flex-col gap-2">
            <span className="text-caption text-content-secondary">Execution Steps</span>
            <div className="flex flex-col gap-2 text-caption">
              {useLiveSteps
                ? executionSteps!.map((step, i) => {
                    const ms = elapsedMs(step.started_at, step.finished_at);
                    return (
                      <div
                        key={`${step.name}-${i}`}
                        className="rounded border border-border-subtle bg-white/60 p-2"
                      >
                        <div className="flex items-center gap-3">
                          <div
                            className={cn('w-2 h-2 rounded-full', STATUS_DOT[step.status])}
                            aria-hidden
                          />
                          <span className="text-content-primary">{formatStepLabel(step.name)}</span>
                          <span
                            className={cn(
                              'ml-2 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase',
                              STATUS_PILL[step.status],
                            )}
                          >
                            {step.status}
                          </span>
                          <span className="text-content-tertiary ml-auto font-mono">
                            {ms !== null ? `${ms} ms` : '—'}
                          </span>
                        </div>
                        {step.detail && (
                          <p className="mt-1 text-content-secondary">{step.detail}</p>
                        )}
                      </div>
                    );
                  })
                : (spans ?? []).map((span) => (
                    <div
                      key={span.id}
                      className="rounded border border-border-subtle bg-white/60 p-2"
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className={cn(
                            'w-2 h-2 rounded-full',
                            span.status === 'complete'
                              ? 'bg-emerald-500'
                              : span.status === 'failed'
                                ? 'bg-rose-600'
                                : 'bg-amber-500',
                          )}
                        />
                        <span className="text-content-primary">{span.label}</span>
                        <span className="text-content-tertiary ml-auto">
                          {span.durationMs ? `${(span.durationMs / 1000).toFixed(1)}s` : span.status}
                        </span>
                      </div>
                      <p className="mt-1 text-content-secondary">{span.detail}</p>
                    </div>
                  ))}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
