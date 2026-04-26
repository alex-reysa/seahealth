# Product Readiness Report — SeaHealth (`integrate/ship-12h`)

**Generated:** 2026-04-26 — refreshed after live-backend connection plan.
**Source plan:** `docs/PRODUCT_READINESS_AUDIT_PROMPT.md` and
`docs/LIVE_BACKEND_FRONTEND_CONNECTION_PLAN.md`.
**Branch hash:** integrate/ship-12h tip after Phase 7 integration (see
`git log --oneline`).
**Test count:** **317 passing**, `pytest -q` clean from a fresh worktree.
**Locked demo query:** *"Find the nearest facility in rural Bihar that can perform an emergency appendectomy and typically leverages parttime doctors."*
**Locked facility audit demo target:** **CIMS Hospital Patna** (`vf_02239_cims-hospital-patna-a-un`) — present in the bundled `fixtures/facility_audit_demo.json`.

---

## Definition of Done — current status

| # | Criterion | Status | Evidence / Gap |
|---|---|---|---|
| 1.1 | 10k facility corpus processed, auditable, queryable | **Yes (with caveats)** | Phase 6 ran 9646/10000 facilities through Haiku 4.5; 2784 with capabilities, 4802 capability rows, 974 verified, 900 flagged. Live data in gitignored `tables/`; checked into repo as fixtures only. |
| 1.2 | Multi-attribute planning query works end-to-end on real data | **Yes** | MQ-1 closed-taxonomy `staffing_qualifier` shipped (`parttime`/`fulltime`/`twentyfour_seven`/`low_volume`); 10 unit tests; soft re-rank via `numberDoctors`. |
| 1.3 | Trust scores deterministic, explainable, citation-tied | **Yes** | `TrustScore.score = clamp(round(confidence*100) - severity_penalty_sum, 0, 100)` enforced via `model_validator`. Citations join via `evidence_ref_id = f"{source_doc_id}:{chunk_id}"`. |
| 1.4 | Medical deserts rendered geographically with planner actions | **Yes** | Phase 4/5 (commit `746702c`) wires `useMapAggregates()` into the Dashboard map; `app/src/lib/mapJoin.ts` joins backend `region_id` to topology features via an explicit alias map (unmatched rows render neutral with a dev-only warn); `app/src/lib/regionTree.ts` + `Breadcrumbs.tsx` drive India → Bihar → district drill-through with map flyTo; `MapLegend.tsx` surfaces "population unavailable" when `population_source === 'unavailable'`. |
| 2.1 | UC, Delta, Serverless SQL, MLflow, VS — live or substitution documented | **Partial** | UC catalog `workspace`, MLflow exp `405251052688464`, VS endpoint READY are documented. Live wiring requires `DATABRICKS_TOKEN`; FAISS/Parquet fallback chain runs locally. Substitutions (OpenRouter Haiku 4.5 vs. Agent Bricks) are noted in `DECISIONS.md`. **Gap:** judge-facing one-page rationale at the top of README. |
| 2.2 | MLflow trace IDs in audit records resolve to real traces when live | **Partial** | `_maybe_mlflow_span` prefers real `trace_id`/`request_id` when `MLFLOW_TRACKING_URI` is set; deterministic `local::<facility_id>::<run_uuid>` fallback when absent. **Gap:** current 10000 audits all have `mlflow_trace_id=None` because the 10k extraction predates MLT-1's parquet column. Trace-prefix validation + a re-extract option close this. |
| 2.3 | OpenRouter / direct LLM use framed as decision, not hidden | **Yes (Phase 2B)** | README architecture table, `docs/AGENT_ARCHITECTURE.md` substitutions section, and two new `DECISIONS.md` ADRs name the OpenRouter Haiku 4.5 substitution and the Genie/Agent-Bricks deferral. The agent code is provider-agnostic — flipping `SEAHEALTH_LLM_HEAVY_MODEL` reverts to Databricks Foundation Models. |
| 3.1 | Dashboard / Map / Planner / Audit run against live API | **Yes** | Live-wire plan complete: typed hooks (`useFetch`, `useSummary`, `usePlannerQuery`, `useFacilityAudit`, `useMapAggregates`, `useHealthData`), `AsyncBoundary` for the loading/empty/unavailable/error/success taxonomy, and `DataModeBanner` for visible mode reporting. PlannerQuery (commit `98b0f0e`), FacilityAudit (`604cadd`), and Dashboard counts/choropleth (`746702c`) all consume the API in live mode and bundled fixtures in demo mode. |
| 3.2 | Demo data is deliberate offline mode, not hidden dependency | **Yes (with one bounded carve-out)** | Pages flip on `VITE_SEAHEALTH_API_MODE`. The Dashboard still imports `demoData.ts` for the funding-priority lens copy (per-region `priorityScore`/`needSignal` etc.), which is committee-supplied client-side overlay metadata explicitly out-of-scope per the plan's Non-Goals. Visible counts and choropleth fill come from the API. |
| 3.3 | Every recommendation shows evidence + contradiction + confidence | **Yes** | FacilityAudit renders live trust score, evidence (snippet + source_doc_id + retrieved_at), contradictions (severity + reasoning + evidence_for/against counts), and `TraceClassBadge` driven by `audit.mlflow_trace_id`. PlannerQuery's `TracePanel` renders the four-step `execution_steps` with ok/fallback/error pills + ms elapsed, and the `TraceClassBadge` distinguishes live MLflow traces from synthetic correlation ids. |
| 4.1 | Naomi eval re-runnable from clean checkout | **Partial** | `python -m seahealth.eval.run_eval --labels tables/naomi_labels.csv` works; report at `docs/eval/naomi_run.md`. **Gap:** `tables/naomi_labels.csv` is gitignored; needs a clear "where to put the xlsx and run the adapter" walkthrough (Lane 4A). |
| 4.2 | P / R / F1 / contradiction recall + known limitations reported | **Partial** | Capability P=0.488 R=0.362 F1=0.416; per-capability breakdown shipped; **contradiction recall=0** with explanation. **Gap:** the limitations section needs an honest separation of extraction failures, unsupported labels, and model errors. |
| 4.3 | Aggregate claims include uncertainty | **Partial** | Schema has `MapRegionAggregate.capability_count_ci` and `TrustScore.confidence_interval` invariants; **gap:** UI does not render uncertainty (Lane 4B). |
| 5.1 | README quickstart works on clean clone | **Yes** | README quickstart updated to 317-test floor; modes matrix added (live vs demo); `docs/eval/live_smoke.md` is the copy-paste reviewer recipe with curl + browser steps for PARQUET, live-frontend, and demo-offline. |
| 5.2 | Demo script + video + one-pager + judge walkthrough | **No** | None of these artifacts exist yet (Phase 6). |
| 5.3 | No secrets, local-only paths, or untracked required artifacts | **Partial** | Audit Swarm AUD-10 confirmed secret scan clean across history; AUD-05 removed laptop-absolute paths from `db/retriever.py` and `db/databricks_resources.py`. **Gap:** README must state how a judge regenerates `tables/*.parquet` or runs in fixture mode without them. |

