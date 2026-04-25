"use client";

import * as React from "react";
import { cn, getTrustScoreBand } from "@/lib/utils";
import { Badge } from "./badge";
import type { TrustScore } from "@/lib/types";

interface TrustScoreBadgeProps {
  score: number | null;
  confidenceInterval?: [number, number];
  size?: "sm" | "md" | "lg";
  showCI?: boolean;
  className?: string;
}

export function TrustScoreBadge({
  score,
  confidenceInterval,
  size = "md",
  showCI = false,
  className,
}: TrustScoreBadgeProps) {
  if (score === null) {
    return (
      <Badge variant="insufficient" className={className}>
        Insufficient
      </Badge>
    );
  }

  const band = getTrustScoreBand(score);
  const variant = band === "verified" ? "verified" : band === "flagged" ? "flagged" : "critical";

  const sizeClasses = {
    sm: "text-xs px-1.5",
    md: "text-sm px-2",
    lg: "text-base px-3 py-1",
  };

  const labels = {
    verified: "Verified",
    flagged: "Flagged",
    critical: "Critical",
  };

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Badge variant={variant} className={sizeClasses[size]}>
        {score}
      </Badge>
      {showCI && confidenceInterval && (
        <span className="text-mono-s text-[var(--color-content-secondary)]">
          ±{Math.round((confidenceInterval[1] - confidenceInterval[0]) * 50)} (CI 95%)
        </span>
      )}
    </div>
  );
}

interface TrustScoreDisplayProps {
  trustScore: TrustScore;
  showReasoning?: boolean;
  className?: string;
}

export function TrustScoreDisplay({
  trustScore,
  showReasoning = false,
  className,
}: TrustScoreDisplayProps) {
  const band = getTrustScoreBand(trustScore.score);

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-baseline gap-3">
        <span className="text-display text-[var(--color-content-primary)]">
          {trustScore.score}
        </span>
        <Badge
          variant={
            band === "verified"
              ? "verified"
              : band === "flagged"
              ? "flagged"
              : "critical"
          }
        >
          {band === "verified"
            ? "Verified"
            : band === "flagged"
            ? "Flagged"
            : "Critical"}
        </Badge>
      </div>
      <div className="text-mono text-[var(--color-content-secondary)]">
        ±{Math.round((trustScore.confidence_interval[1] - trustScore.confidence_interval[0]) * 50)}{" "}
        (CI 95%)
      </div>
      {showReasoning && trustScore.reasoning && (
        <p className="text-body text-[var(--color-content-secondary)] mt-3">
          {trustScore.reasoning}
        </p>
      )}
    </div>
  );
}
