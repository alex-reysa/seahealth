# SeaHealth — Databricks, Agentic RAG, and End-State Audit

**Reviewed:** 2026-04-26  
**Branch context:** `integrate/ship-12h` plus product-readiness follow-ups  
**Scope:** Repository-grounded audit of Databricks usage, RAG/retrieval wiring,
agentic traceability, and the remaining path to the desired challenge end state.

This file is intentionally stricter than the architecture docs. It separates:

- **Built:** code or Databricks resources exist.
- **Wired:** a production/demo runtime path calls them.
- **Visible:** the user or judge can see the capability in the API/UI/demo.

---

## TL;DR

- **The Databricks foundation is real, but unevenly productized.** Unity
  Catalog schemas, a managed Volume, 7 Delta tables, an MLflow experiment, SQL
  Warehouse helpers, and a Mosaic AI Vector Search endpoint/index are
  provisioned by `src/seahealth/db/databricks_resources.py`. The bundle itself
  is much thinner: it declares the MLflow experiment and a single extraction
  job, not the full lakehouse lifecycle.
- **The agent pipeline exists, but the desired RAG loop is not wired.**
  `VectorSearchRetriever` / `FaissRetriever` are implemented and tested, yet no
  production agent or pipeline calls `get_retriever()` or `retriever.search()`.
  The Validator can assess retrieved evidence, but `build_audits.py` invokes it
  only as a heuristics safety net with `use_llm=False` and no retrieved chunks.
- **MLflow traceability is partially real, not end-to-end.** Extraction wraps
  each facility in an MLflow span and propagates the trace id onto
  `Capability` / `FacilityAudit`. Query opens a best-effort `seahealth.query`
  span, but it closes before the actual parse/retrieve/score work. Validator,
  Trust Scorer, and Audit Builder do not open their own spans.
- **The live Delta serving story needs one more hardening pass.** Extraction
  best-effort inserts capabilities into Delta. `build_audits.py` writes the
  canonical gold artifact to Parquet and only performs a smoke SQL call for the
  Delta mirror. The gold `facility_audits` DDL is also slimmer than the current
  Pydantic `FacilityAudit` / `TrustScore` shape consumed by the API.
- **Highest-leverage next move:** add a dedicated Validate step that retrieves
  same-facility chunks, calls `validate_capability(..., use_llm=True)`, writes
  `evidence_assessments` / `contradictions`, and wraps Retrieve → Validate →
  Score in MLflow spans. That closes the biggest gap against Discovery &
  Verification and UX/Transparency.

---

## Desired End State

The challenge asks for an agentic healthcare intelligence system that can audit
10k messy facility reports, reason across attributes, flag contradictions, and
make the reasoning transparent. For this repo, the desired end state is:

1. **Delta as source of truth.** Raw/chunked facility records land in bronze,
   extracted and validated claims land in silver, and `FacilityAudit` /
   `MapRegionAggregate` are served from gold with schemas matching the Python
   contracts.
2. **RAG-backed verification.** Every extracted `Capability` is cross-checked
   against retrieved same-facility chunks before trust scoring. The
   `EvidenceAssessment` table is populated by the Validator, not just reserved.
3. **Multi-attribute planner query.** The Query Agent combines structured gold
   audit search with semantic retrieval over unstructured notes so phrases that
   miss the closed enum still surface candidate facilities and evidence.
4. **End-to-end traceability.** MLflow traces cover Extract → Retrieve →
   Validate → Score → Build Audit and Query parse/tool calls/ranking. The UI
   can honestly open a trace that shows more than one span.
5. **One data spine for demo and live.** React pages, FastAPI responses,
   fixtures, OpenAPI, and submission docs describe the same objects and clearly
   label when a screen is fixture-backed versus Delta-backed.
6. **Transparent Databricks-native posture.** Databricks-native components are
   used where they materially help; substitutions such as OpenRouter for the
   10k LLM run are explicit, reversible, and not hidden in judge-facing copy.

---

## Current State vs. Desired State

