import React from 'react';
import { createPortal } from 'react-dom';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Map, Marker } from '@vis.gl/react-maplibre';
import { feature } from 'topojson-client';
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Command,
  ExternalLink,
  FileText,
  Loader2,
  MapPin,
  Play,
  RotateCcw,
  Search,
  ShieldAlert,
  Target,
  X,
} from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';

import { Breadcrumbs } from '@/src/components/domain/Breadcrumbs';
import { TrustScore } from '@/src/components/domain/TrustScore';
import { Button } from '@/src/components/ui/Button';
import { Card } from '@/src/components/ui/Card';
import { Input } from '@/src/components/ui/Input';
import indiaDistrictsTopoRaw from '@/src/data/indiaDistricts.topojson?raw';
import { useFacilityAudit } from '@/src/hooks/useFacilityAudit';
import { useFacilityLocations } from '@/src/hooks/useFacilityLocations';
import { useMapAggregates } from '@/src/hooks/useMapAggregates';
import { usePlannerQuery } from '@/src/hooks/usePlannerQuery';
import { useSummary } from '@/src/hooks/useSummary';
import { CAPABILITIES, CHALLENGE_QUERY, formatNumber, getCapabilityLabel } from '@/src/lib/capabilities';
import { getBounds } from '@/src/lib/regionTree';
import type {
  CapabilityType,
  Contradiction,
  EvidenceRef,
  ExecutionStep,
  FacilityAudit,
  MapRegionAggregate,
  RankedFacility,
  TrustScore as ApiTrustScore,
} from '@/src/types/api';

const INDIA_CENTER = [78.9629, 20.5937] as [number, number];
const RADIUS_OPTIONS = [30, 50, 60, 120];
type SearchMode = 'semantic' | 'capability';
type AgentPanelView = 'facilities' | 'trace';

type DesertRadius = 30 | 60 | 120;
const DESERT_RADIUS_OPTIONS: DesertRadius[] = [30, 60, 120];

const RISK_TIER_COLORS: Record<string, string> = {
  critical: '#7E2F2C',
  high: '#C56556',
  moderate: '#E5B86F',
  low: '#72B7A8',
};

const RISK_TIER_OPACITY: Record<string, number> = {
  critical: 0.75,
  high: 0.6,
  moderate: 0.45,
  low: 0.3,
};

const DESERT_LEGEND_STOPS = [
  { threshold: 0, color: '#72B7A8', label: 'Low' },
  { threshold: 1, color: '#E5B86F', label: 'Moderate' },
  { threshold: 2, color: '#C56556', label: 'High' },
  { threshold: 3, color: '#7E2F2C', label: 'Critical' },
];

const indiaDistrictsTopo = JSON.parse(indiaDistrictsTopoRaw);
const indiaDistrictsGeoJson = feature(indiaDistrictsTopo, indiaDistrictsTopo.objects.data) as any;

function geoCircleFeature(lng: number, lat: number, radiusKm: number, steps = 64): any {
  const earthRadiusKm = 6371;
  const angularDistance = radiusKm / earthRadiusKm;
  const latRad = (lat * Math.PI) / 180;
  const lngRad = (lng * Math.PI) / 180;
  const ring: Array<[number, number]> = [];
  for (let i = 0; i <= steps; i++) {
    const bearing = (i * 2 * Math.PI) / steps;
    const lat2 = Math.asin(
      Math.sin(latRad) * Math.cos(angularDistance) +
        Math.cos(latRad) * Math.sin(angularDistance) * Math.cos(bearing),
    );
    const lng2 =
      lngRad +
      Math.atan2(
        Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(latRad),
        Math.cos(angularDistance) - Math.sin(latRad) * Math.sin(lat2),
      );
    ring.push([(lng2 * 180) / Math.PI, (lat2 * 180) / Math.PI]);
  }
  return {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [ring] },
    properties: {},
  };
}

function buildCoverageFeatureCollection(facilities: RankedFacility[], radiusKm: number): any {
  return {
    type: 'FeatureCollection',
    features: facilities.map((f) => geoCircleFeature(f.location.lng, f.location.lat, radiusKm)),
  };
}

function facilityDotsGeoJson(locations: Array<{ facility_id: string; name: string; lat: number; lng: number; score: number; has_contradictions: boolean }>): any {
  return {
    type: 'FeatureCollection',
    features: locations.map((f) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [f.lng, f.lat] },
      properties: { id: f.facility_id, name: f.name, score: f.score, flagged: f.has_contradictions ? 1 : 0 },
    })),
  };
}

function pinPrefixBucket(pinCode: string | null | undefined): string | null {
  const digit = pinCode?.trim().match(/^\d/)?.[0];
  return digit ? `PIN-${digit}xxxxx` : null;
}

function findFacilityRegionAggregate(
  aggregates: MapRegionAggregate[],
  capability: CapabilityType,
  audit: FacilityAudit | undefined,
  rankedFacility: RankedFacility | undefined,
): MapRegionAggregate | undefined {
  const bucket = pinPrefixBucket(audit?.location.pin_code ?? rankedFacility?.location.pin_code);
  if (!bucket) return undefined;

  return aggregates.find(
    (row) =>
      row.capability_type === capability &&
      (row.region_id === `AUTO-${bucket}` || row.region_name === bucket || row.state === bucket),
  );
}

function formatRegionContextName(regionAggregate: MapRegionAggregate): string {
  const bucket = regionAggregate.region_name.match(/^PIN-(\d)x{5}$/);
  if (!bucket) return regionAggregate.region_name;
  return `PIN prefix ${bucket[1]} region`;
}

function isSyntheticPinRegion(regionAggregate: MapRegionAggregate): boolean {
  return /^PIN-\dx{5}$/.test(regionAggregate.region_name);
}

