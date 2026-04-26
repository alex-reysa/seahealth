# Map Workbench Direction

This document updates the frontend direction without changing implementation yet. The goal is to make SeaHealth feel less like a set of separate demo pages and more like one agentic healthcare intelligence system.

## Product Thesis

SeaHealth should feel like an agentic map workbench for healthcare planning in India.

The map is the primary canvas. The agent runs beside it, performs visible tool calls, updates geographic context, produces ranked facilities, and hands off to evidence-backed audit views. Planner Query remains available as the table and export mode, but the map becomes the main place where the agent feels alive.

This better matches `challenge.md`: build an Agentic Healthcare Intelligence System that audits capabilities, identifies specialized deserts, navigates contradictions, and shows traceability.

## Updated Surface Model

### 1. Map Workbench

Route recommendation:

- Preferred: `/`
- Optional alias or redirect: `/desert-map`

Primary job:

- Show the India healthcare capability map.
- Let the planner ask an agentic request directly in the map context.
- Show agent tool calls as they happen.
- Update map filters, selected region, ranked facilities, and facility highlights.

This replaces the conceptual split between Dashboard and Desert Map. The old Dashboard role becomes the command/status layer inside the Map Workbench.

Core layout:

- Left nav rail.
- Main map canvas.
- Top map controls: capability, radius, state/region/PIN search, reset.
- Floating summary strip: audited facilities, verified facilities, flagged facilities, generated time.
- Right-side Agent Run Panel.
- Right-side or lower ranked results panel, integrated with the agent panel.

### 2. Planner Query Console

Route:

- `/planner-query`

Primary job:

- Convert a natural-language planning question into a ranked, exportable table.
- Show parsed intent, ranking rationale, query trace, and CSV export.

Planner Query should feel like report mode, not chat. It is where Sarah reviews a structured list and exports results for grant-planning work.

### 3. Facility Audit View

Route:

- `/facilities/:facility_id`

Primary job:

- Prove why one facility can or cannot be trusted for a selected capability.
- Show Trust Score, evidence trail, contradictions, source snippets, and MLflow trace.

Facility Audit is the proof layer. It should not be a top-level nav item, but should appear as breadcrumb/detail context when opened from Map Workbench or Planner Query.

## Revised Navigation

Recommended nav:

- SeaHealth
- Map Workbench
- Planner Query

Detail-only routes:

- Facility Audit View

Routes to avoid for hackathon scope remain unchanged:

- Login
- Settings
- Saved searches
- Patients
- Chat
- Admin
- Reports
- Mobile

The nav may feel small, but that is acceptable if the two top-level surfaces are strong and clearly named. Fewer surfaces are better than redundant pages.

## Agent Run Panel

The Agent Run Panel should sit directly on the map screen, preferably in the right rail.

It is not a chat transcript. It is an execution trace plus controls.

### Panel Structure

Header:

- Current request.
- Run status.
- Trace id when available.
- Reset or rerun action.

Input:

- Single command/query input.
- Example chips for demo flows.

Execution timeline:

1. `parse_intent`
2. `geocode`
3. `set_capability`
4. `set_radius`
5. `search_facilities`
6. `get_facility_audit`
7. `rank_results`
8. `update_map`

Each step should show:

- Status: pending, running, complete, failed.
- Tool name.
- Compact input/output summary.
- Duration.
- Expandable structured payload.

Result area:

- Ranked facilities.
- Trust Score.
- Distance.
- Contradictions.
- Evidence count.
- "Open audit" action.

### Example Timeline Copy

Request:

`Find the nearest facility in rural Bihar that can perform an emergency appendectomy and typically leverages part-time doctors.`

Timeline:

- `parse_intent`: capability `SURGERY_APPENDECTOMY`, location `rural Bihar`, staffing constraint `part_time_doctors`
- `geocode`: Bihar focus, Patna fallback centroid, PIN context loaded
- `search_facilities`: 34 candidates within 50 km
- `get_facility_audit`: 7 canonical audits loaded
- `validate_staffing`: found part-time doctor notes and anesthesia roster gap
- `rank_results`: top facility score 72, one HIGH contradiction
- `update_map`: highlighted 7 candidates and selected top facility

This creates the feeling of an agent working without using chat bubbles or exposing raw chain-of-thought.

## Planner Query Accuracy

Planner Query should be more than a fake table. Even with mock data, it should behave as if it is rendering `QueryResult`.

Required improvements:

- Query input updates `?q=`.
- Parsed intent should reflect the user's query.
- The challenge query should be supported:
  - `Find the nearest facility in rural Bihar that can perform an emergency appendectomy and typically leverages part-time doctors.`
