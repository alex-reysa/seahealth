"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Badge } from "./ui/badge";
import { FileText, Users, Package, BarChart3, ExternalLink } from "lucide-react";
import type { EvidenceRef, EvidenceStance, SourceType } from "@/lib/types";
import { formatTimestamp } from "@/lib/utils";

interface EvidenceCardProps {
  evidence: EvidenceRef;
  stance?: EvidenceStance;
  rationale?: string;
  className?: string;
}

const sourceIcons: Record<SourceType, React.ReactNode> = {
  facility_note: <FileText className="h-3.5 w-3.5" />,
  staff_roster: <Users className="h-3.5 w-3.5" />,
  equipment_inventory: <Package className="h-3.5 w-3.5" />,
  volume_report: <BarChart3 className="h-3.5 w-3.5" />,
  external: <ExternalLink className="h-3.5 w-3.5" />,
};

const sourceLabels: Record<SourceType, string> = {
  facility_note: "Facility Note",
  staff_roster: "Staff Roster",
  equipment_inventory: "Equipment",
  volume_report: "Volume Report",
  external: "External Source",
};

const stanceLabels: Record<EvidenceStance, string> = {
  verifies: "Verifies",
  contradicts: "Contradicts",
  silent: "Silent",
};

export function EvidenceCard({
  evidence,
  stance,
  rationale,
  className,
}: EvidenceCardProps) {
  const stanceVariant =
    stance === "verifies"
      ? "verified"
      : stance === "contradicts"
      ? "critical"
      : "insufficient";

  return (
    <div
      className={cn(
        "bg-[var(--color-surface-raised)] border border-[var(--color-border-subtle)] rounded-[var(--radius-md)] overflow-hidden",
        className
      )}
    >
      {/* Source header */}
      <div className="flex items-center justify-between px-4 py-2 bg-[var(--color-surface-sunken)] border-b border-[var(--color-border-subtle)]">
        <div className="flex items-center gap-2 text-mono-s text-[var(--color-content-secondary)]">
          {sourceIcons[evidence.source_type]}
          <span>{sourceLabels[evidence.source_type]}</span>
          <span className="text-[var(--color-content-tertiary)]">
            {evidence.source_doc_id.slice(0, 12)}...
          </span>
        </div>
        {stance && (
          <Badge variant={stanceVariant} showIcon={true}>
            {stanceLabels[stance]}
          </Badge>
        )}
      </div>

      {/* Snippet with accent border */}
      <div className="p-4 border-l-[3px] border-[var(--color-accent-primary)] bg-[var(--color-accent-primary-subtle)] m-3 rounded-r-[var(--radius-sm)]">
        <p className="text-body-l text-[var(--color-content-primary)]">
          &ldquo;{evidence.snippet}&rdquo;
        </p>
      </div>

      {/* Metadata footer */}
      <div className="px-4 pb-3 flex items-center justify-between text-caption text-[var(--color-content-tertiary)]">
        <span>Retrieved: {formatTimestamp(evidence.retrieved_at)}</span>
        {evidence.source_observed_at && (
          <span>Source date: {formatTimestamp(evidence.source_observed_at)}</span>
        )}
      </div>

      {/* Rationale if provided */}
      {rationale && (
        <div className="px-4 pb-4">
          <p className="text-body text-[var(--color-content-secondary)]">
            {rationale}
          </p>
        </div>
      )}
    </div>
  );
}
