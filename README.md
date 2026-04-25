# Seahealth

Audit workbench for NGO planners allocating rural healthcare grants in India.
Three connected surfaces — Desert Map, Planner Query Console, Facility Audit
View — backed by a typed agent pipeline (Extractor → Validator → Trust Scorer
→ FacilityAudit Builder) and an MLflow trace per claim.

## Quickstart

```bash
git clone https://github.com/alex-reysa/seahealth.git
cd seahealth
pip install -e ".[dev]"
cp .env.example .env                       # update DATABRICKS_TOKEN (PAT) before first run
pytest -q                                  # 246 tests, all green
python -m seahealth.db.smoke_test          # exercises the data layer
uvicorn seahealth.api.main:app --reload    # FastAPI on :8000
```

`/health/data` reports the active data mode (`DELTA` / `PARQUET` / `FIXTURE`).

## Demo

Locked appendectomy query: *"Which facilities within 50km of Patna can perform
an appendectomy?"* See `docs/UX_FLOWS.md` for the cross-surface flow and
`docs/AGENT_ARCHITECTURE.md` for the agent contract.

## Team

TBD
