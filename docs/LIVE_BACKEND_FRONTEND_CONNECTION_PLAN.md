# Live Backend-Frontend Connection Plan

Date: 2026-04-26
Target: make SeaHealth a live planning workbench backed by real FastAPI/Databricks data, not a static demo UI.

## Success Criteria

1. Agent queries run from the frontend against the backend, return real ranked facilities, and show the real execution trace/correlation state.
2. Users can click and navigate across multiple Indian regions with smooth parent-child navigation and breadcrumbs.
3. The map shows real locations and real backend data, not hardcoded demo counters.
4. The product has a usable planning layer: filters, query intent, ranked options, evidence, export/share, and planner-facing explanations.
5. The solution meets or exceeds the challenge criteria: discovery/verification, intelligent document parsing, social impact/utility, and transparency.

## Current Gap Summary

- The FastAPI backend already exposes the right starting surface: `/summary`, `/query`, `/facilities`, `/facilities/{id}`, `/map/aggregates`, `/health/data`.
- The React app has a typed API client, but primary pages still import `demoData.ts` directly.
- The visible trace timeline is demo-only; backend `QueryResult` returns `query_trace_id` but not a step/span timeline.
- Map aggregates are flat rows today; true parent-child navigation needs either hierarchy fields from the backend or a client-side region hierarchy index.
- Real map population/gap claims depend on the Delta/gold path; PARQUET fallback currently cannot support the full population-desert story without extra joined data.

## Phase 0: Stabilize Contracts Before Wiring

Goal: make the backend contract the single source of truth.

Tasks:

1. Regenerate `docs/api/openapi.yaml` from the current FastAPI app.
2. Sync `app/src/types/api.ts` with the regenerated backend schema.
3. Add missing frontend fields:
   - `SummaryMetrics.verified_count_ci`
   - `HealthData.retriever_mode`, `vs_endpoint`, `vs_index`
   - any planned query trace fields.
4. Remove misleading comments about runtime validators unless validators are implemented.
5. Add a contract test that fails when committed OpenAPI drifts from `app.openapi()`.

Acceptance criteria:

- `docs/api/openapi.yaml` contains every runtime field returned by `/summary` and `/health/data`.
- TypeScript types match snake_case API responses or a documented adapter maps them.
- No page-level code depends on undocumented response fields.

Likely files:

- `src/seahealth/api/main.py`
- `src/seahealth/schemas/*.py`
- `docs/api/openapi.yaml`
- `app/src/types/api.ts`
- `tests/test_api_contract.py`

## Phase 1: Create One Frontend Data Spine

Goal: every page gets data through one live/demo abstraction.

Tasks:

1. Introduce a data provider or hooks layer:
   - `useSummary`
   - `usePlannerQuery`
   - `useFacilityAudit`
   - `useMapAggregates`
   - `useFacilities`
   - `useHealthData`
2. Route mode through `VITE_SEAHEALTH_API_MODE=live|demo`.
3. Keep demo mode as explicit fixture fallback, but remove direct page imports from `demoData.ts`.
4. Add adapters for snake_case API responses to the UI view models where needed.
5. Add loading, empty, and error states for every live surface.

Acceptance criteria:

- No page imports `app/src/data/demoData.ts` directly.
- `VITE_SEAHEALTH_API_MODE=live` calls FastAPI.
- `VITE_SEAHEALTH_API_MODE=demo` uses bundled fixtures deterministically.
- One switch can move the app between live and demo without page rewrites.

Likely files:

- `app/src/api/client.ts`
- `app/src/hooks/*`
- `app/src/providers/*`
- `app/src/lib/apiAdapters.ts`
- `app/src/pages/Dashboard.tsx`
- `app/src/pages/PlannerQuery.tsx`
- `app/src/pages/FacilityAudit.tsx`
- `app/src/pages/DesertMap.tsx`

## Phase 2: Live Planner Query With Real Trace State

Goal: the planner query page becomes a real agent surface.

Backend tasks:

1. Clarify `query_trace_id` semantics:
   - If it is a client correlation id, rename/copy description away from "MLflow trace id".
   - If it must be a real MLflow trace id, capture the MLflow span/trace id and return it.
2. Extend `QueryResult` with optional execution metadata:
   - `execution_steps`: ordered planner/tool/retriever/validator steps.
   - `retriever_mode`: `vector_search`, `faiss_local`, `fixture`, or equivalent.
   - `used_llm`: boolean.
   - `trace_url`: optional external MLflow URL when constructible.
3. Ensure heuristic and fixture paths still return a truthful trace state:
   - `live`
   - `synthetic`
   - `missing`
4. Add tests for header/body trace consistency.

Frontend tasks:

1. Replace simulated `setTimeout` stages in `PlannerQuery.tsx` with real request lifecycle states.
2. Render:
   - parsed intent
   - ranked facilities
   - evidence count
   - contradiction count
   - query trace id/class
   - execution steps/timeline.
