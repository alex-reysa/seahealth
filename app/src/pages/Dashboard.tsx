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
import { MapLegend } from '@/src/components/domain/MapLegend';
import { TrustScore } from '@/src/components/domain/TrustScore';
import { Button } from '@/src/components/ui/Button';
import { Card } from '@/src/components/ui/Card';
import { Input } from '@/src/components/ui/Input';
import indiaDistrictsTopoRaw from '@/src/data/indiaDistricts.topojson?raw';
import mockIndiaRegionsTopologyRaw from '@/src/data/mockIndiaRegions.topojson?raw';
import { useFacilityAudit } from '@/src/hooks/useFacilityAudit';
import { useFacilityLocations } from '@/src/hooks/useFacilityLocations';
import { useMapAggregates } from '@/src/hooks/useMapAggregates';
import { usePlannerQuery } from '@/src/hooks/usePlannerQuery';
import { useSummary } from '@/src/hooks/useSummary';
import { CAPABILITIES, CHALLENGE_QUERY, formatNumber, getCapabilityLabel } from '@/src/lib/capabilities';
import { decorateFeaturesWithJoin, joinAggregatesToFeatures } from '@/src/lib/mapJoin';
import { getBounds } from '@/src/lib/regionTree';
import type {
  CapabilityType,
  Contradiction,
  EvidenceRef,
  ExecutionStep,
  FacilityAudit,
  MapRegionAggregate,
  PopulationSource,
  RankedFacility,
  TrustScore as ApiTrustScore,
} from '@/src/types/api';

const INDIA_CENTER = [78.9629, 20.5937] as [number, number];
const PATNA_CENTER = [85.14, 25.61] as [number, number];
const MADHUBANI_CENTER = [86.07, 26.36] as [number, number];
const RADIUS_OPTIONS = [30, 50, 60, 120];
type SearchMode = 'semantic' | 'capability';
type AgentPanelView = 'facilities' | 'trace';
type MapOverlayMode = 'priority_score' | 'need_signal' | 'verified_access' | 'contradiction_risk';
type PlanningLayerId = 'verified_access_gap' | 'need_signal' | 'contradiction_risk' | 'facility_coverage_radius';
type PlanningLayerVisibility = Record<PlanningLayerId, boolean>;

const DEFAULT_PLANNING_LAYER_VISIBILITY: PlanningLayerVisibility = {
  verified_access_gap: true,
  need_signal: true,
  contradiction_risk: true,
  facility_coverage_radius: false,
};

const NEUTRAL_LENS_FILL = '#DDEBE5';

type LensRamp = ReadonlyArray<readonly [number, string]>;

const LENS_CONFIG: Record<MapOverlayMode, {
  label: string;
  legend: string;
  propertyName: string;
  layerId: PlanningLayerId | null;
  ramp: LensRamp;
}> = {
  priority_score: {
    label: 'Priority score',
    legend: 'committee priority',
    propertyName: 'priorityScore',
    layerId: null,
    ramp: [[0, '#E4F3EC'], [0.55, '#B7DFC9'], [0.75, '#72B7A8'], [1, '#2F7F72']],
  },
  need_signal: {
    label: 'Need signal',
    legend: 'newborn burden',
    propertyName: 'needSignal',
    layerId: 'need_signal',
    ramp: [[0, '#F5EFE5'], [0.55, '#F1C7A6'], [0.78, '#D88975'], [1, '#A4473E']],
  },
  verified_access: {
    label: 'Verified access',
    legend: 'audited supply',
    propertyName: 'verifiedAccessScore',
    layerId: 'verified_access_gap',
    ramp: [[0, '#A4473E'], [0.35, '#F1C7A6'], [0.72, '#72B7A8'], [1, '#176D6A']],
  },
  contradiction_risk: {
    label: 'Contradiction risk',
    legend: 'claim reliability',
    propertyName: 'contradictionRisk',
    layerId: 'contradiction_risk',
    ramp: [[0, '#E4F3EC'], [0.5, '#E5B86F'], [0.8, '#C56556'], [1, '#7E2F2C']],
  },
};

const OVERLAY_MODE_OPTIONS: Array<{ id: MapOverlayMode; label: string; legend: string }> =
  (Object.entries(LENS_CONFIG) as Array<[MapOverlayMode, (typeof LENS_CONFIG)[MapOverlayMode]]>).map(([id, cfg]) => ({
    id,
    label: cfg.label,
    legend: cfg.legend,
  }));

