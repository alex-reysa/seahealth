# Desert Map

The Desert Map is the visual hook: a desktop choropleth showing where a selected healthcare capability is missing, low-trust, or geographically inaccessible. It helps Sarah identify funding gaps, then sends her into Facility Audit View for proof.

Shared rules live in `docs/uxui_docs/00_frontend_guidelines.md`; route behavior lives in `docs/uxui_docs/01_sitemap.md`.

## Purpose

Enable one task: choose a capability and radius, identify high-gap regions, and drill into ranked facilities that explain the gap.

The map is not the proof surface. It summarizes aggregates and points to Facility Audit View for claim-by-claim evidence.

## Default demo state

For the locked end-to-end demo:

- Capability: `SURGERY_APPENDECTOMY`
- Radius: `50km` when entered from the Planner Query demo
- Region context: Patna/Bihar when geocoding is available
- Color metric: `gap_population`

For standalone map exploration, start with whole India visible, radius `60km`, and the last selected capability if present. If no prior context exists, use `NEONATAL` as a strong visual example.

When no route parameters are present:

- Fit to whole India bounds.
- Show aggregate heatmap/choropleth only.
- Hide facility markers and labels.
- No region is selected.

## Layout

Top filter bar:

- Capability dropdown backed by `CapabilityType`
- Radius control with `30km`, `60km`, and `120km` presets; support route-provided `50km` for the appendectomy demo
- State or region filter
- Reset map button

Main canvas:

- Whole India map by default, with state/district/PIN choropleth by region.
- Color encodes `gap_population`: darker red means more people uncovered for the selected capability and radius.
- Selected region uses a distinct outline and remains selected until another region is clicked or filters reset.
- Facility clusters and markers appear only after sufficient zoom.

Right rail:

- Region name and population.
- `gap_population`, `covered_population`, and `coverage_ratio`.
- `verified_capability_count` with `capability_count_ci`.
- Ranked facility list for the selected region and capability.
- Facility rows show name, distance, Trust Score, contradictions, evidence count, and an audit action.

Bottom metric strip:

- Total audited facilities.
- Verified count for the selected capability.
- Flagged count.
- Aggregate generation timestamp.

## Implementation recommendation

Recommended frontend map stack for the hackathon build:

| Need | Package / framework | Use |
|---|---|---|
| Base interactive map | `maplibre-gl` | WebGL map renderer, vector/GeoJSON sources, camera methods like `flyTo`, `fitBounds`, and layer filters. |
| React integration | `@vis.gl/react-maplibre` | React wrapper around MapLibre with controlled view state. Use this as the default React map package. |
| Heavy overlays, optional | `deck.gl`, `@deck.gl/react`, `@deck.gl/layers`, `@deck.gl/geo-layers` | Facility clusters, point clouds, halos, arcs, animated layers, or large overlay datasets if MapLibre layers become limiting. |
| Geometry helpers | `@turf/turf` | Bounds, centroids, distances, point-in-polygon checks, and radius helpers. |
| Clustering | `supercluster` | Fast client-side clustering for facility markers if not using MapLibre's built-in GeoJSON clustering. |
| TopoJSON conversion | `topojson-client` | Convert TopoJSON boundaries to GeoJSON features in the browser or build step. |
| Color ramps | `d3-scale`, `d3-scale-chromatic` | Choropleth/heatmap color scales for `gap_population` and `coverage_ratio`. |

Install target for a React/Next frontend:

```bash
npm install maplibre-gl @vis.gl/react-maplibre @turf/turf supercluster topojson-client d3-scale d3-scale-chromatic
npm install @deck.gl/react @deck.gl/layers @deck.gl/geo-layers
```

Only install deck.gl packages when we actually need heavier overlays. The first version can ship with MapLibre layers, GeoJSON sources, and MapLibre/`supercluster` clustering.

Why:

- MapLibre exposes imperative camera and layer APIs such as `flyTo`, `fitBounds`, and `setFilter`, which are straightforward to wrap as agent commands.
- `@vis.gl/react-maplibre` supports controlled view state, which lets user gestures, typed commands, voice transcripts, and agent actions all update the same camera/filter state.
- deck.gl is useful when we need data-heavy overlays beyond a simple choropleth, but it is not required for the first choropleth.

