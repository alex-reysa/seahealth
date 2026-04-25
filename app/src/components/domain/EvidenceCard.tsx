import React from 'react';
import { Card } from '@/src/components/ui/Card';
import { CheckCircle2, XCircle, MinusCircle, FileText } from 'lucide-react';
import { cn } from '@/src/lib/utils';

export type Stance = 'verifies' | 'contradicts' | 'silent';

export interface EvidenceCardProps {
  key?: React.Key;
  stance: Stance;
  snippet: string;
  sourceType: string;
  rationale: string;
  sourceDocId?: string;
  span?: string;
  sourceObservedAt?: string;
  retrievedAt?: string;
  className?: string;
}

export function EvidenceCard({
  stance,
  snippet,
  sourceType,
  rationale,
  sourceDocId,
  span,
  sourceObservedAt,
  retrievedAt,
  className,
}: EvidenceCardProps) {
  const getStanceConfig = () => {
    switch (stance) {
      case 'verifies':
        return { icon: CheckCircle2, color: 'text-semantic-verified', bg: 'bg-semantic-verified-subtle', label: 'Verifies' };
      case 'contradicts':
        return { icon: XCircle, color: 'text-semantic-critical', bg: 'bg-semantic-critical-subtle', label: 'Contradicts' };
      case 'silent':
        return { icon: MinusCircle, color: 'text-content-tertiary', bg: 'bg-surface-sunken', label: 'Silent' };
    }
  };

  const config = getStanceConfig();
  const Icon = config.icon;

  return (
    <Card variant="default" className={cn("p-4 flex flex-col gap-3", className)}>
      <div className="flex items-center justify-between">
        <div className={cn("flex items-center gap-1.5 px-2 py-1 rounded-sm text-caption font-medium", config.bg, config.color)}>
          <Icon className="w-3.5 h-3.5" />
          <span>{config.label}</span>
        </div>
        <div className="flex items-center gap-1 text-caption text-content-secondary">
          <FileText className="w-3 h-3" />
          {sourceType}
        </div>
      </div>
      <div className="text-body text-content-primary border-l-2 border-border-default pl-3 py-1 italic">
        "{snippet}"
      </div>
      <div className="text-caption text-content-secondary">
        <span className="font-medium text-content-primary">Rationale: </span>
        {rationale}
      </div>
      {(sourceDocId || span || sourceObservedAt || retrievedAt) && (
        <div className="grid grid-cols-2 gap-2 border-t border-border-subtle pt-3 text-mono-s text-content-secondary">
          {sourceDocId && <span>Doc: {sourceDocId}</span>}
          {span && <span>Span: {span}</span>}
          {sourceObservedAt && <span>Observed: {new Date(sourceObservedAt).toLocaleDateString()}</span>}
          {retrievedAt && <span>Retrieved: {new Date(retrievedAt).toLocaleTimeString()}</span>}
        </div>
      )}
    </Card>
  );
}
