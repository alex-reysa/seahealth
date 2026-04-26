# Live Backend ↔ Frontend Connection Plan

**Date:** 2026-04-26
**Branch target:** `integrate/ship-12h` (release branch: `release/seahealth-submission`)
**Owner:** integrator (single lane at a time; see *Ordering Rationale*)
**Locked demo query:** *"Find the nearest facility in rural Bihar that can perform an emergency appendectomy and typically leverages parttime doctors."*

## TL;DR

SeaHealth ships today as a backend-complete FastAPI + a frontend that still imports `app/src/data/demoData.ts` directly on every page. This plan moves the visible UI onto the live API in eight scoped phases, preserves a deterministic demo path for offline review, and keeps every claim — traces, intervals, populations — tied to a real data field or an explicit "unavailable" state. No phase introduces new mock data; every phase ends with a green `pytest -q` and a green `npm run build`.

The submission story does not require live Databricks credentials. PARQUET mode (regenerated `tables/*.parquet`) is the production-equivalent path for judging; FIXTURE mode is the offline-review path. Live DELTA mode is documented and reachable but optional for the demo.

## Locked Invariants (do not change in this plan)

These are contract-level facts. Touching them breaks the rest of the plan and the existing 310-test floor.

1. **Closed enums.** `CapabilityType` (12 members) and `ContradictionType` (6 members) are frozen. New cases are out of scope.
2. **TrustScore formula.** `score = clamp(round(confidence * 100) - sum(severity_penalty), 0, 100)`, enforced by `model_validator`.
3. **Trace classification taxonomy.** `live` | `synthetic` (prefix `local::`) | `missing`. Frontend mirrors via `classifyTraceId()` in `app/src/types/api.ts`.
4. **Data mode auto-detect order.** `DELTA → PARQUET → FIXTURE` in `seahealth.api.data_access`. Each downgrade is a logged decision, never a silent fallback.
5. **Schema source of truth.** Pydantic in `src/seahealth/schemas/` → OpenAPI in `docs/api/openapi.yaml` → TS in `app/src/types/api.ts`. Drift is a test failure, not a runtime failure.
6. **Demo path stays green.** `VITE_SEAHEALTH_API_MODE=demo` must render every page without a backend running, for offline judging.

## Success Criteria (measurable)

A reviewer on a clean clone, with `DATABRICKS_TOKEN` unset, can:

1. `pytest -q` — green, ≥ 310 tests.
2. `cd app && npm run build` — green, no TypeScript errors.
3. Run `SEAHEALTH_API_MODE=parquet uvicorn seahealth.api.main:app --reload` and `cd app && VITE_SEAHEALTH_API_MODE=live VITE_SEAHEALTH_API_BASE=http://localhost:8000 npm run dev`.
4. Open the Planner page, paste the locked query, press run, see ≥ 1 backend-ranked facility with a non-empty `query_trace_id`, an evidence count, and a contradiction count.
5. Click a result, see a Facility Audit page populated from `GET /facilities/{id}` with capabilities, evidence snippets, contradictions, and a `TraceClassBadge` that matches the audit's actual trace state.
6. Open the Map page, see ≥ 3 distinct backend region rows with non-zero verified counts, click one, see the side panel update from `/map/aggregates` and the URL contain `?region_id=…`.
7. Switch to `VITE_SEAHEALTH_API_MODE=demo`, restart the dev server, repeat steps 4–6 and get the bundled fixture flow with no backend running.
8. Reproduce the eval claims from `docs/eval/naomi_run.md` via the documented commands.

If any one of these fails, the phase is not done.

## Current State (verified, with line refs)

### Backend — already wired
- `src/seahealth/api/main.py:115-153` — `/health/data` returns mode, retriever_mode, vs_endpoint, vs_index; redacts in production CORS posture.
- `src/seahealth/api/main.py:182-212` — `/query` routes through `run_query` in DELTA/PARQUET, falls back to fixture in FIXTURE mode, sets `X-Query-Trace-Id` header.
- `src/seahealth/api/main.py:215-242` — `/facilities/{id}`, `/map/aggregates`, `/facilities` all live and tested.
- `src/seahealth/schemas/query_result.py:56-67` — `QueryResult` has `query_trace_id` typed as MLflow trace id but is currently populated from a deterministic synthetic id when `MLFLOW_TRACKING_URI` is unset. Drift between docstring and runtime is the single largest contract bug in scope for Phase 2.
- `src/seahealth/schemas/map.py:22-45` — `MapRegionAggregate` has `region_id`, `centroid`, `gap_population`, **but no `parent_region_id` / `level` / `bounds`**. Phase 5 lands this.

