"use client";

import * as React from "react";
import { useRouter, useSearchParams, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrustScoreDisplay } from "@/components/ui/trust-score-badge";
import { EvidenceCard } from "@/components/evidence-card";
import { ContradictionBanner } from "@/components/contradiction-banner";
import { Skeleton } from "@/components/ui/skeleton";
import { getFacilityById } from "@/lib/mock-data";
import { CAPABILITY_LABELS, SEVERITY_PENALTY } from "@/lib/types";
import type { FacilityAudit, CapabilityType, TrustScore } from "@/lib/types";
import { formatTimestamp, getTrustScoreBand } from "@/lib/utils";
import {
  ChevronLeft,
  ChevronDown,
  MapPin,
  AlertTriangle,
  FileText,
  Clock,
  ExternalLink,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Copy,
  Check,
} from "lucide-react";

export default function FacilityAuditPage() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();

  const facilityId = params.facility_id as string;
  const initialCapability =
    (searchParams.get("capability") as CapabilityType) || "SURGERY_APPENDECTOMY";
  const fromRoute = searchParams.get("from") || "dashboard";

  const [facility, setFacility] = React.useState<FacilityAudit | null>(null);
  const [selectedCapability, setSelectedCapability] =
    React.useState<CapabilityType>(initialCapability);
  const [showTrace, setShowTrace] = React.useState(false);
  const [copiedTraceId, setCopiedTraceId] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(true);

  // Load facility data
  React.useEffect(() => {
    const timer = setTimeout(() => {
      const f = getFacilityById(facilityId);
      setFacility(f || null);

      // Auto-select capability with highest contradiction if none provided
      if (f && !searchParams.get("capability")) {
        const capabilities = Object.entries(f.trust_scores);
        const withHighContradiction = capabilities.find(
          ([, ts]) =>
            ts.contradictions.some((c) => c.severity === "HIGH")
        );
        if (withHighContradiction) {
          setSelectedCapability(withHighContradiction[0] as CapabilityType);
        } else if (capabilities.length > 0) {
          setSelectedCapability(capabilities[0][0] as CapabilityType);
        }
      }

      setIsLoading(false);
    }, 600);

    return () => clearTimeout(timer);
  }, [facilityId, searchParams]);

  const handleBack = () => {
    if (fromRoute === "planner-query") {
      router.push("/planner-query");
    } else if (fromRoute === "desert-map") {
      router.push("/desert-map");
    } else {
      router.push("/");
    }
  };

  const handleCopyTraceId = () => {
    if (facility?.mlflow_trace_id) {
      navigator.clipboard.writeText(facility.mlflow_trace_id);
      setCopiedTraceId(true);
      setTimeout(() => setCopiedTraceId(false), 2000);
    }
  };

  const selectedTrustScore: TrustScore | null =
    facility?.trust_scores[selectedCapability] || null;

  const capabilityList = React.useMemo(() => {
    if (!facility) return [];
    return Object.entries(facility.trust_scores).map(([type, ts]) => ({
      type: type as CapabilityType,
      trustScore: ts,
      hasHighContradiction: ts.contradictions.some((c) => c.severity === "HIGH"),
    }));
  }, [facility]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[var(--color-surface-canvas)] p-6">
        <div className="max-w-7xl mx-auto">
          <Skeleton className="h-8 w-32 mb-6" />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="space-y-4">
              <Skeleton className="h-32 w-full" />
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
            <div className="lg:col-span-2 space-y-4">
              <Skeleton className="h-48 w-full" />
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-32 w-full" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!facility) {
    return (
      <div className="min-h-screen bg-[var(--color-surface-canvas)] p-6 flex items-center justify-center">
        <Card className="p-12 text-center max-w-md">
          <XCircle className="h-12 w-12 mx-auto text-[var(--color-semantic-critical)] mb-4" />
          <h2 className="text-heading-m text-[var(--color-content-primary)] mb-2">
            Facility audit unavailable
          </h2>
          <p className="text-body text-[var(--color-content-secondary)] mb-6">
            The facility with ID &ldquo;{facilityId}&rdquo; could not be found or has not
            been audited yet.
          </p>
          <Button variant="secondary" onClick={handleBack}>
            <ChevronLeft className="h-4 w-4" />
            Back to {fromRoute === "planner-query" ? "Query" : "Dashboard"}
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--color-surface-canvas)]">
      {/* Header */}
      <div className="bg-white border-b border-[var(--color-border-subtle)] px-6 py-4">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="sm" onClick={handleBack}>
                <ChevronLeft className="h-4 w-4" />
                Back
              </Button>
              <div>
                <h1 className="text-heading-l text-[var(--color-content-primary)]">
                  {facility.name}
                </h1>
                <div className="flex items-center gap-4 mt-1">
                  <span className="flex items-center gap-1 text-body text-[var(--color-content-secondary)]">
                    <MapPin className="h-4 w-4" />
                    {facility.location.pin_code || "Location unavailable"}
                  </span>
                  <span className="flex items-center gap-1 text-body text-[var(--color-content-secondary)]">
                    <Clock className="h-4 w-4" />
                    Last audited: {formatTimestamp(facility.last_audited_at)}
                  </span>
                  {facility.total_contradictions > 0 && (
                    <span className="flex items-center gap-1 text-body text-[var(--color-semantic-flagged)]">
                      <AlertTriangle className="h-4 w-4" />
                      {facility.total_contradictions} contradiction
                      {facility.total_contradictions > 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Trace button */}
            {facility.mlflow_trace_id && (
              <Button variant="secondary" onClick={() => setShowTrace(!showTrace)}>
                <FileText className="h-4 w-4" />
                View Trace
                <ChevronDown
                  className={`h-4 w-4 transition-transform ${
                    showTrace ? "rotate-180" : ""
                  }`}
                />
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto p-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Pane - Capabilities List */}
          <div className="space-y-3">
            <h2 className="text-heading-s text-[var(--color-content-secondary)]">
              Claimed Capabilities
            </h2>

            {capabilityList.map(({ type, trustScore, hasHighContradiction }) => {
              const isSelected = selectedCapability === type;
              const band = getTrustScoreBand(trustScore.score);

              return (
                <button
                  key={type}
                  onClick={() => setSelectedCapability(type)}
                  className={`w-full p-4 rounded-[var(--radius-md)] border text-left transition-all ${
                    isSelected
                      ? "border-[var(--color-accent-primary)] bg-[var(--color-accent-primary-subtle)] shadow-[var(--shadow-elevation-1)]"
                      : "border-[var(--color-border-subtle)] bg-[var(--color-surface-raised)] hover:border-[var(--color-border-default)]"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-body font-medium text-[var(--color-content-primary)]">
                          {CAPABILITY_LABELS[type]}
                        </span>
                        {trustScore.claimed ? (
                          <CheckCircle2 className="h-4 w-4 text-[var(--color-semantic-verified)]" />
                        ) : (
                          <XCircle className="h-4 w-4 text-[var(--color-semantic-critical)]" />
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-2 text-caption">
                        <span className="flex items-center gap-1 text-[var(--color-content-secondary)]">
                          <FileText className="h-3 w-3" />
                          {trustScore.evidence.length}
                        </span>
                        {trustScore.contradictions.length > 0 && (
                          <span
                            className={`flex items-center gap-1 ${
                              hasHighContradiction
                                ? "text-[var(--color-semantic-critical)]"
                                : "text-[var(--color-semantic-flagged)]"
                            }`}
                          >
                            <AlertTriangle className="h-3 w-3" />
                            {trustScore.contradictions.length}
                          </span>
                        )}
                      </div>
                    </div>
                    <Badge
                      variant={
                        band === "verified"
                          ? "verified"
                          : band === "flagged"
                          ? "flagged"
                          : "critical"
                      }
                    >
                      {trustScore.score}
                    </Badge>
                  </div>

                  {/* Confidence interval */}
                  <div className="mt-2 text-mono-s text-[var(--color-content-tertiary)]">
                    CI:{" "}
                    {(trustScore.confidence_interval[0] * 100).toFixed(0)}-
                    {(trustScore.confidence_interval[1] * 100).toFixed(0)}
                  </div>
                </button>
              );
            })}

            {capabilityList.length === 0 && (
              <Card className="p-6 text-center">
                <HelpCircle className="h-8 w-8 mx-auto text-[var(--color-content-tertiary)] mb-2" />
                <p className="text-body text-[var(--color-content-secondary)]">
                  No capabilities audited for this facility.
                </p>
              </Card>
            )}
          </div>

          {/* Right Pane - Selected Capability Details */}
          <div className="lg:col-span-2 space-y-6">
            {selectedTrustScore ? (
              <>
                {/* Trust Score Summary */}
                <Card className="p-6">
                  <h3 className="text-heading-s text-[var(--color-content-secondary)] mb-4">
                    Trust Score
                  </h3>
                  <TrustScoreDisplay
                    trustScore={selectedTrustScore}
                    showReasoning={true}
                  />

                  {/* Score formula explanation */}
                  <div className="mt-6 pt-4 border-t border-[var(--color-border-subtle)]">
                    <p className="text-mono-s text-[var(--color-content-tertiary)]">
                      score = max(0, min(100, round(confidence × 100) − severity_penalty))
                    </p>
                    <p className="text-caption text-[var(--color-content-secondary)] mt-1">
                      Penalties: LOW=5, MEDIUM=15, HIGH=30
                    </p>
                  </div>
                </Card>

                {/* Contradictions */}
                {selectedTrustScore.contradictions.length > 0 && (
                  <div className="space-y-3">
                    <h3 className="text-heading-s text-[var(--color-content-primary)]">
                      Contradictions
                    </h3>
                    {/* Sort by severity: HIGH first */}
                    {[...selectedTrustScore.contradictions]
                      .sort((a, b) => {
                        const order = { HIGH: 0, MEDIUM: 1, LOW: 2 };
                        return order[a.severity] - order[b.severity];
                      })
                      .map((contradiction, i) => (
                        <ContradictionBanner
                          key={i}
                          contradiction={contradiction}
                          defaultExpanded={i === 0}
                        />
                      ))}
                  </div>
                )}

                {selectedTrustScore.contradictions.length === 0 && (
                  <Card className="p-6">
                    <div className="flex items-center gap-3">
                      <CheckCircle2 className="h-6 w-6 text-[var(--color-semantic-verified)]" />
                      <div>
                        <h4 className="text-body font-medium text-[var(--color-content-primary)]">
                          No contradictions found
                        </h4>
                        <p className="text-caption text-[var(--color-content-secondary)]">
                          Evidence for this capability is consistent with
                          facility claims.
                        </p>
                      </div>
                    </div>
                  </Card>
                )}

                {/* Evidence */}
                <div className="space-y-3">
                  <h3 className="text-heading-s text-[var(--color-content-primary)]">
                    Evidence ({selectedTrustScore.evidence.length})
                  </h3>

                  {selectedTrustScore.evidence.length > 0 ? (
                    selectedTrustScore.evidence.map((ev, i) => (
                      <EvidenceCard
                        key={i}
                        evidence={ev}
                        stance="verifies"
                      />
                    ))
                  ) : (
                    <Card className="p-6">
                      <div className="flex items-center gap-3">
                        <HelpCircle className="h-6 w-6 text-[var(--color-semantic-insufficient)]" />
                        <div>
                          <h4 className="text-body font-medium text-[var(--color-content-primary)]">
                            No evidence refs were produced for this claim
                          </h4>
                          <p className="text-caption text-[var(--color-content-secondary)]">
                            The audit process did not extract verifiable
                            evidence for this capability.
                          </p>
                        </div>
                      </div>
                    </Card>
                  )}
                </div>
              </>
            ) : (
              <Card className="p-12 text-center">
                <HelpCircle className="h-12 w-12 mx-auto text-[var(--color-content-tertiary)] mb-4" />
                <h3 className="text-heading-m text-[var(--color-content-primary)] mb-2">
                  Select a capability
                </h3>
                <p className="text-body text-[var(--color-content-secondary)]">
                  Choose a capability from the list to view its Trust Score,
                  evidence, and contradictions.
                </p>
              </Card>
            )}
          </div>
        </div>

        {/* Trace Panel (expandable at bottom) */}
        {showTrace && facility.mlflow_trace_id && (
          <Card className="mt-6 p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-heading-s text-[var(--color-content-primary)]">
                MLflow Trace
              </h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCopyTraceId}
              >
                {copiedTraceId ? (
                  <>
                    <Check className="h-4 w-4" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4" />
                    Copy ID
                  </>
                )}
              </Button>
            </div>

            <div className="flex items-center gap-2 mb-4">
              <span className="text-caption text-[var(--color-content-secondary)]">
                Trace ID:
              </span>
              <code className="text-mono text-[var(--color-accent-primary)]">
                {facility.mlflow_trace_id}
              </code>
            </div>

            <div className="space-y-2">
              {[
                { step: "Document Extraction", agent: "extractor.v1", time: "1.2s" },
                { step: "Capability Extraction", agent: "extractor.capability_v1", time: "0.8s" },
                { step: "Staff Validation", agent: "validator.staff_v1", time: "0.5s" },
                { step: "Equipment Validation", agent: "validator.equipment_v1", time: "0.4s" },
                { step: "Trust Score Computation", agent: "scorer.v1", time: "0.2s" },
                { step: "Audit Record Build", agent: "builder.v1", time: "0.1s" },
              ].map((step, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between py-3 border-b border-[var(--color-border-subtle)] last:border-0"
                >
                  <div className="flex items-center gap-3">
                    <div className="h-2 w-2 rounded-full bg-[var(--color-accent-primary)]" />
                    <span className="text-body text-[var(--color-content-primary)]">
                      {step.step}
                    </span>
                    <span className="text-mono-s text-[var(--color-content-tertiary)]">
                      {step.agent}
                    </span>
                  </div>
                  <span className="text-mono-s text-[var(--color-content-secondary)]">
                    {step.time}
                  </span>
                </div>
              ))}
            </div>

            <Button variant="ghost" className="w-full mt-4">
              <ExternalLink className="h-4 w-4" />
              Open in MLflow
            </Button>
          </Card>
        )}
      </div>
    </div>
  );
}
