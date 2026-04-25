"use client";

import * as React from "react";
import { Map, Source, Layer, NavigationControl, ScaleControl } from "@vis.gl/react-maplibre";
import type { MapRef, MapLayerMouseEvent } from "@vis.gl/react-maplibre";
import type { FillLayerSpecification, LineLayerSpecification } from "maplibre-gl";
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

// Choropleth color scale based on gap_population
function getColorForGap(gapPopulation: number, maxGap: number): string {
  const ratio = Math.min(gapPopulation / maxGap, 1);
  // Color scale from light to dark red
  const colors = [
    "#fee5d9",
    "#fcbba1",
    "#fc9272",
    "#fb6a4a",
    "#ef3b2c",
    "#cb181d",
    "#99000d",
  ];
  const index = Math.floor(ratio * (colors.length - 1));
  return colors[index];
}

export function IndiaMap({
  regions = [],
  selectedRegionId,
  onRegionClick,
  onRegionHover,
  showFacilities = false,
  className,
}: IndiaMapProps) {
  const mapRef = React.useRef<MapRef>(null);
  const [viewState, setViewState] = React.useState({
    longitude: INDIA_CENTER[0],
    latitude: INDIA_CENTER[1],
    zoom: 4.5,
  });
  const [hoveredRegionId, setHoveredRegionId] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  // Calculate max gap for color scale
  const maxGap = React.useMemo(() => {
    return Math.max(...regions.map((r) => r.gap_population), 1);
  }, [regions]);

  // Create GeoJSON from regions (simplified - in production, use actual boundary data)
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

  // Layer styles
  const circleLayer: FillLayerSpecification = {
    id: "region-circles",
    type: "fill",
    source: "regions",
    paint: {
      "fill-color": ["get", "color"],
      "fill-opacity": 0.6,
    },
  };

  const handleMapLoad = React.useCallback(() => {
    setIsLoading(false);
    // Fit to India bounds
    if (mapRef.current) {
      mapRef.current.fitBounds(INDIA_BOUNDS, {
        padding: 50,
        duration: 1000,
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
            <div className="h-8 w-8 border-2 border-[var(--color-accent-primary)] border-t-transparent rounded-full animate-spin" />
            <span className="text-body text-[var(--color-content-secondary)]">
              Loading map...
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
      >
        <NavigationControl position="top-right" showCompass={false} />
        <ScaleControl position="bottom-right" />

        {/* Region data points - in production, replace with actual state/district boundaries */}
        {regions.length > 0 && (
          <Source id="regions" type="geojson" data={regionsGeoJson}>
            <Layer
              id="region-points"
              type="circle"
              paint={{
                "circle-radius": [
                  "interpolate",
                  ["linear"],
                  ["get", "gap_population"],
                  0,
                  15,
                  3000000,
                  50,
                ],
                "circle-color": ["get", "color"],
                "circle-opacity": [
                  "case",
                  ["==", ["get", "region_id"], selectedRegionId || ""],
                  0.9,
                  ["==", ["get", "region_id"], hoveredRegionId || ""],
                  0.8,
                  0.6,
                ],
                "circle-stroke-width": [
                  "case",
                  ["==", ["get", "region_id"], selectedRegionId || ""],
                  3,
                  ["==", ["get", "region_id"], hoveredRegionId || ""],
                  2,
                  1,
                ],
                "circle-stroke-color": [
                  "case",
                  ["==", ["get", "region_id"], selectedRegionId || ""],
                  "#176D6A",
                  "#ffffff",
                ],
              }}
            />
            <Layer
              id="region-labels"
              type="symbol"
              layout={{
                "text-field": ["get", "region_name"],
                "text-size": 12,
                "text-anchor": "top",
                "text-offset": [0, 1.5],
              }}
              paint={{
                "text-color": "#142126",
                "text-halo-color": "#ffffff",
                "text-halo-width": 1.5,
              }}
            />
          </Source>
        )}
      </Map>

      {/* Legend */}
      <div className="absolute bottom-16 left-4 glass-standard rounded-[var(--radius-md)] p-3">
        <div className="text-caption text-[var(--color-content-secondary)] mb-2">
          Gap Population
        </div>
        <div className="flex items-center gap-1">
          {["#fee5d9", "#fc9272", "#ef3b2c", "#99000d"].map((color, i) => (
            <div
              key={i}
              className="w-6 h-3 first:rounded-l-sm last:rounded-r-sm"
              style={{ backgroundColor: color }}
            />
          ))}
        </div>
        <div className="flex justify-between text-mono-s text-[var(--color-content-tertiary)] mt-1">
          <span>Low</span>
          <span>High</span>
        </div>
      </div>
    </div>
  );
}
