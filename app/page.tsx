"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { IndiaMap } from "@/components/india-map";
import { CommandInput } from "@/components/command-input";
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
import type { MapRegionAggregate } from "@/lib/types";
import { formatNumber, formatTimestamp } from "@/lib/utils";
import {
  ChevronRight,
  MapPin,
  AlertTriangle,
  FileText,
  Clock,
  Search,
  X,
} from "lucide-react";

const GAP_LEGEND = [
  { color: "#EAD8C5", label: "Low" },
  { color: "#D7AF92", label: "" },
  { color: "#C2876A", label: "" },
  { color: "#A4473E", label: "" },
  { color: "#7A2E2A", label: "High" },
];

export default function DashboardPage() {
  const router = useRouter();
  const [command, setCommand] = React.useState("");
  const [isExecuting, setIsExecuting] = React.useState(false);
  const [commandStatus, setCommandStatus] = React.useState<string | undefined>();
  const [selectedRegion, setSelectedRegion] =
    React.useState<MapRegionAggregate | null>(null);
  const [hoveredRegion, setHoveredRegion] =
    React.useState<MapRegionAggregate | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  React.useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 800);
    return () => clearTimeout(timer);
  }, []);

  const handleCommand = async (cmd: string) => {
    setIsExecuting(true);
    setCommandStatus("Parsing command");

    await new Promise((r) => setTimeout(r, 900));

    const lowerCmd = cmd.toLowerCase();
    if (lowerCmd.includes("patna") || lowerCmd.includes("appendectomy")) {
      setCommandStatus("Focusing Patna · appendectomy · 50 km");
      await new Promise((r) => setTimeout(r, 400));
      router.push("/planner-query?q=" + encodeURIComponent(cmd));
    } else if (lowerCmd.includes("desert") || lowerCmd.includes("map")) {
      setCommandStatus("Opening Desert Map");
      await new Promise((r) => setTimeout(r, 400));
      router.push("/desert-map");
    } else {
      setCommandStatus("Command executed");
    }

    setIsExecuting(false);
  };

  const topFacilities = React.useMemo(() => {
    return MOCK_FACILITIES.filter((f) => f.trust_scores.SURGERY_APPENDECTOMY)
      .sort(
        (a, b) =>
          (b.trust_scores.SURGERY_APPENDECTOMY?.score || 0) -
          (a.trust_scores.SURGERY_APPENDECTOMY?.score || 0)
      )
      .slice(0, 4);
  }, []);

  const displayRegion = selectedRegion || hoveredRegion;

  return (
    <div className="h-screen flex flex-col bg-[var(--color-surface-canvas-tint)] relative overflow-hidden">
      {/* Map Canvas - fills the entire workspace */}
      <div className="absolute inset-0">
        <IndiaMap
          regions={MOCK_REGION_AGGREGATES}
          selectedRegionId={selectedRegion?.region_id}
          onRegionClick={setSelectedRegion}
          onRegionHover={setHoveredRegion}
        />
      </div>

      {/* === TOP CONTROL BAR === */}
      <header className="relative z-20 p-4 pointer-events-none">
        <div className="glass-control rounded-[var(--radius-xl)] flex items-stretch divide-x divide-[var(--color-border-subtle)] pointer-events-auto">
          {/* Stats cluster */}
          <div className="flex items-center gap-6 px-5 py-3">
            <StatItem
              label="Audited"
              value={MOCK_AUDIT_SUMMARY.audited_facilities}
              hint="facilities"
              isLoading={isLoading}
            />
            <StatItem
              label="Verified"
              value={MOCK_AUDIT_SUMMARY.verified_facilities}
              hint={CAPABILITY_LABELS[MOCK_AUDIT_SUMMARY.current_capability]}
              tone="verified"
              isLoading={isLoading}
            />
            <StatItem
              label="Flagged"
              value={MOCK_AUDIT_SUMMARY.flagged_facilities}
              hint="for review"
              tone="flagged"
              isLoading={isLoading}
            />
          </div>

          {/* Command input takes remaining width */}
          <div className="flex-1 min-w-0 px-3 py-2">
            <CommandInput
              value={command}
              onChange={setCommand}
              onSubmit={handleCommand}
              isExecuting={isExecuting}
              status={commandStatus}
              placeholder="Focus Patna, appendectomy, 50 km"
            />
          </div>
        </div>
      </header>

      {/* === RIGHT TELEMETRY PANEL === */}
      {displayRegion && (
        <aside className="absolute top-28 right-4 w-[340px] z-20 max-h-[calc(100vh-14rem)] flex flex-col">
          <div className="glass-elevated rounded-[var(--radius-xl)] flex flex-col overflow-hidden">
            <div className="px-4 pt-4 pb-3 flex items-start justify-between gap-3 border-b border-[var(--color-border-subtle)]">
              <div className="min-w-0">
                <p className="text-mono-s text-[var(--color-content-tertiary)] uppercase tracking-wider">
                  Region focus
                </p>
                <h3 className="text-heading-l text-[var(--color-content-primary)] truncate mt-0.5">
                  {displayRegion.region_name}
                </h3>
                <Badge variant="subtle" className="mt-2">
                  {CAPABILITY_LABELS[displayRegion.capability_type]}
                </Badge>
              </div>
              {selectedRegion && (
                <button
                  onClick={() => setSelectedRegion(null)}
                  className="p-1 rounded-[var(--radius-sm)] text-[var(--color-content-tertiary)] hover:text-[var(--color-content-primary)] hover:bg-[var(--color-surface-sunken)] transition-colors"
                  aria-label="Clear selection"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>

            <div className="p-4 overflow-y-auto">
              <div className="grid grid-cols-2 gap-x-4 gap-y-3 mb-4">
                <Metric
                  label="Population"
                  value={formatNumber(displayRegion.population.population_count)}
                />
                <Metric
                  label="Coverage"
                  value={`${(displayRegion.coverage_ratio * 100).toFixed(0)}%`}
                />
                <Metric
                  label="Gap population"
                  value={formatNumber(displayRegion.gap_population)}
                  tone="critical"
                />
                <Metric
                  label="Verified"
                  value={`${displayRegion.verified_capability_count}`}
                  hint={`${displayRegion.capability_count_ci[0]}–${displayRegion.capability_count_ci[1]} CI`}
                />
              </div>

              <div className="border-t border-[var(--color-border-subtle)] pt-3">
                <p className="text-mono-s text-[var(--color-content-tertiary)] uppercase tracking-wider mb-2">
                  Top facilities
                </p>
                <div className="space-y-1">
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
                        className="w-full flex items-center gap-3 p-2 rounded-[var(--radius-md)] hover:bg-[var(--color-surface-sunken)] transition-colors text-left group"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-body text-[var(--color-content-primary)] truncate">
                            {facility.name}
                          </p>
                          <div className="flex items-center gap-2 text-mono-s text-[var(--color-content-tertiary)] mt-0.5">
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
                        {ts && <TrustScoreBadge score={ts.score} size="sm" />}
                        <ChevronRight className="h-4 w-4 text-[var(--color-content-tertiary)] group-hover:text-[var(--color-content-primary)] transition-colors" />
                      </button>
                    );
                  })}
                </div>
              </div>

              <Button
                variant="secondary"
                className="w-full mt-4"
                onClick={() =>
                  router.push(
                    `/desert-map?region_id=${displayRegion.region_id}&capability=${displayRegion.capability_type}`
                  )
                }
              >
                Open in Desert Map
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </aside>
      )}

      {/* === BOTTOM ACTION BAND === */}
      <footer className="relative z-20 mt-auto p-4 flex items-end justify-between gap-4 pointer-events-none">
        {/* Legend + status */}
        <div className="glass-standard rounded-[var(--radius-lg)] px-4 py-3 flex items-center gap-5 pointer-events-auto">
          <div className="flex items-center gap-2">
            <span className="text-mono-s text-[var(--color-content-tertiary)] uppercase tracking-wider">
              Gap
            </span>
            <div className="flex items-center gap-0.5">
              {GAP_LEGEND.map((stop, i) => (
                <div
                  key={i}
                  className="w-5 h-2 first:rounded-l-sm last:rounded-r-sm"
                  style={{ backgroundColor: stop.color }}
                />
              ))}
            </div>
            <span className="text-caption text-[var(--color-content-tertiary)] ml-1">
              Low → High
            </span>
          </div>

          <div className="h-6 w-px bg-[var(--color-border-subtle)]" />

          <div className="flex items-center gap-2 text-caption text-[var(--color-content-secondary)]">
            <Clock className="h-3.5 w-3.5 text-[var(--color-content-tertiary)]" />
            <span>
              Last audit{" "}
              <span className="text-[var(--color-content-primary)] font-medium">
                {MOCK_AUDIT_SUMMARY.last_audited_at
                  ? formatTimestamp(MOCK_AUDIT_SUMMARY.last_audited_at)
                  : "—"}
              </span>
            </span>
          </div>

          <div className="h-6 w-px bg-[var(--color-border-subtle)]" />

          <div className="flex items-center gap-2 text-caption text-[var(--color-content-secondary)]">
            <FileText className="h-3.5 w-3.5 text-[var(--color-content-tertiary)]" />
            <span>Trace ready</span>
          </div>
        </div>

        {/* Quick actions */}
        <div className="flex items-center gap-2 pointer-events-auto">
          <Button
            variant="secondary"
            onClick={() =>
              router.push(
                "/planner-query?q=Which+facilities+within+50km+of+Patna+can+perform+an+appendectomy?"
              )
            }
          >
            <Search className="h-4 w-4" />
            Run demo query
          </Button>
          <Button variant="primary" onClick={() => router.push("/desert-map")}>
            Open Desert Map
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </footer>
    </div>
  );
}