Avoid for v1:

- A static SVG-only map if we want zoom, pan, and agent camera control.
- A heavy GIS platform unless the team already has it wired.
- Mapbox-only features unless access tokens and license constraints are acceptable.

Optional agent geospatial services:

- Mapbox MCP Server can give an agent access to Mapbox location intelligence if the project accepts a Mapbox token and external service dependency.
- This does not replace front-end map control. The SeaHealth UI still needs its own `MapCommand` dispatcher to move the camera, set filters, select regions, and open audits.

Reference docs:

- MapLibre GL JS package: https://www.npmjs.com/package/maplibre-gl
- MapLibre GL JS API: https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/
- React MapLibre package: https://www.npmjs.com/package/@vis.gl/react-maplibre
- react-map-gl / vis.gl docs: https://visgl.github.io/react-map-gl/
- deck.gl views and view state: https://deck.gl/docs/developer-guide/views
- Mapbox MCP Server: https://github.com/mapbox/mcp-server

## India map data sources

Use web-ready GeoJSON/TopoJSON when speed matters; use shapefiles when we need more authoritative boundaries and can preprocess them.

Recommended order:

1. `udit-001/india-maps-data` — https://github.com/udit-001/india-maps-data
   - Best for fast frontend prototyping.
   - Provides whole-country and per-state India maps in GeoJSON and TopoJSON.
   - Includes district-level boundaries and direct CDN-style links in the repo docs.
   - Use this first for the dashboard choropleth if license/boundary fit is acceptable.

2. DataMeet maps — https://github.com/datameet/maps
   - Best for a community-maintained India geospatial source.
   - Provides Indian boundary data primarily as shapefiles.
   - The repo notes conversion to GeoJSON/KML/vector formats through `ogr2ogr` or Mapshaper.
   - DataMeet India boundaries are listed as CC BY 4.0; preserve attribution.

3. `mickeykedia/India-Maps` — https://github.com/mickeykedia/India-Maps
   - Useful fallback collection of India shapefiles and GeoJSON files.
   - Review freshness, boundary source, and license before use.

4. Natural Earth — https://www.naturalearthdata.com/
   - Good for country/neighbor context and a coarse India outline.
   - Not sufficient for district/PIN-level healthcare planning.

Preprocessing workflow:

```bash
# Shapefile -> GeoJSON
ogr2ogr -f GeoJSON india_districts.geojson input_districts.shp

# Simplify and export web-ready GeoJSON/TopoJSON
npx mapshaper india_districts.geojson -simplify 10% keep-shapes -o format=topojson india_districts.topojson
```

Runtime data contract:

- Boundary feature id must join to `MapRegionAggregate.region_id`.
- Boundary feature name must be normalized to `MapRegionAggregate.region_name`.
- PIN-level navigation needs a lookup from six-digit `pin_code` to centroid or region id.
- Facility points use `FacilityAudit.location.lat`, `FacilityAudit.location.lng`, and `FacilityAudit.location.pin_code`.

## Agent and voice control

The map should be commandable through an internal `MapCommand` model. Voice is just another input source that produces the same command objects.

Initial command set:

- `focus_location`: geocode or use known coordinates, then set map camera.
- `set_capability`: update `CapabilityType` filter.
- `set_radius`: update coverage radius.
- `select_region`: select one `MapRegionAggregate.region_id`.
- `highlight_facilities`: highlight ranked facilities matching current filters.
- `open_facility`: route to Facility Audit View.
- `reset_map`: return to whole India view.

Example command:

```json
{
  "type": "focus_location",
  "location_label": "Patna",
  "center": { "lat": 25.61, "lng": 85.14, "pin_code": "800001" },
  "zoom": 8,
  "capability_type": "SURGERY_APPENDECTOMY",
  "radius_km": 50
}
```

There is no requirement to find an off-the-shelf "agent-controlled map" repo. The reliable implementation is to keep the map controlled by app state and expose a small, typed command dispatcher for the agent.

## Map encoding

Primary color metric:

- Use `MapRegionAggregate.gap_population`.
- Show `coverage_ratio` as supporting text in tooltips and the right rail.
- Show `capability_count_ci` whenever displaying verified capability count.

Verified definition:

- `TrustScore.score >= 80`
- No HIGH contradiction for the selected capability

