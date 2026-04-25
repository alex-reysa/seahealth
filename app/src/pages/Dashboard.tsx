import React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Map } from '@vis.gl/react-maplibre';
import { Activity, AlertCircle, CheckCircle2, MapPin, Search, ShieldAlert, Sparkles } from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';

import { Card } from '@/src/components/ui/Card';
import { Input } from '@/src/components/ui/Input';
import { Button } from '@/src/components/ui/Button';
import { Badge } from '@/src/components/ui/Badge';
import {
  APPENDECTOMY_QUERY_RESULT,
  CAPABILITIES,
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
            '#105B58',
            selectedRegionId === 'BR_MADHUBANI',
            '#F0B8A8',
            '#DDEFEF',
          ],
          'fill-opacity': 0.9,
        },
      },
      {
        id: 'india-lines',
        type: 'line',
        source: 'india-districts',
        paint: { 'line-color': '#176D6A', 'line-opacity': 0.2, 'line-width': 1 },
      },
    ],
  } as any;
}

function SummaryStrip({ capability }: { capability: CapabilityType }) {
  const facilities = getFacilityRowsForRegion('BR_PATNA', capability);
  const verified = facilities.filter((facility) => (getCapabilityAudit(facility, capability)?.score ?? 0) >= 80).length;
  const flagged = facilities.filter((facility) => facility.totalContradictions > 0).length;

  return (
    <Card variant="glass" className="flex items-center gap-6 px-6 py-3 pointer-events-auto">
      <div className="flex flex-col">
        <span className="text-display text-content-primary">2,145</span>
        <span className="text-caption text-content-secondary uppercase tracking-wider">Audited Facilities</span>
      </div>
      <div className="w-px h-10 bg-border-default" />
      <div className="flex flex-col">
        <div className="flex items-center gap-2">
          <span className="text-heading-l text-semantic-verified">{verified}</span>
          <CheckCircle2 className="w-4 h-4 text-semantic-verified" />
        </div>
        <span className="text-caption text-content-secondary uppercase tracking-wider">Verified {getCapabilityLabel(capability)}</span>
      </div>
      <div className="w-px h-10 bg-border-default" />
      <div className="flex flex-col">
        <div className="flex items-center gap-2">
          <span className="text-heading-l text-semantic-flagged">{flagged}</span>
          <AlertCircle className="w-4 h-4 text-semantic-flagged" />
        </div>
        <span className="text-caption text-content-secondary uppercase tracking-wider">Flagged</span>
      </div>
      <div className="w-px h-10 bg-border-default" />
      <div className="flex flex-col text-right ml-auto pl-8">
        <span className="text-caption text-content-tertiary">Last Audit Build</span>
        <span className="text-mono-s text-content-secondary">14:41 UTC · query trace ready</span>
      </div>
    </Card>
  );
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

  const [command, setCommand] = React.useState(searchParams.get('q') || 'Focus Patna, appendectomy, 50 km');
  const [status, setStatus] = React.useState('Ready: appendectomy demo context loaded');

  const updateContext = (nextCommand: string) => {
    const parsed = parseDemoCommand(nextCommand);
    setStatus(`Ready: ${getCapabilityLabel(parsed.capability)} around ${parsed.location}, ${parsed.radiusKm}km`);
    setSearchParams({
      capability: parsed.capability,
      radius_km: String(parsed.radiusKm),
      region_id: parsed.regionId,
      pin_code: parsed.pinCode,
    });
    mapRef.current?.flyTo?.({
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
    setStatus('Geocoding and applying command...');
    window.setTimeout(() => updateContext(command), 250);
  };

  const onMouseMove = (event: any) => {
    if (!event.features?.length) return;
    event.target.getCanvas().style.cursor = 'pointer';
    const map = event.target;
    const featureId = event.features[0].id;
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
        onClick={() => updateContext(`Focus Patna, ${getCapabilityLabel(capability)}, ${radiusKm} km`)}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
      />

      <div className="absolute inset-0 pointer-events-none p-6 flex flex-col justify-between">
        <div className="flex justify-between items-start">
          <Card variant="glass-control" className="w-[520px] p-4 flex flex-col gap-4 pointer-events-auto">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-accent-primary" />
                <span className="text-heading-s">Agent Planner</span>
              </div>
              <Badge variant="subtle">{status}</Badge>
            </div>
            <form onSubmit={onCommandSubmit} className="relative">
              <label htmlFor="dashboard-command" className="sr-only">
                Command the map or planner
              </label>
              <Input
                id="dashboard-command"
                value={command}
                onChange={(event) => setCommand(event.target.value)}
                placeholder="Focus Patna, appendectomy, 50 km"
                className="pl-10 pr-4 py-6 text-body-l shadow-inner bg-white/70 focus:bg-white transition-all border-border-strong rounded-lg"
              />
              <Search className="w-5 h-5 text-content-tertiary absolute left-3 top-1/2 -translate-y-1/2" />
            </form>
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" size="sm" onClick={runPlanner}>
                Run Planner Query
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => navigate(`/desert-map?capability=${capability}&radius_km=${radiusKm}&region_id=${regionId}`)}
              >
                Open Desert Map
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate(`/facilities/${APPENDECTOMY_QUERY_RESULT.rankedFacilities[0]}?capability=${capability}&from=dashboard`)}
              >
                Open Top Audit
              </Button>
            </div>
            <div className="flex gap-2 text-caption text-content-secondary px-1">
              <span>Current:</span>
              <span className="font-mono text-content-primary">{capability}</span>
              <span>·</span>
              <span className="font-mono text-content-primary">{radiusKm}km</span>
              <span>·</span>
              <span className="font-mono text-content-primary">PIN {pinCode}</span>
            </div>
          </Card>

          <Card variant="glass" className="w-[360px] max-h-fit flex flex-col pointer-events-auto">
            <div className="p-4 border-b border-border-subtle bg-white/40">
              <div className="text-caption text-content-secondary mb-1 uppercase tracking-wider">Selected Region</div>
              <div className="text-heading-m mb-1">{aggregate.name}</div>
              <p className="text-caption text-content-secondary">
                {formatNumber(aggregate.gapPopulation)} people uncovered · nearest verified facility {aggregate.nearestVerifiedKm}km
              </p>
              <div className="grid grid-cols-2 gap-4 mt-4">
                <div>
                  <div className="text-heading-m">{Math.round(aggregate.coverageRatio * 100)}%</div>
                  <div className="text-caption text-content-secondary">Coverage</div>
                </div>
                <div>
                  <div className="text-heading-m text-semantic-critical">{formatNumber(aggregate.gapPopulation)}</div>
                  <div className="text-caption text-content-secondary">Gap Pop.</div>
                </div>
              </div>
            </div>
            <div className="p-4 flex flex-col gap-3">
              <div className="text-caption text-content-secondary uppercase tracking-wider">Top Facilities</div>
              {facilities.slice(0, 4).map((facility) => {
                const audit = getCapabilityAudit(facility, capability);
                if (!audit) return null;
                return (
                  <button
                    key={facility.id}
                    type="button"
                    onClick={() => navigate(`/facilities/${facility.id}?capability=${capability}&from=dashboard`)}
                    className="text-left flex flex-col gap-1 p-2 rounded hover:bg-white/50 border border-transparent hover:border-border-subtle transition-colors"
                  >
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-body font-medium">{facility.name}</span>
                      <Badge variant={audit.score >= 80 ? 'verified' : audit.score >= 50 ? 'flagged' : 'critical'}>{audit.score}</Badge>
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
                      <div className="text-caption text-semantic-critical flex items-center gap-1 mt-1">
                        <ShieldAlert className="w-3 h-3" /> {audit.contradictionCount} contradictions
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </Card>
        </div>

        <div className="flex justify-center items-end">
          <SummaryStrip capability={capability} />
        </div>
      </div>

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
