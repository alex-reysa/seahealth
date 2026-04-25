"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { IndiaMap } from "@/components/india-map";
import { CommandInput } from "@/components/command-input";
import { StatStrip } from "@/components/stat-card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { TrustScoreBadge } from "@/components/ui/trust-score-badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  MOCK_REGION_AGGREGATES,
  MOCK_AUDIT_SUMMARY,
  MOCK_FACILITIES,
} from "@/lib/mock-data";
import { CAPABILITY_LABELS } from "@/lib/types";
import type { MapRegionAggregate, CapabilityType } from "@/lib/types";
import { formatNumber, formatTimestamp, formatDistance } from "@/lib/utils";
import {
  ChevronRight,
  MapPin,
  AlertTriangle,
  FileText,
  Clock,
  Search,
} from "lucide-react";

export default function DashboardPage() {
  const router = useRouter();
  const [command, setCommand] = React.useState("");
  const [isExecuting, setIsExecuting] = React.useState(false);
  const [commandStatus, setCommandStatus] = React.useState<string | undefined>();
  const [selectedRegion, setSelectedRegion] = React.useState<MapRegionAggregate | null>(null);
  const [hoveredRegion, setHoveredRegion] = React.useState<MapRegionAggregate | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  // Simulate data loading
  React.useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 1000);
    return () => clearTimeout(timer);
  }, []);

  const handleCommand = async (cmd: string) => {
    setIsExecuting(true);
    setCommandStatus("Processing command...");

    // Simulate command execution
    await new Promise((r) => setTimeout(r, 1500));

    // Parse simple commands
    const lowerCmd = cmd.toLowerCase();
    if (lowerCmd.includes("patna") || lowerCmd.includes("appendectomy")) {
      setCommandStatus("Focusing Patna, appendectomy, 50 km");
      await new Promise((r) => setTimeout(r, 500));
      router.push("/planner-query?q=" + encodeURIComponent(cmd));
    } else if (lowerCmd.includes("desert") || lowerCmd.includes("map")) {
      setCommandStatus("Opening Desert Map");
      await new Promise((r) => setTimeout(r, 500));
      router.push("/desert-map");
    } else {
      setCommandStatus("Command executed");
    }

    setIsExecuting(false);
  };

  const handleRegionClick = (region: MapRegionAggregate | null) => {
    setSelectedRegion(region);
  };

  // Get top facilities for selected region
  const topFacilities = React.useMemo(() => {
    return MOCK_FACILITIES.filter(
      (f) => f.trust_scores.SURGERY_APPENDECTOMY
    ).slice(0, 5);
  }, []);

  const displayRegion = selectedRegion || hoveredRegion;

  return (
    <div className="h-screen flex flex-col bg-[var(--color-surface-canvas)]">
      {/* Map Canvas - fills most of the screen */}
      <div className="flex-1 relative">
        <IndiaMap
          regions={MOCK_REGION_AGGREGATES}
          selectedRegionId={selectedRegion?.region_id}
          onRegionClick={handleRegionClick}
          onRegionHover={setHoveredRegion}
        />

        {/* Floating Command Panel - top center */}
        <div className="absolute top-6 left-1/2 -translate-x-1/2 w-full max-w-2xl px-4">
          <CommandInput
            value={command}
            onChange={setCommand}
            onSubmit={handleCommand}
            isExecuting={isExecuting}
            status={commandStatus}
            placeholder="Focus Patna, appendectomy, 50 km"
          />
        </div>

        {/* Floating Summary Strip - top left */}
        <div className="absolute top-6 left-6">
          <StatStrip
            isLoading={isLoading}
            stats={[
              {
                label: "Audited",
                value: MOCK_AUDIT_SUMMARY.audited_facilities,
                subValue: "facilities",
              },
              {
                label: "Verified",
                value: MOCK_AUDIT_SUMMARY.verified_facilities,
                subValue: CAPABILITY_LABELS[MOCK_AUDIT_SUMMARY.current_capability],
              },
              {
                label: "Flagged",
                value: MOCK_AUDIT_SUMMARY.flagged_facilities,
                subValue: "for review",
              },
            ]}
          />
        </div>

        {/* Right Telemetry Panel - shows region details */}
        {displayRegion && (
          <div className="absolute top-24 right-6 w-80 glass-control rounded-[var(--radius-xl)] p-4 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-heading-m text-[var(--color-content-primary)]">
                {displayRegion.region_name}
              </h3>
              <Badge variant="subtle">
                {CAPABILITY_LABELS[displayRegion.capability_type]}
              </Badge>
            </div>

            {/* Region metrics */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <span className="text-caption text-[var(--color-content-secondary)] block">
                  Population
                </span>
                <span className="text-heading-s text-[var(--color-content-primary)]">
                  {formatNumber(displayRegion.population.population_count)}
                </span>
              </div>
              <div>
                <span className="text-caption text-[var(--color-content-secondary)] block">
                  Gap Population
                </span>
                <span className="text-heading-s text-[var(--color-semantic-critical)]">
                  {formatNumber(displayRegion.gap_population)}
                </span>
              </div>
              <div>
                <span className="text-caption text-[var(--color-content-secondary)] block">
                  Coverage Ratio
                </span>
                <span className="text-heading-s text-[var(--color-content-primary)]">
                  {(displayRegion.coverage_ratio * 100).toFixed(0)}%
                </span>
              </div>
              <div>
                <span className="text-caption text-[var(--color-content-secondary)] block">
                  Verified Facilities
                </span>
                <span className="text-heading-s text-[var(--color-content-primary)]">
                  {displayRegion.verified_capability_count}
                  <span className="text-mono-s text-[var(--color-content-tertiary)] ml-1">
                    ({displayRegion.capability_count_ci[0]}-{displayRegion.capability_count_ci[1]} CI)
                  </span>
                </span>
              </div>
            </div>

            {/* Top facilities for region */}
            <div className="pt-3 border-t border-[var(--color-border-subtle)]">
              <h4 className="text-heading-s text-[var(--color-content-secondary)] mb-3">
                Top Facilities
              </h4>
              <div className="space-y-2">
                {topFacilities.slice(0, 3).map((facility) => {
                  const ts = facility.trust_scores.SURGERY_APPENDECTOMY;
                  return (
                    <button
                      key={facility.facility_id}
                      onClick={() =>
                        router.push(
                          `/facilities/${facility.facility_id}?capability=SURGERY_APPENDECTOMY`
                        )
                      }
                      className="w-full flex items-center justify-between p-2 rounded-[var(--radius-md)] hover:bg-[var(--color-surface-sunken)] transition-colors text-left"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-body text-[var(--color-content-primary)] truncate">
                          {facility.name}
                        </p>
                        <div className="flex items-center gap-2 text-caption text-[var(--color-content-tertiary)]">
                          <MapPin className="h-3 w-3" />
                          <span>{facility.location.pin_code}</span>
                          {facility.total_contradictions > 0 && (
                            <span className="flex items-center gap-1 text-[var(--color-semantic-flagged)]">
                              <AlertTriangle className="h-3 w-3" />
                              {facility.total_contradictions}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {ts && <TrustScoreBadge score={ts.score} size="sm" />}
                        <ChevronRight className="h-4 w-4 text-[var(--color-content-tertiary)]" />
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <Button
              variant="secondary"
              className="w-full"
              onClick={() =>
                router.push(
                  `/desert-map?region_id=${displayRegion.region_id}&capability=${displayRegion.capability_type}`
                )
              }
            >
              View in Desert Map
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}

        {/* Bottom Status Band */}
        <div className="absolute bottom-6 left-6 right-6 flex items-center justify-between">
          <div className="glass-control rounded-[var(--radius-lg)] px-4 py-2 flex items-center gap-4">
            <div className="flex items-center gap-2 text-caption text-[var(--color-content-secondary)]">
              <Clock className="h-4 w-4" />
              <span>
                Last audited:{" "}
                {MOCK_AUDIT_SUMMARY.last_audited_at
                  ? formatTimestamp(MOCK_AUDIT_SUMMARY.last_audited_at)
                  : "—"}
              </span>
            </div>
            <div className="h-4 w-px bg-[var(--color-border-subtle)]" />
            <div className="flex items-center gap-2 text-caption text-[var(--color-content-secondary)]">
              <FileText className="h-4 w-4" />
              <span>Query trace available</span>
            </div>
          </div>

          {/* Quick actions */}
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              onClick={() =>
                router.push(
                  "/planner-query?q=Which+facilities+within+50km+of+Patna+can+perform+an+appendectomy?"
                )
              }
            >
              <Search className="h-4 w-4" />
              Run Demo Query
            </Button>
            <Button variant="primary" onClick={() => router.push("/desert-map")}>
              Open Desert Map
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
