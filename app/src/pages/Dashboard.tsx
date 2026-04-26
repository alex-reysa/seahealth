import React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Map } from '@vis.gl/react-maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Command,
  MapPin,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';

import { TrustScore } from '@/src/components/domain/TrustScore';
import {
  APPENDECTOMY_QUERY_RESULT,
  DEMO_QUERY,
  type CapabilityType,
  formatNumber,
  getCapabilityAudit,
  getCapabilityLabel,
  getFacilityRowsForRegion,
  getRegionAggregate,
  parseDemoCommand,
} from '@/src/data/demoData';

const INDIA_CENTER = [78.9629, 20.5937] as [number, number];
const PATNA_CENTER = [85.14, 25.61] as [number, number];

function getMapStyle(selectedRegionId: string) {
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
        paint: { 'raster-opacity': 0.3, 'raster-saturation': -1 },
      },
      {
        id: 'india-fill',
        type: 'fill',
        source: 'india-districts',
        paint: {
          'fill-color': [
            'case',
            ['boolean', ['feature-state', 'hover'], false],
            '#176D6A',
            selectedRegionId === 'BR_MADHUBANI',
            '#F0B8A8',
            '#A9DBD7',
          ],
          'fill-opacity': [
            'case',
            ['boolean', ['feature-state', 'hover'], false],
            0.6,
            0.4,
          ],
        },
      },
      {
        id: 'india-lines',
        type: 'line',
        source: 'india-districts',
        paint: { 'line-color': '#176D6A', 'line-opacity': 0.3, 'line-width': 1 },
      },
    ],
  } as any;
}

