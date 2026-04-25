"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrustScoreBadge } from "@/components/ui/trust-score-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { MOCK_QUERY_RESULT } from "@/lib/mock-data";
import { CAPABILITY_LABELS } from "@/lib/types";
import type { QueryResult, RankedFacility } from "@/lib/types";
import { formatNumber, formatDistance, formatTimestamp } from "@/lib/utils";
import {
  Search,
  Download,
  ChevronRight,
  MapPin,
  AlertTriangle,
  FileText,
  Clock,
  ChevronDown,
  ExternalLink,
} from "lucide-react";

const EXAMPLE_QUERIES = [
  "Which facilities within 50km of Patna can perform an appendectomy?",
  "Show neonatal care facilities in Bihar",
  "ICU beds within 30km of Muzaffarpur",
];

export default function PlannerQueryPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get("q") || "";

  const [query, setQuery] = React.useState(initialQuery);
  const [isLoading, setIsLoading] = React.useState(false);
  const [result, setResult] = React.useState<QueryResult | null>(
    initialQuery ? MOCK_QUERY_RESULT : null
  );
  const [expandedRow, setExpandedRow] = React.useState<string | null>(null);
  const [showTrace, setShowTrace] = React.useState(false);

  // Auto-run query if provided in URL
  React.useEffect(() => {
    if (initialQuery && !result) {
      handleSubmit(initialQuery);
    }
  }, []);

  const handleSubmit = async (q: string) => {
    if (!q.trim()) return;

    setIsLoading(true);
    setResult(null);

    // Simulate query processing
    await new Promise((r) => setTimeout(r, 2000));

    // Use mock data
    setResult({
      ...MOCK_QUERY_RESULT,
      query: q,
      generated_at: new Date().toISOString(),
    });
    setIsLoading(false);
  };

  const handleExport = () => {
    if (!result) return;

    const headers = [
      "rank",
      "facility_id",
      "name",
      "distance_km",
      "trust_score",
      "confidence_interval_low",
      "confidence_interval_high",
      "contradictions_flagged",
      "evidence_count",
      "latitude",
      "longitude",
      "pin_code",
      "audit_url",
    ];

    const rows = result.ranked_facilities.map((f) => [
      f.rank,
      f.facility_id,
      f.name,
      f.distance_km.toFixed(2),
      f.trust_score.score,
      (f.trust_score.confidence_interval[0] * 100).toFixed(0),
      (f.trust_score.confidence_interval[1] * 100).toFixed(0),
      f.contradictions_flagged,
      f.evidence_count,
      f.location.lat,
      f.location.lng,
      f.location.pin_code || "",
      `/facilities/${f.facility_id}?capability=${result.parsed_intent.capability_type}`,
    ]);

    const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `query-result-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleRowClick = (facility: RankedFacility) => {
    router.push(
      `/facilities/${facility.facility_id}?capability=${result?.parsed_intent.capability_type}&from=planner-query`
    );
  };

  return (
    <div className="min-h-screen bg-[var(--color-surface-canvas)] p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-heading-l text-[var(--color-content-primary)]">
            Planner Query Console
          </h1>
          <p className="text-body text-[var(--color-content-secondary)] mt-1">
            Ask natural-language questions to find and rank healthcare facilities by
            capability and trust.
          </p>
        </div>

        {/* Query Input Area */}
        <Card className="p-6">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSubmit(query);
            }}
            className="space-y-4"
          >
            <div>
              <label
                htmlFor="query"
                className="text-heading-s text-[var(--color-content-primary)] block mb-2"
              >
                Query
              </label>
              <div className="flex gap-3">
                <Input
                  id="query"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Which facilities within 50km of Patna can perform an appendectomy?"
                  icon={<Search className="h-5 w-5" />}
                  className="flex-1"
                  disabled={isLoading}
                />
                <Button
                  type="submit"
                  variant="primary"
                  isLoading={isLoading}
                  disabled={!query.trim() || isLoading}
                >
                  {isLoading ? "Processing..." : "Run Query"}
                </Button>
              </div>
            </div>

            {/* Example queries */}
            <div className="flex flex-wrap gap-2">
              <span className="text-caption text-[var(--color-content-tertiary)]">
                Examples:
              </span>
              {EXAMPLE_QUERIES.map((eq) => (
                <button
                  key={eq}
                  type="button"
                  onClick={() => {
                    setQuery(eq);
                    handleSubmit(eq);
                  }}
                  className="text-caption text-[var(--color-accent-primary)] hover:underline"
                  disabled={isLoading}
                >
                  {eq}
                </button>
              ))}
            </div>
          </form>
        </Card>

        {/* Results Area */}
        {isLoading && (
          <Card className="p-6">
            <div className="space-y-4">
              <Skeleton className="h-6 w-48" />
              <div className="space-y-3">
                {[1, 2, 3, 4, 5].map((i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            </div>
          </Card>
        )}

        {result && !isLoading && (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            {/* Main Results Table */}
            <div className="lg:col-span-3 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <h2 className="text-heading-m text-[var(--color-content-primary)]">
                    Results
                  </h2>
                  <Badge variant="subtle">
                    {result.ranked_facilities.length} of {result.total_candidates}{" "}
                    candidates
                  </Badge>
                </div>
                <Button variant="secondary" onClick={handleExport}>
                  <Download className="h-4 w-4" />
                  Export CSV
                </Button>
              </div>

              {/* Results Table */}
              <Card className="overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-[var(--color-surface-sunken)] border-b border-[var(--color-border-subtle)]">
                      <tr>
                        <th className="text-left text-caption text-[var(--color-content-secondary)] px-4 py-3 font-medium">
                          Rank
                        </th>
                        <th className="text-left text-caption text-[var(--color-content-secondary)] px-4 py-3 font-medium">
                          Facility
                        </th>
                        <th className="text-left text-caption text-[var(--color-content-secondary)] px-4 py-3 font-medium">
                          Distance
                        </th>
                        <th className="text-left text-caption text-[var(--color-content-secondary)] px-4 py-3 font-medium">
                          Trust Score
                        </th>
                        <th className="text-left text-caption text-[var(--color-content-secondary)] px-4 py-3 font-medium">
                          CI
                        </th>
                        <th className="text-left text-caption text-[var(--color-content-secondary)] px-4 py-3 font-medium">
                          Issues
                        </th>
                        <th className="text-left text-caption text-[var(--color-content-secondary)] px-4 py-3 font-medium">
                          Evidence
                        </th>
                        <th className="text-left text-caption text-[var(--color-content-secondary)] px-4 py-3 font-medium">
                          Action
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.ranked_facilities.map((facility) => (
                        <React.Fragment key={facility.facility_id}>
                          <tr
                            className="border-b border-[var(--color-border-subtle)] hover:bg-[var(--color-surface-sunken)] cursor-pointer transition-colors h-[56px]"
                            onClick={() => handleRowClick(facility)}
                            tabIndex={0}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleRowClick(facility);
                            }}
                          >
                            <td className="px-4 py-3">
                              <span className="text-mono text-[var(--color-content-primary)]">
                                #{facility.rank}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <div>
                                <p className="text-body text-[var(--color-content-primary)] font-medium">
                                  {facility.name}
                                </p>
                                <div className="flex items-center gap-1 text-caption text-[var(--color-content-tertiary)]">
                                  <MapPin className="h-3 w-3" />
                                  <span>{facility.location.pin_code || "—"}</span>
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-body text-[var(--color-content-primary)]">
                                {formatDistance(facility.distance_km)}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <TrustScoreBadge
                                score={facility.trust_score.score}
                                size="sm"
                              />
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-mono-s text-[var(--color-content-secondary)]">
                                {(
                                  facility.trust_score.confidence_interval[0] * 100
                                ).toFixed(0)}
                                -
                                {(
                                  facility.trust_score.confidence_interval[1] * 100
                                ).toFixed(0)}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              {facility.contradictions_flagged > 0 ? (
                                <div className="flex items-center gap-1 text-[var(--color-semantic-flagged)]">
                                  <AlertTriangle className="h-4 w-4" />
                                  <span className="text-body">
                                    {facility.contradictions_flagged}
                                  </span>
                                </div>
                              ) : (
                                <span className="text-body text-[var(--color-content-tertiary)]">
                                  —
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-1 text-[var(--color-content-secondary)]">
                                <FileText className="h-4 w-4" />
                                <span className="text-body">
                                  {facility.evidence_count}
                                </span>
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRowClick(facility);
                                }}
                              >
                                Audit
                                <ChevronRight className="h-4 w-4" />
                              </Button>
                            </td>
                          </tr>

                          {/* Expandable row with reasoning */}
                          {expandedRow === facility.facility_id && (
                            <tr className="bg-[var(--color-surface-sunken)]">
                              <td colSpan={8} className="px-4 py-4">
                                <div className="pl-8">
                                  <h4 className="text-heading-s text-[var(--color-content-secondary)] mb-2">
                                    Trust Score Reasoning
                                  </h4>
                                  <p className="text-body text-[var(--color-content-primary)]">
                                    {facility.trust_score.reasoning}
                                  </p>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>

            {/* Right Sidebar - Parsed Intent & Trace */}
            <div className="space-y-4">
              {/* Parsed Intent */}
              <Card className="p-4">
                <h3 className="text-heading-s text-[var(--color-content-primary)] mb-4">
                  Parsed Intent
                </h3>
                <div className="space-y-3">
                  <div>
                    <span className="text-caption text-[var(--color-content-secondary)] block">
                      Capability
                    </span>
                    <Badge variant="verified" className="mt-1">
                      {CAPABILITY_LABELS[result.parsed_intent.capability_type]}
                    </Badge>
                  </div>
                  <div>
                    <span className="text-caption text-[var(--color-content-secondary)] block">
                      Location
                    </span>
                    <div className="flex items-center gap-1 mt-1">
                      <MapPin className="h-4 w-4 text-[var(--color-content-tertiary)]" />
                      <span className="text-body text-[var(--color-content-primary)]">
                        {result.parsed_intent.location.lat.toFixed(4)},{" "}
                        {result.parsed_intent.location.lng.toFixed(4)}
                      </span>
                    </div>
                    {result.parsed_intent.location.pin_code && (
                      <span className="text-mono-s text-[var(--color-content-tertiary)]">
                        PIN: {result.parsed_intent.location.pin_code}
                      </span>
                    )}
                  </div>
                  <div>
                    <span className="text-caption text-[var(--color-content-secondary)] block">
                      Radius
                    </span>
                    <span className="text-body text-[var(--color-content-primary)]">
                      {result.parsed_intent.radius_km} km
                    </span>
                  </div>
                  <div className="pt-3 border-t border-[var(--color-border-subtle)]">
                    <span className="text-caption text-[var(--color-content-secondary)] block">
                      Generated
                    </span>
                    <span className="text-mono-s text-[var(--color-content-tertiary)]">
                      {formatTimestamp(result.generated_at)}
                    </span>
                  </div>
                </div>
              </Card>

              {/* Query Trace */}
              <Card className="p-4">
                <button
                  onClick={() => setShowTrace(!showTrace)}
                  className="w-full flex items-center justify-between"
                >
                  <h3 className="text-heading-s text-[var(--color-content-primary)]">
                    Query Trace
                  </h3>
                  <ChevronDown
                    className={`h-5 w-5 text-[var(--color-content-tertiary)] transition-transform ${
                      showTrace ? "rotate-180" : ""
                    }`}
                  />
                </button>

                {showTrace && (
                  <div className="mt-4 space-y-3">
                    <div className="flex items-center gap-2">
                      <span className="text-caption text-[var(--color-content-secondary)]">
                        Trace ID:
                      </span>
                      <code className="text-mono-s text-[var(--color-accent-primary)]">
                        {result.query_trace_id}
                      </code>
                    </div>
                    <div className="space-y-2">
                      {[
                        { step: "Parse Intent", time: "45ms" },
                        { step: "Geocode Location", time: "120ms" },
                        { step: "Search Facilities", time: "280ms" },
                        { step: "Fetch Audits", time: "150ms" },
                        { step: "Rank Results", time: "85ms" },
                      ].map((step, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between py-2 border-b border-[var(--color-border-subtle)] last:border-0"
                        >
                          <span className="text-body text-[var(--color-content-primary)]">
                            {step.step}
                          </span>
                          <span className="text-mono-s text-[var(--color-content-tertiary)]">
                            {step.time}
                          </span>
                        </div>
                      ))}
                    </div>
                    <Button variant="ghost" size="sm" className="w-full">
                      <ExternalLink className="h-4 w-4" />
                      Open in MLflow
                    </Button>
                  </div>
                )}
              </Card>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!result && !isLoading && (
          <Card className="p-12 text-center">
            <Search className="h-12 w-12 mx-auto text-[var(--color-content-tertiary)] mb-4" />
            <h3 className="text-heading-m text-[var(--color-content-primary)] mb-2">
              Run a query to see results
            </h3>
            <p className="text-body text-[var(--color-content-secondary)] max-w-md mx-auto">
              Enter a natural-language query about healthcare facilities, or try one
              of the example queries above.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}