### Frontend — partially wired
- `app/src/api/client.ts:102-146` — typed fetchers for `/summary`, `/query`, `/facilities/{id}`, `/map/aggregates`, `/health/data`, mode-aware via `resolveApiMode()`.
- `app/src/types/api.ts` — TS mirrors of every Pydantic shape; includes `classifyTraceId()`.
- `app/src/data/fixtures/*.json` — 4 bundled API-shape fixtures the client uses in demo mode.
- `app/src/pages/{Dashboard,DesertMap,FacilityAudit,PlannerQuery}.tsx` — **all four still import `app/src/data/demoData.ts` directly**, so the API client is unused by the visible UI today. This is the single largest UI-side gap.

### Documentation — already aligned
- `docs/api/openapi.yaml` — pinned by `tests/test_openapi_contract.py`; field set matches `app.openapi()`.
- `docs/PRODUCT_READINESS_REPORT.md` — Definition-of-Done table; this plan executes its remaining "Partial" rows for `1.4`, `3.1`, `3.2`, `3.3`, `4.3`.

## Target Operating Picture

```
┌─────────────────────────────┐         ┌─────────────────────────────┐
│ Browser (Vite + React 19)   │         │ FastAPI (Pydantic schemas)  │
│                             │         │                             │
│  ┌──────────────────────┐   │  HTTP   │  ┌──────────────────────┐   │
│  │ data-spine hooks     │◄──┼─────────┼──┤  /summary             │   │
│  │  useSummary          │   │         │  │  /query   (POST)      │   │
│  │  usePlannerQuery     │   │         │  │  /facilities/{id}     │   │
│  │  useFacilityAudit    │   │         │  │  /map/aggregates      │   │
│  │  useMapAggregates    │   │         │  │  /regions, children   │   │
│  │  useRegionTree       │   │         │  │  /health/data         │   │
│  │  useHealthData       │   │         │  └──────────┬───────────┘   │
│  └──────────┬───────────┘   │         │             │               │
│             │ live | demo   │         │   data_access (DELTA→PARQUET│
│  ┌──────────▼───────────┐   │         │              →FIXTURE)      │
│  │ pages                │   │         │                             │
│  │  Dashboard           │   │         │   agents.run_query (LLM     │
│  │  DesertMap           │   │         │     toggle on TOKEN)        │
│  │  PlannerQuery        │   │         │                             │
│  │  FacilityAudit       │   │         │   trace classifier:         │
│  └──────────────────────┘   │         │     live|synthetic|missing  │
└─────────────────────────────┘         └─────────────────────────────┘
        ▲                                              ▲
        │ VITE_SEAHEALTH_API_MODE=demo                 │ SEAHEALTH_API_MODE=fixture
        │ (no backend)                                 │ (no DB / no creds)
        │                                              │
   bundled fixtures                              tables/*.parquet (regenerable)
   (app/src/data/fixtures/*.json)                or fixtures/*.json (committed)
```

## Non-Goals

These are explicitly out of scope for the live-wire effort. Listing them prevents scope creep.

- New capability types or contradiction types.
- Authentication / user accounts / RBAC.
- Server-side rendering, SSG, or Vercel edge migration.
- Real-time streaming responses (SSE, WebSocket) for the planner query.
- Saved searches / persistent shortlists across reloads (URL state only).
- Live re-extraction or re-evaluation triggered from the UI.
- Multi-language i18n.
- Mobile-first responsive design beyond "doesn't break at 1024px".

## Cross-Cutting Concerns (apply to every phase)

### C1. Schema sync (3-step rule)

When any Pydantic schema changes, the same PR updates:
1. `src/seahealth/schemas/*` — the source.
2. `docs/api/openapi.yaml` — regenerated from `app.openapi()` (`tests/test_openapi_contract.py` enforces).
3. `app/src/types/api.ts` — hand-mirrored.

A test failure in `test_openapi_contract` means the OpenAPI is stale. A `tsc --noEmit` failure in `app/` means the TS mirror is stale. Both must pass before merge.

### C2. Error / Empty / Loading taxonomy

Every live surface renders four states, never just "happy path":

