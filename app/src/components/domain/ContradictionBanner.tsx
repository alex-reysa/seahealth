import React from 'react';
import { ShieldAlert, AlertTriangle, AlertCircle } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import type { Contradiction, ContradictionSeverity } from '@/src/types/api';

export interface ContradictionBannerProps {
  key?: React.Key;
  contradiction: Contradiction;
  className?: string;
}

const SEVERITY_CONFIG: Record<ContradictionSeverity, {
  icon: typeof ShieldAlert;
  bg: string;
  border: string;
  text: string;
}> = {
  HIGH: {
    icon: ShieldAlert,
    bg: 'bg-semantic-critical-subtle',
    border: 'border-semantic-critical/20',
    text: 'text-semantic-critical',
  },
  MEDIUM: {
    icon: AlertTriangle,
    bg: 'bg-semantic-flagged-subtle',
    border: 'border-semantic-flagged/20',
    text: 'text-semantic-flagged',
  },
  LOW: {
    icon: AlertCircle,
    bg: 'bg-surface-sunken',
    border: 'border-border-default',
    text: 'text-content-secondary',
  },
};

export function ContradictionBanner({ contradiction, className }: ContradictionBannerProps) {
  const config = SEVERITY_CONFIG[contradiction.severity];
  const Icon = config.icon;
  const forCount = contradiction.evidence_for?.length ?? 0;
  const againstCount = contradiction.evidence_against?.length ?? 0;

  return (
    <div className={cn('flex items-start gap-3 p-3 rounded-md border', config.bg, config.border, className)}>
      <Icon className={cn('w-5 h-5 shrink-0 mt-0.5', config.text)} />
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className={cn('text-caption font-bold uppercase', config.text)}>
            {contradiction.severity} SEVERITY
          </span>
          <span className="text-caption text-content-secondary">•</span>
          <span className="text-caption font-mono text-content-primary">
            {contradiction.contradiction_type}
          </span>
        </div>
        <div className="text-body text-content-primary">{contradiction.reasoning}</div>
        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-mono-s text-content-secondary">
          <span>For: {forCount} evidence</span>
          <span>Against: {againstCount} evidence</span>
          {contradiction.detected_by && <span>Detected by: {contradiction.detected_by}</span>}
          {contradiction.detected_at && (
            <span>At: {new Date(contradiction.detected_at).toLocaleString()}</span>
          )}
        </div>
      </div>
    </div>
  );
}