function getMapStyle(
  desertRadius: DesertRadius,
  coverageFeatures: any,
  facilityLocationsGeoJson: any,
  showCoverageRadius: boolean,
) {
  const riskProp = `risk_tier_${desertRadius}km`;

  return {
    version: 8,
    sources: {
      osm: {
        type: 'raster',
        tiles: ['https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}@2x.png'],
        tileSize: 256,
        attribution: 'Carto',
      },
      'india-districts': {
        type: 'geojson',
        data: indiaDistrictsGeoJson,
        generateId: true,
      },
      'coverage-radius': {
        type: 'geojson',
        data: coverageFeatures,
      },
      'facility-dots': {
        type: 'geojson',
        data: facilityLocationsGeoJson,
        cluster: true,
        clusterMaxZoom: 10,
        clusterRadius: 40,
      },
    },
    layers: [
      {
        id: 'osm',
        type: 'raster',
        source: 'osm',
        paint: { 'raster-opacity': 0.25, 'raster-saturation': -1 },
      },
      {
        id: 'india-fill',
        type: 'fill',
        source: 'india-districts',
        paint: {
          'fill-color': [
            'case',
            ['boolean', ['feature-state', 'hover'], false],
            '#B7DFC9',
            ['match', ['get', riskProp],
              'critical', '#7E2F2C',
              'high', '#C56556',
              'moderate', '#E5B86F',
              'low', '#72B7A8',
              '#DDEBE5',
            ],
          ],
          'fill-opacity': [
            'case',
            ['boolean', ['feature-state', 'hover'], false],
            0.8,
            ['match', ['get', riskProp],
              'critical', 0.75,
              'high', 0.6,
              'moderate', 0.45,
              'low', 0.3,
              0.2,
            ],
          ],
        },
      },
      {
        id: 'india-lines',
        type: 'line',
        source: 'india-districts',
        paint: { 'line-color': '#176D6A', 'line-opacity': 0.18, 'line-width': 0.8 },
      },
      {
        id: 'coverage-radius-fill',
        type: 'fill',
        source: 'coverage-radius',
        layout: { visibility: showCoverageRadius ? 'visible' : 'none' },
        paint: {
          'fill-color': '#3D9D89',
          'fill-opacity': 0.08,
        },
      },
      {
        id: 'coverage-radius-line',
        type: 'line',
        source: 'coverage-radius',
        layout: { visibility: showCoverageRadius ? 'visible' : 'none' },
        paint: {
          'line-color': '#176D6A',
          'line-opacity': 0.45,
          'line-width': 1.4,
          'line-dasharray': [2, 1.2],
        },
      },
      {
        id: 'facility-clusters',
        type: 'circle',
        source: 'facility-dots',
        filter: ['has', 'point_count'],
        paint: {
          'circle-color': ['step', ['get', 'point_count'], '#72B7A8', 20, '#3D9D89', 100, '#176D6A'],
          'circle-radius': ['step', ['get', 'point_count'], 16, 20, 22, 100, 30],
          'circle-opacity': 0.85,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
        },
      },
      {
        id: 'facility-cluster-count',
        type: 'symbol',
        source: 'facility-dots',
        filter: ['has', 'point_count'],
        layout: {
          'text-field': ['get', 'point_count_abbreviated'],
          'text-font': ['Open Sans Bold'],
          'text-size': 12,
        },
        paint: {
          'text-color': '#ffffff',
        },
      },
      {
        id: 'facility-dots',
        type: 'circle',
        source: 'facility-dots',
        filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 2, 7, 4, 10, 7],
          'circle-color': [
            'case',
            ['==', ['get', 'flagged'], 1],
            '#C56556',
            '#3D9D89',
          ],
          'circle-opacity': 0.8,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1,
        },
      },
    ],
  } as any;
}

// ---------------------------------------------------------------------------
// Execution timeline — renders ExecutionStep[] from the live /query response
// ---------------------------------------------------------------------------

function stepStatusColor(status: ExecutionStep['status']) {
  if (status === 'ok') return { bg: 'bg-semantic-verified', text: 'text-semantic-verified' };
  if (status === 'fallback') return { bg: 'bg-semantic-flagged', text: 'text-semantic-flagged' };
  return { bg: 'bg-semantic-critical', text: 'text-semantic-critical' };
}