| State | Trigger | UI treatment |
|---|---|---|
| `loading` | request in flight | skeleton matching final shape; no layout shift |
| `empty` | 200 with empty list | "No results for {context}" with the active filter inline |
| `data-unavailable` | 503 from backend (DataLayerError) | banner with mode hint from `/health/data`, retry button |
| `error` | network / 4xx / unexpected shape | banner with `ApiError.detail`, retry button |

Implemented once in `app/src/components/domain/AsyncBoundary.tsx`. Pages compose it; pages do not handle states ad hoc.

### C3. Observability

- Every `/query` response sets `X-Query-Trace-Id`. Frontend logs it in dev mode and surfaces it in the trace panel.
- `/health/data` is the only endpoint a frontend calls to know its data mode. Cached for 30s in the data spine.
- Frontend errors flush to `console.error` with the trace id and request URL. No third-party telemetry.

### C4. Performance budgets

Per-page first-meaningful-paint on a fresh load against a local backend, measured with the dev server:

- Dashboard: ≤ 1.5s (1 `/summary` call, 1 `/health/data`).
- DesertMap: ≤ 2.5s (1 `/map/aggregates`, 1 TopoJSON parse).
- PlannerQuery: ≤ 2.0s for the page; `/query` itself is bounded by the agent (≤ 5s in PARQUET, ≤ 15s in DELTA with LLM).
- FacilityAudit: ≤ 1.5s.

If a phase pushes a page past budget, the phase is not done. Measured via Chrome devtools, not lighthouse.

### C5. Security & posture

- `CORS_ALLOW_ORIGINS` defaults to `*` (demo). Production posture (`!= *`) redacts `facility_audits_path`, `vs_endpoint`, `vs_index` and hides exception text in 503 bodies. Already implemented in `main.py:97-153` and tested in `tests/test_api.py`.
- No secrets in repo. `.env.example` uses placeholders. `tests/test_secrets_scan.py` (existing) keeps history clean.
- API client never sends `Authorization` headers. If live Databricks is needed, the backend holds the token; the frontend never sees it.

### C6. Testing strategy

Layered, no overlap:

| Layer | Tool | What it asserts |
|---|---|---|
| Schema contract | `pytest test_openapi_contract` | OpenAPI YAML matches `app.openapi()` |
| Backend unit | `pytest test_*.py` (existing) | Pydantic validators, agent logic |
| Backend route | `pytest test_api.py` (TestClient) | Status codes, headers, redaction |
| Frontend type | `tsc --noEmit` | TS shapes match the manual mirror |
| Frontend unit | (deferred) | not adding a runner this round |
| Frontend smoke | `npm run build` + manual curl + browser | renders, no console errors |
| E2E | Playwright (Phase 8 only, optional) | three flows: query → audit, map click, mode switch |

We do not add Vitest / Jest in this plan. The cost / benefit at this stage favors the schema contract test and the build gate over a partial unit suite.

## Risk Register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | `query_trace_id` claims to be MLflow but is synthetic in PARQUET mode | High | Medium | Phase 2: rename/document; surface trace class in body & header |
| R2 | Map needs `parent_region_id` but the gold table has none | Medium | High | Phase 5 ships a client hierarchy index from TopoJSON metadata as the fallback |
| R3 | Population denominators in PARQUET mode are stale | Medium | Medium | Phase 4: explicit "population unavailable" state instead of zero |
| R4 | Removing direct `demoData.ts` imports breaks the recorded demo video | Low | High | Demo mode keeps `app/src/data/fixtures/*.json` parity; re-record only if shapes diverge |
| R5 | Live `/query` latency exceeds 5s when LLM is on | Medium | Medium | Backend already has heuristic fallback; frontend shows step-level progress (Phase 2) |
| R6 | Schema drift between OpenAPI and TS during multi-PR work | High | Low | Contract test fails CI; PRs cannot merge with drift |
| R7 | TopoJSON file size pushes initial load past budget | Low | Medium | Asset is in `topoJson/`; if > 500KB gzipped, simplify with `mapshaper` (out of phase scope) |
| R8 | Region click triggers full TopoJSON re-render on map | Low | Medium | Maintain a stable feature collection; only update layer paint props |
| R9 | Reviewer runs in DELTA mode with no token, sees confusing 503s | Medium | Low | `/health/data` banner visible at all times; demo mode advertised in README |
| R10 | Hooks/state library choice (react-query vs custom) bloats bundle | Low | Low | Decision: stay with custom hooks + in-flight dedupe (no new dependency) |

