import React from 'react';
import { ShieldAlert, AlertTriangle, AlertCircle } from 'lucide-react';
import { cn } from '@/src/lib/utils';

export type Severity = 'HIGH' | 'MEDIUM' | 'LOW';

export interface ContradictionBannerProps {
  key?: React.Key;
  severity: Severity;
  type: string;
  reasoning: string;
  evidenceFor?: string;
  evidenceAgainst?: string;
  detectedBy?: string;
  detectedAt?: string;
  className?: string;
}

export function ContradictionBanner({
  severity,
  type,
  reasoning,
  evidenceFor,
  evidenceAgainst,
  detectedBy,
  detectedAt,
  className,
}: ContradictionBannerProps) {
  const getSeverityConfig = () => {
    switch (severity) {
      case 'HIGH':
        return { icon: ShieldAlert, bg: 'bg-semantic-critical-subtle', border: 'border-semantic-critical/20', text: 'text-semantic-critical' };
      case 'MEDIUM':
        return { icon: AlertTriangle, bg: 'bg-semantic-flagged-subtle', border: 'border-semantic-flagged/20', text: 'text-semantic-flagged' };
      case 'LOW':
        return { icon: AlertCircle, bg: 'bg-surface-sunken', border: 'border-border-default', text: 'text-content-secondary' };
    }
  };

  const config = getSeverityConfig();
  const Icon = config.icon;

  return (
    <div className={cn("flex items-start gap-3 p-3 rounded-md border", config.bg, config.border, className)}>
      <Icon className={cn("w-5 h-5 shrink-0 mt-0.5", config.text)} />
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className={cn("text-caption font-bold uppercase", config.text)}>{severity} SEVERITY</span>
          <span className="text-caption text-content-secondary">•</span>
          <span className="text-caption font-mono text-content-primary">{type}</span>
        </div>
        <div className="text-body text-content-primary">
          {reasoning}
        </div>
        {(evidenceFor || evidenceAgainst || detectedBy || detectedAt) && (
          <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-mono-s text-content-secondary">
            {evidenceFor && <span>For: {evidenceFor}</span>}
            {evidenceAgainst && <span>Against: {evidenceAgainst}</span>}
            {detectedBy && <span>Detected by: {detectedBy}</span>}
            {detectedAt && <span>At: {new Date(detectedAt).toLocaleTimeString()}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
