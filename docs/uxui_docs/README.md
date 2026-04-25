# UX/UI Docs

This folder defines the SeaHealth front end for the hackathon build. Read these docs in order before implementing UI.

## Read order

1. `00_frontend_guidelines.md` — app-wide UX, visual, accessibility, and data-contract rules.
2. `01_sitemap.md` — route map, navigation model, URL parameters, and cross-surface journeys.
3. `dashboard.md` — map-first control panel and demo launcher.
4. `planner_query.md` — natural-language query to ranked, exportable results.
5. `facility-audit.md` — claim-by-claim evidence, contradictions, Trust Score reasoning, and trace.
6. `desert_map.md` — regional capability-gap map and facility drilldown.

## Source hierarchy

Use the project-level docs as the higher-level source of truth:

- `docs/VISION.md` defines the product promise and scope.
- `docs/DECISIONS.md` defines hard product constraints.
- `docs/DATA_CONTRACT.md` defines canonical schemas and field names.
- `docs/AGENT_ARCHITECTURE.md` defines trace and agent dependencies.
- `docs/PHASES.md` defines delivery order.
- `docs/UX_FLOWS.md` gives the original three-surface flow summary.

The docs in this folder translate those decisions into UI implementation specs. If a UX/UI doc conflicts with a project-level source, treat the project-level source as authoritative and update the UX/UI doc.

## Surface relationship

SeaHealth has one desktop shell and three product surfaces:

- Dashboard / control panel shows the India choropleth, command input, and launches the demo.
- Planner Query Console produces `QueryResult` and opens Facility Audit View from ranked rows.
- Desert Map summarizes `MapRegionAggregate` and opens Facility Audit View from region facility rows.
- Facility Audit View is the proof surface for one `FacilityAudit`.

Do not add chat, auth, saved searches, dark mode, mobile routes, or custom design-system work for the hackathon build.
