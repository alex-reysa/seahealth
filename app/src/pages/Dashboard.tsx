import React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Map, Marker } from '@vis.gl/react-maplibre';
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
  Terminal,
  X,
} from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';

import { TrustScore } from '@/src/components/domain/TrustScore';
import { Button } from '@/src/components/ui/Button';
import { Card } from '@/src/components/ui/Card';
import { Input } from '@/src/components/ui/Input';
import {
  CAPABILITIES,
  CHALLENGE_QUERY,
  type CapabilityType,
  type DemoFacility,
  type DemoQueryResult,
  type DemoTraceSpan,
  formatNumber,
  getCapabilityAudit,
  getCapabilityLabel,
  getFacilityById,
  getFacilityRowsForRegion,
  getQueryResultForCommand,
  getRankedFacilities,
  getRegionAggregate,
  parseDemoCommand,
} from '@/src/data/demoData';

const INDIA_CENTER = [78.9629, 20.5937] as [number, number];
const PATNA_CENTER = [85.14, 25.61] as [number, number];
const MADHUBANI_CENTER = [86.07, 26.36] as [number, number];
const RADIUS_OPTIONS = [30, 50, 60, 120];
type SearchMode = 'semantic' | 'capability';
type AgentPanelView = 'facilities' | 'trace';