export function Dashboard() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const mapRef = React.useRef<any>(null);
  const hoveredFeatureId = React.useRef<string | number | null>(null);

  const capability = (searchParams.get('capability') as CapabilityType) || 'SURGERY_APPENDECTOMY';
  const radiusKm = Number(searchParams.get('radius_km') || '50');
  const regionId = searchParams.get('region_id') || 'BR_PATNA';
  const pinCode = searchParams.get('pin_code') || '800001';
  const aggregate = getRegionAggregate(regionId, capability);
  const facilities = getFacilityRowsForRegion(regionId, capability);

  const auditedCount = 2145;
  const verifiedCount = facilities.filter(
    (f) => (getCapabilityAudit(f, capability)?.score ?? 0) >= 70,
  ).length;
  const flaggedCount = facilities.filter((f) => f.totalContradictions > 0).length;

  const [command, setCommand] = React.useState(searchParams.get('q') || 'Focus Patna, appendectomy, 50 km');
  const [status, setStatus] = React.useState<'ready' | 'pending'>('ready');
  const [statusLabel, setStatusLabel] = React.useState(`Ready: ${getCapabilityLabel(capability)} · ${radiusKm}km`);

  const updateContext = (nextCommand: string) => {
    const parsed = parseDemoCommand(nextCommand);
    setStatus('ready');
    setStatusLabel(`Ready: ${getCapabilityLabel(parsed.capability)} · ${parsed.location} · ${parsed.radiusKm}km`);
    setSearchParams({
      q: nextCommand,
      capability: parsed.capability,
      radius_km: String(parsed.radiusKm),
      region_id: parsed.regionId,
      pin_code: parsed.pinCode,
    });
    mapRef.current?.getMap()?.flyTo({
      center: parsed.regionId === 'BR_MADHUBANI' ? [86.07, 26.36] : PATNA_CENTER,
      zoom: parsed.regionId === 'BR_PATNA' ? 7 : 8,
      duration: 900,
    });
  };

  const runPlanner = () => {
    const q = command.toLowerCase().includes('which facilities') ? command : DEMO_QUERY;
    navigate(`/planner-query?q=${encodeURIComponent(q)}`);
  };

  const onCommandSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setStatus('pending');
    setStatusLabel('Geocoding…');
    window.setTimeout(() => updateContext(command), 250);
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
      event.target.setFeatureState(
        { source: 'india-districts', id: hoveredFeatureId.current },
        { hover: false },
      );
      hoveredFeatureId.current = null;
    }
  };

  const topFacilityId = React.useMemo(() => {
    if (capability === 'SURGERY_APPENDECTOMY' && regionId === 'BR_PATNA') {
      return APPENDECTOMY_QUERY_RESULT.rankedFacilities[0];
    }
    const rows = getFacilityRowsForRegion(regionId, capability);
    return rows.length > 0 ? rows[0].id : APPENDECTOMY_QUERY_RESULT.rankedFacilities[0];
  }, [capability, regionId]);

  return (
    <div className="relative w-full h-full">
      <Map
        ref={mapRef}
        initialViewState={{
          longitude: regionId === 'BR_PATNA' ? PATNA_CENTER[0] : INDIA_CENTER[0],
          latitude: regionId === 'BR_PATNA' ? PATNA_CENTER[1] : INDIA_CENTER[1],
          zoom: regionId === 'BR_PATNA' ? 7 : 4,
        }}
        mapStyle={getMapStyle(regionId)}
        style={{ width: '100%', height: '100%' }}
        interactiveLayerIds={['india-fill']}
        onClick={() => updateContext(`Focus ${regionId === 'BR_MADHUBANI' ? 'Madhubani' : 'Patna'}, ${getCapabilityLabel(capability)}, ${radiusKm} km`)}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
      />

      {/* TOP-LEFT SUMMARY PILLS */}
      <div className="absolute top-6 left-6 right-6 z-10 flex gap-3 pointer-events-none flex-wrap">
        <div className="pointer-events-auto flex items-center gap-2 px-4 py-2 glass-standard rounded-xl">
          <span className="text-content-secondary text-caption">Audited Facilities</span>
          <span className="font-mono font-medium text-content-primary">
            {auditedCount.toLocaleString()}
          </span>
        </div>
        <div className="pointer-events-auto flex items-center gap-2 px-4 py-2 glass-standard rounded-xl border-l-[3px] border-semantic-verified">
          <ShieldCheck className="w-4 h-4 text-semantic-verified" />
          <span className="text-content-secondary text-caption">Verified</span>
          <span className="font-mono font-medium text-content-primary">{verifiedCount}</span>
        </div>
        <div className="pointer-events-auto flex items-center gap-2 px-4 py-2 glass-standard rounded-xl border-l-[3px] border-semantic-flagged">
          <AlertTriangle className="w-4 h-4 text-semantic-flagged" />
          <span className="text-content-secondary text-caption">Flagged</span>
          <span className="font-mono font-medium text-content-primary">{flaggedCount}</span>
        </div>
        <div className="pointer-events-auto flex items-center gap-2 px-4 py-2 glass-standard rounded-xl">
          <span className="text-content-secondary text-caption">Capability:</span>
          <span className="text-content-primary text-caption font-medium font-mono">{capability}</span>
        </div>
        <div className="pointer-events-auto flex items-center gap-2 px-4 py-2 glass-standard rounded-xl">
          <span className="text-content-secondary text-caption">PIN</span>
          <span className="text-content-primary text-caption font-medium font-mono">{pinCode}</span>
          <span className="text-content-tertiary text-caption">·</span>
          <span className="text-content-secondary text-caption">{radiusKm}km</span>
        </div>
      </div>

      {/* RIGHT TELEMETRY PANEL */}
      <div className="absolute top-24 right-6 bottom-24 w-[360px] z-10 pointer-events-auto">
        <div className="glass-elevated rounded-xl flex flex-col h-full overflow-hidden">
          <div className="p-5 border-b border-border-subtle bg-white/40 shrink-0">
            <div className="text-caption text-content-secondary uppercase tracking-wider">
              Selected Region
            </div>
            <div className="text-heading-m text-content-primary mt-0.5">{aggregate.name}</div>
            <p className="text-caption text-content-secondary mt-2">
              {formatNumber(aggregate.gapPopulation)} uncovered · nearest verified facility{' '}
              {aggregate.nearestVerifiedKm}km
            </p>

            <div className="grid grid-cols-2 gap-x-4 gap-y-4 mt-5">
              <div>
                <div className="text-heading-m text-semantic-critical">
                  {formatNumber(aggregate.gapPopulation)}
                </div>
                <div className="text-caption text-content-secondary">Gap Population</div>
              </div>
              <div>
                <div className="text-heading-m text-semantic-verified">
                  {formatNumber(aggregate.coveredPopulation)}
                </div>
                <div className="text-caption text-content-secondary">Covered Pop.</div>
              </div>
              <div>
                <div className="text-heading-m text-semantic-verified">
                  {Math.round(aggregate.coverageRatio * 100)}%
                </div>
                <div className="text-caption text-content-secondary">Coverage Ratio</div>
              </div>
              <div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-heading-m text-content-primary">
                    {aggregate.verifiedFacilitiesCount}
                  </span>
                  <span className="text-mono-s text-content-secondary">
                    CI {aggregate.capabilityCountCi[0]}–{aggregate.capabilityCountCi[1]}
                  </span>
                </div>
                <div className="text-caption text-content-secondary">Verified Count</div>
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-auto">
            <div className="p-5">
              <div className="text-caption text-content-secondary uppercase tracking-wider font-semibold mb-3">
                Top Facilities
              </div>

              {facilities.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-6 text-center text-content-secondary border border-dashed border-border-default rounded-md bg-surface-sunken/50">
                  <span className="text-body font-medium mb-1 text-content-primary">No matches</span>
                  <span className="text-caption">
                    No audited facilities for this capability in this region.
                  </span>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  {facilities.slice(0, 4).map((facility) => {
                    const audit = getCapabilityAudit(facility, capability);
                    if (!audit) return null;
                    return (
                      <button
                        key={facility.id}
                        type="button"
                        onClick={() =>
                          navigate(
                            `/facilities/${facility.id}?capability=${capability}&from=dashboard`,
                          )
                        }
                        className="text-left flex flex-col gap-1.5 p-3 rounded-lg bg-white/70 border border-border-subtle hover:border-accent-primary-soft hover:bg-white cursor-pointer transition-all group"
                      >
                        <div className="flex justify-between items-start gap-2">
                          <span className="text-body font-medium text-content-primary group-hover:text-accent-primary transition-colors">
                            {facility.name}
                          </span>
                          <TrustScore score={audit.score} confidenceInterval={audit.confidenceInterval} showLabel={false} />
                        </div>
                        <div className="flex items-center gap-3 text-caption text-content-secondary">
                          <span className="flex items-center gap-1">
                            <MapPin className="w-3 h-3" /> {facility.distanceKm}km
                          </span>
                          <span className="flex items-center gap-1">
                            <Activity className="w-3 h-3" /> {audit.evidenceCount} evidence
                          </span>
                        </div>
                        {audit.contradictionCount > 0 && (
                          <div className="text-caption text-semantic-critical flex items-center gap-1 mt-0.5">
                            <ShieldAlert className="w-3 h-3" /> {audit.contradictionCount}{' '}
                            contradictions
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* BOTTOM-CENTER QUICK ACTIONS + COMMAND BAR */}
      <div className="absolute bottom-12 left-1/2 -translate-x-1/2 w-full max-w-2xl px-6 z-20 flex flex-col items-center gap-2">
        <div className="flex gap-2 pointer-events-auto">
          <button
            type="button"
            onClick={runPlanner}
            className="px-3 py-1.5 text-caption font-medium glass-standard rounded-full text-content-primary hover:text-accent-primary transition-colors"
          >
            Run Planner
          </button>
          <button
            type="button"
            onClick={() =>
              navigate(
                `/desert-map?capability=${capability}&radius_km=${radiusKm}&region_id=${regionId}`,
              )
            }
            className="px-3 py-1.5 text-caption font-medium glass-standard rounded-full text-content-primary hover:text-accent-primary transition-colors"
          >
            Open Desert Map
          </button>
          <button
            type="button"
            onClick={() =>
              navigate(`/facilities/${topFacilityId}?capability=${capability}&from=dashboard`)
            }
            className="px-3 py-1.5 text-caption font-medium glass-standard rounded-full text-content-primary hover:text-accent-primary transition-colors"
          >
            Open Top Audit
          </button>
        </div>

        <form onSubmit={onCommandSubmit} className="w-full">
          <div className="glass-control rounded-2xl p-3 flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-accent-primary-subtle flex items-center justify-center shrink-0">
              <Command className="w-4 h-4 text-accent-primary" />
            </div>
            <input
              type="text"
              value={command}
              onChange={(event) => setCommand(event.target.value)}
              placeholder="Focus Patna, appendectomy, 50 km"
              className="flex-1 bg-transparent border-none outline-none text-body-l placeholder:text-content-tertiary text-content-primary"
            />
            <div
              className={`shrink-0 flex items-center gap-2 text-caption px-3 ${
                status === 'ready' ? 'text-semantic-verified' : 'text-semantic-flagged'
              }`}
            >
              <span className="relative flex h-2 w-2">
                {status === 'ready' && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-semantic-verified opacity-75" />
                )}
                <span
                  className={`relative inline-flex rounded-full h-2 w-2 ${
                    status === 'ready' ? 'bg-semantic-verified' : 'bg-semantic-flagged'
                  }`}
                />
              </span>
              <span className="whitespace-nowrap">{statusLabel}</span>
            </div>
          </div>
        </form>
      </div>

      {/* BOTTOM STATUS BAND */}
      <div className="absolute bottom-0 inset-x-0 h-8 bg-surface-raised border-t border-border-default flex items-center px-4 text-mono-s text-content-tertiary gap-4 z-10 pointer-events-auto">
        <span className="flex items-center gap-1">
          <CheckCircle2 className="w-3 h-3" /> Mock gold audit data loaded
        </span>
        <span className="flex items-center gap-1">
          <CheckCircle2 className="w-3 h-3" /> Query trace {APPENDECTOMY_QUERY_RESULT.queryTraceId}
        </span>
        <span className="flex items-center gap-1">
          <AlertCircle className="w-3 h-3" /> Backend detached
        </span>
      </div>
    </div>
  );
}
