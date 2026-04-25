"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { IndiaMap } from "@/components/india-map";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrustScoreBadge } from "@/components/ui/trust-score-badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  MOCK_REGION_AGGREGATES,
  MOCK_FACILITIES,
  MOCK_AUDIT_SUMMARY,
} from "@/lib/mock-data";
import { CAPABILITY_LABELS } from "@/lib/types";
import type { MapRegionAggregate, CapabilityType } from "@/lib/types";
import { formatNumber, formatTimestamp, validatePinCode } from "@/lib/utils";
import {
  ChevronRight,
  ChevronDown,
  MapPin,
  AlertTriangle,
  FileText,
  Clock,
  Search,
  RotateCcw,
  Filter,
} from "lucide-react";

const RADIUS_OPTIONS = [30, 50, 60, 120];

export default function DesertMapPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Parse URL parameters
  const initialCapability =
    (searchParams.get("capability") as CapabilityType) || "SURGERY_APPENDECTOMY";
  const initialRadius = Number(searchParams.get("radius_km")) || 50;
  const initialRegion = searchParams.get("region_id") || null;

  const [capability, setCapability] = React.useState<CapabilityType>(initialCapability);
  const [radius, setRadius] = React.useState(initialRadius);
  const [selectedRegion, setSelectedRegion] = React.useState<MapRegionAggregate | null>(
    initialRegion
      ? MOCK_REGION_AGGREGATES.find((r) => r.region_id === initialRegion) || null
      : null
  );
  const [hoveredRegion, setHoveredRegion] = React.useState<MapRegionAggregate | null>(null);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [showFilters, setShowFilters] = React.useState(true);
  const [isLoading, setIsLoading] = React.useState(true);

  // Simulate loading
  React.useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 800);
    return () => clearTimeout(timer);
  }, []);

  // Update URL when filters change
  React.useEffect(() => {
    const params = new URLSearchParams();
    params.set("capability", capability);
    params.set("radius_km", String(radius));
    if (selectedRegion) {
      params.set("region_id", selectedRegion.region_id);
    }
    router.replace(`/desert-map?${params.toString()}`, { scroll: false });
  }, [capability, radius, selectedRegion, router]);

  const handleRegionClick = (region: MapRegionAggregate | null) => {
    setSelectedRegion(region);
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    // Check if it's a PIN code
    if (validatePinCode(searchQuery)) {
      // In production, geocode the PIN and focus
      console.log("Searching PIN:", searchQuery);
    } else {
      // Search regions by name
      const found = MOCK_REGION_AGGREGATES.find((r) =>
        r.region_name.toLowerCase().includes(searchQuery.toLowerCase())
      );
      if (found) {
        setSelectedRegion(found);
      }
    }
  };

  const handleReset = () => {
    setSelectedRegion(null);
    setSearchQuery("");
    setCapability("SURGERY_APPENDECTOMY");
    setRadius(50);
  };

  // Get facilities for selected region
  const regionFacilities = React.useMemo(() => {
    return MOCK_FACILITIES.filter(
      (f) => f.trust_scores[capability]
    ).sort(
      (a, b) =>
        (b.trust_scores[capability]?.score || 0) -
        (a.trust_scores[capability]?.score || 0)
    );
  }, [capability]);

  const displayRegion = selectedRegion || hoveredRegion;

  return (
    <div className="h-screen flex flex-col bg-[var(--color-surface-canvas)]">
      {/* Top Filter Bar */}
      <div className="flex-shrink-0 border-b border-[var(--color-border-subtle)] bg-white px-6 py-3">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <h1 className="text-heading-m text-[var(--color-content-primary)]">
              Desert Map
            </h1>

            {/* Capability Filter */}
            <div className="relative">
              <select
                value={capability}
                onChange={(e) => setCapability(e.target.value as CapabilityType)}
                className="appearance-none h-10 pl-4 pr-10 rounded-[var(--radius-md)] bg-[var(--color-surface-sunken)] border border-[var(--color-border-subtle)] text-body text-[var(--color-content-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary-subtle)] cursor-pointer"
              >
                {Object.entries(CAPABILITY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--color-content-tertiary)] pointer-events-none" />
            </div>

            {/* Radius Filter */}
            <div className="flex items-center gap-1 bg-[var(--color-surface-sunken)] rounded-[var(--radius-md)] p-1">
              {RADIUS_OPTIONS.map((r) => (
                <button
                  key={r}
                  onClick={() => setRadius(r)}
                  className={`px-3 py-1.5 rounded-[var(--radius-sm)] text-caption transition-colors ${
                    radius === r
                      ? "bg-[var(--color-accent-primary)] text-[var(--color-content-inverse)]"
                      : "text-[var(--color-content-secondary)] hover:text-[var(--color-content-primary)]"
                  }`}
                >
                  {r} km
                </button>
              ))}
            </div>

            {/* Search */}
            <form onSubmit={handleSearch} className="flex items-center gap-2">
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search region or PIN..."
                icon={<Search className="h-4 w-4" />}
                className="w-48"
              />
            </form>
          </div>

          <Button variant="ghost" onClick={handleReset}>
            <RotateCcw className="h-4 w-4" />
            Reset Map
          </Button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex">
        {/* Map Canvas */}
        <div className="flex-1 relative">
          <IndiaMap
            regions={MOCK_REGION_AGGREGATES.filter(
              (r) => r.capability_type === capability
            )}
            selectedRegionId={selectedRegion?.region_id}
            onRegionClick={handleRegionClick}
            onRegionHover={setHoveredRegion}
          />

          {/* Bottom Metric Strip */}
          <div className="absolute bottom-6 left-6 glass-control rounded-[var(--radius-lg)] px-4 py-2 flex items-center gap-6">
            <div className="flex items-center gap-2 text-caption">
              <span className="text-[var(--color-content-secondary)]">Audited:</span>
              <span className="text-[var(--color-content-primary)] font-medium">
                {MOCK_AUDIT_SUMMARY.audited_facilities}
              </span>
            </div>
            <div className="h-4 w-px bg-[var(--color-border-subtle)]" />
            <div className="flex items-center gap-2 text-caption">
              <span className="text-[var(--color-content-secondary)]">Verified:</span>
              <span className="text-[var(--color-semantic-verified)] font-medium">
                {MOCK_AUDIT_SUMMARY.verified_facilities}
              </span>
            </div>
            <div className="h-4 w-px bg-[var(--color-border-subtle)]" />
            <div className="flex items-center gap-2 text-caption">
              <span className="text-[var(--color-content-secondary)]">Flagged:</span>
              <span className="text-[var(--color-semantic-flagged)] font-medium">
                {MOCK_AUDIT_SUMMARY.flagged_facilities}
              </span>
            </div>
            <div className="h-4 w-px bg-[var(--color-border-subtle)]" />
            <div className="flex items-center gap-2 text-caption text-[var(--color-content-tertiary)]">
              <Clock className="h-4 w-4" />
              <span>
                {MOCK_AUDIT_SUMMARY.last_audited_at
                  ? formatTimestamp(MOCK_AUDIT_SUMMARY.last_audited_at)
                  : "—"}
              </span>
            </div>
          </div>
        </div>

        {/* Right Rail - Region Details */}
        <div className="w-96 border-l border-[var(--color-border-subtle)] bg-white overflow-y-auto">
          {isLoading ? (
            <div className="p-6 space-y-4">
              <Skeleton className="h-8 w-32" />
              <div className="grid grid-cols-2 gap-4">
                {[1, 2, 3, 4].map((i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
              <Skeleton className="h-6 w-24" />
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : displayRegion ? (
            <div className="p-6 space-y-6">
              {/* Region Header */}
              <div>
                <div className="flex items-center justify-between">
                  <h2 className="text-heading-l text-[var(--color-content-primary)]">
                    {displayRegion.region_name}
                  </h2>
                  <Badge variant="subtle">{displayRegion.radius_km} km</Badge>
                </div>
                <Badge variant="verified" className="mt-2">
                  {CAPABILITY_LABELS[displayRegion.capability_type]}
                </Badge>
              </div>

              {/* Region Metrics */}
              <div className="grid grid-cols-2 gap-4">
                <Card variant="stat">
                  <span className="text-caption text-[var(--color-content-secondary)] block">
                    Population
                  </span>
                  <span className="text-heading-m text-[var(--color-content-primary)]">
                    {formatNumber(displayRegion.population.population_count)}
                  </span>
                </Card>
                <Card variant="stat">
                  <span className="text-caption text-[var(--color-content-secondary)] block">
                    Gap Population
                  </span>
                  <span className="text-heading-m text-[var(--color-semantic-critical)]">
                    {formatNumber(displayRegion.gap_population)}
                  </span>
                </Card>
                <Card variant="stat">
                  <span className="text-caption text-[var(--color-content-secondary)] block">
                    Coverage Ratio
                  </span>
                  <span className="text-heading-m text-[var(--color-content-primary)]">
                    {(displayRegion.coverage_ratio * 100).toFixed(1)}%
                  </span>
                </Card>
                <Card variant="stat">
                  <span className="text-caption text-[var(--color-content-secondary)] block">
                    Verified Facilities
                  </span>
                  <div className="flex items-baseline gap-1">
                    <span className="text-heading-m text-[var(--color-content-primary)]">
                      {displayRegion.verified_capability_count}
                    </span>
                    <span className="text-mono-s text-[var(--color-content-tertiary)]">
                      ({displayRegion.capability_count_ci[0]}-
                      {displayRegion.capability_count_ci[1]} CI)
                    </span>
                  </div>
                </Card>
              </div>

              {/* Coverage info */}
              <div className="py-4 border-y border-[var(--color-border-subtle)]">
                <div className="flex items-center justify-between text-body">
                  <span className="text-[var(--color-content-secondary)]">
                    Covered Population
                  </span>
                  <span className="text-[var(--color-content-primary)]">
                    {formatNumber(displayRegion.covered_population)}
                  </span>
                </div>
                {/* Coverage bar */}
                <div className="mt-2 h-2 bg-[var(--color-surface-sunken)] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-[var(--color-accent-primary)] rounded-full transition-all"
                    style={{ width: `${displayRegion.coverage_ratio * 100}%` }}
                  />
                </div>
              </div>

              {/* Facility List */}
              <div>
                <h3 className="text-heading-s text-[var(--color-content-primary)] mb-3">
                  Top Facilities
                </h3>
                <div className="space-y-2">
                  {regionFacilities.slice(0, 6).map((facility) => {
                    const ts = facility.trust_scores[capability];
                    return (
                      <button
                        key={facility.facility_id}
                        onClick={() =>
                          router.push(
                            `/facilities/${facility.facility_id}?capability=${capability}&from=desert-map`
                          )
                        }
                        className="w-full flex items-center justify-between p-3 rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] hover:bg-[var(--color-surface-sunken)] transition-colors text-left"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-body text-[var(--color-content-primary)] font-medium truncate">
                            {facility.name}
                          </p>
                          <div className="flex items-center gap-3 text-caption text-[var(--color-content-tertiary)] mt-1">
                            <span className="flex items-center gap-1">
                              <MapPin className="h-3 w-3" />
                              {facility.location.pin_code}
                            </span>
                            <span className="flex items-center gap-1">
                              <FileText className="h-3 w-3" />
                              {ts?.evidence.length || 0}
                            </span>
                            {facility.total_contradictions > 0 && (
                              <span className="flex items-center gap-1 text-[var(--color-semantic-flagged)]">
                                <AlertTriangle className="h-3 w-3" />
                                {facility.total_contradictions}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 ml-3">
                          {ts && <TrustScoreBadge score={ts.score} size="sm" />}
                          <ChevronRight className="h-4 w-4 text-[var(--color-content-tertiary)]" />
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Timestamp */}
              <div className="text-caption text-[var(--color-content-tertiary)] flex items-center gap-2">
                <Clock className="h-4 w-4" />
                <span>Generated: {formatTimestamp(displayRegion.generated_at)}</span>
              </div>
            </div>
          ) : (
            <div className="p-6 flex flex-col items-center justify-center h-full text-center">
              <MapPin className="h-12 w-12 text-[var(--color-content-tertiary)] mb-4" />
              <h3 className="text-heading-m text-[var(--color-content-primary)] mb-2">
                Select a region
              </h3>
              <p className="text-body text-[var(--color-content-secondary)]">
                Click on a region in the map or search to see detailed coverage
                information and facility rankings.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
