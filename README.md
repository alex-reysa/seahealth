# SeaHealth

Audit workbench for NGO planners allocating rural healthcare grants in India.
Three connected surfaces — Desert Map, Planner Query Console, Facility Audit
View — backed by a typed agent pipeline (Extractor → Validator → Trust Scorer
→ FacilityAudit Builder) and an MLflow trace per claim.

## Quickstart

```bash
git clone https://github.com/alex-reysa/seahealth.git
cd seahealth
pip install -e ".[dev]"
cp .env.example .env                       # update DATABRICKS_TOKEN before live mode
pytest -q                                  # ≥ 316 tests, all green
python -m seahealth.db.smoke_test          # exercises the data layer
uvicorn seahealth.api.main:app --reload    # FastAPI on :8000
cd app && npm install && npm run dev       # Vite dev server on :5173
```

For a one-page reviewer recipe (with copy-paste curl + browser steps), see
`docs/eval/live_smoke.md`.

### Frontend modes

The React app is mode-aware via two env vars:

| Mode | env | Behavior |
|---|---|---|
| **live** | `VITE_SEAHEALTH_API_BASE=http://localhost:8000` (and unset/`live` for `VITE_SEAHEALTH_API_MODE`) | Every page consumes the FastAPI surface through typed hooks. The data-mode banner shows `live · parquet · faiss_local` (or whatever the backend reports). |
| **demo** | `VITE_SEAHEALTH_API_MODE=demo` | No backend required. Pages render against bundled `app/src/data/fixtures/*.json`. The banner shows `demo (offline fixtures)`. |

`/health/data` reports the active data and retriever modes:

```json
{
  "mode": "fixture",
  "facility_audits_path": "tables/facility_audits.parquet",
  "delta_reachable": false,
  "retriever_mode": "faiss_local",
  "vs_endpoint": null,
  "vs_index": null
}
```

## Demo

**Locked demo query:** *"Find the nearest facility in rural Bihar that can
perform an emergency appendectomy and typically leverages parttime doctors."*

**Locked facility audit demo target:** **CIMS Hospital Patna**
(`vf_02239_cims-hospital-patna-a-un`).

See `docs/UX_FLOWS.md` for the cross-surface flow and
`docs/AGENT_ARCHITECTURE.md` for the agent contract.

## Architecture: Databricks-native, with explicit substitutions

The challenge calls for the Databricks Data Intelligence Platform. SeaHealth
is built on it; every shipped component runs end-to-end on the platform, and
where we substituted an open alternative the substitution is intentional and
documented here.

| Challenge layer | What we ship | Substitution? |
|---|---|---|
| Unity Catalog + Delta tables | UC catalog `workspace`, schemas `seahealth_silver` / `seahealth_gold`, 7 Delta tables (`chunks`, `facilities_index`, `capabilities`, `contradictions`, `evidence_assessments`, `facility_audits`, `map_aggregates`). Provisioned by `databricks bundle deploy`. | None |
| Mosaic AI Vector Search | Endpoint `seahealth-vs` with `chunks_index` (DELTA_SYNC, BAAI/bge-large-en-v1.5, 1024-dim). API surface: `seahealth.db.retriever.VectorSearchRetriever`. Falls back to local FAISS / BM25 / TF when env is unset; `/health/data` surfaces the active mode. | None on the live path; FAISS is the offline-mode fallback. |
| MLflow 3 Tracing | `MLFLOW_TRACKING_URI=databricks` opens real spans during extraction. Each `Capability` carries the trace id; `FacilityAudit` inherits it. When MLflow is unavailable the extractor stamps a deterministic `local::<facility_id>::<run_uuid>` synthetic id. `seahealth.agents.facility_audit_builder.classify_trace_id` distinguishes live vs. synthetic vs. missing for the UI. | None |
| Agent Bricks (Foundation Model serving) | OpenAI-compatible serving endpoints on Databricks Foundation Models — heavy agents (Extractor / Validator / Query) on `databricks-meta-llama-3-3-70b-instruct`, light agents (TrustScore reasoning) on `databricks-meta-llama-3-1-8b-instruct`. **Active substitution for the 10k extraction**: OpenRouter Anthropic Haiku 4.5, because the free-tier Databricks endpoint hit a rate ceiling on a 10k-row run. The provider is auto-detected by model id (a slash routes to OpenRouter, otherwise Databricks). | Substitution; see `docs/DECISIONS.md`. |
| Genie Code | Not used in the shipped product. The data prep + extraction pipeline runs through `seahealth.pipelines` with deterministic Python so the demo is reproducible from a clean clone. Genie remains the recommended operator surface for ad-hoc Naomi-style explorations. | Substitution by intent; out of demo scope. |
| Confidence intervals (research) | `MapRegionAggregate.capability_count_ci`, `TrustScore.confidence_interval` are first-class schema fields. Phase 4B is wiring the UI render. | None |

