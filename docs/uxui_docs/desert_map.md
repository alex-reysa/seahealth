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

For standalone map exploration, default to Bihar, radius `60km`, and the last selected capability if present. If no prior context exists, use `NEONATAL` as a strong visual example.

## Layout

Top filter bar:

- Capability dropdown backed by `CapabilityType`
- Radius control with `30km`, `60km`, and `120km` presets; support route-provided `50km` for the appendectomy demo
- State or region filter
- Reset map button

Main canvas:

- India or state-level choropleth by region.
- Color encodes `gap_population`: darker red means more people uncovered for the selected capability and radius.
- Selected region uses a distinct outline and remains selected until another region is clicked or filters reset.

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

Recommended map stack for the hackathon build:

- Map renderer: MapLibre GL JS.
- React wrapper/state: `react-map-gl/maplibre` in controlled mode.
- Optional overlay layer: deck.gl for high-volume facility points, arcs, halos, or animated layers.
- Boundary data: DataMeet India shapefiles converted to GeoJSON/TopoJSON, or a web-ready India GeoJSON/TopoJSON repo such as `udit-001/india-maps-data` after license and boundary fit review.
- Preprocessing: simplify boundaries and join them to `MapRegionAggregate.region_id` before runtime.

Why:

- MapLibre exposes imperative camera and layer APIs such as `flyTo`, `fitBounds`, and `setFilter`, which are straightforward to wrap as agent commands.
- `react-map-gl` supports controlled view state, which lets user gestures, typed commands, voice transcripts, and agent actions all update the same camera/filter state.
- deck.gl is useful when we need data-heavy overlays beyond a simple choropleth, but it is not required for the first choropleth.

Avoid for v1:

- A static SVG-only map if we want zoom, pan, and agent camera control.
- A heavy GIS platform unless the team already has it wired.
- Mapbox-only features unless access tokens and license constraints are acceptable.

Optional agent geospatial services:

- Mapbox MCP Server can give an agent access to Mapbox location intelligence if the project accepts a Mapbox token and external service dependency.
- This does not replace front-end map control. The SeaHealth UI still needs its own `MapCommand` dispatcher to move the camera, set filters, select regions, and open audits.

Reference docs:

- MapLibre GL JS API: https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/
- react-map-gl controlled state: https://visgl.github.io/react-map-gl/docs/get-started/state-management
- deck.gl views and view state: https://deck.gl/docs/developer-guide/views
- DataMeet maps: https://github.com/datameet/maps
- India maps data: https://github.com/udit-001/india-maps-data
- Mapbox MCP Server: https://github.com/mapbox/mcp-server

## Agent and voice control

The map should be commandable through an internal `MapCommand` model. Voice is just another input source that produces the same command objects.

Initial command set:

- `focus_location`: geocode or use known coordinates, then set map camera.
- `set_capability`: update `CapabilityType` filter.
- `set_radius`: update coverage radius.
- `select_region`: select one `MapRegionAggregate.region_id`.
- `highlight_facilities`: highlight ranked facilities matching current filters.
- `open_facility`: route to Facility Audit View.
- `reset_map`: return to default India/Bihar view.

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

## Interaction flow

1. User selects capability and radius.
2. Map updates aggregate colors.
3. User hovers a region to inspect tooltip metrics.
4. User clicks a region.
5. Right rail opens ranked facilities for that region.
6. User clicks a facility row.
7. App opens `/facilities/:facility_id?capability=<selected capability>&from=desert-map`.

The copy "nearest verified facility: 94km" is allowed only as a derived display value from facility geodata and ranking results. It is not part of `MapRegionAggregate`.

## Data dependencies

Map aggregates:

- `MapRegionAggregate.region_id`
- `MapRegionAggregate.region_name`
- `MapRegionAggregate.capability_type`
- `MapRegionAggregate.centroid`
- `MapRegionAggregate.population`
- `MapRegionAggregate.radius_km`
- `MapRegionAggregate.verified_capability_count`
- `MapRegionAggregate.capability_count_ci`
- `MapRegionAggregate.covered_population`
- `MapRegionAggregate.gap_population`
- `MapRegionAggregate.coverage_ratio`
- `MapRegionAggregate.generated_at`

Population:

- `PopulationReference.region_id`
- `PopulationReference.region_name`
- `PopulationReference.centroid`
- `PopulationReference.population_count`
- `PopulationReference.source_observed_at`

Facility rows:

- `FacilityAudit.facility_id`
- `FacilityAudit.name`
- `FacilityAudit.location`
- `FacilityAudit.trust_scores[selected capability]`
- `FacilityAudit.total_contradictions`

## States

Loading:

- Show stable map container and right-rail skeleton.
- Keep filters visible but disabled while aggregates load.

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

## Acceptance criteria

- User can select capability and radius.
- Map color is driven by `gap_population`.
- Region click opens a right rail with ranked facilities.
- Facility row opens Facility Audit View with selected capability preserved.
- Confidence intervals and generated timestamps appear in detailed region copy.
- No custom basemap, per-region overlays, time-series, saved searches, mobile polish, or dark mode are required.