| Area | Current repository state | Desired state | Gap |
|---|---|---|---|
| UC + Delta foundation | `databricks_resources.py` provisions `workspace.seahealth_bronze`, `workspace.seahealth_silver`, `workspace.seahealth_gold`, Volume `raw`, and 7 tables. | All pipeline outputs are written to Delta and read from Delta in live mode. | Gold audits are Parquet-first; Delta mirror is not a real write path yet. |
| Asset Bundle | `databricks.yml` declares the MLflow experiment and `extract-pipeline` job only. | Bundle declares repeatable jobs/tasks for extract, validate, build audits, and refresh schedule. | Bundle is not the full deployment manifest. |
| Vector Search | Endpoint `seahealth-vs`; index `workspace.seahealth_bronze.chunks_index`; retriever client built. | Validator and Query both call retrieval in normal runtime paths. | Retriever is built/tested but disconnected from agents. |
| Validator | `validate_capability` supports `retrieved_evidence` and emits `EvidenceAssessment`; `build_audits.py` calls it with `use_llm=False` and no evidence. | Validator runs after extraction for every capability with top-k retrieved evidence and writes silver outputs. | Evidence assessment producer is missing. |
| Query Agent | Tool loop uses `geocode`, `search_facilities`, and `get_facility_audit`; `search_facilities` scans `facility_audits.parquet` and applies radius/trust filters. | Query has both structured audit search and semantic chunk search. | No semantic search tool; `retriever_mode` is informational rather than causal. |
| MLflow | Extractor spans are real when MLflow is configured; `QueryResult` has trace fields; query span currently wraps no meaningful work. | Full span tree for extraction/validation/scoring/query tools. | Trace ids are propagated, but most steps do not create spans. |
| Foundation Models | LLM client routes model ids without `/` to Databricks Foundation Models; 10k run used OpenRouter Anthropic Haiku 4.5 due to rate limits. | Native Databricks model run is available for headline numbers or substitution is clearly caveated. | Re-run or keep caveat prominent. |
| API live mode | `data_access.detect_mode`: DELTA → PARQUET → FIXTURE. | DELTA mode is contract-compatible and returns the same shapes as Parquet/fixture. | Gold DDL and Python `FacilityAudit` shape need alignment. |
| UI/demo | Submission script explicitly uses static frontend demo data for deterministic recording. | Demo and API fixtures use one canonical facility/story, or the split is explicitly documented. | Current split is acceptable only if caveated. |
| Confidence intervals | `TrustScore.confidence_interval` exists; `SummaryMetrics.verified_count_ci` exists; slim `MapRegionAggregate` has no CI field. | Interval claims distinguish trust-score bootstrap, summary Wilson CI, and map-region follow-up. | Avoid claiming map CIs until `MapRegionAggregate` carries them. |

---

## Agentic Architecture Audit

### What Is Solid

| Agent | Current implementation | Notes |
|---|---|---|
| Extractor | `agents/extractor.py` emits structured `Capability` rows through the shared LLM client; `pipelines/extract.py` wraps facility extraction in `_maybe_mlflow_span`. | This is the strongest agentic + tracing path today. |
| Validator | `agents/validator.py` runs deterministic heuristics first and optional LLM assessment second. It can add `EvidenceAssessment` rows for retrieved evidence. | The interface is correct; the runtime path does not feed it retrieved evidence. |
| Trust Scorer | `agents/trust_scorer.py` computes deterministic confidence, score, bootstrap CI, and optional LLM reasoning. | Reliable and testable; the LLM adds prose, not core scoring logic. |
| Query Agent | `agents/query.py` has a bounded tool loop and deterministic fallback; outputs `QueryResult`, not chat prose. | Good shape, but retrieval is structured table search, not RAG. |
| FacilityAudit Builder | `agents/facility_audit_builder.py` is a pure Python assembler. | Correct as an aggregation boundary; it should remain deterministic. |

### Main Weaknesses

1. **The architecture diagram is ahead of the runtime.** `docs/AGENT_ARCHITECTURE.md`
   shows the Indexer/Vector Index feeding Validator and Query. In code, the
   retriever is not called from either path.
