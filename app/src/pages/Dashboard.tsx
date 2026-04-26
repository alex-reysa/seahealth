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
// NOTE: demoData drives the funding/lens helpers (committee scores, ranked
// candidate copy). Those values are explicitly out-of-scope for backend
// wiring per the live-backend connection plan: the data spine has no
// "fundingRationale" or "needLayerLabel" yet. The visible /summary counts
// and the choropleth fill come from the API hooks below — see useSummary
// and useMapAggregates. Only the funding-rationale UX leans on demoData.
import {
  CAPABILITIES,
  CHALLENGE_QUERY,
  type CapabilityType,
  type DemoCapabilityAudit,
  type DemoFacility,
  type DemoQueryResult,
  type DemoTraceSpan,
  formatNumber,
  getCapabilityAudit,
  getCapabilityLabel,
  getFacilityById,
  getFundingCandidateRecommendation,
  getFundingPriorityRegion,
  getFacilityRowsForRegion,
  getQueryResultForCommand,
  getRankedFacilities,
  parseDemoCommand,
} from '@/src/data/demoData';
import mockIndiaRegionsTopologyRaw from '@/src/data/mockIndiaRegions.topojson?raw';
import { useFacilityLocations } from '@/src/hooks/useFacilityLocations';
import { useMapAggregates } from '@/src/hooks/useMapAggregates';
import { useSummary } from '@/src/hooks/useSummary';
import { decorateFeaturesWithJoin, joinAggregatesToFeatures } from '@/src/lib/mapJoin';
import { getBounds } from '@/src/lib/regionTree';
import type { MapRegionAggregate, PopulationSource } from '@/src/types/api';

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

function buildCoverageFeatureCollection(facilities: DemoFacility[], radiusKm: number): any {
  return {
    type: 'FeatureCollection',
    features: facilities.map((facility) => geoCircleFeature(facility.lng, facility.lat, radiusKm)),
  };
}

function getMetricLabel(value: number, labels: [string, string, string]) {
  if (value >= 0.75) return labels[2];
  if (value >= 0.45) return labels[1];
  return labels[0];
}

function formatPercentMetric(value: number) {
  return `${Math.round(value * 100)}%`;
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
  const fundingFillOpacity = overlayVisible
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
        data: 'https://raw.githubusercontent.com/udit-001/india-maps-data/main/geojson/india.geojson',
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
          'fill-color': '#DDEBE5',
          'fill-opacity': 0.42,
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
        id: 'facility-dots',
        type: 'circle',
        source: 'facility-dots',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 1.5, 7, 3.5, 10, 6],
          'circle-color': [
            'case',
            ['==', ['get', 'flagged'], 1],
            '#C56556',
            '#3D9D89',
          ],
          'circle-opacity': 0.7,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 0.5,
        },
      },
    ],
  } as any;
}

function getSpanStatus(span: DemoTraceSpan, index: number, activeStep: number | null): DemoTraceSpan['status'] {
  if (activeStep === null) return span.status;
  if (index < activeStep) return 'complete';
  if (index === activeStep) return 'running';
  return 'pending';
}

function statusClass(status: DemoTraceSpan['status']) {
  if (status === 'complete') return 'bg-semantic-verified text-semantic-verified';
  if (status === 'running') return 'bg-semantic-flagged text-semantic-flagged';
  if (status === 'failed') return 'bg-semantic-critical text-semantic-critical';
  return 'bg-content-tertiary text-content-secondary';
}