/* ----------------------- subcomponents ----------------------- */

interface StatItemProps {
  label: string;
  value: number | string;
  hint?: string;
  tone?: "default" | "verified" | "flagged";
  isLoading?: boolean;
}

function StatItem({ label, value, hint, tone = "default", isLoading }: StatItemProps) {
  const valueClass =
    tone === "verified"
      ? "text-[var(--color-semantic-verified)]"
      : tone === "flagged"
        ? "text-[var(--color-semantic-flagged)]"
        : "text-[var(--color-content-primary)]";

  return (
    <div className="flex flex-col min-w-[88px]">
      <span className="text-mono-s text-[var(--color-content-tertiary)] uppercase tracking-wider">
        {label}
      </span>
      {isLoading ? (
        <Skeleton className="h-7 w-12 mt-1" />
      ) : (
        <div className="flex items-baseline gap-1.5 mt-0.5">
          <span className={`text-heading-l ${valueClass}`}>{value}</span>
          {hint && (
            <span className="text-caption text-[var(--color-content-tertiary)] truncate">
              {hint}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

interface MetricProps {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "critical";
}

function Metric({ label, value, hint, tone = "default" }: MetricProps) {
  return (
    <div>
      <p className="text-mono-s text-[var(--color-content-tertiary)] uppercase tracking-wider">
        {label}
      </p>
      <p
        className={`text-heading-m mt-0.5 ${
          tone === "critical"
            ? "text-[var(--color-semantic-critical)]"
            : "text-[var(--color-content-primary)]"
        }`}
      >
        {value}
      </p>
      {hint && (
        <p className="text-mono-s text-[var(--color-content-tertiary)] mt-0.5">
          {hint}
        </p>
      )}
    </div>
  );
}
