# PHASES

> Time-boxed milestones with cutoff rules. **At hour 24, scope freezes.** This is the most important sentence in this document.

**Hackathon start:** TBD (set when the clock starts). All hour numbers below are relative to start.

---

## Two non-negotiables

1. **Schema ownership.** `Alejandro (acting schema owner)` owns `DATA_CONTRACT.md`. After hour 4, all changes to canonical schema names (`GeoPoint`, `CapabilityType`, `EvidenceRef`, `EvidenceStance`, `EvidenceAssessment`, `Capability`, `Contradiction`, `ContradictionType`, `TrustScore`, `FacilityAudit`, `IndexedDoc`, `ParsedIntent`, `QueryResult`, `RankedFacility`, `PopulationReference`, `MapRegionAggregate`) require their explicit approval. Veto power is real. Without this, three different `Facility` shapes appear in three files by hour 12.
2. **Demo script written at hour 24, not hour 36.** If a feature isn't in the demo script at hour 24, stop polishing it. The demo script is the spec for "what's actually shipping." Naomi (domain expert) drafts it at the Phase 2 → Phase 3 boundary.

---

## Phase 0 — Hours 0-4: Foundation — MERGED

- [x] `DATA_CONTRACT.md` locked. `Alejandro (acting schema owner)` assigned. Veto power active from hour 4.
- [x] Repo skeleton, env, secrets wired: Databricks workspace, MLflow tracking URI, Anthropic API key.
- [ ] Data exploration notebook in `docs/notebooks/` — sample 100 facility records, eyeball schema fit against `DATA_CONTRACT.md`.
- [x] Pydantic schemas implemented in `src/seahealth/schemas/` mirroring `DATA_CONTRACT.md` exactly: `GeoPoint`, `CapabilityType`, `EvidenceRef`, `EvidenceStance`, `EvidenceAssessment`, `Capability`, `Contradiction`, `ContradictionType`, `TrustScore`, `FacilityAudit`, `IndexedDoc`, `ParsedIntent`, `QueryResult`, `RankedFacility`, `PopulationReference`, `MapRegionAggregate`, `SummaryMetrics`.
- [x] One Extractor Agent run end-to-end on 10 rows producing valid `list[Capability]` (mocked-LLM tests merged in G-1).
- [ ] **Naomi (domain expert) parallel track:** starts hand-labeling 30 facility records — gold eval set seed.
- [x] MLflow tracing instrumented for the Extractor Agent; one trace visible end-to-end.

**Exit criteria:** schema is frozen; one row goes raw → `FacilityAudit` successfully (Trust Score may be stubbed); MLflow trace visible for one extraction.

---

## Phase 1 — Hours 4-12: Pipeline — MERGED

- [x] Full Extractor Agent pipeline runs over 10K rows; outputs `list[Capability]` to bronze Delta table (pipeline code lives in `src/seahealth/pipelines/extract.py`; tested with fixtures).
- [x] Vector index live: all chunks indexed as `IndexedDoc` with `BAAI/bge-large-en-v1.5` embeddings (Databricks VS endpoint READY in F-1; FAISS / SQL-warehouse fallbacks in retriever).
- [x] Query Agent answers ONE NL query end-to-end, returning a (rough) `QueryResult` with `RankedFacility` entries (heuristic path; live LLM path on Databricks Foundation Models, gated on `DATABRICKS_TOKEN`).
- [x] MLflow tracing turned on for Extractor Agent + Query Agent; `QueryResult.query_trace_id` stored on query output.
- [ ] **Naomi parallel track:** delivers contradiction taxonomy spec as rubric/examples mapped to locked `ContradictionType` values.

**Exit criteria:** can ask the demo query — "Which facilities within 50km of Patna can perform an appendectomy?" — and get a real (rough) ranked list with citations via `EvidenceRef`.

---

## Phase 2 — Hours 12-24: Trust + first surface — MERGED

- [x] Validator Agent online; runs on EVERY extraction (not on-demand); produces `list[Contradiction]` typed by `ContradictionType` plus `list[EvidenceAssessment]` for evidence stance.
- [x] Trust Scorer computes `TrustScore` for every `(facility_id, capability_type)` pair; `confidence_interval` populated via bootstrap.
- [x] FacilityAudit Builder writes canonical `FacilityAudit` records to gold Delta table (atomic-write-with-uuid path landed in AUD-03).
- [x] Planner Query Console wired through `/query` (heuristic path live; live Anthropic path on key drop).
- [x] MLflow tracing extended to Validator + Trust Scorer; `FacilityAudit.mlflow_trace_id` propagated into every `FacilityAudit`.
- [ ] **Naomi parallel track:** her hand-labeled 30-record set evaluated against extractions; precision/recall logged in MLflow (harness ready in M-1; awaiting real labels).
- [x] Top-line metric computed and surfaced via `SummaryMetrics`: "audited / verified / flagged".
- [ ] **Demo script drafted by Naomi at end of phase** (4 minutes, scripted to the second).

**Exit criteria — HARD HOUR-24 SCOPE FREEZE:**

> **At hour 24, scope freezes. From this point: the two already-planned Phase 3 surfaces may still ship, but no unplanned new feature is accepted. Anything else is rejected and logged below.**

---

## Phase 3 — Hours 24-36: Desert Map + Facility Audit View, polish — BACKEND MERGED

- [x] Backend endpoints for Desert Map (`/map/aggregates`) and Facility Audit (`/facilities/{id}`) live, backed by `GeoPoint`, `RankedFacility`, `MapRegionAggregate`, and `PopulationReference`.
- [x] Facility Audit View payload returns real `FacilityAudit` records with `EvidenceRef` snippets joined via `evidence_ref_id`.
- [x] Demo query — "Which facilities within 50km of Patna can perform an appendectomy?" — wired end-to-end on the heuristic path; ranked output ready for the three surfaces.
- [ ] Frontend (Desert Map / Facility Audit View / Planner Console) polished — out of this audit's scope.
- [ ] MLflow trace expansion functional inside Facility Audit View (or screenshot fallback documented in demo script).
- [ ] **Naomi parallel track:** delivers the FINAL demo script (4 minutes, scripted to the second), locked.

**Hard rule:** demo script is locked. Anything not on the demo script gets zero attention. New ideas go in the scope freeze log, not into the codebase.

---

## Phase 4 — Final 6-8: Ship — IN FLIGHT

- [ ] Demo video recorded (screen + voiceover, 4 min, follows Naomi's locked script).
- [ ] One-pager PDF for judges (data on left, product on right).
- [x] README Quickstart finalized — clone / install / env / pytest / smoke / uvicorn (see `README.md`).
- [x] Audit Swarm cherry-picks landed (`b93b400`, `7b7182c`, `e932076`, `cdfa9a3`, `2c02d2d`, `cab1981`); 246 tests green.
- [ ] L-1: regenerate fixtures from real data once `DATABRICKS_TOKEN` is in `.env` (LLM backend swapped to Databricks Foundation Models in DBX-1).
- [ ] Bug fixes only — NO new features, NO refactors, NO "while I'm in here" cleanups.
- [ ] Submission packaged.

---

## Scope freeze log (hours 24+)

_Anything attempted after hour 24 must be logged here AND rejected unless it's one of the two planned Phase 3 surfaces or a bug fix on an existing surface._

Format:

```
HH:MM — [proposer] proposed [feature]. Rejected. Reason: scope freeze.
HH:MM — [proposer] proposed [change]. Accepted as bug fix because [why].
```

- TBD