function getMapStyle(regionId: string, aggregateGapPopulation: number) {
  const gapColor = aggregateGapPopulation > 10_000_000 ? '#D88975' : '#F1C7A6';
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
            '#105B58',
            regionId === 'BR_MADHUBANI',
            '#F0B8A8',
            gapColor,
          ],
          'fill-opacity': regionId ? 0.78 : 0.58,
        },
      },
      {
        id: 'india-lines',
        type: 'line',
        source: 'india-districts',
        paint: { 'line-color': '#176D6A', 'line-opacity': 0.25, 'line-width': 1 },
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

  const parsed = parseDemoCommand(command);
  const capability = (searchParams.get('capability') as CapabilityType) || activeResult.parsedIntent.capability || parsed.capability;
  const radiusKm = Number(searchParams.get('radius_km') || activeResult.parsedIntent.radiusKm || parsed.radiusKm);
  const regionId = searchParams.get('region_id') || parsed.regionId;
  const pinCode = searchParams.get('pin_code') || parsed.pinCode;
  const aggregate = getRegionAggregate(regionId, capability);
  const regionFacilities = getFacilityRowsForRegion(regionId, capability);
  const rankedFacilities = getRankedFacilities(activeResult);
  const mapFacilities = rankedFacilities.length ? rankedFacilities : regionFacilities;
  const topFacility = mapFacilities[0];
  const selectedFacility = selectedFacilityId ? getFacilityById(selectedFacilityId) : undefined;
  const selectedFacilityRank = selectedFacility ? Math.max(1, mapFacilities.findIndex((facility) => facility.id === selectedFacility.id) + 1) : 0;
  const selectedAudit = selectedFacility ? getCapabilityAudit(selectedFacility, capability) : undefined;

  const auditedCount = 2145;
  const verifiedCount = regionFacilities.filter((facility) => (getCapabilityAudit(facility, capability)?.score ?? 0) >= 70).length;
  const flaggedCount = regionFacilities.filter((facility) => facility.totalContradictions > 0).length;
  const isRunning = activeStep !== null;

  React.useEffect(() => {
    return () => {
      timersRef.current.forEach(window.clearTimeout);
    };
  }, []);

  const focusMap = (nextRegionId: string) => {
    mapRef.current?.getMap()?.flyTo({
      center: nextRegionId === 'BR_MADHUBANI' ? MADHUBANI_CENTER : PATNA_CENTER,
      zoom: nextRegionId === 'BR_MADHUBANI' ? 8 : 7,
      duration: 900,
    });
  };

  const applyCommand = (nextCommand: string, animate = true) => {
    const nextParsed = parseDemoCommand(nextCommand);
    const nextResult = getQueryResultForCommand(nextCommand);
    timersRef.current.forEach(window.clearTimeout);
    timersRef.current = [];
    setCommand(nextCommand);
    setActiveResult(nextResult);
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
    setSelectedFacilityId(facilityId);
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
      map.setFeatureState({ source: 'india-districts', id: hoveredFeatureId.current }, { hover: false });
    }
    hoveredFeatureId.current = featureId;
    map.setFeatureState({ source: 'india-districts', id: hoveredFeatureId.current }, { hover: true });
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
          longitude: regionId === 'BR_MADHUBANI' ? MADHUBANI_CENTER[0] : PATNA_CENTER[0],
          latitude: regionId === 'BR_MADHUBANI' ? MADHUBANI_CENTER[1] : PATNA_CENTER[1],
          zoom: regionId ? 7 : 4,
        }}
        mapStyle={getMapStyle(regionId, aggregate.gapPopulation)}
        style={{ width: '100%', height: '100%' }}
        interactiveLayerIds={['india-fill']}
        onClick={() => focusMap(regionId)}
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
              className={`pointer-events-auto flex h-9 w-9 items-center justify-center rounded-full border-2 text-caption font-semibold text-white shadow-elevation-3 transition-transform hover:scale-110 ${
                index === 0 ? 'bg-semantic-critical' : 'bg-accent-primary'
              } ${selectedFacilityId === facility.id ? 'border-content-primary ring-4 ring-white/80' : 'border-white'}`}
              aria-label={`Open ${facility.name}`}
            >
              {index + 1}
            </button>
          </Marker>
        ))}
      </Map>

      <div className={`pointer-events-none absolute left-6 ${isAgentPanelOpen ? 'right-[500px]' : 'right-6'} top-5 z-20 flex flex-col gap-2 transition-all duration-300`}>
        <div className="pointer-events-auto flex flex-wrap items-center gap-2">
          <Card variant="glass" className="flex items-center gap-3 rounded-2xl bg-white/58 px-3 py-2 shadow-elevation-1">
            <div>
              <div className="text-body font-semibold text-content-primary">{auditedCount.toLocaleString()}</div>
              <div className="text-mono-s uppercase text-content-secondary">Audited</div>
            </div>
            <div className="h-7 w-px bg-border-default" />
            <div>
              <div className="flex items-center gap-1.5 text-body font-semibold text-semantic-verified">
                {verifiedCount} <CheckCircle2 className="h-3.5 w-3.5" />
              </div>
              <div className="text-mono-s uppercase text-content-secondary">Verified</div>
            </div>
            <div className="h-7 w-px bg-border-default" />
            <div>
              <div className="flex items-center gap-1.5 text-body font-semibold text-semantic-critical">
                {flaggedCount} <AlertCircle className="h-3.5 w-3.5" />
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

      <div className="pointer-events-none absolute left-6 top-24 z-10 flex items-center gap-3 rounded-full border border-border-subtle bg-white/66 px-3 py-2 text-caption text-content-secondary shadow-elevation-1 backdrop-blur-xl">
        <span className="font-semibold text-content-primary">Legend</span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-5 rounded-full bg-gradient-to-r from-[#F1C7A6] to-[#D88975]" />
          gap
        </span>
        <span className="flex items-center gap-1.5">
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-accent-primary text-[9px] font-semibold text-white">1</span>
          rank
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-semantic-critical" />
          contradiction
        </span>
      </div>

      <div
        className="absolute bottom-12 z-20 -translate-x-1/2 transition-all duration-300"
        style={{
          left: isAgentPanelOpen ? 'calc((100% - 500px) / 2)' : '50%',
          width: isAgentPanelOpen ? 'min(720px, calc(100% - 540px))' : 'min(760px, calc(100% - 48px))',
        }}
      >
        <form onSubmit={onCommandSubmit} className="pointer-events-auto">
          <div className="glass-control flex flex-col gap-3 rounded-3xl p-3">
            <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border-subtle bg-white/64 px-3 py-2">
              <div className="flex rounded-full bg-surface-sunken p-1">
                {([
                  ['semantic', 'Semantic request'],
                  ['capability', 'Capability search'],
                ] as Array<[SearchMode, string]>).map(([mode, label]) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setSearchMode(mode)}
                    className={`rounded-full px-3 py-1.5 text-caption font-semibold transition-colors ${
                      searchMode === mode ? 'bg-white text-content-primary shadow-elevation-1' : 'text-content-secondary hover:text-content-primary'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="text-caption text-content-secondary">
                {searchMode === 'semantic'
                  ? 'Ask the agent in plain language. It infers capability, location, and ranking intent.'
                  : 'Use explicit filters for faster postal-code and capability searches.'}
              </div>
              <Button variant="ghost" size="sm" className="ml-auto h-8 gap-1.5 px-2 text-caption" onClick={handleResetMap}>
                <RotateCcw className="h-3.5 w-3.5" /> Reset
              </Button>
            </div>

            {searchMode === 'capability' && (
              <div className="grid grid-cols-[1.1fr_auto_0.8fr] gap-2 rounded-2xl border border-border-subtle bg-white/58 p-2">
                <label className="flex items-center gap-2 rounded-xl bg-white/70 px-3 py-2">
                  <span className="text-mono-s uppercase text-content-secondary">Capability</span>
                  <select
                    value={capability}
                    onChange={(event) => updateContext({ capability: event.target.value as CapabilityType })}
                    className="min-w-0 flex-1 bg-transparent text-caption font-semibold text-content-primary focus:outline-none"
                  >
                    {CAPABILITIES.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="flex items-center gap-2 rounded-xl bg-white/70 px-3 py-2">
                  <span className="text-mono-s uppercase text-content-secondary">Radius</span>
                  <div className="flex rounded-md bg-surface-sunken p-0.5">
                    {RADIUS_OPTIONS.map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => updateContext({ radiusKm: option })}
                        className={`rounded px-2.5 py-1 text-mono-s transition-colors ${
                          radiusKm === option ? 'bg-white text-content-primary shadow-elevation-1' : 'text-content-secondary hover:text-content-primary'
                        }`}
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="relative rounded-xl bg-white/70">
                  <label htmlFor="map-region-search" className="sr-only">
                    Search by region or PIN
                  </label>
                  <Input
                    id="map-region-search"
                    value={regionSearch}
                    onChange={(event) => setRegionSearch(event.target.value)}
                    placeholder={`PIN ${pinCode}`}
                    className="h-full border-0 bg-transparent pl-8 text-caption shadow-none"
                  />
                  <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-content-tertiary" />
                </div>
              </div>
            )}

            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-primary-subtle">
                <Command className="h-4 w-4 text-accent-primary" />
              </div>
              <input
                type="text"
                value={searchMode === 'semantic' ? command : capabilityDetails}
                onChange={(event) => (searchMode === 'semantic' ? setCommand(event.target.value) : setCapabilityDetails(event.target.value))}
                placeholder={searchMode === 'semantic' ? CHALLENGE_QUERY : 'Optional details, e.g. part-time doctors or night coverage'}
                className="flex-1 border-none bg-transparent text-body-l text-content-primary outline-none placeholder:text-content-tertiary"
              />
              <Button type="submit" variant="primary" className="gap-2 !text-white hover:!text-white disabled:!text-white" disabled={isRunning}>
                <Play className="h-4 w-4" />
                {isRunning ? 'Running' : searchMode === 'semantic' ? 'Run Agent' : 'Search'}
              </Button>
            </div>
          </div>
        </form>
      </div>

      <div className="absolute bottom-0 inset-x-0 z-10 flex h-8 items-center gap-4 border-t border-border-default bg-surface-raised px-4 text-mono-s text-content-tertiary">
        <span className="flex items-center gap-1">
          <CheckCircle2 className="h-3 w-3" /> Map Workbench active
        </span>
        <span className="flex items-center gap-1">
          <Terminal className="h-3 w-3" /> Query trace {activeResult.queryTraceId}
        </span>
        <span className="flex items-center gap-1">
          <AlertCircle className="h-3 w-3" /> Backend detached mock events
        </span>
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
                  {isRunning ? 'Searching facilities' : 'Ranked facilities'}
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
                <div className="text-caption text-content-tertiary">Selected Region</div>
                <div className="mt-1 text-heading-s text-content-primary">{aggregate.name}</div>
              </div>
              <div className="rounded-lg bg-white/65 p-3">
                <div className="text-caption text-content-tertiary">Gap Population</div>
                <div className="mt-1 text-heading-s text-semantic-critical">{formatNumber(aggregate.gapPopulation)}</div>
              </div>
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
                ['facilities', 'Facilities'],
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
                    <Target className="h-4 w-4" /> Ranked Facilities
                  </div>
                  <span className="text-caption text-content-tertiary">{activeResult.totalCandidates} candidates</span>
                </div>

                <div className="mt-3 flex flex-col gap-2">
                  {mapFacilities.slice(0, 5).map((facility, index) => {
                    const audit = getCapabilityAudit(facility, capability);
                    if (!audit) return null;
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
                                <FileText className="h-3.5 w-3.5" /> {audit.evidenceCount} evidence
                              </span>
                            </div>
                          </div>
                          <TrustScore score={audit.score} confidenceInterval={audit.confidenceInterval} showLabel={false} />
                        </div>
                        {audit.contradictionCount > 0 && (
                          <div className="mt-2 inline-flex items-center gap-1.5 rounded bg-semantic-critical-subtle px-2 py-1 text-caption text-semantic-critical">
                            <ShieldAlert className="h-3.5 w-3.5" /> {audit.contradictionCount} contradictions, HIGH visible
                          </div>
                        )}
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

      {selectedFacility && selectedAudit && (
        <div
          className="absolute bottom-10 top-20 z-30 w-[430px] pointer-events-auto"
          style={{ right: isAgentPanelOpen ? 496 : 24 }}
        >
          <div className="glass-elevated flex h-full flex-col overflow-hidden rounded-2xl">
            <div className="border-b border-border-subtle bg-white/50 p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">
                    Facility detail / selected capability
                  </div>
                  <h2 className="mt-1 text-heading-l text-content-primary">{selectedFacility.name}</h2>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-caption text-content-secondary">
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
                  className="rounded-full border border-border-subtle bg-white/70 p-1.5 text-content-tertiary transition-colors hover:text-content-primary"
                  aria-label="Close facility detail"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="mt-4 grid grid-cols-[1fr_auto] items-center gap-4 rounded-xl border border-border-subtle bg-white/62 p-3">
                <div>
                  <div className="text-mono-s uppercase text-content-tertiary">Selected capability</div>
                  <div className="mt-1 text-heading-s text-content-primary">{getCapabilityLabel(capability)}</div>
                </div>
                <TrustScore score={selectedAudit.score} confidenceInterval={selectedAudit.confidenceInterval} />
              </div>
            </div>

            <div className="flex-1 overflow-auto p-5">
              <section className="rounded-xl border border-border-subtle bg-white/72 p-4">
                <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">Why this facility ranked here</div>
                <p className="mt-2 text-body text-content-primary">{getRankRationale(selectedFacility, selectedFacilityRank, activeResult)}</p>
              </section>

              <section className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-border-subtle bg-white/72 p-3">
                  <div className="text-mono-s uppercase text-content-tertiary">Evidence</div>
                  <div className="mt-1 text-heading-m text-content-primary">{selectedAudit.evidenceCount}</div>
                </div>
                <div className="rounded-xl border border-border-subtle bg-white/72 p-3">
                  <div className="text-mono-s uppercase text-content-tertiary">Contradictions</div>
                  <div className={`mt-1 text-heading-m ${selectedAudit.contradictionCount > 0 ? 'text-semantic-critical' : 'text-semantic-verified'}`}>
                    {selectedAudit.contradictionCount}
                  </div>
                </div>
              </section>

              {selectedAudit.contradictions.length > 0 && (
                <section className="mt-4">
                  <div className="mb-2 flex items-center gap-2 text-caption font-semibold uppercase tracking-wider text-content-secondary">
                    <ShieldAlert className="h-4 w-4 text-semantic-critical" /> Contradictions
                  </div>
                  <div className="flex flex-col gap-2">
                    {selectedAudit.contradictions.slice(0, 2).map((contradiction) => (
                      <div key={contradiction.id} className="rounded-xl border border-semantic-critical/20 bg-semantic-critical-subtle p-3">
                        <div className="flex items-center gap-2">
                          <span className="rounded bg-white/70 px-2 py-0.5 text-mono-s font-semibold text-semantic-critical">{contradiction.severity}</span>
                          <span className="font-mono text-caption text-content-primary">{contradiction.type}</span>
                        </div>
                        <p className="mt-2 text-caption text-content-primary">{contradiction.reasoning}</p>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <section className="mt-4">
                <details className="group rounded-xl border border-border-subtle bg-white/72">
                  <summary className="flex cursor-pointer list-none items-center justify-between p-4">
                    <span className="flex items-center gap-2 text-caption font-semibold uppercase tracking-wider text-content-secondary">
                      <FileText className="h-4 w-4" /> Evidence preview
                    </span>
                    <ChevronRight className="h-4 w-4 text-content-tertiary transition-transform group-open:rotate-90" />
                  </summary>
                  <div className="border-t border-border-subtle p-4">
                    <div className="flex flex-col gap-3">
                      {selectedAudit.evidence.slice(0, 3).map((evidence) => (
                        <div key={evidence.id} className="rounded-lg bg-surface-sunken p-3">
                          <div className="mb-1 flex items-center justify-between gap-2">
                            <span className={`text-mono-s uppercase ${evidence.stance === 'contradicts' ? 'text-semantic-critical' : evidence.stance === 'verifies' ? 'text-semantic-verified' : 'text-content-tertiary'}`}>
                              {evidence.stance}
                            </span>
                            <span className="text-mono-s text-content-tertiary">{evidence.sourceType}</span>
                          </div>
                          <p className="text-caption text-content-primary">"{evidence.snippet}"</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </details>
              </section>
            </div>

            <div className="border-t border-border-subtle bg-white/60 p-4">
              <Button
                type="button"
                variant="secondary"
                className="w-full gap-2"
                onClick={() => navigate(`/facilities/${selectedFacility.id}?capability=${capability}&from=map-workbench&q=${encodeURIComponent(command)}`)}
              >
                <ExternalLink className="h-4 w-4" />
                Open full audit
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