function AgentTimeline({ result, activeStep }: { result: DemoQueryResult; activeStep: number | null }) {
  return (
    <div className="flex flex-col gap-2">
      {result.spans.map((span, index) => {
        const status = getSpanStatus(span, index, activeStep);
        const colorClass = statusClass(status);
        return (
          <details key={span.id} className="group rounded-lg border border-border-subtle bg-white/70 open:bg-white">
            <summary className="flex cursor-pointer list-none items-start gap-3 p-3">
              <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${colorClass.split(' ')[0]} ${status === 'running' ? 'animate-pulse' : ''}`} />
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-3">
                  <span className="font-mono text-caption text-content-primary">{span.toolName ?? span.label}</span>
                  <span className={`text-mono-s uppercase ${colorClass.split(' ')[1]}`}>{status}</span>
                </span>
                <span className="mt-1 block text-caption text-content-secondary">{span.outputSummary ?? span.detail}</span>
              </span>
              <ChevronRight className="mt-0.5 h-4 w-4 text-content-tertiary transition-transform group-open:rotate-90" />
            </summary>
            <div className="border-t border-border-subtle px-3 pb-3 pt-2">
              <div className="grid grid-cols-2 gap-2 text-caption">
                <div>
                  <div className="text-content-tertiary">Input</div>
                  <div className="text-content-secondary">{span.inputSummary ?? 'Mock context'}</div>
                </div>
                <div>
                  <div className="text-content-tertiary">Duration</div>
                  <div className="font-mono text-content-secondary">{span.durationMs ? `${span.durationMs}ms` : status}</div>
                </div>
              </div>
              <pre className="mt-2 max-h-28 overflow-auto rounded-md bg-surface-sunken p-2 text-mono-s text-content-secondary">
                {JSON.stringify(span.payload ?? { detail: span.detail }, null, 2)}
              </pre>
            </div>
          </details>
        );
      })}
    </div>
  );
}

function getRankRationale(facility: DemoFacility, rank: number, result: DemoQueryResult) {
  if (result.queryTraceId === 'query_rural_bihar_appendectomy_staffing' && facility.id === 'facility_patna_medical') {
    return 'Ranked first because it is the nearest staffing-matching facility with verified appendectomy evidence, part-time doctor notes, and the HIGH missing-anesthesiologist contradiction kept visible.';
  }
  return `Ranked #${rank} by Trust Score first, then distance as the tie-breaker for the selected capability.`;
}

function getCandidateRecommendation(
  facility: DemoFacility,
  audit: DemoCapabilityAudit | undefined,
  rank: number,
  fundingRegion: ReturnType<typeof getFundingPriorityRegion>,
) {
  const dataBackedRecommendation = getFundingCandidateRecommendation(fundingRegion, facility.id);
  if (dataBackedRecommendation) return dataBackedRecommendation;

  const capabilityLabel = getCapabilityLabel(fundingRegion.capability);
  return {
    facilityId: facility.id,
    whyFund:
      rank === 1
        ? `Closest candidate connected to ${fundingRegion.name}.`
        : `Secondary candidate for extending ${capabilityLabel} access.`,
    trustRisk: audit
      ? `Trust Score ${audit.score}; ${audit.contradictionCount} contradiction${audit.contradictionCount === 1 ? '' : 's'} visible.`
      : `No verified ${capabilityLabel} audit in the current mock evidence.`,
    missingResource: audit && audit.score >= 70 ? 'Grant-ready capacity confirmation.' : `Verified ${capabilityLabel} staff and equipment.`,
    recommendedNextStep: audit && audit.score >= 70 ? 'Confirm scale-up capacity before funding.' : 'Audit before allocating capital.',
  };
}

export function Dashboard() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const mapRef = React.useRef<any>(null);
  const hoveredFeatureId = React.useRef<string | number | null>(null);
  const timersRef = React.useRef<number[]>([]);

  const initialQuery = searchParams.get('q') || CHALLENGE_QUERY;
  const [command, setCommand] = React.useState(initialQuery);
  const [activeResult, setActiveResult] = React.useState(() => getQueryResultForCommand(initialQuery));
  const [activeStep, setActiveStep] = React.useState<number | null>(null);
  const [regionSearch, setRegionSearch] = React.useState(searchParams.get('pin_code') || '');
  const [isAgentPanelOpen, setIsAgentPanelOpen] = React.useState(true);
  const [searchMode, setSearchMode] = React.useState<SearchMode>('semantic');
  const [capabilityDetails, setCapabilityDetails] = React.useState('');
  const [agentPanelView, setAgentPanelView] = React.useState<AgentPanelView>('facilities');
  const [selectedFacilityId, setSelectedFacilityId] = React.useState<string | null>(null);
  const [selectedFacilityCapabilityId, setSelectedFacilityCapabilityId] = React.useState<CapabilityType | null>(null);
  const [overlayMode, setOverlayMode] = React.useState<MapOverlayMode>('priority_score');
  const [isPlanningLayersOpen, setIsPlanningLayersOpen] = React.useState(false);
  const [isPriorityZoneOpen, setIsPriorityZoneOpen] = React.useState(true);
  const [visibleLayers, setVisibleLayers] = React.useState<PlanningLayerVisibility>(DEFAULT_PLANNING_LAYER_VISIBILITY);

  const parsed = parseDemoCommand(command);
  const capability = (searchParams.get('capability') as CapabilityType) || activeResult.parsedIntent.capability || parsed.capability;
  const radiusKm = Number(searchParams.get('radius_km') || activeResult.parsedIntent.radiusKm || parsed.radiusKm);
  const regionId = searchParams.get('region_id') || parsed.regionId;
  const pinCode = searchParams.get('pin_code') || parsed.pinCode;
  const fundingRegion = getFundingPriorityRegion(regionId, capability);

  // Backend-driven counts + per-region signal. The summary tile and the
  // choropleth fill MUST come from these — never from demoData. The funding
  // copy below still leans on demoData for now (committee-supplied values
  // that have no backend equivalent yet).
  const summaryFetch = useSummary(capability);
  const aggregatesFetch = useMapAggregates(capability);
  const locationsFetch = useFacilityLocations();

  const aggregates: MapRegionAggregate[] = aggregatesFetch.data ?? [];
  const join = React.useMemo(
    () => joinAggregatesToFeatures(aggregates, TOPOLOGY_FEATURE_IDS),
    [aggregates],
  );
  React.useEffect(() => {
    if (
      typeof process !== 'undefined' &&
      process.env?.NODE_ENV !== 'production' &&
      join.unmatched.length > 0
    ) {
      // eslint-disable-next-line no-console
      console.warn(
        `[Dashboard] ${join.unmatched.length} /map/aggregates row(s) did not match any topology feature; rendering neutral fill.`,
        join.unmatched.map((row) => row.region_id),
      );
    }
  }, [join]);

  const fundingRegionsGeoJson = React.useMemo(() => {
    return {
      ...mockIndiaRegionsGeoJson,
      features: decorateFeaturesWithJoin(mockIndiaRegionsGeoJson.features, join),
    };
  }, [join]);

  // Choose a per-region aggregate for the side panel. Prefer the row that
  // matched the currently selected region's feature; fall back to the first
  // aggregate so the legend has something coherent to show.
  const selectedAggregate: MapRegionAggregate | undefined =
    join.byFeatureId.get(regionId)?.aggregate ?? aggregates[0];
  const populationSource: PopulationSource | null = selectedAggregate?.population_source ?? null;
  const populationUnavailable = populationSource === 'unavailable';
  const regionFacilities = getFacilityRowsForRegion(regionId, capability);
  const rankedFacilities = getRankedFacilities(activeResult);
  const fundingFacilities = fundingRegion.recommendedFacilities.map((id) => getFacilityById(id)).filter(Boolean) as DemoFacility[];
  const mapFacilities = fundingFacilities.length ? fundingFacilities : rankedFacilities.length ? rankedFacilities : regionFacilities;
  const topFacility = mapFacilities[0];
  const selectedFacility = selectedFacilityId ? getFacilityById(selectedFacilityId) : undefined;
  const selectedFacilityRank = selectedFacility ? Math.max(1, mapFacilities.findIndex((facility) => facility.id === selectedFacility.id) + 1) : 0;
  const selectedAudit = selectedFacility
    ? getCapabilityAudit(selectedFacility, selectedFacilityCapabilityId ?? capability) ?? selectedFacility.capabilities[0]
    : undefined;

  const coverageFeatures = React.useMemo(
    () => buildCoverageFeatureCollection(mapFacilities.slice(0, 7), radiusKm),
    [mapFacilities, radiusKm],
  );
  const facilityLocationsGeoJson = React.useMemo(
    () => facilityDotsGeoJson(locationsFetch.data ?? []),
    [locationsFetch.data],
  );
  const selectedRegionCentroid = regionCentroidsById.get(fundingRegion.regionId);

  // /summary is the canonical source for the audit/verified/flagged counts.
  // Until the fetch resolves we render dashes so the page never advertises a
  // stale demo number as a backend number.
  const summary = summaryFetch.data;
  const auditedCount = summary?.audited_count ?? null;
  const verifiedCount = summary?.verified_count ?? null;
  const flaggedCount = summary?.flagged_count ?? null;
  const isRunning = activeStep !== null;
  const activeOverlayOption = OVERLAY_MODE_OPTIONS.find((option) => option.id === overlayMode) ?? OVERLAY_MODE_OPTIONS[0];
  const selectedFundingAudit = selectedFacility ? getCapabilityAudit(selectedFacility, capability) : undefined;
  const selectedFundingRecommendation = selectedFacility
    ? getCandidateRecommendation(selectedFacility, selectedFundingAudit ?? selectedAudit, selectedFacilityRank, fundingRegion)
    : undefined;

  React.useEffect(() => {
    return () => {
      timersRef.current.forEach(window.clearTimeout);
    };
  }, []);

  const focusMap = (nextRegionId: string) => {
    const map = mapRef.current?.getMap();
    if (!map) return;
    // Prefer the canonical hierarchy bounds (set in regionHierarchy.json) so
    // every level — including the synthetic India root — knows where to fly.
    const bounds = getBounds(nextRegionId);
    if (bounds) {
      map.fitBounds(bounds, { padding: 60, duration: 800, maxZoom: 9 });
      return;
    }
    // Fall back to the legacy hard-coded centers for districts the topology
    // already paints; keeps behaviour identical for unknown ids.
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

  // URL is the source of truth for selection: a fresh load (or a pasted URL)
  // restores the map zoom for whatever ?region_id=… is in the address bar.
  React.useEffect(() => {
    if (regionId) focusMap(regionId);
    // We intentionally only react to regionId changes; map ref is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regionId]);

  const applyCommand = (nextCommand: string, animate = true) => {
    const nextParsed = parseDemoCommand(nextCommand);
    const nextResult = getQueryResultForCommand(nextCommand);
    timersRef.current.forEach(window.clearTimeout);
    timersRef.current = [];
    setCommand(nextCommand);
    setActiveResult(nextResult);
    setIsPriorityZoneOpen(true);
    if (animate) setAgentPanelView('trace');
    setSearchParams({
      q: nextCommand,
      capability: nextParsed.capability,
      radius_km: String(nextParsed.radiusKm),
      region_id: nextParsed.regionId,
      pin_code: nextParsed.pinCode,
    });
    focusMap(nextParsed.regionId);

    if (!animate) {
      setActiveStep(null);
      return;
    }

    setActiveStep(0);
    nextResult.spans.forEach((_, index) => {
      const timer = window.setTimeout(() => {
        const isLastStep = index + 1 >= nextResult.spans.length;
        setActiveStep(isLastStep ? null : index + 1);
        if (isLastStep) setAgentPanelView('facilities');
      }, 260 + index * 190);
      timersRef.current.push(timer);
    });
  };

  const composeCapabilityCommand = () => {
    const targetPin = regionSearch.trim() || pinCode;
    const detail = capabilityDetails.trim();
    return `Find facilities within ${radiusKm}km of PIN ${targetPin} that can perform ${getCapabilityLabel(capability)}${detail ? ` and ${detail}` : ''}.`;
  };

  const openFacilityDetail = (facilityId: string) => {
    const facility = getFacilityById(facilityId);
    const defaultAudit = facility ? getCapabilityAudit(facility, capability) ?? facility.capabilities[0] : undefined;
    setSelectedFacilityCapabilityId(defaultAudit?.id ?? capability);
    setSelectedFacilityId(facilityId);
  };

  const selectPriorityRegion = (nextRegionId: string) => {
    const nextFundingRegion = getFundingPriorityRegion(nextRegionId);
    const nextCommand = `Show funding candidates for ${nextFundingRegion.name} with verified ${getCapabilityLabel(nextFundingRegion.capability)} access gaps.`;
    setCommand(nextCommand);
    setActiveResult(getQueryResultForCommand(nextCommand));
    setAgentPanelView('facilities');
    setIsPriorityZoneOpen(true);
    setSearchParams({
      q: nextCommand,
      capability: nextFundingRegion.capability,
      radius_km: String(radiusKm),
      region_id: nextFundingRegion.regionId,
      pin_code: nextFundingRegion.regionId === 'BR_MADHUBANI' ? '847211' : '800001',
    });
    focusMap(nextFundingRegion.regionId);
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
    applyCommand(CHALLENGE_QUERY, false);
    mapRef.current?.getMap()?.flyTo({ center: INDIA_CENTER, zoom: 4, duration: 1000 });
  };

  const onMouseMove = (event: any) => {
    if (!event.features?.length) return;
    const featureId = event.features[0].id;
    if (featureId == null) return;
    event.target.getCanvas().style.cursor = 'pointer';
    const map = event.target;
    if (hoveredFeatureId.current !== null && hoveredFeatureId.current !== featureId) {
      map.setFeatureState({ source: 'funding-regions', id: hoveredFeatureId.current }, { hover: false });
    }
    hoveredFeatureId.current = featureId;
    map.setFeatureState({ source: 'funding-regions', id: hoveredFeatureId.current }, { hover: true });
  };

  const onMouseLeave = (event: any) => {
    event.target.getCanvas().style.cursor = '';
    if (hoveredFeatureId.current !== null) {
      event.target.setFeatureState({ source: 'funding-regions', id: hoveredFeatureId.current }, { hover: false });
      hoveredFeatureId.current = null;
    }
  };

  return (
    <div className="relative h-full w-full overflow-hidden bg-surface-canvas">
      <Map
        ref={mapRef}
        initialViewState={{
          longitude: regionId === 'BR_MADHUBANI' ? MADHUBANI_CENTER[0] : PATNA_CENTER[0],
          latitude: regionId === 'BR_MADHUBANI' ? MADHUBANI_CENTER[1] : PATNA_CENTER[1],
          zoom: regionId ? 7 : 4,
        }}
        mapStyle={getMapStyle(regionId, overlayMode, visibleLayers, coverageFeatures, fundingRegionsGeoJson, facilityLocationsGeoJson)}
        style={{ width: '100%', height: '100%' }}
        interactiveLayerIds={['funding-fill']}
        onClick={(event: any) => {
          const clickedRegionId = event.features?.[0]?.properties?.regionId;
          if (clickedRegionId) {
            selectPriorityRegion(clickedRegionId);
          } else {
            focusMap(regionId);
          }
        }}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
      >
        {mapFacilities.slice(0, 7).map((facility, index) => (
          <Marker key={facility.id} longitude={facility.lng} latitude={facility.lat} anchor="center">
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                openFacilityDetail(facility.id);
              }}
              className={`pointer-events-auto relative flex h-9 w-9 items-center justify-center rounded-full border-2 text-caption font-semibold text-white shadow-elevation-3 transition-transform hover:scale-110 ${
                index === 0 ? 'bg-semantic-critical' : 'bg-accent-primary'
              } ${selectedFacilityId === facility.id ? 'border-content-primary ring-4 ring-white/80' : 'border-white'}`}
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

      {selectedRegionCentroid && isPriorityZoneOpen && (
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
              <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">Selected priority zone</div>
              <h2 className="mt-1 text-heading-m text-content-primary">{fundingRegion.name}</h2>
              <p className="mt-2 text-caption text-content-secondary">{fundingRegion.regionSummary}</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-xl bg-white/70 p-2.5">
                <div className="text-mono-s uppercase text-content-tertiary">Priority</div>
                <div className="mt-1 text-heading-s text-accent-primary">{Math.round(fundingRegion.priorityScore * 100)}/100</div>
              </div>
              {populationUnavailable ? (
                <div className="rounded-xl bg-white/70 p-2.5">
                  <div className="text-mono-s uppercase text-content-tertiary">Verified / flagged</div>
                  <div className="mt-1 text-heading-s text-content-primary">
                    {selectedAggregate?.verified_facilities_count ?? 0}
                    <span className="text-content-tertiary"> / </span>
                    {selectedAggregate?.flagged_facilities_count ?? 0}
                  </div>
                </div>
              ) : (
                <div className="rounded-xl bg-white/70 p-2.5">
                  <div className="text-mono-s uppercase text-content-tertiary">Gap pop.</div>
                  <div className="mt-1 text-heading-s text-content-primary">{formatNumber(fundingRegion.gapPopulation)}</div>
                </div>
              )}
              <div className="rounded-xl bg-white/70 p-2.5">
                <div className="text-mono-s uppercase text-content-tertiary">Need</div>
                <div className="mt-1 text-caption font-semibold text-content-primary">
                  {getMetricLabel(fundingRegion.needSignal, ['Low', 'Moderate', 'High'])} ({formatPercentMetric(fundingRegion.needSignal)})
                </div>
              </div>
              <div className="rounded-xl bg-white/70 p-2.5">
                <div className="text-mono-s uppercase text-content-tertiary">Access</div>
                <div className="mt-1 text-caption font-semibold text-content-primary">
                  {getMetricLabel(fundingRegion.verifiedAccessScore, ['Low', 'Mixed', 'High'])} ({formatPercentMetric(fundingRegion.verifiedAccessScore)})
                </div>
              </div>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2 rounded-xl border border-border-subtle bg-white/62 p-3">
            <div className="flex items-center justify-between gap-3 text-caption">
              <span className="text-content-secondary">Nearest verified care</span>
              <span className="font-semibold text-content-primary">{fundingRegion.nearestVerifiedKm}km</span>
            </div>
            <div className="flex items-center justify-between gap-3 text-caption">
              <span className="text-content-secondary">Contradiction risk</span>
              <span className="font-semibold text-semantic-critical">
                {getMetricLabel(fundingRegion.contradictionRisk, ['Low', 'Moderate', 'High'])} ({formatPercentMetric(fundingRegion.contradictionRisk)})
              </span>
            </div>
          </div>

          <p className="mt-3 text-caption font-medium text-content-primary">{fundingRegion.recommendedAction}</p>
        </div>
      )}

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
              <div className="text-body font-semibold text-content-primary">{new Date(activeResult.generatedAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</div>
              <div className="text-mono-s uppercase text-content-secondary">Generated</div>
            </div>
          </Card>
        </div>
      </div>

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
                      placeholder={pinCode}
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

      <button
        type="button"
        onClick={handleResetMap}
        className="absolute bottom-12 left-6 z-20 flex h-10 items-center gap-1.5 rounded-full border border-border-subtle bg-white/70 px-3 text-caption text-content-secondary shadow-elevation-1 backdrop-blur-xl transition-colors hover:text-content-primary"
      >
        <RotateCcw className="h-3.5 w-3.5" />
        Reset map
      </button>

      <div className="pointer-events-none absolute inset-x-0 bottom-2 z-10 flex justify-center">
        <Breadcrumbs
          regionId={regionId}
          onSelect={setRegionInUrl}
          className="pointer-events-auto border-white/50 bg-white/45 px-2 py-0.5 opacity-80 shadow-none"
        />
      </div>

      {!isAgentPanelOpen && (
        <button
          type="button"
          onClick={() => setIsAgentPanelOpen(true)}
          className="absolute right-6 top-5 z-30 flex items-center gap-2 rounded-full border border-border-subtle bg-white/82 px-3 py-2 text-left shadow-elevation-2 backdrop-blur-xl transition-transform hover:-translate-x-0.5"
          aria-label="Expand agent run panel"
        >
          <span className={`h-2.5 w-2.5 rounded-full ${isRunning ? 'bg-semantic-flagged animate-pulse' : 'bg-semantic-verified'}`} />
          <span className="text-caption font-semibold text-content-primary">Agent</span>
          <span className="text-caption text-content-secondary">{isRunning ? 'Running' : 'Complete'}</span>
          <ChevronRight className="h-3.5 w-3.5 rotate-180 text-content-tertiary" />
        </button>
      )}

      {isAgentPanelOpen && (
      <aside className="absolute bottom-10 right-6 top-5 z-30 w-[460px]">
        <div className="glass-elevated flex h-full flex-col overflow-hidden rounded-2xl">
          <div className="border-b border-border-subtle bg-white/45 p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">Agent Run</div>
                <h1 className="mt-1 text-heading-l text-content-primary">
                  {isRunning ? 'Searching funding gaps' : 'Funding candidates'}
                </h1>
              </div>
              <div className="flex items-center gap-2">
                <div className={`rounded-full px-3 py-1 text-caption font-semibold ${isRunning ? 'bg-semantic-flagged-subtle text-semantic-flagged' : 'bg-semantic-verified-subtle text-semantic-verified'}`}>
                  {isRunning ? 'Running tools' : 'Run complete'}
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
              <p className="mt-1 line-clamp-2 text-body text-content-secondary">{activeResult.query}</p>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-white/65 p-3">
                <div className="text-caption text-content-tertiary">Priority Zone</div>
                <div className="mt-1 text-heading-s text-content-primary">{fundingRegion.name}</div>
              </div>
              <div className="rounded-lg bg-white/65 p-3">
                <div className="text-caption text-content-tertiary">Priority Score</div>
                <div className="mt-1 text-heading-s text-accent-primary">{Math.round(fundingRegion.priorityScore * 100)}/100</div>
              </div>
            </div>
            <div className="mt-3 rounded-xl border border-border-subtle bg-white/62 p-3">
              <div className="text-mono-s uppercase text-content-tertiary">Funding rationale</div>
              <p className="mt-1 text-caption text-content-secondary">{fundingRegion.fundingRationale}</p>
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-caption">
              <button
                type="button"
                onClick={() => applyCommand(CHALLENGE_QUERY)}
                className="rounded-full border border-border-default bg-white/70 px-3 py-1 text-content-primary transition-colors hover:border-accent-primary-soft"
              >
                Challenge query
              </button>
              <button
                type="button"
                onClick={() => navigate(`/planner-query?q=${encodeURIComponent(command)}`)}
                className="rounded-full border border-border-default bg-white/70 px-3 py-1 text-content-primary transition-colors hover:border-accent-primary-soft"
              >
                Open report mode
              </button>
              {topFacility && (
                <button
                  type="button"
                  onClick={() => openFacilityDetail(topFacility.id)}
                  className="rounded-full border border-border-default bg-white/70 px-3 py-1 text-content-primary transition-colors hover:border-accent-primary-soft"
                >
                  Inspect top facility
                </button>
              )}
            </div>
            <div className="mt-4 grid grid-cols-2 rounded-xl bg-surface-sunken p-1">
              {([
                ['facilities', 'Funding candidates'],
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
                  <span className="text-mono-s text-content-tertiary">{activeResult.queryTraceId}</span>
                </div>
                <AgentTimeline result={activeResult} activeStep={activeStep} />
              </>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-caption font-semibold uppercase tracking-wider text-content-secondary">
                    <Target className="h-4 w-4" /> Funding candidates
                  </div>
                  <span className="text-caption text-content-tertiary">{activeResult.totalCandidates} candidates</span>
                </div>

                <div className="mt-3 flex flex-col gap-2">
                  {mapFacilities.slice(0, 5).map((facility, index) => {
                    const audit = getCapabilityAudit(facility, capability);
                    const recommendation = getCandidateRecommendation(facility, audit, index + 1, fundingRegion);
                    const trustScore = audit?.score ?? 0;
                    const confidenceInterval = audit?.confidenceInterval ?? ([0, 0] as [number, number]);
                    return (
                      <button
                        key={facility.id}
                        type="button"
                        onClick={() => openFacilityDetail(facility.id)}
                        className={`group rounded-lg border bg-white/75 p-3 text-left transition-all hover:border-accent-primary-soft hover:bg-white ${
                          selectedFacilityId === facility.id ? 'border-accent-primary-soft shadow-elevation-1' : 'border-border-subtle'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="rounded bg-surface-sunken px-1.5 py-0.5 font-mono text-caption text-content-secondary">#{index + 1}</span>
                              <span className="text-body font-medium text-content-primary group-hover:text-accent-primary">{facility.name}</span>
                            </div>
                            <div className="mt-2 flex flex-wrap items-center gap-3 text-caption text-content-secondary">
                              <span className="flex items-center gap-1">
                                <MapPin className="h-3.5 w-3.5" /> {facility.distanceKm}km
                              </span>
                              <span className="flex items-center gap-1">
                                <FileText className="h-3.5 w-3.5" /> {audit ? `${audit.evidenceCount} evidence` : 'no verified audit'}
                              </span>
                            </div>
                          </div>
                          <TrustScore score={trustScore} confidenceInterval={confidenceInterval} showLabel={false} />
                        </div>
                        {audit && audit.contradictionCount > 0 && (
                          <div className="mt-2 inline-flex items-center gap-1.5 rounded bg-semantic-critical-subtle px-2 py-1 text-caption text-semantic-critical">
                            <ShieldAlert className="h-3.5 w-3.5" /> {audit.contradictionCount} contradictions, HIGH visible
                          </div>
                        )}
                        <div className="mt-3 grid gap-2 text-caption">
                          <div>
                            <span className="font-semibold text-content-primary">Why fund: </span>
                            <span className="text-content-secondary">{recommendation.whyFund}</span>
                          </div>
                          <div>
                            <span className="font-semibold text-content-primary">Trust risk: </span>
                            <span className="text-content-secondary">{recommendation.trustRisk}</span>
                          </div>
                          <div>
                            <span className="font-semibold text-content-primary">Missing resource: </span>
                            <span className="text-content-secondary">{recommendation.missingResource}</span>
                          </div>
                          <div className="rounded-lg bg-surface-sunken px-2.5 py-2 text-content-primary">
                            <span className="font-semibold">Action: </span>
                            {recommendation.recommendedNextStep}
                          </div>
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

      {selectedFacility && selectedAudit && createPortal(
        <div
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-content-primary/35 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label={`${selectedFacility.name} facility detail`}
          onClick={() => setSelectedFacilityId(null)}
        >
          <div
            className="flex h-[min(920px,calc(100vh-32px))] w-[min(1440px,calc(100vw-32px))] overflow-hidden rounded-[28px] border border-border-subtle bg-surface-canvas shadow-elevation-4"
            onClick={(event) => event.stopPropagation()}
          >
            <aside className="flex w-[390px] shrink-0 flex-col border-r border-border-subtle bg-white/86">
              <div className="p-6">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">
                      Facility detail
                    </div>
                    <h2 className="mt-2 text-heading-l text-content-primary">{selectedFacility.name}</h2>
                    <div className="mt-3 flex flex-wrap items-center gap-3 text-caption text-content-secondary">
                      <span className="flex items-center gap-1">
                        <MapPin className="h-3.5 w-3.5" /> {selectedFacility.distanceKm}km
                      </span>
                      <span>Rank #{selectedFacilityRank}</span>
                      <span>PIN {selectedFacility.pinCode}</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedFacilityId(null)}
                    className="rounded-full border border-border-subtle bg-white p-2 text-content-tertiary transition-colors hover:text-content-primary"
                    aria-label="Close facility detail"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                <div className="mt-6">
                  <div className="mb-3 text-caption font-semibold uppercase tracking-wider text-content-secondary">Capabilities at this facility</div>
                  <div className="flex flex-col gap-2">
                    {selectedFacility.capabilities.map((facilityCapability) => {
                      const isSelected = selectedAudit.id === facilityCapability.id;
                      return (
                        <button
                          key={facilityCapability.id}
                          type="button"
                          onClick={() => setSelectedFacilityCapabilityId(facilityCapability.id)}
                          className={`rounded-2xl border p-3 text-left transition-all ${
                            isSelected ? 'border-border-strong bg-surface-canvas shadow-elevation-1' : 'border-border-subtle bg-white/65 hover:border-border-default hover:bg-surface-canvas/70'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-body font-semibold text-content-primary">{facilityCapability.name}</div>
                              <div className="mt-1 flex items-center gap-2 text-caption text-content-secondary">
                                {facilityCapability.claimed ? (
                                  <span className="flex items-center gap-1 text-semantic-verified">
                                    <CheckCircle2 className="h-3 w-3" /> Claimed
                                  </span>
                                ) : (
                                  <span className="text-content-tertiary">Not claimed</span>
                                )}
                                <span>{facilityCapability.evidenceCount} evidence</span>
                                <span className={facilityCapability.contradictionCount > 0 ? 'text-semantic-critical' : 'text-content-secondary'}>
                                  {facilityCapability.contradictionCount} flags
                                </span>
                              </div>
                            </div>
                            <TrustScore score={facilityCapability.score} confidenceInterval={facilityCapability.confidenceInterval} showLabel={false} />
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-2xl border border-border-subtle bg-surface-canvas p-4">
                    <div className="text-mono-s uppercase text-content-tertiary">Evidence</div>
                    <div className="mt-1 text-heading-m text-content-primary">{selectedAudit.evidenceCount}</div>
                  </div>
                  <div className="rounded-2xl border border-border-subtle bg-surface-canvas p-4">
                    <div className="text-mono-s uppercase text-content-tertiary">Contradictions</div>
                    <div className={`mt-1 text-heading-m ${selectedAudit.contradictionCount > 0 ? 'text-semantic-critical' : 'text-semantic-verified'}`}>
                      {selectedAudit.contradictionCount}
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-auto border-t border-border-subtle p-5">
                <Button
                  type="button"
                  variant="secondary"
                  className="w-full gap-2"
                  onClick={() => navigate(`/facilities/${selectedFacility.id}?capability=${selectedAudit.id}&from=map-workbench&q=${encodeURIComponent(command)}`)}
                >
                  <ExternalLink className="h-4 w-4" />
                  Open full audit
                </Button>
              </div>
            </aside>

            <main className="flex-1 overflow-y-auto p-7">
              <section className="rounded-2xl border border-accent-primary/15 bg-accent-primary-subtle p-5 shadow-elevation-1">
                <div className="mb-3 flex items-center justify-between gap-4">
                  <div>
                    <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">Funding relevance</div>
                    <h3 className="mt-1 text-heading-l text-content-primary">{fundingRegion.name}</h3>
                  </div>
                  <span className="rounded-full bg-white/70 px-3 py-1 text-caption font-semibold text-accent-primary">
                    Priority {Math.round(fundingRegion.priorityScore * 100)}/100
                  </span>
                </div>
                <p className="text-body-l text-content-primary">
                  {selectedFundingAudit
                    ? `${selectedFacility.name} could help close the ${getCapabilityLabel(capability).toLowerCase()} access gap for ${fundingRegion.name}, but its current Trust Score is ${selectedFundingAudit.score} and ${selectedFundingAudit.contradictionCount} contradiction${selectedFundingAudit.contradictionCount === 1 ? '' : 's'} must be weighed before funding.`
                    : `${selectedFacility.name} is relevant to ${fundingRegion.name}, but the current evidence does not verify ${getCapabilityLabel(capability).toLowerCase()} readiness.`}
                </p>
                {selectedFundingRecommendation && (
                  <div className="mt-4 grid gap-3 md:grid-cols-3">
                    <div className="rounded-xl bg-white/72 p-3">
                      <div className="text-mono-s uppercase text-content-tertiary">Why fund</div>
                      <p className="mt-1 text-caption text-content-primary">{selectedFundingRecommendation.whyFund}</p>
                    </div>
                    <div className="rounded-xl bg-white/72 p-3">
                      <div className="text-mono-s uppercase text-content-tertiary">Risk</div>
                      <p className="mt-1 text-caption text-content-primary">{selectedFundingRecommendation.trustRisk}</p>
                    </div>
                    <div className="rounded-xl bg-white/72 p-3">
                      <div className="text-mono-s uppercase text-content-tertiary">Resolve first</div>
                      <p className="mt-1 text-caption text-content-primary">{selectedFundingRecommendation.missingResource}</p>
                    </div>
                  </div>
                )}
                <p className="mt-4 rounded-xl border border-border-subtle bg-white/62 p-3 text-caption font-medium text-content-primary">
                  {selectedFundingRecommendation?.recommendedNextStep ?? fundingRegion.recommendedAction}
                </p>
              </section>

              <section className="mt-5 rounded-2xl border border-border-subtle bg-white p-5 shadow-elevation-1">
                <div className="mb-4 flex items-start justify-between gap-4">
                  <div>
                    <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">Selected audit claim</div>
                    <h3 className="mt-1 text-heading-l text-content-primary">{getCapabilityLabel(selectedAudit.id)}</h3>
                  </div>
                  <TrustScore score={selectedAudit.score} confidenceInterval={selectedAudit.confidenceInterval} />
                </div>
                <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">Why this facility ranked here</div>
                <p className="mt-2 text-body-l text-content-primary">{getRankRationale(selectedFacility, selectedFacilityRank, activeResult)}</p>
                <p className="mt-3 text-caption text-content-secondary">
                  Deterministic score logic: score = round(confidence * 100) - severity penalties. HIGH contradictions carry a 30-point penalty.
                </p>
              </section>

              {selectedAudit.contradictions.length > 0 && (
                <section className="mt-5">
                  <div className="mb-3 flex items-center gap-2 text-caption font-semibold uppercase tracking-wider text-content-secondary">
                    <ShieldAlert className="h-4 w-4 text-semantic-critical" /> Contradictions
                  </div>
                  <div className="grid gap-3">
                    {selectedAudit.contradictions.map((contradiction) => (
                      <div key={contradiction.id} className="rounded-2xl border border-semantic-critical/20 bg-semantic-critical-subtle p-4">
                        <div className="flex items-center gap-2">
                          <span className="rounded bg-white/70 px-2 py-0.5 text-mono-s font-semibold text-semantic-critical">{contradiction.severity}</span>
                          <span className="font-mono text-caption text-content-primary">{contradiction.type}</span>
                        </div>
                        <p className="mt-2 text-body text-content-primary">{contradiction.reasoning}</p>
                        <div className="mt-3 grid grid-cols-2 gap-2 text-mono-s text-content-secondary">
                          <span>For: {contradiction.evidenceFor}</span>
                          <span>Against: {contradiction.evidenceAgainst}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <section className="mt-5">
                <div className="mb-3 flex items-center gap-2 text-caption font-semibold uppercase tracking-wider text-content-secondary">
                  <FileText className="h-4 w-4" /> Evidence trail
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {selectedAudit.evidence.map((evidence) => (
                    <div key={evidence.id} className="rounded-2xl border border-border-subtle bg-white p-4 shadow-elevation-1">
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <span className={`rounded-full px-2 py-0.5 text-mono-s uppercase ${evidence.stance === 'contradicts' ? 'bg-semantic-critical-subtle text-semantic-critical' : evidence.stance === 'verifies' ? 'bg-semantic-verified-subtle text-semantic-verified' : 'bg-surface-sunken text-content-tertiary'}`}>
                          {evidence.stance}
                        </span>
                        <span className="text-mono-s text-content-tertiary">{evidence.sourceType}</span>
                      </div>
                      <p className="text-body text-content-primary">"{evidence.snippet}"</p>
                      <p className="mt-3 text-caption text-content-secondary">{evidence.rationale}</p>
                    </div>
                  ))}
                </div>
              </section>
            </main>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
