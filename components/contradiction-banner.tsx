"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Badge } from "./ui/badge";
import { AlertTriangle, ChevronDown, ChevronUp } from "lucide-react";
import type { Contradiction } from "@/lib/types";
import { CONTRADICTION_LABELS } from "@/lib/types";
import { formatTimestamp } from "@/lib/utils";

interface ContradictionBannerProps {
  contradiction: Contradiction;
  expandable?: boolean;
  defaultExpanded?: boolean;
  className?: string;
}

export function ContradictionBanner({
  contradiction,
  expandable = true,
  defaultExpanded = false,
  className,
}: ContradictionBannerProps) {
  const [isExpanded, setIsExpanded] = React.useState(defaultExpanded);

  const severityStyles = {
    HIGH: "border-[var(--color-semantic-critical)] bg-[var(--color-semantic-critical-subtle)]",
    MEDIUM: "border-[var(--color-semantic-flagged)] bg-[var(--color-semantic-flagged-subtle)]",
    LOW: "border-[var(--color-border-default)] bg-[var(--color-surface-sunken)]",
  };

  const severityIconFill = {
    HIGH: "fill-[var(--color-semantic-critical)]",
    MEDIUM: "fill-none",
    LOW: "fill-none",
  };

  return (
    <div
      className={cn(
        "border-l-4 rounded-[var(--radius-md)] overflow-hidden",
        severityStyles[contradiction.severity],
        className
      )}
    >
      <button
        onClick={() => expandable && setIsExpanded(!isExpanded)}
        className={cn(
          "w-full px-4 py-3 flex items-start gap-3 text-left",
          expandable && "cursor-pointer hover:bg-black/5 transition-colors"
        )}
        disabled={!expandable}
      >
        <AlertTriangle
          className={cn(
            "h-5 w-5 flex-shrink-0 mt-0.5",
            contradiction.severity === "HIGH"
              ? "text-[var(--color-semantic-critical)]"
              : contradiction.severity === "MEDIUM"
              ? "text-[var(--color-semantic-flagged)]"
              : "text-[var(--color-content-secondary)]",
            severityIconFill[contradiction.severity]
          )}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge
              variant={
                contradiction.severity === "HIGH"
                  ? "critical"
                  : contradiction.severity === "MEDIUM"
                  ? "flagged"
                  : "subtle"
              }
              showIcon={false}
            >
              {contradiction.severity}
            </Badge>
            <span className="text-mono-s text-[var(--color-content-secondary)]">
              {CONTRADICTION_LABELS[contradiction.contradiction_type]}
            </span>
          </div>
          <p className="text-body text-[var(--color-content-primary)] mt-1">
            {contradiction.reasoning}
          </p>
        </div>
        {expandable && (
          <div className="flex-shrink-0 text-[var(--color-content-tertiary)]">
            {isExpanded ? (
              <ChevronUp className="h-5 w-5" />
            ) : (
              <ChevronDown className="h-5 w-5" />
            )}
          </div>
        )}
      </button>

      {/* Expanded details */}
      {isExpanded && (
        <div className="px-4 pb-4 pt-0 space-y-3">
          <div className="h-px bg-[var(--color-border-subtle)] ml-8" />
          
          {/* Evidence for */}
          {contradiction.evidence_for.length > 0 && (
            <div className="ml-8">
              <h4 className="text-heading-s text-[var(--color-content-secondary)] mb-2">
                Claim:
              </h4>
              {contradiction.evidence_for.map((ev, i) => (
                <p
                  key={i}
                  className="text-body text-[var(--color-content-primary)] bg-[var(--color-surface-raised)] p-2 rounded-[var(--radius-sm)] border border-[var(--color-border-subtle)]"
                >
                  &ldquo;{ev.snippet}&rdquo;
                </p>
              ))}
            </div>
          )}

          {/* Evidence against */}
          {contradiction.evidence_against.length > 0 && (
            <div className="ml-8">
              <h4 className="text-heading-s text-[var(--color-content-secondary)] mb-2">
                Counter-evidence:
              </h4>
              {contradiction.evidence_against.map((ev, i) => (
                <p
                  key={i}
                  className="text-body text-[var(--color-content-primary)] bg-[var(--color-surface-raised)] p-2 rounded-[var(--radius-sm)] border border-[var(--color-border-subtle)]"
                >
                  &ldquo;{ev.snippet}&rdquo;
                </p>
              ))}
            </div>
          )}

          {/* Metadata */}
          <div className="ml-8 flex items-center gap-4 text-caption text-[var(--color-content-tertiary)]">
            <span>Detected by: {contradiction.detected_by}</span>
            <span>At: {formatTimestamp(contradiction.detected_at)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