---

## Data artifact inventory

### Tracked (in repo)

- `fixtures/summary_demo.json` — `{audited:10000, verified:974, flagged:900, last_audited_at:2026-04-26T02:44:57Z}`
- `fixtures/facility_audit_demo.json` — CIMS Hospital Patna with capabilities, evidence refs, trust scores, **`mlflow_trace_id=null`** (legacy)
- `fixtures/demo_query_appendectomy.json` — 20 ranked Patna facilities for the locked query
- `fixtures/map_aggregates_demo.json` — 8 region rollups
- `tests/fixtures/naomi_labels_sample.csv` — 5-row synthetic Naomi sample (committed for tests)

### Untracked / gitignored (regenerated by pipeline)

- `tables/chunks.parquet` — vector index source chunks (10k rows)
- `tables/facilities_index.parquet` — `numberDoctors`, geo, used by MQ-1 re-rank
- `tables/capabilities.parquet` — 4802 capability rows from the 10k Haiku 4.5 run
- `tables/facility_audits.parquet` — 10000 audits (974 verified, 900 flagged)
- `tables/demo_subset.json` — `facility_ids` array for `seahealth.pipelines.extract --subset demo`
- `tables/naomi_labels.csv` — Naomi's 30-facility xlsx adapted to CSV; needed for eval