## Phase Plan

Each phase: **Goal → Dependencies → Scope (in/out) → Backend tasks → Frontend tasks → Acceptance → Files → Sizing → Risks**.

Sizing in T-shirts: **S** ≈ 0.5d, **M** ≈ 1d, **L** ≈ 2d. Sequential single-developer estimates.

---

### Phase 0 — Stabilize Contracts (S)

**Goal.** Prove the OpenAPI / TS / Pydantic triad is locked, so every later phase can move fast.

**Dependencies.** None.

**In scope.** OpenAPI regen, TS mirror parity, contract test, README env doc.
**Out of scope.** Adding new fields. (Phase 2 / 5 will add fields against this locked baseline.)

**Backend tasks.**
1. Verify `tests/test_openapi_contract.py` passes from a clean checkout.
2. Add a `test_query_trace_header_matches_body` regression test (header `X-Query-Trace-Id` == body `query_trace_id`).
3. Document `MLFLOW_TRACKING_URI`, `DATABRICKS_TOKEN`, `SEAHEALTH_API_MODE`, `CORS_ALLOW_ORIGINS` in `.env.example`.

**Frontend tasks.**
1. Run `tsc --noEmit`; fix any drift in `app/src/types/api.ts`.
2. Remove the misleading "validateApiResponse" comment from `client.ts` if any survives (the implemented client is a cast, not a validator — already addressed in commit 06f39a9; verify).

**Acceptance.**
- `pytest -q` green, contract test green.
- `cd app && tsc --noEmit` green.
- README and `.env.example` agree on env var names.

**Files.** `docs/api/openapi.yaml`, `tests/test_openapi_contract.py`, `tests/test_api.py`, `.env.example`, `README.md`.

**Risks.** R6.

---

### Phase 1 — Frontend Data Spine (M)

**Goal.** Every page reads through one set of hooks. Direct `demoData.ts` imports are deleted.

**Dependencies.** Phase 0.

**In scope.** Hooks, `AsyncBoundary`, mode banner, page rewrites.
**Out of scope.** Adding new endpoints. UI design changes.

**Decision.** No `react-query` / `swr`. We add ~120 lines of custom hooks: `useFetch<T>`, in-flight dedupe by URL, 30s health cache, abort on unmount. This keeps the bundle lean and avoids a behavioral mismatch between fetch and cached state during the demo.

**Frontend tasks.**
1. Add `app/src/hooks/`:
   - `useFetch.ts` — generic suspense-free `{ data, error, status, refetch }` over the API client.
   - `useSummary.ts`, `usePlannerQuery.ts`, `useFacilityAudit.ts`, `useMapAggregates.ts`, `useHealthData.ts`.
2. Add `app/src/components/domain/AsyncBoundary.tsx` per C2.
3. Add `app/src/components/domain/DataModeBanner.tsx` reading `useHealthData()` — shows mode in dev, hidden under production CORS.
4. Rewrite each page in `app/src/pages/` to consume hooks; delete the `demoData.ts` import line.
5. Keep `app/src/data/demoData.ts` on disk for **only** the components that still legitimately want demo-shape data (none planned). Otherwise delete in Phase 8.

**Acceptance.**
- `grep -r "from '@/src/data/demoData'" app/src/pages` returns nothing.
- `VITE_SEAHEALTH_API_MODE=live` with backend up: every page renders with backend data.
- `VITE_SEAHEALTH_API_MODE=demo` (no backend running): every page renders with bundled fixtures, no console errors.
- Mode banner reflects `/health/data.mode` in live mode; says "demo (offline fixtures)" in demo mode.

**Files.** `app/src/hooks/*` (new), `app/src/components/domain/AsyncBoundary.tsx` (new), `app/src/components/domain/DataModeBanner.tsx` (new), `app/src/pages/{Dashboard,DesertMap,FacilityAudit,PlannerQuery}.tsx`.

**Sizing.** M (1d). The pages are ~200 lines each; the rewrite is mostly mechanical once the boundary lands.

**Risks.** R4 — keep fixtures byte-identical to current shapes; if they diverge, re-record demo per `docs/demo/script.md`.

---

### Phase 2 — Live Planner Query + Truthful Trace State (M)