const PLANNING_LAYER_OPTIONS: Array<{ id: PlanningLayerId; label: string; detail: string }> = [
  { id: 'verified_access_gap', label: 'Verified access gap', detail: 'low audited supply' },
  { id: 'need_signal', label: 'Need signal', detail: 'population burden' },
  { id: 'contradiction_risk', label: 'Contradiction risk', detail: 'unreliable claims' },
  { id: 'facility_coverage_radius', label: 'Facility coverage radius', detail: 'candidate reach' },
];

function isOverlayModeVisible(overlayMode: MapOverlayMode, visibleLayers: PlanningLayerVisibility) {
  const layerId = LENS_CONFIG[overlayMode].layerId;
  return layerId ? visibleLayers[layerId] : true;
}

const indiaDistrictsTopo = JSON.parse(indiaDistrictsTopoRaw);
const indiaDistrictsGeoJson = feature(indiaDistrictsTopo, indiaDistrictsTopo.objects.Districts) as any;
const mockIndiaRegionsTopology = JSON.parse(mockIndiaRegionsTopologyRaw);
const mockIndiaRegionsGeoJson = feature(mockIndiaRegionsTopology, mockIndiaRegionsTopology.objects.regions) as any;
const TOPOLOGY_FEATURE_IDS: readonly string[] = mockIndiaRegionsGeoJson.features.map(
  (regionFeature: any) => regionFeature.properties.regionId as string,
);
const regionCentroidsById = new globalThis.Map<string, [number, number]>(
  mockIndiaRegionsGeoJson.features.map((regionFeature: any) => [
    regionFeature.properties.regionId as string,
    regionFeature.properties.centroid as [number, number],
  ]),
);

const FLAGGED_LEGEND_STOPS = [
  { threshold: 0, color: '#E4F3EC', label: '0 flagged' },
  { threshold: 1, color: '#B7DFC9', label: '1–9' },
  { threshold: 10, color: '#72B7A8', label: '10–49' },
  { threshold: 50, color: '#2F7F72', label: '≥ 50' },
];

function getOverlayFillColor(overlayMode: MapOverlayMode, visibleLayers: PlanningLayerVisibility): any {
  if (!isOverlayModeVisible(overlayMode, visibleLayers)) {
    return NEUTRAL_LENS_FILL;
  }
  const cfg = LENS_CONFIG[overlayMode];
  const stops: any[] = [];
  cfg.ramp.forEach(([stop, color]) => {
    stops.push(stop, color);
  });
  return ['interpolate', ['linear'], ['get', cfg.propertyName], ...stops];
}

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

