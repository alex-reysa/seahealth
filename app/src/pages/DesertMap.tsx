import React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Map, Marker } from '@vis.gl/react-maplibre';
import { AlertCircle, CheckCircle2, MapPin, RotateCcw, Search, ShieldAlert, Target } from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';

import { Card } from '@/src/components/ui/Card';
import { Button } from '@/src/components/ui/Button';
import { Input } from '@/src/components/ui/Input';
import { TrustScore } from '@/src/components/domain/TrustScore';
import {
  CAPABILITIES,
  type CapabilityType,
  formatNumber,
  getCapabilityAudit,
  getCapabilityLabel,
  getFacilityRowsForRegion,
  getRegionAggregate,
  parseDemoCommand,
} from '@/src/data/demoData';

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
      { id: 'osm', type: 'raster', source: 'osm', paint: { 'raster-opacity': 0.3, 'raster-saturation': -1 } },
      {
        id: 'india-fill',
        type: 'fill',
        source: 'india-districts',
        paint: {
          'fill-color': ['case', ['boolean', ['feature-state', 'hover'], false], '#105B58', gapColor],
          'fill-opacity': regionId ? 0.82 : 0.7,
        },
      },
      { id: 'india-lines', type: 'line', source: 'india-districts', paint: { 'line-color': '#176D6A', 'line-opacity': 0.22, 'line-width': 1 } },
    ],
  } as any;
}