3. Keep URL state: `?q=...&capability=...&region_id=...`.
4. Provide clear error states when backend data is unavailable.

Acceptance criteria:

- User enters the challenge query in the frontend and receives backend-ranked results.
- `X-Query-Trace-Id` matches the `query_trace_id` or documented correlation id in the body.
- The UI shows whether the trace is live MLflow, synthetic offline, or missing.
- Every recommended facility links to Facility Audit.

Likely files:

- `src/seahealth/schemas/query_result.py`
- `src/seahealth/agents/query.py`
- `src/seahealth/api/main.py`
- `tests/test_query.py`
- `tests/test_api.py`
- `app/src/pages/PlannerQuery.tsx`
- `app/src/components/domain/TracePanel.tsx`
- `app/src/components/domain/TraceClassBadge.tsx`

## Phase 3: Live Facility Audit and Evidence View

Goal: clicking a facility shows the actual audit object, not a static mock.

Tasks:

1. Wire `FacilityAudit.tsx` to `GET /facilities/{facility_id}`.
2. Adapt backend `FacilityAudit` into the existing UI sections:
   - capabilities
   - trust scores
   - contradictions
   - evidence snippets
   - source metadata
   - audit-level trace state.
3. Make missing traces explicit as data-quality gaps.
4. Add "why recommended / why downranked" copy based on trust score penalties and contradictions.
5. Preserve navigation context from map/planner with query params.

Acceptance criteria:

- Facility Audit opens from map and planner rows.
- A planner can explain why a facility was recommended or downranked without leaving the UI.
- Evidence snippets and contradiction reasoning are visible for the selected capability.
- Missing or synthetic traces are not represented as successful live traces.

Likely files:

- `app/src/pages/FacilityAudit.tsx`
- `app/src/components/domain/EvidenceCard.tsx`
- `app/src/components/domain/TrustScore.tsx`
- `app/src/components/domain/TracePanel.tsx`
- `app/src/lib/apiAdapters.ts`
- `src/seahealth/schemas/facility_audit.py`

## Phase 4: Real Map Data and Location Layer

Goal: the map displays backend map aggregates and real facility locations.

Backend tasks:

1. Confirm `GET /map/aggregates` returns real region rows in the deployed mode.
2. Add or verify stable `region_id` values that can join to map geometries.
3. Decide how population/gap data is sourced:
   - Delta gold table for production.
   - Static in-repo population join for local PARQUET mode.
   - Explicit "unavailable" state if neither exists.
4. Add optional confidence interval fields to `MapRegionAggregate` only if the map will claim intervals.
5. Ensure `GET /facilities` can return enough real geocoded facilities for markers and side panels.

Frontend tasks:

1. Replace hardcoded summary counters and region properties with `/summary` and `/map/aggregates`.
2. Join backend aggregates to India geometry by `region_id`.
3. Use `centroid` for fly-to and selected-region camera behavior.
4. Use real facility lat/lng markers from `/facilities` or query results.
5. Add map legend copy that explains exactly what severity means.

Acceptance criteria:

- Multiple regions display distinct backend aggregate values.
- Region click updates URL state and side panel data.
- Facility markers correspond to real API facility records.
- Map does not claim population or Wilson intervals unless those fields are backed by data.

Likely files:

- `src/seahealth/schemas/map.py`
- `src/seahealth/api/data_access.py`
- `src/seahealth/api/main.py`
- `app/src/pages/Dashboard.tsx`
- `app/src/pages/DesertMap.tsx`
- `app/src/lib/mapJoin.ts`
- `app/src/components/domain/MapLegend.tsx`

## Phase 5: Parent-Child Region Navigation and Breadcrumbs

Goal: users can navigate India → state → district/region smoothly.

Backend option A: real hierarchy API.

1. Extend `MapRegionAggregate` or add `RegionNode`:
   - `region_id`
   - `region_name`
   - `level`: `country|state|district|pin_cluster`
   - `parent_region_id`
   - `children_count`
   - `centroid`
   - `bounds`
2. Add `GET /regions` and `GET /regions/{region_id}/children`.
3. Add tests for parent-child integrity.

Frontend option B: client hierarchy index.

1. Build a local region hierarchy from geometry metadata plus backend aggregates.
2. Store breadcrumb stack in URL.
3. Drill down from state to child regions when geometry/data is available.

Recommended path:

- Use backend hierarchy if Delta/gold tables can provide stable region levels.
- Use client-derived hierarchy only as an interim UI path.

Acceptance criteria:

- Breadcrumb shows `India > State > Region`.
- Clicking a parent breadcrumb zooms out and resets child filters.
- Clicking a child region updates map, side panel, planner query context, and URL.
- Navigation remains smooth across at least three states and several child regions.

Likely files:

