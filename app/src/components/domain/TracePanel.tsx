import React, { useState } from 'react';
import { Check, ChevronDown, ChevronUp, Clipboard, Terminal, Activity } from 'lucide-react';
import { Card } from '@/src/components/ui/Card';
import { cn } from '@/src/lib/utils';
import type { DemoTraceSpan } from '@/src/data/demoData';

export interface TracePanelProps {
  mlflowTraceId?: string;
  queryTraceId?: string;
  spans?: DemoTraceSpan[];
  className?: string;
}

const DEFAULT_SPANS: DemoTraceSpan[] = [
  { id: 'extract', label: 'Extraction', status: 'complete', durationMs: 1200, detail: 'Extracted facility capabilities from source documents.' },
  { id: 'validate', label: 'Validation', status: 'complete', durationMs: 800, detail: 'Cross-checked claims against staff and equipment sources.' },
  { id: 'score', label: 'Scoring', status: 'complete', durationMs: 300, detail: 'Computed Trust Score and confidence interval.' },
];

export function TracePanel({ mlflowTraceId, queryTraceId, spans = DEFAULT_SPANS, className }: TracePanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const hasTrace = !!(mlflowTraceId || queryTraceId);
  const copyTrace = async (id: string) => {
    await navigator.clipboard?.writeText(id);
    setCopied(id);
    window.setTimeout(() => setCopied(null), 1200);
  };

  return (
    <Card variant="glass" className={cn("flex flex-col overflow-hidden transition-all duration-300", className)}>
      <div 
        className={cn("flex items-center justify-between p-3 select-none", hasTrace ? "cursor-pointer hover:bg-surface-sunken/50" : "opacity-60")}
        onClick={() => hasTrace && setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2 text-content-secondary">
          <Activity className="w-4 h-4" />
          <span className="text-caption font-medium uppercase tracking-wider">
            {hasTrace ? 'View Trace' : 'Trace Unavailable'}
          </span>
        </div>
        {hasTrace && (
          expanded ? <ChevronUp className="w-4 h-4 text-content-tertiary" /> : <ChevronDown className="w-4 h-4 text-content-tertiary" />
        )}
      </div>
      
      {expanded && hasTrace && (
        <div className="p-4 border-t border-border-subtle bg-surface-canvas/50 flex flex-col gap-4">
          {queryTraceId && (
            <div className="flex flex-col gap-1">
              <span className="text-caption text-content-secondary">Query Trace ID</span>
              <div className="flex items-center gap-2 bg-surface-sunken border border-border-default rounded px-3 py-2 text-mono text-content-primary">
                <Terminal className="w-4 h-4 text-content-tertiary" />
                <span className="flex-1">{queryTraceId}</span>
                <button
                  type="button"
                  aria-label="Copy query trace id"
                  onClick={() => copyTrace(queryTraceId)}
                  className="text-content-tertiary hover:text-content-primary"
                >
                  {copied === queryTraceId ? <Check className="w-4 h-4" /> : <Clipboard className="w-4 h-4" />}
                </button>
              </div>
            </div>
          )}
          {mlflowTraceId && (
            <div className="flex flex-col gap-1">
              <span className="text-caption text-content-secondary">MLflow Trace ID</span>
              <div className="flex items-center gap-2 bg-surface-sunken border border-border-default rounded px-3 py-2 text-mono text-content-primary">
                <Terminal className="w-4 h-4 text-content-tertiary" />
                <span className="flex-1">{mlflowTraceId}</span>
                <button
                  type="button"
                  aria-label="Copy MLflow trace id"
                  onClick={() => copyTrace(mlflowTraceId)}
                  className="text-content-tertiary hover:text-content-primary"
                >
                  {copied === mlflowTraceId ? <Check className="w-4 h-4" /> : <Clipboard className="w-4 h-4" />}
                </button>
              </div>
            </div>
          )}
          
          <div className="mt-2 flex flex-col gap-2">
            <span className="text-caption text-content-secondary">Execution Spans</span>
            <div className="flex flex-col gap-2 text-caption">
              {spans.map((span) => (
                <div key={span.id} className="rounded border border-border-subtle bg-white/60 p-2">
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        'w-2 h-2 rounded-full',
                        span.status === 'complete' ? 'bg-semantic-verified' : 'bg-semantic-insufficient',
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