2. **`evidence_assessments` is a reserved table more than a live output.**
   `build_audits.py` reads `evidence_assessments.parquet`, but there is no
   pipeline that produces it from retrieved chunks and the LLM Validator.
3. **Trace depth is shallow.** A `FacilityAudit.mlflow_trace_id` can exist, but
   it usually points to extraction only. That is useful provenance, not yet the
   "agent thought process" promised by the stretch goal.
4. **Query trace id and MLflow trace id are easy to conflate.**
   `QueryResult.query_trace_id` is a synthetic correlation id. The optional
   `mlflow_trace_id` is only present when a meaningful active MLflow span exists;
   today the query span is not active during the actual work.

---

## RAG / Retrieval Audit

### What Exists

`src/seahealth/db/retriever.py` provides:

- `VectorSearchRetriever`: Databricks Vector Search SDK wrapper for
  `seahealth-vs` / `workspace.seahealth_bronze.chunks_index`.
- `FaissRetriever`: local fallback chain: FAISS + sentence-transformers, then
  BM25, then dependency-free TF/cosine.
- `get_retriever()`: env-driven factory using `SEAHEALTH_VS_ENDPOINT` and
  `SEAHEALTH_VS_INDEX`, falling back to local chunks Parquet.
- `describe_retriever_mode()`: `/health/data` posture snapshot that does not
  instantiate a network client.

### What Is Missing

No production path calls `retriever.search()`. Repository search shows the
search implementation and tests, but no agent/pipeline/API call site. This is
the core gap because retrieval is the bridge between "we extracted claims" and
"we double-checked claims against the source corpus."

### Recommended Shape

Use classic scoped RAG, not a broad agentic web of retrieval tools:

- **Validator retrieval:** for each `Capability`, retrieve top-k chunks from the
  same `facility_id` using a compact query like
  `{capability_type} {facility_name} equipment staff availability`.
- **Evidence conversion:** convert each `IndexedDoc` into an `EvidenceRef`
  preserving `source_doc_id`, `chunk_id`, `source_type`, snippet, and span
  metadata where available.
- **LLM validation:** call
  `validate_capability(cap, facts, retrieved_evidence=hits, use_llm=True)`.
- **Persistence:** write `contradictions.parquet`,
  `evidence_assessments.parquet`, and mirror both to silver Delta.
- **Query semantic search:** add a separate `semantic_search(query, k)` tool for
  unstructured candidate discovery, then always rejoin to `FacilityAudit` before
  ranking or returning a recommendation.

Keep RAG bounded to the workspace corpus. The data changes slowly, the source of
truth is internal, and same-facility filtering prevents broad semantic matches
from overwhelming the Validator.

---

## Databricks Surface Audit

| Databricks surface | Status | Repository evidence | Action |
|---|---|---|---|
| Unity Catalog schemas | Built | `ensure_schemas()` creates bronze/silver/gold. | Keep. |
| UC Volume | Built | `ensure_volume()` and CSV upload to `seahealth_bronze.raw`. | Keep; document source dataset path in runbook. |
| Delta DDL | Built | `ensure_delta_tables()` creates 7 tables. | Align gold DDL with current Pydantic contracts. |
| SQL Warehouse | Built | `sql_warehouse.py`; provisioning calls `ensure_running()`. | Keep; use it for real gold/silver writes or switch to Jobs-native writes. |
| MLflow experiment | Built | `/Shared/seahealth/extraction-runs`. | Keep; move more agent steps inside spans. |
| MLflow tracing | Partial | Extractor spans meaningful; query span currently empty; other agents none. | Add spans around real work, not just before work. |
| Mosaic AI Vector Search | Built | `ensure_vector_search()` creates bronze `chunks_index`; retriever wrapper exists. | Wire into Validator and Query. |
| Foundation Models | Reachable via LLM client | Model-id routing in `llm_client.py`; OpenRouter used for 10k pass. | Re-run on Databricks when rate ceiling allows, or keep substitution caveat. |
| Databricks Workflows | Partial | Bundle has `extract-pipeline` only, no schedule/downstream tasks. | Add validate/build tasks and schedule after P0 loop lands. |
| DLT / Lakeflow | Not used | Pipelines are imperative Python. | Optional; valuable after runtime semantics are correct. |
| Genie | Not used | Explicitly out of shipped product. | Good post-demo operator surface, not a P0. |
| AI/BI Dashboards | Not used | Custom React frontend. | Optional handover surface on gold tables. |
| Databricks Apps | Not used | Frontend has Vercel/local path. | Optional if the goal is workspace-contained deployment. |