**Goal.** The planner page is a real agent surface, and the trace claim is honest.

**Dependencies.** Phase 1.

**Decision (must resolve before code).** What does `query_trace_id` mean?

- **Option A — keep as MLflow trace id.** Backend captures the active span/trace via `mlflow.active_run()` when `MLFLOW_TRACKING_URI` is set; falls back to `local::query::<uuid>` synthetic id otherwise. UI badges trace class.
- **Option B — split into two fields.** `query_trace_id` becomes a correlation id (always present, always synthetic-style); add optional `mlflow_trace_id: str | None` and optional `mlflow_trace_url: str | None`.

**Recommendation: Option B.** It removes the docstring-vs-runtime lie, lets the synthetic id stay deterministic for tests, and lets the UI link out to MLflow only when a real trace exists.

**In scope.** New optional fields on `QueryResult`, real request lifecycle on the page, trace class badge, URL state.
**Out of scope.** Streaming intermediate results. Cancelling in-flight queries from the UI.

**Backend tasks.**
1. Add to `QueryResult`:
   - `mlflow_trace_id: str | None = None`
   - `mlflow_trace_url: str | None = None`
   - `execution_steps: list[ExecutionStep]` where `ExecutionStep = {name: str, started_at, finished_at, status: 'ok'|'fallback'|'error', detail: str | None}`
   - `retriever_mode: Literal['vector_search','faiss_local','fixture']`
   - `used_llm: bool`
2. Capture the steps in `agents.query.run_query` at: parse_intent, retrieve, score, rank. Always emit four steps even on the fallback path.
3. When `MLFLOW_TRACKING_URI` is set and a span is active, populate `mlflow_trace_id`. Construct `mlflow_trace_url` only when `MLFLOW_HOST` (existing convention) is also set.
4. Sync `docs/api/openapi.yaml` (test enforces) and `app/src/types/api.ts`.
5. New tests:
   - `test_query_returns_four_execution_steps`
   - `test_query_mlflow_fields_none_without_tracking_uri`
   - `test_query_header_correlation_id_present`
   - update `test_openapi_contract` reference fixture.

**Frontend tasks.**
1. Replace simulated `setTimeout` stages in `PlannerQuery.tsx` with `usePlannerQuery` from Phase 1, then render `execution_steps` as a step list with status pills.
2. `TraceClassBadge` consumes `mlflow_trace_id` (live) vs `query_trace_id` (synthetic) vs `null` (missing). Existing component covers the visuals; pass the right props.
3. URL state: `?q=…&capability=…&region_id=…`. Parse on mount; serialize on submit.
4. Result row click → `/audit/:facility_id?from=query&q=…` (so the back link is meaningful).

**Acceptance.**
- Submitting the locked query returns ≥ 1 ranked facility, four execution steps, a `query_trace_id`, and a `null` `mlflow_trace_id` in PARQUET mode.
- Header `X-Query-Trace-Id` equals body `query_trace_id`.
- TraceClassBadge says `synthetic` in PARQUET mode without MLflow, `live` if `MLFLOW_TRACKING_URI` is set, `missing` if both are null.
- URL reflects the active query; reload preserves it.

**Files.** `src/seahealth/schemas/query_result.py`, `src/seahealth/agents/query.py`, `src/seahealth/api/main.py`, `tests/test_query.py`, `tests/test_api.py`, `tests/test_openapi_contract.py` fixture, `docs/api/openapi.yaml`, `app/src/types/api.ts`, `app/src/pages/PlannerQuery.tsx`, `app/src/components/domain/TracePanel.tsx`, `app/src/components/domain/TraceClassBadge.tsx`.

**Sizing.** M (1d). The schema additions are mechanical; the lifecycle rewrite on the page is the bulk.

**Risks.** R1 (resolved by Option B), R5.

---

### Phase 3 — Live Facility Audit (S)

**Goal.** Clicking a facility shows the live `FacilityAudit` object.

**Dependencies.** Phase 1.

**In scope.** Wire the page to `/facilities/{id}`. Ensure `TraceClassBadge` reflects the audit's actual `mlflow_trace_id`.
**Out of scope.** New audit fields. Editing audits.

