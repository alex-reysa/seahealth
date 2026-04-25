# Sitemap And Navigation

SeaHealth has one desktop app shell, one home route, and three product surfaces. The goal is to make the demo path obvious while keeping every surface connected to the same canonical audit data.

## Route map

| Route | Surface | Primary job | Canonical data |
|---|---|---|---|
| `/` | Dashboard / control panel | Show the India choropleth, top-line audit status, command input, and launch paths into query/map/audit flows. This is not a fourth analytical surface. | `MapRegionAggregate`, `PopulationReference`, `FacilityAudit`, summary aggregates |
| `/desert-map` | Desert Map | Identify geographic healthcare capability gaps by region and capability. | `MapRegionAggregate`, `PopulationReference`, `FacilityAudit` summary fields |
| `/planner-query` | Planner Query Console | Convert one natural-language planning question into a ranked, exportable table. | `QueryResult`, `ParsedIntent`, `RankedFacility` |
| `/facilities/:facility_id` | Facility Audit View | Inspect claims, evidence, contradictions, Trust Scores, and trace for one facility. | `FacilityAudit` |

## App shell

Persistent left navigation rail:

- SeaHealth
- Dashboard
- Planner Query
- Desert Map

Facility Audit appears as a detail route and breadcrumb when a facility is selected; it does not need a persistent top-level nav link. The active route must be visibly selected in the rail with a sliding active pill. The shell should not expose account, billing, admin, notification, or settings areas in this hackathon scope.

Rail behavior:

- Expanded width: `w-64`.
- Collapsed width: `w-16`, if implemented.
- Main content reserves the rail column so width transitions do not cause disorienting content jumps.
- The rail uses the glass-like elevated treatment from `docs/design_system.md`.

## URL parameters

Use query parameters to preserve demo context:

- `/desert-map?capability=SURGERY_APPENDECTOMY&radius_km=50&region_id=BR_PATNA`
- `/planner-query?q=Which%20facilities%20within%2050km%20of%20Patna%20can%20perform%20an%20appendectomy%3F`
- `/facilities/:facility_id?capability=SURGERY_APPENDECTOMY&from=planner-query`

These parameters are optional but should be supported by the docs and implementation so a demo can jump directly to the right state.

## Cross-surface journeys

Primary demo journey:

1. Dashboard opens with the India choropleth, audit status, and command input.
2. Planner runs or says: "Which facilities within 50km of Patna can perform an appendectomy?"
3. Dashboard focuses Patna/Bihar, sets capability/radius, and offers the structured Planner Query result.
4. Result row opens Facility Audit View for the selected facility.
5. Facility Audit View highlights the appendectomy capability, evidence snippets, contradiction banner, and trace.

Map-first journey:

1. Desert Map opens with a capability and radius selected.
2. Planner clicks a high-gap region.
3. Right rail ranks facilities relevant to that region.
4. Facility row opens Facility Audit View.

Audit-first journey:

1. Dashboard or direct URL opens `/facilities/:facility_id`.
2. Planner selects a capability.
3. Evidence and contradiction details explain the Trust Score.
4. "Back to results" returns to Planner Query or Desert Map when source context exists.

## Interaction contracts

Facility rows:

- Click opens `/facilities/:facility_id`.
- Carry selected `capability` when the row came from a query or map filter.
- Preserve source context through `from`.

Trace links:

- Planner Query uses `QueryResult.query_trace_id`.
- Facility Audit uses `FacilityAudit.mlflow_trace_id`.
- Trace opens in a drawer or expandable panel on the current route.

CSV export:

- Only exists in Planner Query Console.
- Exports the ranked result table, not raw trace or full evidence docs.

Command control:

- Typed command, voice transcript, and agent action all dispatch to the same internal command model.
- Supported commands should include `focus_location`, `set_capability`, `set_radius`, `select_region`, `highlight_facilities`, `open_facility`, and `reset_map`.
- Commands update route/query parameters when they change shareable state.

## Out-of-scope routes

Do not add these routes for the hackathon build:

- `/login`
- `/settings`
- `/saved-searches`
- `/patients`
- `/chat`
- `/admin`
- `/reports`
- `/mobile`

If a future feature needs one of these routes, log it after the demo scope is frozen.
