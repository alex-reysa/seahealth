import React from 'react';
import { Card } from '@/src/components/ui/Card';
import { CheckCircle2, XCircle, MinusCircle, FileText } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import type { EvidenceRef } from '@/src/types/api';

export type EvidenceStance = 'verifies' | 'contradicts' | 'silent';

export interface EvidenceCardProps {
  key?: React.Key;
  evidence: EvidenceRef;
  /**
   * Optional stance derived by the caller. The live `EvidenceRef` shape has
   * no inherent stance — it is "verifies" when it appears in
   * `trust_score.evidence` and not in any contradiction's `evidence_against`,
   * "contradicts" when it appears in `evidence_against`, otherwise "silent".
   */
  stance?: EvidenceStance;
  className?: string;
}

const STANCE_CONFIG: Record<EvidenceStance, {
  icon: typeof CheckCircle2;
  color: string;
  bg: string;
  label: string;
}> = {
  verifies: {
    icon: CheckCircle2,
    color: 'text-semantic-verified',
    bg: 'bg-semantic-verified-subtle',
    label: 'Verifies',
  },
  contradicts: {
    icon: XCircle,
    color: 'text-semantic-critical',
    bg: 'bg-semantic-critical-subtle',
    label: 'Contradicts',
  },
  silent: {
    icon: MinusCircle,
    color: 'text-content-tertiary',
    bg: 'bg-surface-sunken',
    label: 'Silent',
  },
};

function formatSpan(span: [number, number] | undefined): string | undefined {
  if (!span) return undefined;
  return `${span[0]}–${span[1]}`;
}

export function EvidenceCard({ evidence, stance = 'verifies', className }: EvidenceCardProps) {
  const config = STANCE_CONFIG[stance];
  const Icon = config.icon;
  const spanLabel = formatSpan(evidence.span);

  return (
    <Card variant="default" className={cn('p-4 flex flex-col gap-3', className)}>
      <div className="flex items-center justify-between">
        <div className={cn('flex items-center gap-1.5 px-2 py-1 rounded-sm text-caption font-medium', config.bg, config.color)}>
          <Icon className="w-3.5 h-3.5" />
          <span>{config.label}</span>
        </div>
        <div className="flex items-center gap-1 text-caption text-content-secondary">
          <FileText className="w-3 h-3" />
          {evidence.source_type}
        </div>
      </div>
      <div className="text-body text-content-primary border-l-2 border-border-default pl-3 py-1 italic">
        "{evidence.snippet}"
      </div>
      <div className="grid grid-cols-2 gap-2 border-t border-border-subtle pt-3 text-mono-s text-content-secondary">
        <span>Doc: {evidence.source_doc_id}</span>
        {spanLabel && <span>Span: {spanLabel}</span>}
        {evidence.source_observed_at && (
          <span>Observed: {new Date(evidence.source_observed_at).toLocaleDateString()}</span>
        )}
        {evidence.retrieved_at && (
          <span>Retrieved: {new Date(evidence.retrieved_at).toLocaleString()}</span>
        )}
      </div>
    </Card>
  );
}