**Frontend tasks.**
1. `FacilityAudit.tsx` consumes `useFacilityAudit(id)`.
2. Trust score, evidence cards, contradictions render from the live shape (already TS-typed).
3. Empty/missing trace → badge `missing` + tooltip "this audit predates the trace column".
4. Add "why recommended" copy generated client-side from `trust_score.score`, `severity_penalties`, and the highest-severity contradiction. Pure function; no extra fetch.
5. `?from=query&q=…` → "← Back to results for '…'" affordance.

**Acceptance.**
- Open `/audit/<facility_id>` directly: live data renders, no console errors.
- The 10000 audits in PARQUET mode all show `missing` trace class (legacy data); fresh audits (post Phase 1A of the prior plan) show `synthetic` or `live`.
- Demo mode renders the bundled `facility_audit_demo.json`.

**Files.** `app/src/pages/FacilityAudit.tsx`, `app/src/components/domain/EvidenceCard.tsx`, `app/src/components/domain/TrustScore.tsx`, `app/src/components/domain/TracePanel.tsx`.

**Sizing.** S (0.5d).

**Risks.** R4.

---

### Phase 4 — Real Map Data + Honest Population (M)

**Goal.** Map shows backend `/map/aggregates`. Populates only when the data source supports it.

**Dependencies.** Phase 1.

**In scope.** Backend rendering of real region rows; frontend join-by-`region_id`; explicit "population unavailable" state when missing.
**Out of scope.** New geometry layers. Heatmaps.

**Backend tasks.**
1. Verify `/map/aggregates` returns ≥ 8 distinct `region_id` values in PARQUET mode (matches the bundled fixture today).
2. If `MapRegionAggregate.population` cannot be backed in PARQUET mode, set it to `0` AND add a sibling `population_source: Literal['delta','fixture','unavailable']` field. Do not ship a phantom denominator.
3. Add `verified_count_ci: tuple[int,int] | None` only if and when the Wilson helper is wired through. Keep the field optional; `null` is acceptable per C2.

**Frontend tasks.**
1. `DesertMap.tsx` joins TopoJSON features to `/map/aggregates` rows by `region_id`. Unjoined features render in a neutral "no data" paint.
2. Map legend explains severity bands explicitly (not "high/medium/low" — actual count thresholds).
3. Region click → URL `?region_id=…` and side panel update.
4. Side panel shows `population_source` so reviewers know whether the denominator is real.

**Acceptance.**
- Map renders ≥ 3 colored regions in PARQUET mode.
- Hovering Bihar shows verified/flagged counts that match `curl /map/aggregates`.
- Clicking a region updates URL and side panel without re-fetching `/map/aggregates`.
- No region tile claims a population number when `population_source == 'unavailable'`.

**Files.** `src/seahealth/schemas/map.py`, `src/seahealth/api/data_access.py`, `src/seahealth/api/main.py`, `tests/test_map.py`, `app/src/types/api.ts`, `app/src/pages/DesertMap.tsx`, `app/src/lib/mapJoin.ts` (new), `app/src/components/domain/MapLegend.tsx`.

**Sizing.** M (1d).

**Risks.** R3, R7, R8.

---

### Phase 5 — Region Hierarchy + Breadcrumbs (M)

**Goal.** Drill India → state → district. Two paths; pick the one that ships fastest.

**Dependencies.** Phase 4.

**Decision.** Two implementations are viable; choose based on what's actually in the gold table.

- **Path A — backend hierarchy.** Add `RegionNode` and two endpoints. Best long-term; requires gold-table support.
- **Path B — client hierarchy from TopoJSON.** India admin levels live in the geometry properties already (`topoJson/india_states.topo.json`). Build the parent-child index in JS; backend stays unchanged.

**Recommendation: Path B for the submission, Path A as a follow-up.** TopoJSON ships hierarchy metadata at the geometry level; we don't need a backend round-trip to do "click state → show districts". This avoids R2 and lets Phase 5 finish in M instead of L.

**Backend tasks (Path B).** None. (Path A would add `/regions` and `/regions/{id}/children`.)

**Frontend tasks.**
1. `app/src/lib/regionTree.ts` (new) — parses TopoJSON once, builds `Map<region_id, {parent, children, level, bounds, centroid}>`. Memoized at module scope.
2. `app/src/components/domain/Breadcrumbs.tsx` — reads `?region_id=…` from URL, walks the tree up, renders crumbs.
3. Click a parent crumb → URL parent `region_id`; map fly-to `bounds`.
4. Click a child region on the map → URL child `region_id`; side panel and planner-query context update.