### Important Schema Mismatch

The current gold `facility_audits` DDL is a simplified serving shape:

- `capabilities` omits nested `evidence_refs`.
- `trust_scores` is a compact map with `score`, `band`, `contradictions`, and
  `verifying_evidence`.

The Python API expects the full `FacilityAudit` shape, including full
`Capability` and full `TrustScore` objects. Parquet mode carries that full shape
through JSON columns. Before claiming Delta as the live serving source, either:

1. widen the Delta DDL to match the Pydantic contracts, or
2. add an explicit Delta projection/adapter that converts the compact gold
   table into valid `FacilityAudit` objects.

Option 1 is cleaner for this repo because `FacilityAudit` is the canonical
object shared by API, UI, and tests.

---

## Challenge Scoring Impact

| Criterion | Weight | Current posture | Best next lift |
|---|---:|---|---|
| Discovery & Verification | 35% | Strong extraction scaffold; weak cross-source verification because retrieved evidence is not fed to Validator. | P0 Validate step with retriever + LLM evidence assessments. |
| IDP Innovation | 30% | Good: structured Pydantic extraction, closed enums, span-anchored evidence refs, prompt-injection framing. | Citation QA on regenerated outputs; keep schema claims honest. |
| Social Impact / NGO utility | 25% | Three-surface product direction is strong; map/gap metrics exist, but fixture/live split must stay clear. | One data spine and honest interval language. |
| UX & Transparency | 10% | UI has trace/evidence concepts; MLflow tree is shallow. | Real spans for retrieve/validate/score/query tools plus a UI trace link that resolves. |

The two highest-leverage changes are still:

1. **Wire retrieval into validation.**
2. **Make MLflow spans cover the agent chain.**

Both directly improve the challenge's "double-check their own work" and
"traceability" requirements without inventing a new feature.

---

## Ranked Gap Inventory

1. **[P0] Validator does not consume retrieved evidence in runtime paths.** Add
   `pipelines/validate.py` or extend the pipeline sequence so every capability
   retrieves same-facility chunks and produces `EvidenceAssessment` rows.
2. **[P0] Gold Delta path is not contract-compatible.** Either widen
   `facility_audits` Delta DDL to match `FacilityAudit` / `TrustScore` or add a
   tested adapter. Then make `build_audits.py` perform a real Delta write.
3. **[P0] Agent-chain MLflow spans are missing or misplaced.** Wrap real
   retrieve/validate/score/build/query work. Do not create empty spans that
   close before work starts.
4. **[P1] Query Agent has no semantic search tool.** Add `semantic_search` via
   `get_retriever()` for candidate discovery, but continue ranking only after
   rejoining to trusted `FacilityAudit` rows.
5. **[P1] Bundle does not express the full production workflow.** Add validate
   and build-audits tasks after P0 is implemented; then add a schedule.
6. **[P1] Foundation Model substitution remains part of the headline story.**
   Either re-run the 10k pass on Databricks Foundation Models or keep the
   OpenRouter caveat prominent in README/submission materials.
7. **[P1] Demo/live data spines are split.** Keep the caveat if recording must
   use static frontend demo data; otherwise route pages through the API client
   and make fixtures share the same canonical facility story.
8. **[P2] Map-region confidence interval is not in the slim API schema.** Do
   not claim `MapRegionAggregate.capability_count_ci` in the live UI until the
   field exists in `src/seahealth/schemas/map.py`, TS types, fixtures, OpenAPI,
   and tests.
