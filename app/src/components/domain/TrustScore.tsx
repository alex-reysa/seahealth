import React from 'react';
import { Badge } from '@/src/components/ui/Badge';
import { cn } from '@/src/lib/utils';

export interface TrustScoreProps {
  score: number;
  confidenceInterval?: [number, number];
  className?: string;
  showLabel?: boolean;
}

export function TrustScore({ score, confidenceInterval, className, showLabel = true }: TrustScoreProps) {
  const getVariant = (s: number) => {
    if (s >= 80) return 'verified';
    if (s >= 50) return 'flagged';
    return 'critical';
  };

  return (
    <div className={cn("flex flex-col items-start gap-1", className)}>
      <div className="flex items-baseline gap-2">
        <Badge variant={getVariant(score)} className="text-body-l px-3 py-1 font-semibold">
          {score}
        </Badge>
        {confidenceInterval && (
          <span className="text-mono-s text-content-secondary">
            ±{Math.round((confidenceInterval[1] - confidenceInterval[0]) / 2)}
          </span>
        )}
      </div>
      {showLabel && <span className="text-caption text-content-secondary uppercase tracking-wider">Trust Score</span>}
    </div>
  );
}