**Acceptance.**
- Breadcrumbs render `India > State > District` for a 3-level URL.
- Browser back button walks the breadcrumb stack.
- Map fly-to is smooth (≤ 800ms ease) on parent and child clicks.
- Planner query inherits the current `region_id` as a default capability filter.

**Files.** `app/src/lib/regionTree.ts` (new), `app/src/components/domain/Breadcrumbs.tsx` (new), `app/src/pages/DesertMap.tsx`, `app/src/pages/Dashboard.tsx`.

**Sizing.** M (1d).

**Risks.** R2 (mitigated by choosing Path B).

---

### Phase 6 — Planner Usability (M)

**Goal.** A planner can do real work: filter, refine, shortlist, export.

**Dependencies.** Phases 2, 3, 4, 5.

**In scope.** PlannerControls, ShortlistPanel, CSV export, scenario comparison **for two regions only**.
**Out of scope.** Saving shortlists across sessions. Comments / notes on facilities. Multi-user collaboration.

**Frontend tasks.**
1. `PlannerControls.tsx` — capability dropdown, region picker (uses Phase 5 tree), radius slider, staffing qualifier select. Updates URL on every change.
2. `ShortlistPanel.tsx` — array of `facility_id` in URL (`?shortlist=a,b,c`); render mini-cards; remove buttons.
3. `app/src/lib/exportCsv.ts` — flat CSV from the shortlist (id, name, capability, score, contradictions count, top evidence snippet). Browser-side, no server round-trip.
4. "Compare two regions" — side-by-side panel with verified / flagged / gap deltas; uses two `/map/aggregates` queries with different `region_id` filters (or one filtered client-side).

**Acceptance.**
- Shortlist of 3+ facilities exports to CSV in one click.
- URL fully describes the planner state (query, region, capability, shortlist) — paste into a new tab and the state is identical.
- Scenario compare renders in ≤ 2.5s.

**Files.** `app/src/pages/PlannerQuery.tsx`, `app/src/pages/Dashboard.tsx`, `app/src/components/domain/PlannerControls.tsx` (new), `app/src/components/domain/ShortlistPanel.tsx` (new), `app/src/lib/exportCsv.ts` (new), `app/src/lib/scenarioCompare.ts` (new).

**Sizing.** M (1d).

**Risks.** R10 (decision: stay custom).

---

### Phase 7 — Submission Hardening (S)

**Goal.** Every claim in `docs/demo/script.md`, `docs/submission/one_pager.md`, and `README.md` matches the live UI.

**Dependencies.** Phases 1-6 merged.

**Tasks.**
1. Re-record `docs/demo/script.md` against the live-mode UI; remove the demoData.ts caveat (it no longer applies).
2. Update `docs/submission/one_pager.md`'s "three intervals" table — confirm what actually ships.
3. README quickstart: verify the four startup paths (PARQUET live, FIXTURE live, demo offline, full DELTA) line by line.
4. `docs/PRODUCT_READINESS_REPORT.md` — flip remaining "Partial" rows to "Yes" or to "Yes with residual-risk paragraph".
5. New `docs/eval/live_smoke.md` — terminal recipe a judge can copy-paste, with expected sample outputs.