9. **[P2] DLT/Lakeflow is not used.** It would improve refresh quality and
   lineage, but should wait until the simpler Python pipeline has the correct
   semantics.
10. **[P3] Genie, AI/BI, and Databricks Apps are absent.** Useful handover and
    operator surfaces, not required to make the current judged story honest.

---

## Implementation Path

### Phase A — Close Verification Loop

Goal: a capability claim is never scored without same-facility retrieval and a
Validator stance pass.

1. Add `pipelines/validate.py`.
2. Load `capabilities.parquet`, `facilities_index.parquet`, and chunks through
   `get_retriever()`.
3. For each capability, retrieve `k=5` same-facility chunks.
4. Build non-empty `FacilityFacts` from the facility index where columns exist
   (`numberDoctors`, `capacity`, facility type, and any equipment/staff fields
   available after normalization).
5. Call `validate_capability(..., retrieved_evidence=..., use_llm=True)`.
6. Write `contradictions.parquet` and `evidence_assessments.parquet`.
7. Add tests over a small fixture proving at least one `EvidenceAssessment`
   row is produced and can be consumed by `build_audits.py`.

### Phase B — Make Traces and Delta Honest

Goal: live mode and the trace UI describe the actual system.

1. Move the query MLflow span so it wraps `_run_llm` / `_run_heuristic` work.
2. Add spans around retrieve, validate, score, and build-audit steps.
3. Add stable span attributes: `facility_id`, `capability_type`,
   `retriever_mode`, `evidence_count`, `contradiction_count`, `model`.
4. Widen gold Delta DDL or add a tested adapter, then make `build_audits.py`
   write actual gold rows.
5. Add a smoke test that DELTA-shaped rows validate to `FacilityAudit`.

### Phase C — Promote Databricks-Native Operations

Goal: the live workspace can refresh the product without a local operator.

1. Extend `databricks.yml` with extract → validate → build-audits tasks.
2. Add a scheduled Databricks Workflow after the tasks are idempotent.
3. Re-run or sample-run the heavy LLM path on Databricks Foundation Models and
   update the substitution note with exact scope.
4. Optionally wrap Naomi eval with MLflow logging so extraction quality, trace
   examples, and row-level failures live in one workspace experiment.

### Phase D — Operator Handover

Goal: the project becomes usable beyond a 4-minute demo.

1. Add a Genie space over `seahealth_gold` for ad-hoc NGO planner questions.
2. Add an AI/BI dashboard for map aggregates and audited/verified/flagged
   trends.
3. Consider Databricks Apps if the deployment goal is "everything inside the
   workspace"; otherwise keep Vercel/local frontend but document the ops model.

---

## Recommended Next Steps

If there are **2 hours**, implement Phase A for a tiny subset and regenerate
`evidence_assessments.parquet`. That creates the most defensible improvement:
the Validator visibly cross-references evidence.

If there is **half a day**, add Phase A plus real MLflow spans around
retrieve/validate/score. The demo trace becomes a real transparency artifact.

If there is **one day**, also fix the gold Delta contract and make
`build_audits.py` write actual `facility_audits` rows. Then `/health/data`
with `mode=delta` can be shown without caveats about shape drift.

If there are **two days**, promote the validated pipeline into the Databricks
bundle and add a scheduled Workflow. DLT/Lakeflow, Genie, AI/BI, and Apps are
good follow-ups only after this core loop is true.

---

## Open Decisions

- **Databricks FM rerun:** Is the OpenRouter 10k pass acceptable for submission
  if fully disclosed, or do we need a smaller native Databricks FM rerun for
  judge screenshots?
- **Gold Delta shape:** Should gold Delta store the full canonical Pydantic
  shape, or a compact serving projection plus a tested adapter?
- **Validator default:** Should LLM validation be default-on in the pipeline, or
  an explicit `--use-llm-validator` mode for cost/rate-limit control?
- **Demo data spine:** Should we keep the static frontend fixture for recording,
  or unify the visible UI with FastAPI demo fixtures before submission?
