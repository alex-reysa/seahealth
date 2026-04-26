# SeaHealth — One-Pager

**Mission.** Cut Discovery-to-Care time for India's rural healthcare planners
by turning 10,000 messy facility reports into an audit workbench with
typed evidence and trust scoring.

**User.** NGO planners allocating rural healthcare grants — not patients,
not clinicians. They live in spreadsheets and maps, so we ship a Desert
Map, a Planner Query Console, and a Facility Audit View. No chat UI.

## Architecture

```
[10k facility docs]
       │
       ▼
[ Extractor ]──→ Capability + EvidenceRef (typed Pydantic, MLflow-traced)
       │
       ▼
[ Validator ]──→ Contradictions (closed taxonomy + heuristics + LLM)
       │
       ▼
[ Trust Scorer ]──→ TrustScore (deterministic 0–100 score + bootstrap CI on confidence)
       │
       ▼
[ FacilityAudit Builder ]──→ FacilityAudit (gold Delta, gold Vector index)
       │
       ▼
[ FastAPI ]──→ React UI (Desert Map / Planner Query / Facility Audit)
```

Native on Databricks: Unity Catalog (`workspace`), 7 Delta tables, Mosaic
AI Vector Search (`seahealth-vs` / `chunks_index`), MLflow 3 Tracing.
Substitution: OpenRouter Anthropic Haiku 4.5 for the 10k extraction (free-
tier Databricks rate ceiling) — reversible by flipping
`SEAHEALTH_LLM_HEAVY_MODEL`. Out of scope: Genie Code (operator-only).

## Eval

Hand-labeled 30 facilities with a clinical reviewer (Naomi). Scoped to
the labeled universe:

| Metric | Capability extraction |
|---|---|
| Precision | 0.488 |
| Recall | 0.362 |
| F1 | 0.416 |

Best per-capability: ONCOLOGY (F1=0.769), DIALYSIS (F1=0.667),
NEONATAL (F1=0.571). Phase 1C lifted contradiction recall from 0 by
fixing the audits-shape parser and adding a `vague_claim` heuristic;
re-run pending live audits.

## Three different intervals — what we ship vs. what we don't

| Interval | Where | Implementation |
|---|---|---|
| Per-capability confidence interval | `TrustScore.confidence_interval` | Bootstrap CI in `seahealth.agents.trust_scorer`, deterministic given an rng seed. Pre-existing, schema-locked. |
| Aggregate verified-count CI | `SummaryMetrics.verified_count_ci` | Wilson 95% score interval scaled to integer counts, computed in `seahealth.api.data_access._summary_from_audits`. Phase 4B. |
| Map region CI | not shipped | `MapRegionAggregate` deliberately has no CI field in the API shape today. The Wilson helper exists, so wiring it onto `/map/aggregates` is a follow-up — we list this as an explicit gap rather than overclaim it on the demo. |

## What's real vs. fixture

- **Real:** 10,000 facility extraction; 4,802 capability rows; 974
  verified / 900 flagged audits; Naomi's 30 hand-labels; the agent
  pipeline; the Databricks bundle.
- **Fixture (committed for demo):** four JSON files in `fixtures/` and
  `app/src/data/fixtures/`. Identical schema to the live API.
- **Untracked / regenerable:** `tables/*.parquet` (extraction outputs);
  the README walks the regen path.

## Known limitations

- Current 10,000 audits have `mlflow_trace_id=null` — they predate the
  MLT-1 column. Fresh extractions populate `live` traces. The UI marks
  the gap as a data-quality state, not a successful render.
- Contradiction recall on Naomi labels is currently 0 in the report on
  disk because the read path was reading the wrong shape; Phase 1C
  fixes that and the re-run is the next regen step.
- Naomi's 30 facilities are a small sample; we report scoped P/R/F1 only,
  with explicit caveats.

## How to run

```bash
git clone https://github.com/alex-reysa/seahealth.git
cd seahealth
pip install -e ".[dev]"
pytest -q                                  # ~300 tests
uvicorn seahealth.api.main:app --reload    # FIXTURE mode by default
cd app && npm install && npm run dev       # demo mode by default
```

Live mode requires `DATABRICKS_TOKEN` + `DATABRICKS_SQL_HTTP_PATH`;
`/health/data` reports the active mode and retriever.

## Why it matters

A planner today can ask the locked query — *"Find the nearest facility in
rural Bihar that can perform an emergency appendectomy and typically
leverages parttime doctors"* — and get a ranked list with evidence,
contradictions, and a confidence interval in under a second. That's the
shape of equitable healthcare allocation: not a map pin, an audit.