**Acceptance.**
- A reviewer following only `README.md` reaches a working planner in < 5 minutes from clean clone.
- No `docs/*.md` references `demoData.ts` as the visible demo path (it's offline-fixture-only now).

**Files.** `docs/demo/script.md`, `docs/submission/one_pager.md`, `docs/PRODUCT_READINESS_REPORT.md`, `docs/eval/live_smoke.md` (new), `README.md`.

**Sizing.** S (0.5d).

**Risks.** R4, R9.

---

### Phase 8 — Optional E2E + Cleanup (S)

**Goal.** Lock the demo path against regression with three Playwright specs.

**Dependencies.** Phase 7.

**In scope.** Playwright install in `app/`, three specs, GitHub Actions workflow.
**Out of scope.** Visual regression. Cross-browser matrix.

**Tasks.**
1. `npm i -D @playwright/test`.
2. Specs:
   - `query.spec.ts` — open planner, paste locked query, see ≥ 1 result row.
   - `audit.spec.ts` — click first row, see TrustScore on next page.
   - `map.spec.ts` — click any region, breadcrumb shows two levels.
3. Run against `VITE_SEAHEALTH_API_MODE=demo` so CI doesn't need a backend.
4. Delete `app/src/data/demoData.ts` if no remaining import after Phase 1.

**Acceptance.**
- `npm run e2e` passes locally and in CI.
- `grep -r demoData app/src` returns nothing.

**Files.** `app/playwright.config.ts` (new), `app/e2e/*.spec.ts` (new), `app/package.json`, `.github/workflows/e2e.yml` (new).

**Sizing.** S (0.5d).

**Risks.** None new.

## Ordering Rationale

```
   Phase 0 (contracts)
        │
        ▼
   Phase 1 (data spine) ────────────────────────────┐
        │                                             │
        ├──► Phase 2 (planner + trace)               │
        ├──► Phase 3 (audit) ◄──────── (Phase 2 trace classes feed audit page)
        ├──► Phase 4 (map data) ──────► Phase 5 (hierarchy)
        │                                              │
        └────────────────────► Phase 6 (planner UX) ◄──┘
                                       │
                                       ▼
                                 Phase 7 (docs + demo)
                                       │
                                       ▼
                                 Phase 8 (E2E, optional)
```

Phases 2, 3, 4 are independent after Phase 1 lands and can be parallelized if multiple developers are available. Phase 5 must follow Phase 4 (uses the joined region rows). Phase 6 is the only consumer of all upstream phases.

## Verification Gates

Run before every PR merge into `integrate/ship-12h`:

```bash
# Backend
pip install -e ".[dev]"
pytest -q                            # ≥ 310 tests, all green
ruff check src tests                 # zero warnings

# Frontend
cd app
npm install
tsc --noEmit                         # zero TS errors
npm run build                        # vite build green, no warnings
```

### Live smoke (one terminal each)

```bash
# 1) Backend in PARQUET mode (no token needed)
SEAHEALTH_API_MODE=parquet uvicorn seahealth.api.main:app --reload --port 8000

# 2) Confirm wiring
curl -s http://localhost:8000/health/data | jq
# expect: {"mode":"parquet","retriever_mode":"faiss_local",...}

curl -s -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"Find the nearest facility in rural Bihar that can perform an emergency appendectomy and typically leverages parttime doctors."}' \
  -i | head -20
# expect: 200, X-Query-Trace-Id header, body.ranked_facilities length >= 1

# 3) Frontend live
cd app && VITE_SEAHEALTH_API_MODE=live VITE_SEAHEALTH_API_BASE=http://localhost:8000 npm run dev
# open http://localhost:3000, run the locked query, click first row, click map
```

### Demo smoke (one terminal)

```bash
cd app && VITE_SEAHEALTH_API_MODE=demo npm run dev
# open http://localhost:3000 — every page renders without a backend
```

## Rollout Strategy

This is hackathon-scoped, single-trunk, no feature flags beyond the env var.

- Each phase merges to `integrate/ship-12h` independently.
- `release/seahealth-submission` tracks `integrate/ship-12h` after Phase 7. The release tag is cut from there.
- No `main` merge in scope; the submission lives on the release branch.
- Rollback: `git revert` the offending merge; the contract test will catch any backend / frontend mismatch within a PR cycle.

## Definition of Done

The release is ready when:

1. Every Phase 1–7 acceptance check passes.
2. `pytest -q` floor ≥ 310, every gate above green.
3. The eight Success Criteria at the top of this doc all pass on a clean clone.
4. `docs/PRODUCT_READINESS_REPORT.md` shows zero "Partial" rows or paired residual-risk paragraphs.
5. `docs/demo/script.md` matches the live UI and has been re-recorded.
6. Tag `submission-live-final` pushed.

## Open Questions

1. **DELTA mode in the demo.** Do we want to actually flip on `DATABRICKS_TOKEN` in any judging environment, or is PARQUET sufficient? Default plan: PARQUET only; DELTA documented but not in the demo path.
2. **Population denominators.** `population_source: 'unavailable'` is the safe move; if a clean census source can be joined into PARQUET in Phase 4, upgrade to `'fixture'`. Decide before Phase 4 starts.
3. **MLflow URL construction.** Do we have a stable `MLFLOW_HOST` convention? If not, `mlflow_trace_url` stays `null` even when `mlflow_trace_id` is present. Confirm before Phase 2 implementation.
4. **Phase 8 (E2E) ship vs defer.** Hackathon time-budget call. Defer if Phase 7 lands < 24h before submission.