function getMapStyle(
  regionId: string,
  overlayMode: MapOverlayMode,
  visibleLayers: PlanningLayerVisibility,
  coverageFeatures: any,
  fundingRegionsGeoJson: any,
  facilityLocationsGeoJson: any,
) {
  const overlayVisible = isOverlayModeVisible(overlayMode, visibleLayers);
  const hasBiharRegion = regionId.startsWith('BR_');
  const fundingFillOpacity = !hasBiharRegion
    ? 0.12
    : overlayVisible
      ? ['case', ['==', ['get', 'regionId'], regionId], 0.7, 0.5]
      : ['case', ['==', ['get', 'regionId'], regionId], 0.34, 0.16];

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
      'funding-regions': {
        type: 'geojson',
        data: fundingRegionsGeoJson,
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
            '#DDEBE5',
          ],
          'fill-opacity': [
            'case',
            ['boolean', ['feature-state', 'hover'], false],
            0.7,
            0.42,
          ],
        },
      },
      {
        id: 'india-lines',
        type: 'line',
        source: 'india-districts',
        paint: { 'line-color': '#176D6A', 'line-opacity': 0.16, 'line-width': 0.8 },
      },
      {
        id: 'funding-fill',
        type: 'fill',
        source: 'funding-regions',
        paint: {
          'fill-color': [
            'case',
            ['boolean', ['feature-state', 'hover'], false],
            '#105B58',
            ['==', ['get', 'regionId'], regionId],
            '#3D9D89',
            getOverlayFillColor(overlayMode, visibleLayers),
          ],
          'fill-opacity': fundingFillOpacity,
        },
      },
      {
        id: 'funding-lines',
        type: 'line',
        source: 'funding-regions',
        layout: { visibility: visibleLayers.verified_access_gap ? 'visible' : 'none' },
        paint: { 'line-color': '#176D6A', 'line-opacity': 0.34, 'line-width': 1.2 },
      },
      {
        id: 'funding-need-lines',
        type: 'line',
        source: 'funding-regions',
        layout: { visibility: visibleLayers.need_signal ? 'visible' : 'none' },
        paint: {
          'line-color': '#D88975',
          'line-opacity': 0.42,
          'line-width': ['interpolate', ['linear'], ['get', 'needSignal'], 0, 0.4, 1, 2.4],
        },
      },
      {
        id: 'funding-risk-lines',
        type: 'line',
        source: 'funding-regions',
        layout: { visibility: visibleLayers.contradiction_risk ? 'visible' : 'none' },
        paint: {
          'line-color': '#A4473E',
          'line-opacity': 0.32,
          'line-width': ['interpolate', ['linear'], ['get', 'contradictionRisk'], 0, 0.4, 1, 2.8],
          'line-dasharray': [2, 1.4],
        },
      },
      {
        id: 'coverage-radius-fill',
        type: 'fill',
        source: 'coverage-radius',
        layout: { visibility: visibleLayers.facility_coverage_radius ? 'visible' : 'none' },
        paint: {
          'fill-color': '#3D9D89',
          'fill-opacity': 0.08,
        },
      },
      {
        id: 'coverage-radius-line',
        type: 'line',
        source: 'coverage-radius',
        layout: { visibility: visibleLayers.facility_coverage_radius ? 'visible' : 'none' },
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
                  <h3 className="mt-1 text-heading-l text-content-primary">{regionAggregate.region_name}</h3>
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
  const [overlayMode, setOverlayMode] = React.useState<MapOverlayMode>('priority_score');
  const [isPlanningLayersOpen, setIsPlanningLayersOpen] = React.useState(false);
  const [isPriorityZoneOpen, setIsPriorityZoneOpen] = React.useState(false);
  const [visibleLayers, setVisibleLayers] = React.useState<PlanningLayerVisibility>(DEFAULT_PLANNING_LAYER_VISIBILITY);

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
  const join = React.useMemo(
    () => joinAggregatesToFeatures(aggregates, TOPOLOGY_FEATURE_IDS),
    [aggregates],
  );

  const fundingRegionsGeoJson = React.useMemo(() => {
    return {
      ...mockIndiaRegionsGeoJson,
      features: decorateFeaturesWithJoin(mockIndiaRegionsGeoJson.features, join),
    };
  }, [join]);

  const selectedAggregate: MapRegionAggregate | undefined =
    join.byFeatureId.get(regionId)?.aggregate ?? aggregates[0];
  const populationSource: PopulationSource | null = selectedAggregate?.population_source ?? null;

  const queryResult = plannerQuery.data;
  const rankedFacilities: RankedFacility[] = queryResult?.ranked_facilities ?? [];
  const topFacilities = rankedFacilities.slice(0, 7);
  const selectedRankedFacility = selectedFacilityId
    ? rankedFacilities.find((f) => f.facility_id === selectedFacilityId)
    : undefined;

  const coverageFeatures = React.useMemo(
    () => buildCoverageFeatureCollection(topFacilities, radiusKm),
    [topFacilities, radiusKm],
  );
  const facilityLocationsGeoJson = React.useMemo(
    () => facilityDotsGeoJson(locationsFetch.data ?? []),
    [locationsFetch.data],
  );

  const selectedRegionCentroid = regionId ? regionCentroidsById.get(regionId) : undefined;

  const summary = summaryFetch.data;
  const auditedCount = summary?.audited_count ?? null;
  const verifiedCount = summary?.verified_count ?? null;
  const flaggedCount = summary?.flagged_count ?? null;
  const isRunning = plannerQuery.status === 'loading';

  const activeOverlayOption = OVERLAY_MODE_OPTIONS.find((option) => option.id === overlayMode) ?? OVERLAY_MODE_OPTIONS[0];

  const focusMap = (nextRegionId: string) => {
    const map = mapRef.current?.getMap();
    if (!map) return;
    const bounds = getBounds(nextRegionId);
    if (bounds) {
      map.fitBounds(bounds, { padding: 60, duration: 800, maxZoom: 9 });
      return;
    }
    map.flyTo({
      center: nextRegionId === 'BR_MADHUBANI' ? MADHUBANI_CENTER : PATNA_CENTER,
      zoom: nextRegionId === 'BR_MADHUBANI' ? 8 : 7,
      duration: 800,
    });
  };

  const setRegionInUrl = (nextRegionId: string) => {
    const params = new URLSearchParams(searchParams);
    params.set('region_id', nextRegionId);
    setSearchParams(params);
    setIsPriorityZoneOpen(true);
    focusMap(nextRegionId);
  };

  React.useEffect(() => {
    if (regionId) focusMap(regionId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regionId]);

  const applyCommand = (nextCommand: string) => {
    setCommand(nextCommand);
    setIsAgentPanelOpen(true);
    setAgentPanelView('trace');
    const params = new URLSearchParams(searchParams);
    params.set('q', nextCommand);
    setSearchParams(params);
    plannerQuery.run(nextCommand).then(() => {
      setAgentPanelView('facilities');
    });
  };

  const composeCapabilityCommand = () => {
    const targetPin = regionSearch.trim() || pinCode;
    const detail = capabilityDetails.trim();
    return `Find facilities within ${radiusKm}km of PIN ${targetPin} that can perform ${getCapabilityLabel(capability)}${detail ? ` and ${detail}` : ''}.`;
  };

  const openFacilityDetail = (facilityId: string) => {
    setSelectedFacilityId(facilityId);
  };

  const selectPriorityRegion = (nextRegionId: string) => {
    setIsPriorityZoneOpen(true);
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
    if (next.regionId) {
      setIsPriorityZoneOpen(true);
      focusMap(next.regionId);
    }
  };

  const onCommandSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    applyCommand(searchMode === 'semantic' ? command : composeCapabilityCommand());
  };

  const handleResetMap = () => {
    setRegionSearch('');
    setIsAgentPanelOpen(false);
    setIsPriorityZoneOpen(false);
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
    const source = feat.source || 'funding-regions';
    if (hoveredFeatureId.current !== null && hoveredFeatureId.current !== featureId) {
      map.setFeatureState({ source: 'funding-regions', id: hoveredFeatureId.current }, { hover: false });
      map.setFeatureState({ source: 'india-districts', id: hoveredFeatureId.current }, { hover: false });
    }
    hoveredFeatureId.current = featureId;
    map.setFeatureState({ source, id: featureId }, { hover: true });
  };

  const onMouseLeave = (event: any) => {
    event.target.getCanvas().style.cursor = '';
    if (hoveredFeatureId.current !== null) {
      event.target.setFeatureState({ source: 'funding-regions', id: hoveredFeatureId.current }, { hover: false });
      event.target.setFeatureState({ source: 'india-districts', id: hoveredFeatureId.current }, { hover: false });
      hoveredFeatureId.current = null;
    }
  };

  return (
    <div className="relative h-full w-full overflow-hidden bg-surface-canvas">
      <Map
        ref={mapRef}
        initialViewState={{
          longitude: regionId ? (regionId === 'BR_MADHUBANI' ? MADHUBANI_CENTER[0] : PATNA_CENTER[0]) : INDIA_CENTER[0],
          latitude: regionId ? (regionId === 'BR_MADHUBANI' ? MADHUBANI_CENTER[1] : PATNA_CENTER[1]) : INDIA_CENTER[1],
          zoom: regionId ? 7 : 4,
        }}
        mapStyle={getMapStyle(regionId, overlayMode, visibleLayers, coverageFeatures, fundingRegionsGeoJson, facilityLocationsGeoJson)}
        style={{ width: '100%', height: '100%' }}
        interactiveLayerIds={['funding-fill', 'india-fill', 'facility-dots', 'facility-clusters']}
        onClick={(event: any) => {
          const feat = event.features?.[0];
          const props = feat?.properties;
          const layer = feat?.layer?.id;

          if (layer === 'facility-clusters' && props?.cluster_id != null) {
            const map = mapRef.current?.getMap();
            if (map) {
              const source = map.getSource('facility-dots');
              source?.getClusterExpansionZoom?.(props.cluster_id, (_: any, zoom: number) => {
                map.flyTo({ center: [event.lngLat.lng, event.lngLat.lat], zoom: zoom ?? 8, duration: 600 });
              });
            }
            return;
          }

          if (layer === 'facility-dots' && props?.id) {
            navigate(`/facilities/${props.id}?from=map-workbench`);
            return;
          }

          const clickedRegionId = props?.regionId;
          if (clickedRegionId) {
            selectPriorityRegion(clickedRegionId);
            return;
          }

          const stateName = props?.ST_NM;
          const distName = props?.Dist_name;
          if (stateName || distName) {
            const label = distName ? `${distName}, ${stateName}` : stateName;
            const [lng, lat] = [event.lngLat.lng, event.lngLat.lat];
            mapRef.current?.getMap()?.flyTo({ center: [lng, lat], zoom: 8, duration: 800 });
            const params = new URLSearchParams(searchParams);
            params.set('region_id', distName || stateName);
            params.set('region_name', label);
            setSearchParams(params);
            return;
          }
          focusMap(regionId);
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
              } ${selectedFacilityId === facility.facility_id ? 'border-content-primary ring-4 ring-white/80' : 'border-white'}`}
              aria-label={`Open ${facility.name}`}
            >
              {index + 1}
            </button>
          </Marker>
        ))}

        {aggregates.map((zone) => {
          const total = zone.verified_facilities_count + zone.flagged_facilities_count;
          if (total === 0) return null;
          const size = Math.min(56, Math.max(20, 12 + Math.sqrt(total) * 5));
          const flaggedRatio = total > 0 ? zone.flagged_facilities_count / total : 0;
          const bg = flaggedRatio > 0.5 ? 'bg-semantic-critical/30 border-semantic-critical/50' : 'bg-accent-primary/25 border-accent-primary/40';
          return (
            <Marker key={zone.region_id} longitude={zone.centroid.lng} latitude={zone.centroid.lat} anchor="center">
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  setRegionInUrl(zone.region_id);
                }}
                title={`${zone.region_name}: ${zone.verified_facilities_count} verified, ${zone.flagged_facilities_count} flagged`}
                className={`pointer-events-auto flex items-center justify-center rounded-full border-2 text-mono-s font-bold text-content-primary backdrop-blur-sm transition-transform hover:scale-110 ${bg}`}
                style={{ width: size, height: size }}
              >
                {total}
              </button>
            </Marker>
          );
        })}

        {selectedRegionCentroid && (
          <Marker longitude={selectedRegionCentroid[0]} latitude={selectedRegionCentroid[1]} anchor="center">
            <span className="block h-3 w-3 rounded-full bg-accent-primary ring-4 ring-white/80 shadow-elevation-2" />
          </Marker>
        )}
      </Map>

      {/* Priority zone popup — from live MapRegionAggregate */}
      {selectedRegionCentroid && isPriorityZoneOpen && selectedAggregate && (
        <div className="pointer-events-auto absolute left-1/2 top-[44%] z-40 w-[460px] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border-subtle bg-white/90 p-4 pr-10 shadow-elevation-4 backdrop-blur-xl">
          <button
            type="button"
            onClick={() => setIsPriorityZoneOpen(false)}
            className="absolute right-3 top-3 rounded-full border border-border-subtle bg-white/70 p-1.5 text-content-tertiary transition-colors hover:text-content-primary"
            aria-label="Close selected priority zone"
          >
            <X className="h-3.5 w-3.5" />
          </button>
          <div className="grid grid-cols-[1.15fr_0.85fr] gap-4">
            <div>
              <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">Selected region</div>
              <h2 className="mt-1 text-heading-m text-content-primary">{selectedAggregate.region_name}</h2>
              <p className="mt-2 text-caption text-content-secondary">
                {selectedAggregate.state} · {getCapabilityLabel(selectedAggregate.capability_type)}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-xl bg-white/70 p-2.5">
                <div className="text-mono-s uppercase text-content-tertiary">Verified</div>
                <div className="mt-1 text-heading-s text-semantic-verified">{selectedAggregate.verified_facilities_count}</div>
              </div>
              <div className="rounded-xl bg-white/70 p-2.5">
                <div className="text-mono-s uppercase text-content-tertiary">Flagged</div>
                <div className="mt-1 text-heading-s text-semantic-critical">{selectedAggregate.flagged_facilities_count}</div>
              </div>
              <div className="rounded-xl bg-white/70 p-2.5">
                <div className="text-mono-s uppercase text-content-tertiary">Population</div>
                <div className="mt-1 text-caption font-semibold text-content-primary">
                  {formatNumber(selectedAggregate.population)}
                </div>
              </div>
              <div className="rounded-xl bg-white/70 p-2.5">
                <div className="text-mono-s uppercase text-content-tertiary">Gap pop.</div>
                <div className="mt-1 text-caption font-semibold text-content-primary">
                  {formatNumber(selectedAggregate.gap_population)}
                </div>
              </div>
            </div>
          </div>
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

      {/* Planning layers panel */}
      <div className="pointer-events-auto absolute left-6 top-24 z-20 flex max-h-[calc(100vh-190px)] w-[350px] flex-col gap-3 overflow-y-auto pr-1">
        <Card variant="glass-control" className="pointer-events-auto rounded-2xl p-2.5">
          <button
            type="button"
            onClick={() => setIsPlanningLayersOpen((isOpen) => !isOpen)}
            aria-expanded={isPlanningLayersOpen}
            className="flex w-full items-center justify-between gap-3 rounded-xl px-1.5 py-1 text-left transition-colors hover:bg-white/40"
          >
            <span>
              <span className="block text-caption font-semibold uppercase tracking-wider text-content-secondary">Planning layers</span>
              <span className="mt-0.5 block text-heading-s text-content-primary">{activeOverlayOption.label}</span>
            </span>
            <span className="flex items-center gap-2">
              <span className="rounded-full bg-white/70 px-2 py-1 text-mono-s text-content-secondary">{activeOverlayOption.legend}</span>
              <ChevronRight className={`h-4 w-4 text-content-tertiary transition-transform ${isPlanningLayersOpen ? 'rotate-90' : ''}`} />
            </span>
          </button>

          {isPlanningLayersOpen && (
            <div className="mt-3 border-t border-border-subtle pt-3">
              <div>
                <div className="mb-2 text-mono-s uppercase text-content-tertiary">Color map by</div>
                <div className="grid grid-cols-2 gap-1 rounded-xl bg-surface-sunken p-1">
                  {OVERLAY_MODE_OPTIONS.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => setOverlayMode(option.id)}
                      className={`rounded-lg px-2 py-1.5 text-left text-caption font-semibold transition-colors ${
                        overlayMode === option.id ? 'bg-white text-content-primary shadow-elevation-1' : 'text-content-secondary hover:text-content-primary'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-4 flex flex-col gap-2">
                {PLANNING_LAYER_OPTIONS.map((layer) => {
                  const isVisible = visibleLayers[layer.id];
                  return (
                    <button
                      key={layer.id}
                      type="button"
                      aria-pressed={isVisible}
                      onClick={() => setVisibleLayers((current) => ({ ...current, [layer.id]: !current[layer.id] }))}
                      className="flex items-center justify-between gap-3 rounded-xl border border-border-subtle bg-white/62 px-3 py-2 text-left transition-colors hover:border-accent-primary-soft hover:bg-white"
                    >
                      <span>
                        <span className="block text-caption font-semibold text-content-primary">{layer.label}</span>
                        <span className="block text-mono-s text-content-tertiary">{layer.detail}</span>
                      </span>
                      <span className={`h-5 w-9 rounded-full p-0.5 transition-colors ${isVisible ? 'bg-accent-primary' : 'bg-content-tertiary/25'}`}>
                        <span className={`block h-4 w-4 rounded-full bg-white shadow-elevation-1 transition-transform ${isVisible ? 'translate-x-4' : ''}`} />
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* Legend */}
      <div
        className="absolute bottom-12 z-20 transition-all duration-300"
        style={{ right: isAgentPanelOpen ? '500px' : '24px' }}
      >
        <MapLegend
          title="Flagged facilities"
          caption="live"
          stops={FLAGGED_LEGEND_STOPS}
          populationSource={populationSource}
          unmatchedCount={join.unmatched.length}
        />
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
          regionAggregate={selectedAggregate}
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
