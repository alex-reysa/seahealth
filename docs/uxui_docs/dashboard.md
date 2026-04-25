# Dashboard / Control Panel

The dashboard is the desktop control panel and landing route for SeaHealth. It is not a fourth analytical product surface. Its job is to put the India capability map directly in front of Sarah, expose audit readiness, and route her into the three core surfaces defined in `docs/VISION.md` and `docs/UX_FLOWS.md`: Planner Query Console, Desert Map, and Facility Audit View.

Shared rules live in `docs/uxui_docs/00_frontend_guidelines.md`; route behavior lives in `docs/uxui_docs/01_sitemap.md`.

## Purpose

Enable an NGO planner or judge to answer four questions within the first screen:

- Where are the capability deserts right now?
- Is the audit pipeline ready enough to trust for the demo?
- What command or query should I run next?
- How do I move between query, map, and facility-level proof?

The default action should still support the Planner Query Console because `docs/PHASES.md` ships it first and the appendectomy query is the locked demo path, but the visual center of the page is the choropleth map.

## Default view

The home route `/` should feel like a live control panel, not a marketing homepage. The whole India map is visible immediately and fills most of the workspace.

Recommended layout:

- Left app rail: SeaHealth, Dashboard, Planner Query, Desert Map.
- Main canvas: whole India map, fit to India bounds, with heatmap/choropleth color driven by `MapRegionAggregate.gap_population`.
- Floating command panel: typed command input, voice transcript hook, current capability, radius, and execution status.
- Floating summary strip: audited facilities, verified facilities, flagged facilities, last audited timestamp.
- Right-side telemetry panel: selected region, coverage ratio, gap population, verified count CI, top facilities.
- Bottom trace/status band: data loaded, query trace available, facility trace available, CSV export available.

Keep the content dense and functional. Avoid hero copy, large illustration areas, testimonials, or broad product-positioning sections. Visual drama should come from the map, glass panels, and command response.

## Initial Map State

When no route parameters are present:

- Viewport fits the whole India boundary.
- No region, facility, or cluster is selected.
- Individual facilities are hidden.
- Map color communicates aggregate capability gap by region.
- Default capability is `SURGERY_APPENDECTOMY` for the demo.
- Default radius is `50km` for the appendectomy demo.

This state is for national pattern recognition. It should be easy to see where gaps are concentrated before drilling into Bihar, Patna, a district, or a PIN code.

## Zoom-Level Rendering

Country zoom:

- Show heatmap/choropleth by state, district, or PIN-region aggregate.
- Hide individual facility markers and facility labels.
- Hover/click exposes aggregate metrics: population, `gap_population`, `coverage_ratio`, and `capability_count_ci`.

Region zoom:

- Show clearer boundaries and selected-region outline.
- Right telemetry panel appears with ranked top facilities for the current capability/radius.
- Still prefer aggregate color over individual points unless the geography is small enough.

Local zoom:

- Show clustered facility markers.
- Cluster marker displays facility count and summary Trust Score band.
- Clicking a cluster zooms closer or opens the regional ranked list.

Facility zoom:

- Show individual facility markers.
- Marker preview displays facility name, Trust Score, contradiction count, evidence count, and "Open audit".
- Marker click can route to Facility Audit View.

## Fast Navigation

Manual navigation:

- Pan and zoom.
- Click a region to focus it.
- Search by state, district, city, facility name, or six-digit PIN code.
- Reset to whole India.

PIN navigation:

- PIN input validates exactly six digits before dispatch.
- PIN search should focus the region or centroid linked to `GeoPoint.pin_code`.
- Preserve active capability and radius unless the user changes them.

## Control-panel behavior

The dashboard should support a commandable map model even if the first build only exposes typed commands.

Command examples:

- "Focus Patna, appendectomy, 50 km"
- "Show neonatal deserts in Bihar"
- "Zoom to PIN 800001"
- "Highlight facilities with high contradictions"
- "Open the top facility audit"

Command output is not chat. It updates map state, filters, selected region, highlighted facilities, or route.

Voice control:

- Treat voice as an input method for the same command model.
- A future speech-to-text layer should populate the command input and dispatch after confirmation.
- Keep manual controls visible for all voice-capable actions.

