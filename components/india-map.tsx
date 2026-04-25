"use client";

import * as React from "react";
import { Map, Source, Layer, NavigationControl } from "@vis.gl/react-maplibre";
import type { MapRef, MapLayerMouseEvent } from "@vis.gl/react-maplibre";
import { cn } from "@/lib/utils";
import { INDIA_BOUNDS, INDIA_CENTER } from "@/lib/mock-data";
import type { MapRegionAggregate } from "@/lib/types";

interface IndiaMapProps {
  regions?: MapRegionAggregate[];
  selectedRegionId?: string | null;
  onRegionClick?: (region: MapRegionAggregate | null) => void;
  onRegionHover?: (region: MapRegionAggregate | null) => void;
  showFacilities?: boolean;
  className?: string;
}

// Sober, low-saturation ramp aligned with semantic/critical brand color.
// Used for gap_population: low gap → near-transparent warm cream, high gap → deep muted brick.
const GAP_COLOR_RAMP = [
  "#EAD8C5",
  "#D7AF92",
  "#C2876A",
  "#A4473E",
  "#7A2E2A",
];

function getColorForGap(gapPopulation: number, maxGap: number): string {
  if (maxGap <= 0) return GAP_COLOR_RAMP[0];
  const ratio = Math.min(gapPopulation / maxGap, 1);
  const index = Math.min(
    GAP_COLOR_RAMP.length - 1,
    Math.floor(ratio * GAP_COLOR_RAMP.length)
  );
  return GAP_COLOR_RAMP[index];
}

// Slightly larger than INDIA_BOUNDS so the user can pan/zoom a bit but
// not drift off into the rest of Asia.
const MAX_BOUNDS: [[number, number], [number, number]] = [
  [60, 2],
  [102, 40],
];