export function DesertMap() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const mapRef = React.useRef<any>(null);
  const hoveredFeatureId = React.useRef<string | number | null>(null);

  const capability = (searchParams.get('capability') as CapabilityType) || 'SURGERY_APPENDECTOMY';
  const radiusKm = Number(searchParams.get('radius_km') || '50');
  const regionId = searchParams.get('region_id') || '';
  const selectedRegionId = regionId || 'BR_PATNA';
  const aggregate = getRegionAggregate(selectedRegionId, capability);
  const facilities = getFacilityRowsForRegion(selectedRegionId, capability);
  const [search, setSearch] = React.useState(searchParams.get('pin_code') || '');

  const setContext = (next: Partial<{ capability: CapabilityType; radiusKm: number; regionId: string; pinCode: string }>) => {
    const params = new URLSearchParams(searchParams);
    if (next.capability) params.set('capability', next.capability);
    if (next.radiusKm) params.set('radius_km', String(next.radiusKm));
    if (next.regionId) params.set('region_id', next.regionId);
    if (next.pinCode) params.set('pin_code', next.pinCode);
    setSearchParams(params);
  };

  const focusRegion = (command: string) => {
    const parsed = parseDemoCommand(command);
    setContext({ capability: parsed.capability, radiusKm: parsed.radiusKm, regionId: parsed.regionId, pinCode: parsed.pinCode });
    mapRef.current?.getMap()?.flyTo({
      center: parsed.regionId === 'BR_MADHUBANI' ? [86.07, 26.36] : [85.14, 25.61],
      zoom: 8,
      duration: 900,
    });
  };

  const handleSearch = (event: React.FormEvent) => {
    event.preventDefault();
    focusRegion(search || 'Patna');
  };

  const handleResetMap = () => {
    setSearchParams({ capability: 'SURGERY_APPENDECTOMY', radius_km: '50' });
    mapRef.current?.getMap()?.flyTo({ center: [78.9629, 20.5937], zoom: 4, duration: 1000 });
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
    <div className="relative w-full h-full flex flex-col bg-surface-canvas">
      <div className="h-16 bg-surface-raised border-b border-border-default flex items-center px-6 gap-4 z-10 shadow-elevation-1 shrink-0">
        <label className="flex items-center gap-2">
          <span className="text-caption text-content-secondary uppercase tracking-wider">Capability</span>
          <select
            value={capability}
            onChange={(event) => setContext({ capability: event.target.value as CapabilityType })}
            className="h-9 bg-surface-sunken border border-border-subtle rounded-md px-3 text-body font-medium focus:outline-none focus:ring-2 focus:ring-accent-primary-subtle"
          >
            {CAPABILITIES.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <div className="w-px h-6 bg-border-default mx-1" />

        <div className="flex items-center gap-2">
          <span className="text-caption text-content-secondary uppercase tracking-wider">Radius</span>
          <div className="flex bg-surface-sunken border border-border-subtle rounded-md p-0.5">
            {RADIUS_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setContext({ radiusKm: option })}
                className={`px-3 py-1 text-caption rounded-sm transition-colors ${radiusKm === option ? 'bg-white shadow-elevation-1 text-content-primary font-medium' : 'text-content-secondary hover:text-content-primary'}`}
              >
                {option}km
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={handleSearch} className="relative ml-auto w-72">
          <label htmlFor="map-search" className="sr-only">
            Search by region, facility, or PIN
          </label>
          <Input id="map-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Patna, Madhubani, or PIN" className="pl-9 bg-white/80" />
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-content-tertiary" />
        </form>

        <Button variant="ghost" size="sm" className="gap-2" onClick={handleResetMap}>
          <RotateCcw className="w-4 h-4" /> Reset Map
        </Button>
      </div>

      <div className="relative flex-1 overflow-hidden">
        <Map
          ref={mapRef}
          initialViewState={{
            longitude: regionId ? 85.14 : 78.9629,
            latitude: regionId ? 25.61 : 20.5937,
            zoom: regionId ? 7 : 4,
          }}
          mapStyle={getMapStyle(selectedRegionId, aggregate.gapPopulation)}
          style={{ width: '100%', height: '100%' }}
          interactiveLayerIds={['india-fill']}
          onClick={() => focusRegion(capability === 'NEONATAL' ? 'Madhubani neonatal 60 km' : 'Patna appendectomy 50 km')}
          onMouseMove={onMouseMove}
          onMouseLeave={onMouseLeave}
        >
          {facilities.slice(0, 3).map((facility, index) => (
            <Marker key={facility.id} longitude={facility.lng} latitude={facility.lat} anchor="center">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/facilities/${facility.id}?capability=${capability}&from=desert-map`);
                }}
                className="pointer-events-auto rounded-full border-2 border-white bg-accent-primary text-white shadow-elevation-3 w-9 h-9 text-caption font-semibold hover:scale-110 transition-transform"
                aria-label={`Open ${facility.name}`}
              >
                {index + 1}
              </button>
            </Marker>
          ))}
        </Map>

        <div className="absolute left-8 top-8 pointer-events-none">
          <Card variant="glass-control" className="w-72 p-4">
            <div className="text-caption text-content-secondary uppercase tracking-wider">Map Encoding</div>
            <div className="mt-2 text-heading-s">{getCapabilityLabel(capability)} gap population</div>
            <p className="mt-2 text-caption text-content-secondary">
              Darker red means more people uncovered within {radiusKm}km. Facility points are mocked for demo zoom tiers.
            </p>
          </Card>
        </div>

        <div className="absolute left-8 bottom-24 pointer-events-none">
          <Card variant="glass" className="flex items-center gap-6 px-6 py-3">
            <div>
              <div className="text-display text-content-primary">2,145</div>
              <div className="text-caption text-content-secondary uppercase tracking-wider">Audited Facilities</div>
            </div>
            <div className="w-px h-10 bg-border-default" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-heading-l text-semantic-verified">{aggregate.verifiedFacilitiesCount}</span>
                <CheckCircle2 className="w-4 h-4 text-semantic-verified" />
              </div>
              <div className="text-caption text-content-secondary uppercase tracking-wider">Verified in region</div>
            </div>
            <div className="w-px h-10 bg-border-default" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-heading-l text-semantic-flagged">{aggregate.flaggedFacilitiesCount}</span>
                <AlertCircle className="w-4 h-4 text-semantic-flagged" />
              </div>
              <div className="text-caption text-content-secondary uppercase tracking-wider">Flagged</div>
            </div>
          </Card>
        </div>

        <div className="absolute right-6 top-6 bottom-24 pointer-events-none z-10">
          <Card variant="glass" className="w-[420px] h-full flex flex-col overflow-hidden pointer-events-auto shadow-elevation-glass-map">
            <div className="p-6 border-b border-border-subtle bg-white/60 shrink-0">
              <div className="text-caption text-content-secondary mb-1 uppercase tracking-wider font-semibold">Selected Region</div>
              <div className="text-heading-l mb-1 text-content-primary">{regionId ? aggregate.name : 'India National View'}</div>
              <div className="text-body text-content-secondary mb-6">
                {regionId ? `${formatNumber(aggregate.gapPopulation)} people uncovered; nearest verified care ${aggregate.nearestVerifiedKm}km` : 'Select a region or PIN to inspect ranked facilities.'}
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-6">
                <div>
                  <div className="text-heading-m text-semantic-critical">{formatNumber(aggregate.gapPopulation)}</div>
                  <div className="text-caption text-content-secondary">Gap Population</div>
                </div>
                <div>
                  <div className="text-heading-m text-semantic-verified">{formatNumber(aggregate.coveredPopulation)}</div>
                  <div className="text-caption text-content-secondary">Covered Pop.</div>
                </div>
                <div>
                  <div className="text-heading-m text-semantic-verified">{Math.round(aggregate.coverageRatio * 100)}%</div>
                  <div className="text-caption text-content-secondary">Coverage Ratio</div>
                </div>
                <div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-heading-m text-content-primary">{aggregate.verifiedFacilitiesCount}</span>
                    <span className="text-mono-s text-content-secondary">{aggregate.capabilityCountCi[0]}-{aggregate.capabilityCountCi[1]}</span>
                  </div>
                  <div className="text-caption text-content-secondary">Verified Count CI</div>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-auto bg-surface-canvas/50 p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="text-caption text-content-secondary uppercase tracking-wider font-semibold">Ranked Facilities</div>
                <Target className="w-4 h-4 text-accent-primary" />
              </div>
              {facilities.length === 0 ? (
                <div className="p-8 text-center text-content-secondary border border-dashed border-border-strong rounded-md bg-surface-sunken/50">
                  No verified facilities for this capability in the selected region.
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {facilities.map((facility) => {
                    const audit = getCapabilityAudit(facility, capability);
                    if (!audit) return null;
                    return (
                      <button
                        key={facility.id}
                        type="button"
                        onClick={() => navigate(`/facilities/${facility.id}?capability=${capability}&from=desert-map`)}
                        className="text-left flex flex-col gap-2 p-4 rounded-lg bg-white border border-border-subtle hover:border-accent-primary-subtle hover:shadow-elevation-1 transition-all group"
                      >
                        <div className="flex justify-between items-start gap-3">
                          <span className="text-body-l font-medium text-content-primary group-hover:text-accent-primary transition-colors">{facility.name}</span>
                          <TrustScore score={audit.score} confidenceInterval={audit.confidenceInterval} showLabel={false} />
                        </div>
                        <div className="flex items-center gap-4 text-caption text-content-secondary">
                          <span className="flex items-center gap-1.5">
                            <MapPin className="w-3.5 h-3.5" /> {facility.distanceKm}km
                          </span>
                          <span>PIN {facility.pinCode}</span>
                          <span>{audit.evidenceCount} evidence</span>
                        </div>
                        {audit.contradictionCount > 0 && (
                          <div className="text-caption text-semantic-critical flex items-center gap-1.5 mt-1 bg-semantic-critical-subtle/50 px-2 py-1 rounded w-fit">
                            <ShieldAlert className="w-3.5 h-3.5" /> {audit.contradictionCount} contradictions
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