### Required but only documented (not in `.env.example` or README)

- Path to `VF_Hackathon_Dataset_India_Large.xlsx` ingestion command — **gap**

---

## Mapping audit findings to lanes

Every gap above is owned by exactly one lane in `docs/PRODUCT_READINESS_AUDIT_PROMPT.md`. Cross-reference:

| Gap | Lane | Priority |
|---|---|---|
| 10000 audits have `mlflow_trace_id=null` (legacy parquet predates MLT-1 column) | 1A | High — judge story |
| Trace-prefix validation in audit build | 1A | Medium |
| Citation snippet quality (some empty, some span-mismatched) | 1B | High — judge demo |
| `vague_claim`, `missing_staff`, `equipment_mismatch` heuristics for Naomi labels | 1C | High — eval lift |
| Vector Search live-mode flag in `/health/data` | 2A | Medium |
| Agent Bricks / Genie Code substitution rationale (one-page) | 2B | High — judge story |
| Single API client + `VITE_SEAHEALTH_API_MODE` | 3A | High — UI quality |
| Facility Audit trace-view (snippets + trace IDs together) | 3B | High — demo punchline |
| Map workbench non-placeholder choropleth | 3C | High — desert MVP |
| Naomi eval clean-clone repro | 4A | Medium |
| Confidence interval rendering (TrustScore CI + capability_count_ci) | 4B | Medium |
| Clean-clone runtime path | 5A | High — submission |
| API CORS + structured errors + secret scan | 5B | Medium |
| 4-min demo script + video | 6A | Required |
| One-pager + judge walkthrough | 6B | Required |
| Final integration tag + release branch | 7 | Required |

---

## Quality gates (locked for Phase 1+)

1. `pytest -q` must remain green; current floor is **279 tests**.
2. `ruff check src tests` must pass.
3. Each lane's diff must stay inside the file scope declared in the audit prompt.
4. Before merging into `integrate/ship-12h`, run `cd app && npm run build` for any frontend-touching lane.
5. No secrets ever committed; AUD-10's history scan stays clean.

---

## Residual risks (acknowledged, scoped for Phase 7)

1. **Live MLflow traces.** Current 10000 audits have `mlflow_trace_id=null`. Phase 1A populates the column for **fresh** runs; a full re-extract is deferred unless time allows. The Facility Audit View must mark missing traces as a data-quality state, not a successful render.
2. **Contradiction recall=0 on Naomi labels.** Phase 1C lifts this with the smallest useful heuristics. We will report the lift transparently — not via a label-leakage hack.
3. **`MapRegionAggregate.capability_count_ci`.** Schema is locked but UI rendering of intervals is Phase 4B work.
4. **Demo video not yet recorded.** Phase 6A is the unblocker; a deterministic data mode keeps the recording reproducible.

---

## Definition of "done" gating (re-stated)

The release branch (`release/seahealth-submission`) is created only when:

- All Phase 1–4 lanes are merged or have an explicit residual-risk note in this report.
- Phase 5 clean-clone path produces a green `pytest`, an API on :8000, and a frontend on the dev server **without** a `DATABRICKS_TOKEN`.
- Phase 6 ships a script, a video link, and the one-pager.
- This file's "Definition of Done" table is all **Yes** or has a residual-risk paragraph below.

The integrator owns this report. Each lane appends its own row to the table above when it merges.