export function IndiaMap({
  regions = [],
  selectedRegionId,
  onRegionClick,
  onRegionHover,
  className,
}: IndiaMapProps) {
  const mapRef = React.useRef<MapRef>(null);
  const [viewState, setViewState] = React.useState({
    longitude: INDIA_CENTER[0],
    latitude: INDIA_CENTER[1],
    zoom: 4.2,
  });
  const [hoveredRegionId, setHoveredRegionId] = React.useState<string | null>(
    null
  );
  const [isLoading, setIsLoading] = React.useState(true);

  const maxGap = React.useMemo(() => {
    return Math.max(...regions.map((r) => r.gap_population), 1);
  }, [regions]);

  const regionsGeoJson = React.useMemo(() => {
    return {
      type: "FeatureCollection" as const,
      features: regions.map((region) => ({
        type: "Feature" as const,
        id: region.region_id,
        properties: {
          region_id: region.region_id,
          region_name: region.region_name,
          gap_population: region.gap_population,
          coverage_ratio: region.coverage_ratio,
          verified_count: region.verified_capability_count,
          color: getColorForGap(region.gap_population, maxGap),
        },
        geometry: {
          type: "Point" as const,
          coordinates: [region.centroid.lng, region.centroid.lat],
        },
      })),
    };
  }, [regions, maxGap]);

  const handleMapLoad = React.useCallback(() => {
    setIsLoading(false);
    if (mapRef.current) {
      mapRef.current.fitBounds(INDIA_BOUNDS, {
        padding: { top: 80, bottom: 80, left: 80, right: 80 },
        duration: 800,
      });
    }
  }, []);

  const handleClick = React.useCallback(
    (e: MapLayerMouseEvent) => {
      const feature = e.features?.[0];
      if (feature && onRegionClick) {
        const region = regions.find(
          (r) => r.region_id === feature.properties?.region_id
        );
        onRegionClick(region || null);
      }
    },
    [regions, onRegionClick]
  );

  const handleMouseMove = React.useCallback(
    (e: MapLayerMouseEvent) => {
      const feature = e.features?.[0];
      if (feature) {
        const regionId = feature.properties?.region_id;
        if (regionId !== hoveredRegionId) {
          setHoveredRegionId(regionId);
          if (onRegionHover) {
            const region = regions.find((r) => r.region_id === regionId);
            onRegionHover(region || null);
          }
        }
      }
    },
    [regions, hoveredRegionId, onRegionHover]
  );

  const handleMouseLeave = React.useCallback(() => {
    setHoveredRegionId(null);
    if (onRegionHover) {
      onRegionHover(null);
    }
  }, [onRegionHover]);

  return (
    <div className={cn("relative w-full h-full min-h-[400px]", className)}>
      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-[var(--color-surface-canvas)]/80">
          <div className="glass-standard rounded-[var(--radius-lg)] p-6 flex flex-col items-center gap-3">
            <div className="h-6 w-6 border-2 border-[var(--color-accent-primary)] border-t-transparent rounded-full animate-spin" />
            <span className="text-caption text-[var(--color-content-secondary)]">
              Loading map
            </span>
          </div>
        </div>
      )}

      <Map
        ref={mapRef}
        {...viewState}
        onMove={(evt) => setViewState(evt.viewState)}
        onLoad={handleMapLoad}
        onClick={handleClick}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        interactiveLayerIds={["region-points"]}
        style={{ width: "100%", height: "100%" }}
        mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
        attributionControl={false}
        maxBounds={MAX_BOUNDS}
        minZoom={3.6}
        maxZoom={12}
        dragRotate={false}
        pitchWithRotate={false}
        touchZoomRotate={false}
        cursor={hoveredRegionId ? "pointer" : "grab"}
      >
        <NavigationControl position="top-right" showCompass={false} />

        {regions.length > 0 && (
          <Source id="regions" type="geojson" data={regionsGeoJson}>
            {/* Soft halo - large, very transparent */}
            <Layer
              id="region-halos"
              type="circle"
              paint={{
                "circle-radius": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  4,
                  [
                    "interpolate",
                    ["linear"],
                    ["get", "gap_population"],
                    0,
                    18,
                    3000000,
                    44,
                  ],
                  8,
                  [
                    "interpolate",
                    ["linear"],
                    ["get", "gap_population"],
                    0,
                    32,
                    3000000,
                    72,
                  ],
                ],
                "circle-color": ["get", "color"],
                "circle-opacity": 0.18,
                "circle-blur": 0.6,
              }}
            />

            {/* Core circle - smaller, more defined */}
            <Layer
              id="region-points"
              type="circle"
              paint={{
                "circle-radius": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  4,
                  [
                    "interpolate",
                    ["linear"],
                    ["get", "gap_population"],
                    0,
                    8,
                    3000000,
                    20,
                  ],
                  8,
                  [
                    "interpolate",
                    ["linear"],
                    ["get", "gap_population"],
                    0,
                    14,
                    3000000,
                    34,
                  ],
                ],
                "circle-color": ["get", "color"],
                "circle-opacity": [
                  "case",
                  ["==", ["get", "region_id"], selectedRegionId || ""],
                  0.85,
                  ["==", ["get", "region_id"], hoveredRegionId || ""],
                  0.75,
                  0.55,
                ],
                "circle-stroke-width": [
                  "case",
                  ["==", ["get", "region_id"], selectedRegionId || ""],
                  2,
                  ["==", ["get", "region_id"], hoveredRegionId || ""],
                  1.5,
                  0,
                ],
                "circle-stroke-color": [
                  "case",
                  ["==", ["get", "region_id"], selectedRegionId || ""],
                  "#176D6A",
                  "rgba(255,255,255,0.9)",
                ],
              }}
            />

            <Layer
              id="region-labels"
              type="symbol"
              layout={{
                "text-field": ["get", "region_name"],
                "text-size": 11,
                "text-anchor": "top",
                "text-offset": [0, 1.4],
                "text-font": ["Open Sans Semibold", "Arial Unicode MS Bold"],
                "text-allow-overlap": false,
              }}
              paint={{
                "text-color": "#142126",
                "text-halo-color": "rgba(255,255,255,0.95)",
                "text-halo-width": 1.5,
                "text-opacity": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  4,
                  0.7,
                  6,
                  1,
                ],
              }}
            />
          </Source>
        )}
      </Map>
    </div>
  );
}