function AgentTimeline({ steps }: { steps: ExecutionStep[] }) {
  if (steps.length === 0) {
    return <p className="text-caption text-content-tertiary">No execution steps recorded.</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      {steps.map((step) => {
        const colors = stepStatusColor(step.status);
        const durationMs = new Date(step.finished_at).getTime() - new Date(step.started_at).getTime();
        return (
          <details key={step.name + step.started_at} className="group rounded-lg border border-border-subtle bg-white/70 open:bg-white">
            <summary className="flex cursor-pointer list-none items-start gap-3 p-3">
              <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${colors.bg}`} />
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-3">
                  <span className="font-mono text-caption text-content-primary">{step.name}</span>
                  <span className={`text-mono-s uppercase ${colors.text}`}>{step.status}</span>
                </span>
                {step.detail && (
                  <span className="mt-1 block text-caption text-content-secondary">{step.detail}</span>
                )}
              </span>
              <ChevronRight className="mt-0.5 h-4 w-4 text-content-tertiary transition-transform group-open:rotate-90" />
            </summary>
            <div className="border-t border-border-subtle px-3 pb-3 pt-2">
              <div className="grid grid-cols-2 gap-2 text-caption">
                <div>
                  <div className="text-content-tertiary">Started</div>
                  <div className="font-mono text-content-secondary">{new Date(step.started_at).toLocaleTimeString()}</div>
                </div>
                <div>
                  <div className="text-content-tertiary">Duration</div>
                  <div className="font-mono text-content-secondary">{durationMs}ms</div>
                </div>
              </div>
            </div>
          </details>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Facility detail modal — driven by useFacilityAudit (live API)
// ---------------------------------------------------------------------------

function FacilityModal({
  facilityId,
  audit,
  rankedFacility,
  capability,
  regionAggregate,
  onClose,
  onOpenFull,
}: {
  facilityId: string;
  audit: FacilityAudit;
  rankedFacility: RankedFacility | undefined;
  capability: CapabilityType;
  regionAggregate: MapRegionAggregate | undefined;
  onClose: () => void;
  onOpenFull: () => void;
}) {
  const [selectedCapability, setSelectedCapability] = React.useState<CapabilityType>(capability);

  const trustScoreEntries = Object.entries(audit.trust_scores) as [CapabilityType, ApiTrustScore][];
  const selectedTrust: ApiTrustScore | undefined = audit.trust_scores[selectedCapability] ?? trustScoreEntries[0]?.[1];
  const rank = rankedFacility?.rank ?? 0;
  const regionContextName = regionAggregate ? formatRegionContextName(regionAggregate) : '';
  const hasSyntheticRegionContext = regionAggregate ? isSyntheticPinRegion(regionAggregate) : false;

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-content-primary/35 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`${audit.name} facility detail`}
      onClick={onClose}
    >
      <div
        className="flex h-[min(920px,calc(100vh-32px))] w-[min(1440px,calc(100vw-32px))] overflow-hidden rounded-[28px] border border-border-subtle bg-surface-canvas shadow-elevation-4"
        onClick={(e) => e.stopPropagation()}
      >
        <aside className="flex w-[390px] shrink-0 flex-col border-r border-border-subtle bg-white/86">
          <div className="p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">
                  Facility detail
                </div>
                <h2 className="mt-2 text-heading-l text-content-primary">{audit.name}</h2>
                <div className="mt-3 flex flex-wrap items-center gap-3 text-caption text-content-secondary">
                  {rankedFacility && (
                    <>
                      <span className="flex items-center gap-1">
                        <MapPin className="h-3.5 w-3.5" /> {rankedFacility.distance_km.toFixed(1)}km
                      </span>
                      <span>Rank #{rank}</span>
                    </>
                  )}
                  {audit.location.pin_code && <span>PIN {audit.location.pin_code}</span>}
                </div>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="rounded-full border border-border-subtle bg-white p-2 text-content-tertiary transition-colors hover:text-content-primary"
                aria-label="Close facility detail"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-6">
              <div className="mb-3 text-caption font-semibold uppercase tracking-wider text-content-secondary">Trust scores by capability</div>
              <div className="flex flex-col gap-2">
                {trustScoreEntries.map(([capType, ts]) => {
                  const isSelected = selectedCapability === capType;
                  return (
                    <button
                      key={capType}
                      type="button"
                      onClick={() => setSelectedCapability(capType)}
                      className={`rounded-2xl border p-3 text-left transition-all ${
                        isSelected ? 'border-border-strong bg-surface-canvas shadow-elevation-1' : 'border-border-subtle bg-white/65 hover:border-border-default hover:bg-surface-canvas/70'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-body font-semibold text-content-primary">{getCapabilityLabel(capType)}</div>
                          <div className="mt-1 flex items-center gap-2 text-caption text-content-secondary">
                            {ts.claimed ? (
                              <span className="flex items-center gap-1 text-semantic-verified">
                                <CheckCircle2 className="h-3 w-3" /> Claimed
                              </span>
                            ) : (
                              <span className="text-content-tertiary">Not claimed</span>
                            )}
                            <span>{ts.evidence.length} evidence</span>
                            <span className={ts.contradictions.length > 0 ? 'text-semantic-critical' : 'text-content-secondary'}>
                              {ts.contradictions.length} flags
                            </span>
                          </div>
                        </div>
                        <TrustScore score={ts.score} confidenceInterval={ts.confidence_interval} showLabel={false} />
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {selectedTrust && (
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-2xl border border-border-subtle bg-surface-canvas p-4">
                  <div className="text-mono-s uppercase text-content-tertiary">Evidence</div>
                  <div className="mt-1 text-heading-m text-content-primary">{selectedTrust.evidence.length}</div>
                </div>
                <div className="rounded-2xl border border-border-subtle bg-surface-canvas p-4">
                  <div className="text-mono-s uppercase text-content-tertiary">Contradictions</div>
                  <div className={`mt-1 text-heading-m ${selectedTrust.contradictions.length > 0 ? 'text-semantic-critical' : 'text-semantic-verified'}`}>
                    {selectedTrust.contradictions.length}
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="mt-auto border-t border-border-subtle p-5">
            <Button
              type="button"
              variant="secondary"
              className="w-full gap-2"
              onClick={onOpenFull}
            >
              <ExternalLink className="h-4 w-4" />
              Open full audit
            </Button>
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto p-7">
          {regionAggregate ? (
            <section className="rounded-2xl border border-accent-primary/15 bg-accent-primary-subtle p-5 shadow-elevation-1">
              <div className="mb-3 flex items-center justify-between gap-4">
                <div>
                  <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">Region context</div>
                  <h3 className="mt-1 text-heading-l text-content-primary">{regionContextName}</h3>
                  {hasSyntheticRegionContext && (
                    <p className="mt-1 text-caption text-content-secondary">
                      Synthetic rollup matched from the facility PIN prefix.
                    </p>
                  )}
                </div>
                <span className="rounded-full bg-white/70 px-3 py-1 text-caption font-semibold text-accent-primary">
                  {regionAggregate.verified_facilities_count} verified · {regionAggregate.flagged_facilities_count} flagged
                </span>
              </div>
              {selectedTrust && (
                <p className="text-body-l text-content-primary">
                  {audit.name} has a Trust Score of {selectedTrust.score} for {getCapabilityLabel(selectedCapability).toLowerCase()}
                  {selectedTrust.contradictions.length > 0
                    ? ` with ${selectedTrust.contradictions.length} contradiction${selectedTrust.contradictions.length === 1 ? '' : 's'} that must be weighed before funding.`
                    : ' with no contradictions flagged.'}
                </p>
              )}
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <div className="rounded-xl bg-white/72 p-3">
                  <div className="text-mono-s uppercase text-content-tertiary">Population</div>
                  <p className="mt-1 text-caption text-content-primary">{formatNumber(regionAggregate.population)}</p>
                </div>
                <div className="rounded-xl bg-white/72 p-3">
                  <div className="text-mono-s uppercase text-content-tertiary">Gap population</div>
                  <p className="mt-1 text-caption text-content-primary">{formatNumber(regionAggregate.gap_population)}</p>
                </div>
                <div className="rounded-xl bg-white/72 p-3">
                  <div className="text-mono-s uppercase text-content-tertiary">Capability</div>
                  <p className="mt-1 text-caption text-content-primary">{getCapabilityLabel(regionAggregate.capability_type)}</p>
                </div>
              </div>
            </section>
          ) : (
            <section className="rounded-2xl border border-border-subtle bg-white p-5 shadow-elevation-1">
              <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">Facility detail</div>
              <p className="mt-2 text-body text-content-secondary">Select a region on the map to see context for this facility.</p>
            </section>
          )}

          {selectedTrust && (
            <section className="mt-5 rounded-2xl border border-border-subtle bg-white p-5 shadow-elevation-1">
              <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                  <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">Selected audit claim</div>
                  <h3 className="mt-1 text-heading-l text-content-primary">{getCapabilityLabel(selectedCapability)}</h3>
                </div>
                <TrustScore score={selectedTrust.score} confidenceInterval={selectedTrust.confidence_interval} />
              </div>
              <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">Scoring rationale</div>
              <p className="mt-2 text-body-l text-content-primary">{selectedTrust.reasoning}</p>
            </section>
          )}

          {selectedTrust && selectedTrust.contradictions.length > 0 && (
            <section className="mt-5">
              <div className="mb-3 flex items-center gap-2 text-caption font-semibold uppercase tracking-wider text-content-secondary">
                <ShieldAlert className="h-4 w-4 text-semantic-critical" /> Contradictions
              </div>
              <div className="grid gap-3">
                {selectedTrust.contradictions.map((c: Contradiction, i: number) => (
                  <div key={`${c.contradiction_type}-${i}`} className="rounded-2xl border border-semantic-critical/20 bg-semantic-critical-subtle p-4">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-white/70 px-2 py-0.5 text-mono-s font-semibold text-semantic-critical">{c.severity}</span>
                      <span className="font-mono text-caption text-content-primary">{c.contradiction_type}</span>
                    </div>
                    <p className="mt-2 text-body text-content-primary">{c.reasoning}</p>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-mono-s text-content-secondary">
                      <span>For: {c.evidence_for.length} source{c.evidence_for.length !== 1 ? 's' : ''}</span>
                      <span>Against: {c.evidence_against.length} source{c.evidence_against.length !== 1 ? 's' : ''}</span>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {selectedTrust && selectedTrust.evidence.length > 0 && (
            <section className="mt-5">
              <div className="mb-3 flex items-center gap-2 text-caption font-semibold uppercase tracking-wider text-content-secondary">
                <FileText className="h-4 w-4" /> Evidence trail
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {selectedTrust.evidence.map((ev: EvidenceRef, i: number) => (
                  <div key={`${ev.chunk_id}-${i}`} className="rounded-2xl border border-border-subtle bg-white p-4 shadow-elevation-1">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="rounded-full bg-surface-sunken px-2 py-0.5 text-mono-s uppercase text-content-tertiary">
                        {ev.source_type}
                      </span>
                    </div>
                    <p className="text-body text-content-primary">"{ev.snippet}"</p>
                    <p className="mt-3 text-caption text-content-secondary">
                      Source: {ev.source_doc_id} · Retrieved {new Date(ev.retrieved_at).toLocaleDateString()}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}
        </main>
      </div>
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export function Dashboard() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const mapRef = React.useRef<any>(null);
  const hoveredFeatureId = React.useRef<string | number | null>(null);

  const initialQuery = searchParams.get('q') || '';
  const [command, setCommand] = React.useState(initialQuery);
  const [regionSearch, setRegionSearch] = React.useState(searchParams.get('pin_code') || '');
  const [isAgentPanelOpen, setIsAgentPanelOpen] = React.useState(false);
  const [searchMode, setSearchMode] = React.useState<SearchMode>('semantic');
  const [capabilityDetails, setCapabilityDetails] = React.useState('');
  const [agentPanelView, setAgentPanelView] = React.useState<AgentPanelView>('facilities');
  const [selectedFacilityId, setSelectedFacilityId] = React.useState<string | null>(null);
  const [focusedFacilityId, setFocusedFacilityId] = React.useState<string | null>(null);
  const [desertRadius, setDesertRadius] = React.useState<DesertRadius>(60);
  const [isDesertPanelOpen, setIsDesertPanelOpen] = React.useState(false);
  const [showCoverageRadius, setShowCoverageRadius] = React.useState(false);
  const [selectedDistrictProps, setSelectedDistrictProps] = React.useState<Record<string, any> | null>(null);

  const capability: CapabilityType = (searchParams.get('capability') as CapabilityType) || 'SURGERY_GENERAL';
  const radiusKm = Number(searchParams.get('radius_km') || 50);
  const regionId = searchParams.get('region_id') || '';
  const pinCode = searchParams.get('pin_code') || '';

  const plannerQuery = usePlannerQuery();
  const summaryFetch = useSummary(capability);
  const aggregatesFetch = useMapAggregates(capability);
  const locationsFetch = useFacilityLocations();
  const facilityAuditFetch = useFacilityAudit(selectedFacilityId ?? undefined);

  const aggregates: MapRegionAggregate[] = aggregatesFetch.data ?? [];

  const queryResult = plannerQuery.data;
  const rankedFacilities: RankedFacility[] = queryResult?.ranked_facilities ?? [];
  const topFacilities = rankedFacilities.slice(0, 7);
  const selectedRankedFacility = selectedFacilityId
    ? rankedFacilities.find((f) => f.facility_id === selectedFacilityId)
    : undefined;
  const selectedFacilityRegionAggregate = React.useMemo(
    () => findFacilityRegionAggregate(aggregates, capability, facilityAuditFetch.data, selectedRankedFacility),
    [aggregates, capability, facilityAuditFetch.data, selectedRankedFacility],
  );

  const coverageFeatures = React.useMemo(
    () => buildCoverageFeatureCollection(topFacilities, radiusKm),
    [topFacilities, radiusKm],
  );
  const facilityLocationsGeoJson = React.useMemo(
    () => facilityDotsGeoJson(locationsFetch.data ?? []),
    [locationsFetch.data],
  );

  const summary = summaryFetch.data;
  const auditedCount = summary?.audited_count ?? null;
  const verifiedCount = summary?.verified_count ?? null;
  const flaggedCount = summary?.flagged_count ?? null;
  const isRunning = plannerQuery.status === 'loading';

  const focusMap = (nextRegionId: string) => {
    const map = mapRef.current?.getMap();
    if (!map) return;
    const bounds = getBounds(nextRegionId);
    if (bounds) {
      map.fitBounds(bounds, { padding: 60, duration: 800, maxZoom: 9 });
      return;
    }
    map.flyTo({ center: INDIA_CENTER, zoom: 5, duration: 800 });
  };

  const setRegionInUrl = (nextRegionId: string) => {
    const params = new URLSearchParams(searchParams);
    params.set('region_id', nextRegionId);
    setSearchParams(params);
    focusMap(nextRegionId);
  };

  React.useEffect(() => {
    if (regionId) focusMap(regionId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regionId]);

  const focusFacilityOnMap = (facility: RankedFacility) => {
    setSelectedDistrictProps(null);
    setIsAgentPanelOpen(true);
    setAgentPanelView('facilities');
    setFocusedFacilityId(facility.facility_id);
    mapRef.current?.getMap()?.flyTo({
      center: [facility.location.lng, facility.location.lat],
      zoom: 11,
      duration: 800,
    });
  };

  const applyCommand = (nextCommand: string) => {
    setCommand(nextCommand);
    setIsAgentPanelOpen(true);
    setAgentPanelView('trace');
    setFocusedFacilityId(null);
    const params = new URLSearchParams(searchParams);
    params.set('q', nextCommand);
    setSearchParams(params);
    plannerQuery.run(nextCommand).then((result) => {
      setAgentPanelView('facilities');
      const top = result?.ranked_facilities?.[0];
      if (top) focusFacilityOnMap(top);
    });
  };

  const composeCapabilityCommand = () => {
    const targetPin = regionSearch.trim() || pinCode;
    const detail = capabilityDetails.trim();
    return `Find facilities within ${radiusKm}km of PIN ${targetPin} that can perform ${getCapabilityLabel(capability)}${detail ? ` and ${detail}` : ''}.`;
  };

  const openFacilityDetail = (facilityId: string) => {
    const facility = rankedFacilities.find((f) => f.facility_id === facilityId);
    if (facility) focusFacilityOnMap(facility);
    setSelectedFacilityId(facilityId);
  };

  const selectPriorityRegion = (nextRegionId: string) => {
    const params = new URLSearchParams(searchParams);
    params.set('region_id', nextRegionId);
    setSearchParams(params);
    focusMap(nextRegionId);
  };

  const updateContext = (next: Partial<{ capability: CapabilityType; radiusKm: number; regionId: string; pinCode: string }>) => {
    const params = new URLSearchParams(searchParams);
    if (next.capability) params.set('capability', next.capability);
    if (next.radiusKm) params.set('radius_km', String(next.radiusKm));
    if (next.regionId) params.set('region_id', next.regionId);
    if (next.pinCode) params.set('pin_code', next.pinCode);
    setSearchParams(params);
    if (next.regionId) focusMap(next.regionId);
  };

  const onCommandSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    applyCommand(searchMode === 'semantic' ? command : composeCapabilityCommand());
  };

  const handleResetMap = () => {
    setRegionSearch('');
    setIsAgentPanelOpen(false);
    setSelectedDistrictProps(null);
    setFocusedFacilityId(null);
    setSearchParams({});
    plannerQuery.reset();
    mapRef.current?.getMap()?.flyTo({ center: INDIA_CENTER, zoom: 4, duration: 1000 });
  };

  const onMouseMove = (event: any) => {
    if (!event.features?.length) return;
    const feat = event.features[0];
    const featureId = feat.id;
    if (featureId == null) return;
    event.target.getCanvas().style.cursor = 'pointer';
    const map = event.target;
    const source = feat.source || 'india-districts';
    if (hoveredFeatureId.current !== null && hoveredFeatureId.current !== featureId) {
      map.setFeatureState({ source: 'india-districts', id: hoveredFeatureId.current }, { hover: false });
    }
    hoveredFeatureId.current = featureId;
    map.setFeatureState({ source, id: featureId }, { hover: true });
  };

  const onMouseLeave = (event: any) => {
    event.target.getCanvas().style.cursor = '';
    if (hoveredFeatureId.current !== null) {
      event.target.setFeatureState({ source: 'india-districts', id: hoveredFeatureId.current }, { hover: false });
      hoveredFeatureId.current = null;
    }
  };

  return (
    <div className="relative h-full w-full overflow-hidden bg-surface-canvas">
      <Map
        ref={mapRef}
        initialViewState={{
          longitude: INDIA_CENTER[0],
          latitude: INDIA_CENTER[1],
          zoom: 4,
        }}
        mapStyle={getMapStyle(desertRadius, coverageFeatures, facilityLocationsGeoJson, showCoverageRadius)}
        style={{ width: '100%', height: '100%' }}
        interactiveLayerIds={['india-fill', 'facility-dots', 'facility-clusters', 'facility-cluster-count']}
        onClick={(event: any) => {
          const features = event.features ?? [];
          const clusterFeature = features.find((f: any) => {
            const layerId = f?.layer?.id;
            return layerId === 'facility-clusters' || layerId === 'facility-cluster-count';
          });

          if (clusterFeature?.properties?.cluster_id != null) {
            const map = mapRef.current?.getMap();
            if (!map) return;
            const source: any = map.getSource('facility-dots');
            const clusterId = clusterFeature.properties.cluster_id;
            const coords = clusterFeature.geometry?.type === 'Point'
              ? (clusterFeature.geometry.coordinates as [number, number])
              : ([event.lngLat.lng, event.lngLat.lat] as [number, number]);
            Promise.resolve(source?.getClusterExpansionZoom?.(clusterId))
              .then((zoom: number | undefined) => {
                const target = Math.max((zoom ?? 8) + 1.5, 9);
                map.easeTo({ center: coords, zoom: target, duration: 600 });
              })
              .catch(() => {
                map.easeTo({ center: coords, zoom: 9, duration: 600 });
              });
            return;
          }

          const dotFeature = features.find((f: any) => f?.layer?.id === 'facility-dots');
          if (dotFeature?.properties?.id) {
            setSelectedFacilityId(dotFeature.properties.id);
            return;
          }

          // District click: show desert score info + zoom
          const districtFeature = features.find((f: any) => f?.layer?.id === 'india-fill');
          const props = districtFeature?.properties;
          if (props?.district || props?.state) {
            setSelectedDistrictProps(props);
            const [lng, lat] = [event.lngLat.lng, event.lngLat.lat];
            mapRef.current?.getMap()?.flyTo({ center: [lng, lat], zoom: 7, duration: 800 });
            return;
          }
        }}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
      >
        {topFacilities.map((facility, index) => (
          <Marker key={facility.facility_id} longitude={facility.location.lng} latitude={facility.location.lat} anchor="center">
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                openFacilityDetail(facility.facility_id);
              }}
              className={`pointer-events-auto relative flex h-9 w-9 items-center justify-center rounded-full border-2 text-caption font-semibold text-white shadow-elevation-3 transition-transform hover:scale-110 ${
                index === 0 ? 'bg-semantic-critical' : 'bg-accent-primary'
              } ${
                selectedFacilityId === facility.facility_id || focusedFacilityId === facility.facility_id
                  ? 'border-content-primary ring-4 ring-white/80'
                  : 'border-white'
              }`}
              aria-label={`Open ${facility.name}`}
            >
              {index + 1}
            </button>
          </Marker>
        ))}

      </Map>

      {/* District info popup — from enriched TopoJSON */}
      {selectedDistrictProps && (
        <div className="pointer-events-auto absolute left-1/2 top-[44%] z-40 w-[480px] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border-subtle bg-white/90 p-4 pr-10 shadow-elevation-4 backdrop-blur-xl">
          <button
            type="button"
            onClick={() => setSelectedDistrictProps(null)}
            className="absolute right-3 top-3 rounded-full border border-border-subtle bg-white/70 p-1.5 text-content-tertiary transition-colors hover:text-content-primary"
            aria-label="Close district info"
          >
            <X className="h-3.5 w-3.5" />
          </button>
          <div>
            <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">District health profile</div>
            <h2 className="mt-1 text-heading-m text-content-primary">{selectedDistrictProps.district}</h2>
            <p className="mt-1 text-caption text-content-secondary">{selectedDistrictProps.state}</p>
          </div>
          {(() => {
            const riskKey = `risk_tier_${desertRadius}km`;
            const desertKey = `desert_score_${desertRadius}km`;
            const verifiedKey = `verified_facility_count_${desertRadius}km`;
            const totalKey = `total_facility_count_${desertRadius}km`;
            const contradictionKey = `dominant_contradiction_type_${desertRadius}km`;
            const risk = selectedDistrictProps[riskKey] ?? 'unknown';
            const riskColor = RISK_TIER_COLORS[risk] ?? '#999';
            return (
              <>
                <div className="mt-3 grid grid-cols-4 gap-2">
                  <div className="rounded-xl bg-white/70 p-2.5">
                    <div className="text-mono-s uppercase text-content-tertiary">Risk tier</div>
                    <div className="mt-1 text-heading-s font-bold" style={{ color: riskColor }}>{risk}</div>
                  </div>
                  <div className="rounded-xl bg-white/70 p-2.5">
                    <div className="text-mono-s uppercase text-content-tertiary">Desert score</div>
                    <div className="mt-1 text-caption font-semibold text-content-primary">{typeof selectedDistrictProps[desertKey] === 'number' ? selectedDistrictProps[desertKey].toFixed(1) : '—'}</div>
                  </div>
                  <div className="rounded-xl bg-white/70 p-2.5">
                    <div className="text-mono-s uppercase text-content-tertiary">Verified</div>
                    <div className="mt-1 text-heading-s text-semantic-verified">{selectedDistrictProps[verifiedKey] ?? 0}</div>
                  </div>
                  <div className="rounded-xl bg-white/70 p-2.5">
                    <div className="text-mono-s uppercase text-content-tertiary">Total</div>
                    <div className="mt-1 text-heading-s text-content-primary">{selectedDistrictProps[totalKey] ?? 0}</div>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2">
                  <div className="rounded-xl bg-white/70 p-2.5">
                    <div className="text-mono-s uppercase text-content-tertiary">SBA %</div>
                    <div className="mt-1 text-caption font-semibold text-content-primary">{selectedDistrictProps.skilled_birth_attendance_pct != null ? `${Number(selectedDistrictProps.skilled_birth_attendance_pct).toFixed(1)}%` : '—'}</div>
                  </div>
                  <div className="rounded-xl bg-white/70 p-2.5">
                    <div className="text-mono-s uppercase text-content-tertiary">Inst. births %</div>
                    <div className="mt-1 text-caption font-semibold text-content-primary">{selectedDistrictProps.institutional_births_pct != null ? `${Number(selectedDistrictProps.institutional_births_pct).toFixed(1)}%` : '—'}</div>
                  </div>
                  <div className="rounded-xl bg-white/70 p-2.5">
                    <div className="text-mono-s uppercase text-content-tertiary">ANC 4+ %</div>
                    <div className="mt-1 text-caption font-semibold text-content-primary">{selectedDistrictProps.anc4_plus_pct != null ? `${Number(selectedDistrictProps.anc4_plus_pct).toFixed(1)}%` : '—'}</div>
                  </div>
                </div>
                {selectedDistrictProps[contradictionKey] && (
                  <div className="mt-2 inline-flex items-center gap-1.5 rounded bg-semantic-critical-subtle px-2 py-1 text-caption text-semantic-critical">
                    <ShieldAlert className="h-3.5 w-3.5" /> Dominant contradiction: {selectedDistrictProps[contradictionKey]}
                  </div>
                )}
                <div className="mt-2 flex items-center gap-2 text-mono-s text-content-tertiary">
                  <span>Need index: {selectedDistrictProps.need_index != null ? Number(selectedDistrictProps.need_index).toFixed(1) : '—'}</span>
                  <span>·</span>
                  <span>Source: {selectedDistrictProps.need_index_source ?? '—'}</span>
                  {selectedDistrictProps.nfhs_imputed && <span className="rounded bg-semantic-flagged-subtle px-1.5 py-0.5 text-semantic-flagged">imputed</span>}
                </div>
              </>
            );
          })()}
        </div>
      )}

      {/* Top stats bar */}
      <div className={`pointer-events-none absolute left-6 ${isAgentPanelOpen ? 'right-[500px]' : 'right-6'} top-5 z-20 flex flex-col gap-2 transition-all duration-300`}>
        <div className="pointer-events-auto flex flex-wrap items-center gap-2">
          <Card variant="glass" className="flex items-center gap-3 rounded-2xl bg-white/58 px-3 py-2 shadow-elevation-1">
            <div>
              <div className="text-body font-semibold text-content-primary">
                {auditedCount === null ? '—' : auditedCount.toLocaleString()}
              </div>
              <div className="text-mono-s uppercase text-content-secondary">Audited</div>
            </div>
            <div className="h-7 w-px bg-border-default" />
            <div>
              <div className="flex items-center gap-1.5 text-body font-semibold text-semantic-verified">
                {verifiedCount === null ? '—' : verifiedCount} <CheckCircle2 className="h-3.5 w-3.5" />
              </div>
              <div className="text-mono-s uppercase text-content-secondary">Verified</div>
            </div>
            <div className="h-7 w-px bg-border-default" />
            <div>
              <div className="flex items-center gap-1.5 text-body font-semibold text-semantic-critical">
                {flaggedCount === null ? '—' : flaggedCount} <AlertCircle className="h-3.5 w-3.5" />
              </div>
              <div className="text-mono-s uppercase text-content-secondary">Flagged</div>
            </div>
            <div className="h-7 w-px bg-border-default" />
            <div>
              <div className="text-body font-semibold text-content-primary">{new Date(queryResult?.generated_at ?? new Date().toISOString()).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</div>
              <div className="text-mono-s uppercase text-content-secondary">Generated</div>
            </div>
          </Card>
        </div>
      </div>

      {/* Desert score panel */}
      <div className="pointer-events-auto absolute left-6 top-24 z-20 flex max-h-[calc(100vh-190px)] w-[300px] flex-col gap-3 overflow-y-auto pr-1">
        <Card variant="glass-control" className="pointer-events-auto rounded-2xl p-2.5">
          <button
            type="button"
            onClick={() => setIsDesertPanelOpen((o) => !o)}
            aria-expanded={isDesertPanelOpen}
            className="flex w-full items-center justify-between gap-3 rounded-xl px-1.5 py-1 text-left transition-colors hover:bg-white/40"
          >
            <span>
              <span className="block text-caption font-semibold uppercase tracking-wider text-content-secondary">Healthcare desert</span>
              <span className="mt-0.5 block text-heading-s text-content-primary">{desertRadius}km radius</span>
            </span>
            <ChevronRight className={`h-4 w-4 text-content-tertiary transition-transform ${isDesertPanelOpen ? 'rotate-90' : ''}`} />
          </button>

          {isDesertPanelOpen && (
            <div className="mt-3 border-t border-border-subtle pt-3">
              <div className="mb-3 text-mono-s uppercase text-content-tertiary">Coverage radius</div>
              <div className="flex rounded-xl bg-surface-sunken p-1">
                {DESERT_RADIUS_OPTIONS.map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => setDesertRadius(r)}
                    className={`flex-1 rounded-lg px-2 py-1.5 text-center text-caption font-semibold transition-colors ${
                      desertRadius === r ? 'bg-white text-content-primary shadow-elevation-1' : 'text-content-secondary hover:text-content-primary'
                    }`}
                  >
                    {r}km
                  </button>
                ))}
              </div>
              <div className="mt-3">
                <div className="mb-2 text-mono-s uppercase text-content-tertiary">Risk tiers</div>
                <div className="flex flex-col gap-1">
                  {(['critical', 'high', 'moderate', 'low'] as const).map((tier) => (
                    <div key={tier} className="flex items-center gap-2">
                      <span className="h-3 w-3 rounded-sm" style={{ backgroundColor: RISK_TIER_COLORS[tier], opacity: RISK_TIER_OPACITY[tier] }} />
                      <span className="text-caption capitalize text-content-secondary">{tier}</span>
                    </div>
                  ))}
                </div>
              </div>
              <button
                type="button"
                aria-pressed={showCoverageRadius}
                onClick={() => setShowCoverageRadius((v) => !v)}
                className="mt-3 flex w-full items-center justify-between gap-3 rounded-xl border border-border-subtle bg-white/62 px-3 py-2 text-left transition-colors hover:border-accent-primary-soft hover:bg-white"
              >
                <span>
                  <span className="block text-caption font-semibold text-content-primary">Facility coverage</span>
                  <span className="block text-mono-s text-content-tertiary">show candidate reach circles</span>
                </span>
                <span className={`h-5 w-9 rounded-full p-0.5 transition-colors ${showCoverageRadius ? 'bg-accent-primary' : 'bg-content-tertiary/25'}`}>
                  <span className={`block h-4 w-4 rounded-full bg-white shadow-elevation-1 transition-transform ${showCoverageRadius ? 'translate-x-4' : ''}`} />
                </span>
              </button>
              <p className="mt-3 text-mono-s text-content-tertiary">
                NFHS-5 data · {indiaDistrictsGeoJson.features.length} districts · proxy NeedIndex
              </p>
            </div>
          )}
        </Card>
      </div>

      {/* Command bar */}
      <div
        className="absolute bottom-12 z-20 -translate-x-1/2 transition-all duration-300"
        style={{
          left: isAgentPanelOpen ? 'calc((100% - 500px) / 2)' : '50%',
          width: isAgentPanelOpen ? 'min(720px, calc(100% - 540px))' : 'min(760px, calc(100% - 48px))',
        }}
      >
        <form onSubmit={onCommandSubmit} className="pointer-events-auto">
          <div className="glass-control flex flex-col gap-2 rounded-2xl p-2">
            <div className="flex items-center gap-2 rounded-xl bg-white/50 px-2.5 py-1.5">
              <div className="flex shrink-0 rounded-full border border-border-subtle bg-surface-sunken p-0.5">
                {([
                  ['semantic', Command, 'Semantic'],
                  ['capability', Target, 'Capability'],
                ] as Array<[SearchMode, typeof Command, string]>).map(([mode, Icon, label]) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setSearchMode(mode)}
                    className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-mono-s font-semibold transition-colors ${
                      searchMode === mode ? 'bg-accent-primary text-white shadow-elevation-1' : 'text-content-secondary hover:text-content-primary'
                    }`}
                  >
                    <Icon className="h-3 w-3" />
                    {searchMode === mode && <span>{label}</span>}
                  </button>
                ))}
              </div>
              <input
                type="text"
                value={searchMode === 'semantic' ? command : capabilityDetails}
                onChange={(event) => (searchMode === 'semantic' ? setCommand(event.target.value) : setCapabilityDetails(event.target.value))}
                placeholder={searchMode === 'semantic' ? CHALLENGE_QUERY : 'Optional details, e.g. part-time doctors or night coverage'}
                className="min-w-0 flex-1 border-none bg-transparent text-body text-content-primary outline-none placeholder:text-content-tertiary"
              />
              <Button type="submit" variant="primary" size="sm" className="h-8 gap-1.5 px-3 !text-white hover:!text-white disabled:!text-white" disabled={isRunning}>
                {searchMode === 'semantic' ? <Play className="h-3.5 w-3.5" /> : <Search className="h-3.5 w-3.5" />}
                {isRunning ? (searchMode === 'semantic' ? 'Running' : 'Searching') : searchMode === 'semantic' ? 'Run Agent' : 'Search'}
              </Button>
            </div>

            {searchMode === 'capability' && (
              <div className="rounded-2xl border border-border-subtle bg-white/58 p-2">
                <div className="grid grid-cols-3 gap-2">
                  <label className="rounded-xl bg-white/75 px-3 py-2">
                    <span className="text-mono-s uppercase text-content-secondary">Capability</span>
                    <select
                      value={capability}
                      onChange={(event) => updateContext({ capability: event.target.value as CapabilityType })}
                      className="mt-1 w-full bg-transparent text-body font-semibold text-content-primary focus:outline-none"
                    >
                      {CAPABILITIES.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <div className="rounded-xl bg-white/75 px-3 py-2">
                    <span className="text-mono-s uppercase text-content-secondary">Radius</span>
                    <div className="mt-1 flex rounded-md bg-surface-sunken p-0.5">
                      {RADIUS_OPTIONS.map((option) => (
                        <button
                          key={option}
                          type="button"
                          onClick={() => updateContext({ radiusKm: option })}
                          className={`flex-1 rounded px-2 py-1 text-mono-s transition-colors ${
                            radiusKm === option ? 'bg-white text-content-primary shadow-elevation-1' : 'text-content-secondary hover:text-content-primary'
                          }`}
                        >
                          {option}
                        </button>
                      ))}
                    </div>
                  </div>

                  <label className="relative rounded-xl bg-white/75 px-3 py-2">
                    <span className="text-mono-s uppercase text-content-secondary">PIN / postal code</span>
                    <Input
                      value={regionSearch}
                      onChange={(event) => setRegionSearch(event.target.value)}
                      placeholder={pinCode || '800001'}
                      className="mt-1 h-7 border-0 bg-transparent p-0 pr-6 text-body font-semibold shadow-none"
                    />
                    <Search className="absolute bottom-3 right-3 h-3.5 w-3.5 text-content-tertiary" />
                  </label>
                </div>
              </div>
            )}
          </div>
        </form>
      </div>

      {/* Reset map */}
      <button
        type="button"
        onClick={handleResetMap}
        className="absolute bottom-12 left-6 z-20 flex h-10 items-center gap-1.5 rounded-full border border-border-subtle bg-white/70 px-3 text-caption text-content-secondary shadow-elevation-1 backdrop-blur-xl transition-colors hover:text-content-primary"
      >
        <RotateCcw className="h-3.5 w-3.5" />
        Reset map
      </button>

      {/* Breadcrumbs */}
      <div className="pointer-events-none absolute inset-x-0 bottom-2 z-10 flex justify-center">
        <Breadcrumbs
          regionId={regionId}
          onSelect={setRegionInUrl}
          className="pointer-events-auto border-white/50 bg-white/45 px-2 py-0.5 opacity-80 shadow-none"
        />
      </div>

      {/* Agent panel toggle */}
      {!isAgentPanelOpen && (
        <button
          type="button"
          onClick={() => setIsAgentPanelOpen(true)}
          className="absolute right-6 top-5 z-30 flex items-center gap-2 rounded-full border border-border-subtle bg-white/82 px-3 py-2 text-left shadow-elevation-2 backdrop-blur-xl transition-transform hover:-translate-x-0.5"
          aria-label="Expand agent run panel"
        >
          <span className={`h-2.5 w-2.5 rounded-full ${isRunning ? 'bg-semantic-flagged animate-pulse' : queryResult ? 'bg-semantic-verified' : 'bg-content-tertiary'}`} />
          <span className="text-caption font-semibold text-content-primary">Agent</span>
          <span className="text-caption text-content-secondary">{isRunning ? 'Running' : queryResult ? 'Complete' : 'Idle'}</span>
          <ChevronRight className="h-3.5 w-3.5 rotate-180 text-content-tertiary" />
        </button>
      )}

      {/* Agent panel */}
      {isAgentPanelOpen && (
      <aside className="absolute bottom-10 right-6 top-5 z-30 w-[460px]">
        <div className="glass-elevated flex h-full flex-col overflow-hidden rounded-2xl">
          <div className="border-b border-border-subtle bg-white/45 p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">Agent Run</div>
                <h1 className="mt-1 text-heading-l text-content-primary">
                  {isRunning ? 'Searching facilities' : queryResult ? 'Query complete' : 'Ready'}
                </h1>
              </div>
              <div className="flex items-center gap-2">
                <div className={`rounded-full px-3 py-1 text-caption font-semibold ${
                  isRunning
                    ? 'bg-semantic-flagged-subtle text-semantic-flagged'
                    : queryResult
                      ? 'bg-semantic-verified-subtle text-semantic-verified'
                      : 'bg-surface-sunken text-content-tertiary'
                }`}>
                  {isRunning ? 'Running tools' : queryResult ? 'Run complete' : 'Idle'}
                </div>
                <button
                  type="button"
                  onClick={() => setIsAgentPanelOpen(false)}
                  className="rounded-full border border-border-subtle bg-white/70 p-1.5 text-content-tertiary transition-colors hover:text-content-primary"
                  aria-label="Collapse agent run panel"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="mt-3 rounded-xl border border-border-subtle bg-white/62 p-3">
              <div className="text-mono-s uppercase text-content-tertiary">Current request</div>
              <p className="mt-1 line-clamp-2 text-body text-content-secondary">{queryResult?.query ?? (command || 'Enter a query below to run the agent')}</p>
            </div>
            {queryResult && (
              <div className="mt-4 grid grid-cols-3 gap-3">
                <div className="rounded-lg bg-white/65 p-3">
                  <div className="text-caption text-content-tertiary">Candidates</div>
                  <div className="mt-1 text-heading-s text-content-primary">{queryResult.total_candidates}</div>
                </div>
                <div className="rounded-lg bg-white/65 p-3">
                  <div className="text-caption text-content-tertiary">Retriever</div>
                  <div className="mt-1 text-caption font-semibold text-accent-primary">{queryResult.retriever_mode.replace('_', ' ')}</div>
                </div>
                <div className="rounded-lg bg-white/65 p-3">
                  <div className="text-caption text-content-tertiary">LLM used</div>
                  <div className="mt-1 text-caption font-semibold text-content-primary">{queryResult.used_llm ? 'Yes' : 'No'}</div>
                </div>
              </div>
            )}
            <div className="mt-4 flex flex-wrap gap-2 text-caption">
              <button
                type="button"
                onClick={() => applyCommand(CHALLENGE_QUERY)}
                className="rounded-full border border-border-default bg-white/70 px-3 py-1 text-content-primary transition-colors hover:border-accent-primary-soft"
              >
                Challenge query
              </button>
              {queryResult && (
                <button
                  type="button"
                  onClick={() => navigate(`/planner-query?q=${encodeURIComponent(queryResult.query)}`)}
                  className="rounded-full border border-border-default bg-white/70 px-3 py-1 text-content-primary transition-colors hover:border-accent-primary-soft"
                >
                  Open report mode
                </button>
              )}
              {rankedFacilities[0] && (
                <button
                  type="button"
                  onClick={() => openFacilityDetail(rankedFacilities[0].facility_id)}
                  className="rounded-full border border-border-default bg-white/70 px-3 py-1 text-content-primary transition-colors hover:border-accent-primary-soft"
                >
                  Inspect top facility
                </button>
              )}
            </div>
            <div className="mt-4 grid grid-cols-2 rounded-xl bg-surface-sunken p-1">
              {([
                ['facilities', 'Ranked facilities'],
                ['trace', 'Execution trace'],
              ] as Array<[AgentPanelView, string]>).map(([view, label]) => (
                <button
                  key={view}
                  type="button"
                  onClick={() => setAgentPanelView(view)}
                  className={`rounded-lg px-3 py-2 text-caption font-semibold transition-colors ${
                    agentPanelView === view ? 'bg-white text-content-primary shadow-elevation-1' : 'text-content-secondary hover:text-content-primary'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-auto p-5">
            {agentPanelView === 'trace' ? (
              <>
                <div className="mb-4 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-caption font-semibold uppercase tracking-wider text-content-secondary">
                    <Clock3 className="h-4 w-4" /> Execution Timeline
                  </div>
                  <span className="text-mono-s text-content-tertiary">{queryResult?.query_trace_id ?? '—'}</span>
                </div>
                {isRunning ? (
                  <div className="flex items-center gap-2 text-caption text-content-secondary">
                    <Loader2 className="h-4 w-4 animate-spin" /> Running query agent...
                  </div>
                ) : queryResult ? (
                  <AgentTimeline steps={queryResult.execution_steps} />
                ) : (
                  <p className="text-caption text-content-tertiary">Run a query to see execution steps.</p>
                )}
              </>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-caption font-semibold uppercase tracking-wider text-content-secondary">
                    <Target className="h-4 w-4" /> Ranked facilities
                  </div>
                  <span className="text-caption text-content-tertiary">{queryResult?.total_candidates ?? 0} candidates</span>
                </div>

                {rankedFacilities.length === 0 && !isRunning && (
                  <p className="mt-4 text-caption text-content-tertiary">Run a query to see ranked facility results.</p>
                )}
                {isRunning && (
                  <div className="mt-4 flex items-center gap-2 text-caption text-content-secondary">
                    <Loader2 className="h-4 w-4 animate-spin" /> Ranking facilities...
                  </div>
                )}

                <div className="mt-3 flex flex-col gap-2">
                  {rankedFacilities.slice(0, 7).map((facility) => {
                    const ts = facility.trust_score;
                    return (
                      <button
                        key={facility.facility_id}
                        type="button"
                        onClick={() => openFacilityDetail(facility.facility_id)}
                        className={`group rounded-lg border bg-white/75 p-3 text-left transition-all hover:border-accent-primary-soft hover:bg-white ${
                          selectedFacilityId === facility.facility_id ? 'border-accent-primary-soft shadow-elevation-1' : 'border-border-subtle'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="rounded bg-surface-sunken px-1.5 py-0.5 font-mono text-caption text-content-secondary">#{facility.rank}</span>
                              <span className="text-body font-medium text-content-primary group-hover:text-accent-primary">{facility.name}</span>
                            </div>
                            <div className="mt-2 flex flex-wrap items-center gap-3 text-caption text-content-secondary">
                              <span className="flex items-center gap-1">
                                <MapPin className="h-3.5 w-3.5" /> {facility.distance_km.toFixed(1)}km
                              </span>
                              <span className="flex items-center gap-1">
                                <FileText className="h-3.5 w-3.5" /> {facility.evidence_count} evidence
                              </span>
                            </div>
                          </div>
                          <TrustScore score={ts.score} confidenceInterval={ts.confidence_interval} showLabel={false} />
                        </div>
                        {facility.contradictions_flagged > 0 && (
                          <div className="mt-2 inline-flex items-center gap-1.5 rounded bg-semantic-critical-subtle px-2 py-1 text-caption text-semantic-critical">
                            <ShieldAlert className="h-3.5 w-3.5" /> {facility.contradictions_flagged} contradiction{facility.contradictions_flagged === 1 ? '' : 's'}
                          </div>
                        )}
                        <div className="mt-3 text-caption">
                          <span className="font-semibold text-content-primary">Rationale: </span>
                          <span className="text-content-secondary">{ts.reasoning}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </div>
      </aside>
      )}

      {/* Facility detail modal — from live API */}
      {selectedFacilityId && facilityAuditFetch.status === 'loading' && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-content-primary/35 backdrop-blur-sm">
          <div className="flex items-center gap-3 rounded-2xl bg-white p-6 shadow-elevation-4">
            <Loader2 className="h-5 w-5 animate-spin text-accent-primary" />
            <span className="text-body text-content-primary">Loading facility audit...</span>
          </div>
        </div>,
        document.body,
      )}

      {selectedFacilityId && facilityAuditFetch.data && (
        <FacilityModal
          facilityId={selectedFacilityId}
          audit={facilityAuditFetch.data}
          rankedFacility={selectedRankedFacility}
          capability={capability}
          regionAggregate={selectedFacilityRegionAggregate}
          onClose={() => setSelectedFacilityId(null)}
          onOpenFull={() => {
            const audit = facilityAuditFetch.data!;
            navigate(`/facilities/${audit.facility_id}?from=map-workbench&q=${encodeURIComponent(command)}`);
          }}
        />
      )}

      {selectedFacilityId && facilityAuditFetch.status === 'error' && createPortal(
        <div
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-content-primary/35 backdrop-blur-sm"
          onClick={() => setSelectedFacilityId(null)}
        >
          <div className="rounded-2xl bg-white p-6 shadow-elevation-4" onClick={(e) => e.stopPropagation()}>
            <p className="text-body text-semantic-critical">Failed to load facility audit.</p>
            <p className="mt-2 text-caption text-content-secondary">{facilityAuditFetch.error?.detail}</p>
            <div className="mt-4 flex gap-2">
              <Button variant="secondary" size="sm" onClick={() => facilityAuditFetch.refetch()}>Retry</Button>
              <Button variant="secondary" size="sm" onClick={() => setSelectedFacilityId(null)}>Close</Button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