Tooltip content:

- Region name
- Population
- Gap population
- Coverage ratio
- Verified capability count with confidence interval
- Generated timestamp

Do not rely on color alone. Tooltip and right-rail labels must explain the metric.

## Zoom-Level Rendering

Country zoom:

- Show whole India.
- Render state/district/PIN aggregate heatmap or choropleth.
- Hide individual facility markers.

Region zoom:

- Show district/PIN boundaries.
- Highlight selected region.
- Show aggregate tooltip and right rail.

Local zoom:

- Show clustered facility markers.
- Cluster style communicates count and Trust Score band summary.

Facility zoom:

- Show individual facility markers and labels when space allows.
- Marker preview includes Trust Score, contradictions, evidence count, and audit action.

## Fast Navigation

- Region click focuses that region with `fitBounds`.
- Search supports state, district, city, facility name, and six-digit PIN code.
- PIN search validates exactly six digits and focuses the matching `GeoPoint.pin_code` region or centroid.
- `reset_map` returns to whole India and hides facility markers.

## Interaction flow

1. User selects capability and radius.
2. Map updates aggregate colors.
3. User hovers a region to inspect tooltip metrics.
4. User clicks a region or searches a PIN code.
5. Map focuses the selected geography.
6. User zooms until facility clusters or markers appear.
7. Right rail ranks facilities for that region.
8. User clicks a facility row or marker.
9. App opens `/facilities/:facility_id?capability=<selected capability>&from=desert-map`.

The copy "nearest verified facility: 94km" is allowed only as a derived display value from facility geodata and ranking results. It is not part of `MapRegionAggregate`.

## Data dependencies

Map aggregates (slim Phase-1 export from `seahealth.schemas` — what `/map/aggregates` actually returns):

- `MapRegionAggregate.region_id`
- `MapRegionAggregate.region_name`
- `MapRegionAggregate.state`
- `MapRegionAggregate.capability_type`
- `MapRegionAggregate.centroid`
- `MapRegionAggregate.population`
- `MapRegionAggregate.verified_facilities_count`
- `MapRegionAggregate.flagged_facilities_count`
- `MapRegionAggregate.gap_population`

Rich-variant fields used as derived display values (UI-only, not in the Phase-1 export — see the rich `MapRegionAggregate` block in `docs/DATA_CONTRACT.md`): `radius_km`, `verified_capability_count`, `capability_count_ci`, `covered_population`, `coverage_ratio`, `generated_at`.

Population (slim Phase-1 export):

- `PopulationReference.region_id`
- `PopulationReference.population_total`

Rich-variant `PopulationReference` fields (`region_name`, `centroid`, `population_count`, `source_observed_at`) live in the rich variant in `docs/DATA_CONTRACT.md` and are NOT in the Phase-1 export.

Facility rows:

- `FacilityAudit.facility_id`
- `FacilityAudit.name`
- `FacilityAudit.location`
- `FacilityAudit.location.pin_code`
- `FacilityAudit.trust_scores[selected capability]`
- `FacilityAudit.total_contradictions`

## States

Loading:

- Show stable map container and right-rail skeleton.
- Keep filters visible but disabled while aggregates load.
- Default camera still reserves whole-India framing.

No data:

- Show neutral empty state: "No aggregate data for this capability and radius."
- Keep filters available.

Selected region with no facilities:

- Right rail explains there are no verified facilities for the selected capability in this region.

Partial aggregate failure:

- Render available regions.
- Mark missing regions as unavailable, not zero-gap.

Map render failure:

- Show a table fallback with region, gap population, coverage ratio, verified count CI, and audit action.

PIN not found:

- Keep prior map state.
- Show "PIN code not found in loaded region data."

## Acceptance criteria

- User can select capability and radius.
- Default state shows whole India.
- Map color is driven by `gap_population`.
- Individual facilities are hidden when fully zoomed out.
- Facility clusters and markers appear only after sufficient zoom.
- Search supports region, facility, and six-digit PIN navigation.
- Region click opens a right rail with ranked facilities.
- Facility row opens Facility Audit View with selected capability preserved.
- Confidence intervals and generated timestamps appear in detailed region copy.
- No custom basemap, per-region overlays, time-series, saved searches, mobile polish, or dark mode are required.