- The locked demo query should remain supported:
  - `Which facilities within 50km of Patna can perform an appendectomy?`
- Results should rank by explicit rules:
  - Trust Score descending.
  - Distance ascending as tie-breaker.
  - HIGH contradictions visible, not hidden.
- Each row should have "Why this rank?" expansion.
- CSV export should include query metadata and ranked table fields only.
- Query trace should show geocode, search, audit fetch, validation, and ranking steps.

Planner Query is still useful because it is the planner's spreadsheet/report workflow. Map Workbench is the exploratory agent workflow.

## Demo Data Update

Add a second canonical demo request based directly on `challenge.md`:

`Find the nearest facility in rural Bihar that can perform an emergency appendectomy and typically leverages part-time doctors.`

The demo data should include:

- A top-ranked appendectomy facility.
- `TrustScore.score = 72`.
- One HIGH `MISSING_STAFF` or `STAFFING_GAP` contradiction.
- Evidence that verifies appendectomy capability.
- Evidence that notes part-time doctor staffing.
- Evidence that contradicts safe surgery readiness, such as no anesthesiologist in `staff_roster`.
- A trace showing the agent used `geocode`, `search_facilities`, `get_facility_audit`, and `validate_staffing`.

This strengthens alignment with the challenge's exact MVP example and truth-gap framing.

## Sitemap Update Proposal

Replace the current route table with this conceptual model:

| Route | Surface | Primary job | Canonical data |
|---|---|---|---|
| `/` | Map Workbench | Agentic healthcare map with capability gaps, tool-call timeline, ranked facilities, and map updates. | `MapRegionAggregate`, `PopulationReference`, `FacilityAudit`, `QueryResult` |
| `/planner-query` | Planner Query Console | Exportable table mode for natural-language planning questions. | `QueryResult`, `ParsedIntent`, `RankedFacility` |
| `/facilities/:facility_id` | Facility Audit View | Evidence-backed proof surface for one facility and capability. | `FacilityAudit`, `TrustScore`, `EvidenceAssessment`, `Contradiction` |

`/desert-map` can remain temporarily as a redirect or alias to `/` while the team migrates language from "Desert Map" to "Map Workbench."

## User Journey

Primary demo journey:

1. User opens `/`.
2. Map Workbench shows India with default capability context.
3. User runs the challenge query in the Agent Run Panel.
4. Agent timeline animates through tool calls.
5. Map focuses Bihar/Patna and highlights candidate facilities.
6. Ranked facilities appear beside the timeline.
7. User opens the top Facility Audit.
8. Facility Audit shows appendectomy evidence, part-time staffing notes, missing anesthesiologist contradiction, Trust Score 72, and MLflow trace.
9. User returns to Map Workbench or opens Planner Query for exportable table mode.

Secondary report journey:

1. User opens `/planner-query`.
2. User runs the same query.
3. Planner Query shows parsed intent, ranked table, row rationale, query trace, and CSV export.
4. User opens Facility Audit from a row.

## Implementation Phases

### Phase 1: Documentation Alignment

- Update `01_sitemap.md` to introduce Map Workbench.
- Update `dashboard.md` and `desert_map.md` language so they no longer describe duplicate surfaces.
- Add Agent Run Panel requirements to the UX docs.
- Add the challenge query to Planner Query and Map Workbench docs.

### Phase 2: Frontend Restructure

- Rename Dashboard nav label to Map Workbench.
- Treat `/` as the main map-agent experience.
- Keep `/desert-map` as alias or redirect if needed.
- Move agent execution panel into the map screen.
- Reduce duplicated map controls between Dashboard and Desert Map.

### Phase 3: Mock Demo Upgrade

- Add challenge query and part-time doctor/staffing contradiction to demo data.
- Add agent timeline states to map screen.
- Connect timeline output to map highlights and ranked results.
- Add "Why this rank?" row expansions in Planner Query.

### Phase 4: Backend Integration Path

- Replace fake timeline events with streamed query-agent events.
- Bind `QueryResult.query_trace_id` to the panel.
- Bind `FacilityAudit.mlflow_trace_id` to Facility Audit trace.
- Use actual `search_facilities`, `get_facility_audit`, and geocoding outputs.

## Acceptance Criteria

- Dashboard and Desert Map no longer feel like two versions of the same page.
- The map screen clearly communicates "agentic healthcare intelligence system."
- Agent tool calls are visible on the map screen.
- Planner Query remains table-first and export-focused.
- Facility Audit remains evidence-first and proof-focused.
- Challenge query is supported in the demo data and visible in the UI.
- The Trust Score 72 plus staffing contradiction remains the main demo punchline.
- The UI stays within hackathon scope: no auth, no settings, no saved searches, no patient-facing flow, no chat history.