- `src/seahealth/schemas/region.py`
- `src/seahealth/api/main.py`
- `src/seahealth/api/data_access.py`
- `app/src/components/domain/Breadcrumbs.tsx`
- `app/src/pages/Dashboard.tsx`
- `app/src/pages/DesertMap.tsx`

## Phase 6: Planning Layer Usability

Goal: make the app useful for NGO planners, not just impressive technically.

Features:

1. Planner objective panel:
   - selected capability
   - selected geography
   - radius
   - staffing qualifier
   - urgency/high-acuity toggle.
2. Result explanation:
   - why this facility ranked here
   - trust score components
   - contradictions
   - distance
   - evidence count.
3. Action layer:
   - shortlist facilities
   - export CSV
   - copy/share URL
   - open audit
   - generate planning note.
4. Scenario comparison:
   - compare two regions
   - compare capabilities within region
   - show medical desert severity changes.
5. Honesty states:
   - "data unavailable"
   - "trace unavailable"
   - "population denominator unavailable"
   - "fixture mode"
   - "low evidence count".

Acceptance criteria:

- A planner can start at the map, select a region/capability, run or refine a query, open audits, and export/share a shortlist.
- Every recommendation has visible evidence and contradiction context.
- The UI makes uncertainty and missing data visible.

Likely files:

- `app/src/pages/Dashboard.tsx`
- `app/src/pages/PlannerQuery.tsx`
- `app/src/pages/FacilityAudit.tsx`
- `app/src/components/domain/PlannerControls.tsx`
- `app/src/components/domain/ShortlistPanel.tsx`
- `app/src/lib/exportCsv.ts`

## Phase 7: Challenge Criteria Hardening

Goal: turn implementation into a defensible judging story.

Discovery and Verification (35%):

- Show 10k extraction scale.
- Show trust scoring and contradiction checks.
- Show citation QA counts.
- Add one UI panel or docs section with the latest eval metrics.

IDP Innovation (30%):

- Surface parsed intent and extracted evidence.
- Show messy-note snippets and normalized capability mapping.
- Demonstrate `vague_claim`, `missing_staff`, and equipment mismatch examples.

Social Impact and Utility (25%):

- Map high-risk medical deserts.
- Show gap population only when backed by data.
- Provide planner action outputs: shortlist/export/share.

UX and Transparency (10%):

- Show execution steps/trace state.
- Show citations inline.
- Explain uncertainty and missing data.
- Keep navigation fast and understandable.

Acceptance criteria:

- Demo script matches the actual UI and backend data.
- One-pager claims match implemented fields and verified commands.
- Evaluation evidence can be reproduced from documented commands.
- No challenge claim relies on hidden mock data.

Likely files:

- `docs/demo/script.md`
- `docs/submission/one_pager.md`
- `docs/PRODUCT_READINESS_REPORT.md`
- `docs/PRODUCT_READINESS_IMPLEMENTATION_AUDIT.md`
- `docs/eval/naomi_run.md`
- `README.md`

## Verification Gates

Backend:

```bash
pip install -e ".[dev]"
pytest -q
ruff check src tests
```

Frontend:

```bash
cd app
npm install
npm run lint
npm run build
```

Live smoke test:

1. Start FastAPI with explicit mode:
   ```bash
   SEAHEALTH_API_MODE=parquet uvicorn seahealth.api.main:app --reload
   ```
2. Start frontend:
   ```bash
   cd app
   VITE_SEAHEALTH_API_MODE=live VITE_SEAHEALTH_API_BASE=http://localhost:8000 npm run dev
   ```
3. Confirm:
   - `/health/data` reports expected data mode and retriever mode.
   - planner query returns backend-ranked facilities.
   - trace id appears in body and header.
   - map aggregates come from backend.
   - facility audit opens from planner and map.
   - breadcrumbs update URL and map camera.

Browser/E2E:

- Add Playwright or equivalent for:
  - map loads real regions
  - region click opens side panel
  - planner query runs
  - facility audit opens
  - evidence and trace state render.

## Recommended Implementation Order

1. Fix audit blockers: OpenAPI drift, demo narrative drift, summary timestamp bug, CORS docs.
2. Build the data provider and remove direct `demoData.ts` page imports.
3. Wire live planner query and trace/correlation display.
4. Wire live facility audit.
5. Wire live summary and map aggregates.
6. Add region hierarchy and breadcrumbs.
7. Add planning usability features.
8. Update docs/demo/one-pager to match the real flow.
9. Run gates, browser smoke, and final audit.

## Definition of Done

The release is ready when a reviewer can:

1. Start backend and frontend in live mode.
2. Navigate India → state → region with breadcrumbs.
3. See real map aggregate data and real facility locations.
4. Run the challenge query from the UI.
5. Open a recommended facility audit.
6. See evidence, contradictions, trust score, and trace state.
7. Export/share a planning shortlist.
8. Reproduce evaluation and product claims from documented commands.
