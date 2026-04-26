# Live smoke recipe

Reviewer-friendly walk-through. Copy-paste each command from a clean clone;
no Databricks credentials needed for the PARQUET path. Last verified
2026-04-26 against branch `release/seahealth-submission`.

## 1. Install + tests

```bash
git clone https://github.com/alex-reysa/seahealth.git
cd seahealth
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Expected: `316 passed`. Anything red is a regression — file a bug, don't
proceed.

## 2. Frontend lint + build

```bash
cd app
npm install
npm run lint
npm run build
cd ..
```

Expected: zero TypeScript errors, a clean Vite build.

## 3. Backend in PARQUET mode

```bash
SEAHEALTH_API_MODE=parquet uvicorn seahealth.api.main:app --reload --port 8000
```

In another terminal:

```bash
curl -s http://localhost:8000/health/data | python -m json.tool
# expect: {"mode": "parquet"|"fixture", "retriever_mode": "faiss_local", ...}

curl -s -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"Find the nearest facility in rural Bihar that can perform an emergency appendectomy and typically leverages parttime doctors."}' \
  -i | head -25
# expect:
#   - HTTP/1.1 200 OK
#   - x-query-trace-id: q_<uuid>
#   - body.ranked_facilities length >= 1
#   - body.execution_steps has 4 entries (parse_intent, retrieve, score, rank)
#   - body.mlflow_trace_id is null (MLFLOW_TRACKING_URI is not set)
```

## 4. Frontend in live mode

```bash
cd app
VITE_SEAHEALTH_API_MODE=live VITE_SEAHEALTH_API_BASE=http://localhost:8000 npm run dev
# open http://localhost:5173
```

Verify in the browser:

1. **Map page** — at least 3 colored regions; the data-mode banner shows
   `live · parquet|fixture · faiss_local`. Click a region: URL gains
   `?region_id=…`, side panel updates from `/map/aggregates`.
2. **Planner page** — paste the locked query, run. Result: ≥ 1 ranked
   facility, four-step execution trace, `synthetic` trace badge (or `live`
   if `MLFLOW_TRACKING_URI` is set), URL contains `?q=…`.
3. **Facility audit page** — click any ranked row. Direct hit to
   `/facilities/<id>` works too. Trust score, contradictions, and evidence
   are populated from `/facilities/{id}`.

## 5. Demo (offline) mode

```bash
cd app
VITE_SEAHEALTH_API_MODE=demo npm run dev
# open http://localhost:5173 — no backend required.
```

Banner says `demo (offline fixtures)`. All three pages still render with
the bundled API-shape fixtures.

## 6. Eval

```bash
python -m seahealth.eval.run_eval \
  --labels tables/naomi_labels.csv \
  --output docs/eval/naomi_run.md
```

Expected: capability F1 ≈ 0.416 on Naomi's 30-facility scoped slice.

## What success looks like

- All commands above succeed without code edits.
- The reviewer sees the same query → ranked result → audit click flow in
  both live and demo modes.
- No console errors in the browser devtools on any page.
