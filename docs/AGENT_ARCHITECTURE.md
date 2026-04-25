# AGENT_ARCHITECTURE

> Diagram + contracts, not prose. If you can't draw the happy-path trace, the architecture isn't ready.

## System diagram

```
                     [ raw facility docs ]
                         │             │
                         ▼             ▼
                [ Extractor Agent ]   [ Indexer / Vector Index ] ───► list[IndexedDoc]
                         │             │                  │
                         ▼             │                  ▼
                [ Validator Agent ] ◄──┘           [ Query Agent ] ◄── NL query from Planner Console
                         │                                │
                         ▼                                ▼
                [ Trust Scorer ] ───► TrustScore      QueryResult
                         │                                │
                         ▼                                │
         [ FacilityAudit Builder ] ──────► FacilityAudit  │
                         │                  (canonical output,
                         │                   written to gold Delta table)
                         └───────────────┬────────────────┘
                                         ▼
              [ UI surfaces: Desert Map / Facility Audit / Planner Console ]
```

## Agent contracts

| Agent | Input | Output | Model | Retries | Max steps | Notes |
|---|---|---|---|---|---|---|
| **Extractor Agent** | raw doc chunk (text + source_type) | `list[Capability]` with `EvidenceRef`s | `claude-sonnet-4-6` (structured output) | 2 | n/a | Pydantic-validated output; one chunk → many capabilities; emits MLflow trace per chunk |
| **Indexer / Vector Index** | raw doc chunks | `list[IndexedDoc]` | `BAAI/bge-large-en-v1.5` embeddings (1024 dimensions) | 1 | n/a | Runs early in parallel with extraction; feeds retrieved evidence to Validator Agent and candidate retrieval to Query Agent |
| **Validator Agent** | `Capability` + retrieved evidence (top-k from vector index) | `list[Contradiction]` + `list[EvidenceAssessment]` | `claude-sonnet-4-6` | 1 | n/a | Runs on EVERY extraction (not on-demand); cross-checks against staff_roster / equipment_inventory / volume_report sources; uses `ContradictionType` enum and emits `EvidenceAssessment.stance` |
| **Trust Scorer** | `Capability` + `list[Contradiction]` | `TrustScore` | deterministic rubric + 1 LLM call (`claude-haiku-4-5-20251001`) for `reasoning` field | 0 | n/a | Score formula in docstring; confidence interval via bootstrap over evidence count and contradiction severity |
| **FacilityAudit Builder** | facility_id + all upstream outputs for that facility | `FacilityAudit` | deterministic (no LLM) | 0 | n/a | Aggregates per-capability `TrustScore`s into `dict[CapabilityType, TrustScore]`; writes to gold Delta table; populates `mlflow_trace_id` |
| **Query Agent** | NL query string | `QueryResult` | `claude-sonnet-4-6` (tool-calling) | 1 | 6 | Tools: `search_facilities(capability, lat, lng, radius_km)`, `get_facility_audit(facility_id)`, `geocode(query)`; `search_facilities` joins retrieval candidates with `FacilityAudit.location` or a facility geo table for radius filtering; returns ranked `RankedFacility` recommendations, never chat prose |

## Happy-path trace — appendectomy demo query

_End-to-end. If you can't write this, stop and fix the architecture._

1. User in Planner Console types: *"Which facilities within 50km of Patna can perform an appendectomy?"*
2. Query Agent receives query; opens MLflow trace `query_<uuid>` and binds it as `query_trace_id`.
3. Query Agent calls `geocode("Patna")` → `GeoPoint(lat=25.61, lng=85.14, pin_code="800001")`.
4. Query Agent calls `search_facilities(capability=CapabilityType.SURGERY_APPENDECTOMY, lat=25.61, lng=85.14, radius_km=50)` → returns candidate `facility_id`s by joining vector-index retrieval candidates with `FacilityAudit.location` or a facility geo table for the radius filter.
5. For each candidate, Query Agent calls `get_facility_audit(facility_id)` → fetches the canonical `FacilityAudit` from the gold Delta table (including `capabilities`, `trust_scores` with `trust_scores[*].contradictions`, `mlflow_trace_id`).
6. Query Agent computes `distance_km` per candidate and ranks them by `TrustScore.score` (descending), tie-broken by `distance_km` ascending.
7. Query Agent constructs `QueryResult` with `ranked_facilities: list[RankedFacility]` and populates `query_trace_id`; the result is returned as structured data, never as chat prose.
8. Planner Console renders the `QueryResult` as a sortable table; clicking a row opens the **Facility Audit View** with that facility's MLflow trace expanded by `FacilityAudit.mlflow_trace_id`.
9. The Facility Audit View shows the split pane: claimed `Capability` entries on the left vs. the `EvidenceRef` trail on the right, tagged from `EvidenceAssessment.stance` values: `verifies` / `contradicts` / `silent`.
10. Demo moment: top-ranked facility shows `TrustScore.score=72` with one `ContradictionType.MISSING_STAFF` flagged ("claims appendectomy capability but no anesthesiologist on staff_roster"). The contradiction is the punchline.

### MLflow contract

Every agent emits `mlflow.start_span` with the parent `trace_id` propagated through the pipeline. The two surfaces' lookup keys are:

- `FacilityAudit.mlflow_trace_id` — opens the extraction → validation → scoring trace for one facility.
- `QueryResult.query_trace_id` — opens the planner-side trace for one user query (geocode + search + per-facility audit fetches).

Traces are stored in the workspace MLflow tracking server. The UI fetches a trace by id and renders the span timeline inside the Facility Audit View, so every claim, contradiction, and ranked recommendation is one click away from its underlying agent steps.