**LLM provider fallback behaviour.** `seahealth.agents.llm_client` routes by
model id: a slash in the id (`anthropic/...`, `moonshotai/...`) routes to
OpenRouter via `OPENROUTER_API_KEY`; an id without a slash
(`databricks-meta-llama-3-3-70b-instruct`) routes to Databricks Foundation
Models via `DATABRICKS_TOKEN`. The agent code is identical across providers;
only the client factory differs. This keeps the OpenRouter substitution
explicit and reversible — flip the `SEAHEALTH_LLM_HEAVY_MODEL` env var back
to a Databricks model id and the heavy path runs on Databricks.

## Modes of operation

| Mode | Setup | Use case |
|---|---|---|
| **FIXTURE** | None — committed JSON in `fixtures/` | Demo, tests, cold-start. `/health/data` reports `mode=fixture`. |
| **PARQUET** | Run `python -m seahealth.pipelines.extract --subset demo` then `python -m seahealth.pipelines.build_audits --subset demo` | Local development against extracted data; no Databricks creds. |
| **DELTA** | Set `DATABRICKS_HOST` / `DATABRICKS_SQL_HTTP_PATH` / `DATABRICKS_TOKEN` in `.env` | Live mode against the gold Delta tables; uses Mosaic AI Vector Search if `SEAHEALTH_VS_ENDPOINT` and `SEAHEALTH_VS_INDEX` are also set. |

Mode is auto-detected by `seahealth.api.data_access.detect_mode` (DELTA →
PARQUET → FIXTURE). Override with `SEAHEALTH_API_MODE` if needed.

## Eval

```bash
python -m seahealth.eval.run_eval --labels tables/naomi_labels.csv \
    --output docs/eval/naomi_run.md
```

Latest scoped report: capability extraction P=0.488, R=0.362, F1=0.416 over
Naomi's 30 hand-labeled facilities (58 capability rows). See
`docs/eval/naomi_run.md` for the per-capability breakdown.

```bash
python -m seahealth.eval.citations_qa
```

Reports valid / invalid evidence-ref counts against `tables/chunks.parquet`.
Use it before claiming citation coverage in the demo.

## Project map

- `src/seahealth/agents/` — Extractor, Validator, Trust Scorer, Query, FacilityAudit Builder.
- `src/seahealth/api/` — FastAPI surface (`/summary`, `/query`, `/facilities`, `/facilities/{id}`, `/map/aggregates`, `/health`, `/health/data`).
- `src/seahealth/db/` — Delta + retriever clients.
- `src/seahealth/pipelines/` — `extract`, `build_audits`, `normalize`.
- `src/seahealth/schemas/` — closed Pydantic schemas; the source of truth.
- `app/` — Vite + React frontend.
- `docs/PRODUCT_READINESS_REPORT.md` — current state vs. Definition of Done.
- `docs/DECISIONS.md` — ADRs.
- `docs/AGENT_ARCHITECTURE.md` — agent contract diagram.

## Team

TBD