## Shared metrics

The summary strip should read from canonical audit outputs:

- Audited facilities: count of `FacilityAudit` records.
- Verified facilities: count of selected or default capability records where `TrustScore.score >= 80` and no HIGH contradiction exists.
- Flagged facilities: count where `FacilityAudit.total_contradictions > 0` or any HIGH contradiction exists.
- Last audited: max `FacilityAudit.last_audited_at`.
- Current demo capability: `SURGERY_APPENDECTOMY` unless a route parameter overrides it.

If data is not ready, show the metric shell with neutral unavailable copy rather than inventing placeholder numbers.

## Navigation rules

Primary paths:

- Dashboard -> Planner Query Console with the appendectomy query ready to run.
- Dashboard -> Desert Map with `capability=SURGERY_APPENDECTOMY`, `radius_km=50`, and Bihar/Patna context when available.
- Planner Query row -> Facility Audit View with selected `facility_id` and `capability_type`.
- Desert Map region -> right rail facility row -> Facility Audit View.
- Facility Audit View -> back to source route, preserving query or map parameters.

The dashboard should not introduce saved searches, history, account settings, or user-specific state.

## Data dependencies

Dashboard depends on:

- `MapRegionAggregate.region_id`
- `MapRegionAggregate.region_name`
- `MapRegionAggregate.gap_population`
- `MapRegionAggregate.coverage_ratio` (derived display value; not in the slim Phase-1 export — see `docs/DATA_CONTRACT.md` rich variant)
- `MapRegionAggregate.capability_count_ci` (derived display value; rich-variant only)
- `PopulationReference.population_total` (the slim export; rich variant uses `population_count`)
- `FacilityAudit.facility_id`
- `FacilityAudit.name`
- `FacilityAudit.location`
- `FacilityAudit.location.pin_code`
- `FacilityAudit.trust_scores`
- `FacilityAudit.total_contradictions`
- `FacilityAudit.last_audited_at`
- `FacilityAudit.mlflow_trace_id`
- Summary aggregates derived from `FacilityAudit`
- Current `MapCommand` state: capability, radius, location focus, selected region, selected facility
- Current map view state: bounds, center, zoom, visible layer mode

Do not define dashboard-only data models unless they are clearly derived display values.

## States

Ready:

- Summary strip has real counts.
- Whole India map is visible and color-coded by aggregate gap population.
- Command panel can set capability, radius, and location focus.
- Facility markers remain hidden until sufficient zoom.
- Demo query action is enabled.
- Surface shortcuts route correctly.

Loading:

- Map container is stable and shows a soft glass loading overlay.
- Summary strip shows stable skeleton rows.
- Command panel remains visible but disables submit until required data is available.

Empty:

- No `FacilityAudit` records exist. Show "No facility audits loaded yet" and keep navigation visible.

Partial data:

- Some audits exist but traces or map aggregates are missing. Show usable metrics and mark unavailable pieces as "Trace unavailable" or "Map aggregates unavailable."

Command failed:

- Keep the prior map state.
- Show the failed command and a direct retry.
- Do not clear the command text.

Error:

- Show which dependency failed: audit load, query trace, facility trace, or map aggregate.
- Keep the rest of the shell usable.

## Demo acceptance criteria

- `/` clearly routes to the appendectomy Planner Query path.
- `/` directly shows the India choropleth as the main control surface.
- The command panel can apply the appendectomy/Patna/50km state to the map.
- Search can jump to a named region or six-digit PIN code.
- Zooming in reveals facility clusters and then individual facilities.
- Summary metrics are real or visibly unavailable; no fake counts.
- The shell uses the same names as the rest of the docs: Desert Map, Planner Query Console, Facility Audit View, Trust Score, Evidence, Contradictions.
- The shell uses the vertical left rail from `docs/design_system.md`, not a top navigation bar.
- No dashboard component requires auth, saved searches, chat history, mobile layout work, dark mode, or a custom design system.

## Non-goals

- Full executive analytics dashboard detached from the map
- Marketing homepage
- Account dashboard
- Saved searches or recent history
- Chat interface or conversation history
- Mobile nav
