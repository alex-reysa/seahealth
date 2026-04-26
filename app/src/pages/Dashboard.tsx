import React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Map, Marker } from '@vis.gl/react-maplibre';
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Command,
  FileText,
  MapPin,
  Play,
  RotateCcw,
  Search,
  ShieldAlert,
  Target,
  Terminal,
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
  type DemoQueryResult,
  type DemoTraceSpan,
  formatNumber,
  getCapabilityAudit,
  getCapabilityLabel,
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
        setActiveStep(index + 1 >= nextResult.spans.length ? null : index + 1);
      }, 260 + index * 190);
      timersRef.current.push(timer);
    });
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
    applyCommand(command);
  };

  const handleRegionSearch = (event: React.FormEvent) => {
    event.preventDefault();
    const nextCommand = regionSearch || command;
    applyCommand(nextCommand);
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
                navigate(`/facilities/${facility.id}?capability=${capability}&from=map-workbench&q=${encodeURIComponent(command)}`);
              }}
              className={`pointer-events-auto flex h-9 w-9 items-center justify-center rounded-full border-2 border-white text-caption font-semibold text-white shadow-elevation-3 transition-transform hover:scale-110 ${
                index === 0 ? 'bg-semantic-critical' : 'bg-accent-primary'
              }`}
              aria-label={`Open ${facility.name}`}
            >
              {index + 1}
            </button>
          </Marker>
        ))}
      </Map>

      <div className="pointer-events-none absolute left-6 right-[470px] top-5 z-20 flex flex-col gap-3">
        <div className="pointer-events-auto flex flex-wrap items-center gap-3 rounded-2xl border border-border-subtle bg-white/78 p-3 shadow-elevation-glass-map backdrop-blur-xl">
          <label className="flex items-center gap-2">
            <span className="text-caption uppercase tracking-wider text-content-secondary">Capability</span>
            <select
              value={capability}
              onChange={(event) => updateContext({ capability: event.target.value as CapabilityType })}
              className="h-9 rounded-md border border-border-subtle bg-white px-3 text-body font-medium focus:outline-none focus:ring-2 focus:ring-accent-primary-subtle"
            >
              {CAPABILITIES.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <div className="h-6 w-px bg-border-default" />

          <div className="flex items-center gap-2">
            <span className="text-caption uppercase tracking-wider text-content-secondary">Radius</span>
            <div className="flex rounded-md border border-border-subtle bg-surface-sunken p-0.5">
              {RADIUS_OPTIONS.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => updateContext({ radiusKm: option })}
                  className={`rounded-sm px-3 py-1 text-caption transition-colors ${
                    radiusKm === option ? 'bg-white font-medium text-content-primary shadow-elevation-1' : 'text-content-secondary hover:text-content-primary'
                  }`}
                >
                  {option}km
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={handleRegionSearch} className="relative ml-auto w-72">
            <label htmlFor="map-region-search" className="sr-only">
              Search by region or PIN
            </label>
            <Input
              id="map-region-search"
              value={regionSearch}
              onChange={(event) => setRegionSearch(event.target.value)}
              placeholder="Patna, rural Bihar, or PIN"
              className="bg-white pl-9"
            />
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-content-tertiary" />
          </form>

          <Button variant="ghost" size="sm" className="gap-2" onClick={handleResetMap}>
            <RotateCcw className="h-4 w-4" /> Reset
          </Button>
        </div>

        <div className="pointer-events-auto flex flex-wrap items-center gap-3">
          <Card variant="glass" className="flex items-center gap-5 rounded-2xl px-5 py-3">
            <div>
              <div className="text-heading-m text-content-primary">{auditedCount.toLocaleString()}</div>
              <div className="text-caption uppercase tracking-wider text-content-secondary">Audited Facilities</div>
            </div>
            <div className="h-9 w-px bg-border-default" />
            <div>
              <div className="flex items-center gap-2 text-heading-m text-semantic-verified">
                {verifiedCount} <CheckCircle2 className="h-4 w-4" />
              </div>
              <div className="text-caption uppercase tracking-wider text-content-secondary">Verified in Region</div>
            </div>
            <div className="h-9 w-px bg-border-default" />
            <div>
              <div className="flex items-center gap-2 text-heading-m text-semantic-critical">
                {flaggedCount} <AlertCircle className="h-4 w-4" />
              </div>
              <div className="text-caption uppercase tracking-wider text-content-secondary">Flagged</div>
            </div>
            <div className="h-9 w-px bg-border-default" />
            <div>
              <div className="text-heading-m text-content-primary">{new Date(activeResult.generatedAt).toLocaleTimeString()}</div>
              <div className="text-caption uppercase tracking-wider text-content-secondary">Generated</div>
            </div>
          </Card>
        </div>
      </div>

      <Card variant="glass" className="pointer-events-none absolute bottom-16 left-6 z-10 w-80 p-4">
        <div className="text-caption uppercase tracking-wider text-content-secondary">Map Encoding</div>
        <div className="mt-2 text-heading-s">{getCapabilityLabel(capability)} gap population</div>
        <p className="mt-2 text-caption text-content-secondary">
          Darker red means more people uncovered within {radiusKm}km. Numbered markers reflect the active agent ranking.
        </p>
      </Card>

      <div className="absolute bottom-5 left-6 right-[470px] z-20">
        <form onSubmit={onCommandSubmit} className="pointer-events-auto max-w-4xl">
          <div className="glass-control flex items-center gap-3 rounded-2xl p-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-primary-subtle">
              <Command className="h-4 w-4 text-accent-primary" />
            </div>
            <input
              type="text"
              value={command}
              onChange={(event) => setCommand(event.target.value)}
              placeholder={CHALLENGE_QUERY}
              className="flex-1 border-none bg-transparent text-body-l text-content-primary outline-none placeholder:text-content-tertiary"
            />
            <Button type="submit" variant="primary" className="gap-2" disabled={isRunning}>
              <Play className="h-4 w-4" />
              {isRunning ? 'Running' : 'Run Agent'}
            </Button>
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

      <aside className="absolute bottom-10 right-6 top-5 z-30 w-[430px]">
        <div className="glass-elevated flex h-full flex-col overflow-hidden rounded-2xl">
          <div className="border-b border-border-subtle bg-white/45 p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">Agent Run Panel</div>
                <h1 className="mt-1 text-heading-l text-content-primary">Map Workbench</h1>
              </div>
              <div className={`rounded-full px-3 py-1 text-caption font-semibold ${isRunning ? 'bg-semantic-flagged-subtle text-semantic-flagged' : 'bg-semantic-verified-subtle text-semantic-verified'}`}>
                {isRunning ? 'Running tools' : 'Run complete'}
              </div>
            </div>
            <p className="mt-3 line-clamp-2 text-body text-content-secondary">{activeResult.query}</p>
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
                  onClick={() => navigate(`/facilities/${topFacility.id}?capability=${capability}&from=map-workbench&q=${encodeURIComponent(command)}`)}
                  className="rounded-full border border-border-default bg-white/70 px-3 py-1 text-content-primary transition-colors hover:border-accent-primary-soft"
                >
                  Open top audit
                </button>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-auto p-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2 text-caption font-semibold uppercase tracking-wider text-content-secondary">
                <Clock3 className="h-4 w-4" /> Execution Timeline
              </div>
              <span className="text-mono-s text-content-tertiary">{activeResult.queryTraceId}</span>
            </div>
            <AgentTimeline result={activeResult} activeStep={activeStep} />

            <div className="mt-6 flex items-center justify-between">
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
                    onClick={() => navigate(`/facilities/${facility.id}?capability=${capability}&from=map-workbench&q=${encodeURIComponent(command)}`)}
                    className="group rounded-lg border border-border-subtle bg-white/75 p-3 text-left transition-all hover:border-accent-primary-soft hover:bg-white"
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
          </div>
        </div>
      </aside>
    </div>
  );
}
