# Product Readiness Audit — Prompt

> Paste the **MISSION** section below into a fresh LLM agent (Claude / Codex / etc.). The agent will not have prior context — the prompt is self-contained.

---

## MISSION

You are a **Product Readiness Auditor** for the SeaHealth project at `/Users/alejandro/Desktop/seahealth` (public mirror: https://github.com/alex-reysa/seahealth, branch `integrate/ship-12h`). Your job is to determine **what concrete work remains between current state and a fully working, judge-defensible product** that meets every requirement of `challenge.md`.

You are not implementing anything. You are producing a **prioritized gap report** the engineering team will execute against.

## CONTEXT YOU MUST GROUND IN

Read in order, end-to-end:

1. `challenge.md` — the source of truth on what "done" means.
2. `docs/ROADMAP.md` — the phase-level done/not-done tracker.
3. `state.md` — the detailed task log, latest commit hashes, audit verdicts.
4. `docs/DATA_CONTRACT.md` — canonical schemas; the load-bearing spec.
5. `docs/AGENT_ARCHITECTURE.md` — agent contracts + happy-path trace.
6. `docs/eval/naomi_run.md` — current honest eval numbers vs Naomi's gold set.
7. `README.md` — how the thing runs locally.

Then probe live state (read-only):

- `git log --oneline -20` — recent work
- `tables/` — confirm which parquets exist (`chunks.parquet`, `capabilities.parquet`, `facility_audits.parquet`, `facilities_index.parquet`, `naomi_labels.csv`, `demo_subset.json`)
- `fixtures/` — what the frontend gets handed
- `app/` — what the frontend actually renders (`app/src/pages/`, `app/src/data/demoData.ts`)
- `src/seahealth/api/main.py` + `data_access.py` — how the API serves data
- `src/seahealth/agents/` + `pipelines/` — the agent + pipeline code
- `src/seahealth/db/databricks_resources.py` — what's actually provisioned in the workspace
- `.env.example` (NOT `.env`) — environment surface

## EVALUATION DIMENSIONS

For each of the seven dimensions below, produce a verdict (`✅ DONE` / `⚠️ PARTIAL` / `❌ MISSING` / `N/A`) **with a one-sentence citation** (file:line or commit hash). No vague verdicts.

### 1. Brief MVP requirements (`challenge.md` §2)

- **Massive Unstructured Extraction** over 10k records — count rows in `tables/capabilities.parquet`, count facilities, report % coverage of the 10k corpus.
- **Multi-Attribute Reasoning** — verify the locked example query *"Find the nearest facility in rural Bihar that can perform an emergency appendectomy and typically leverages parttime doctors"* parses end-to-end. Walk the heuristic parser code; confirm it captures capability + location + radius + staffing qualifier.
- **Trust Scorer** — confirm `score = clamp(round(confidence*100) - Σseverity_weights, 0, 100)` is implemented deterministically; confirm reasoning is non-empty; confirm contradictions reach the audit.

### 2. Brief stretch goals (`challenge.md` §3)

- **Agentic Traceability — citations** — what fraction of `Capability.evidence_refs` rows have a non-empty `snippet` AND a valid `(span_start, span_end)`? Are spans actually substring-matched against chunk text or zero-padded?
- **Agentic Traceability — MLflow 3 Tracing** — **CRITICAL.** The brief explicitly names MLflow 3 Tracing. Verify three things:
  1. Is `MLFLOW_TRACKING_URI=databricks` actually set in the environment used at extraction time?
  2. Did real MLflow spans actually fire during the 10k extraction? (Check workspace MLflow experiment `/Shared/seahealth/extraction-runs` (id `405251052688464`) for runs.)
  3. Do `FacilityAudit.mlflow_trace_id` values resolve to real MLflow traces in the workspace UI, or are they synthesized `local::*` strings? Inspect a sample row's `mlflow_trace_id` and report the prefix distribution.
  4. Does the **frontend** Facility Audit View actually render a span timeline, or does it just show the trace_id as text?
- **Self-Correction Loops** — confirm the Validator Agent runs on every extraction (not on-demand) and produces both `Contradiction[]` and `EvidenceAssessment[]`. Are the heuristic short-circuits firing? How many of the 10000 audits have ≥1 heuristic-detected contradiction?
- **Dynamic Crisis Mapping** — does `/map/aggregates` return rows for at least 5 distinct PIN-code regions? Does the frontend Desert Map render an actual choropleth, or a placeholder? Inspect `app/src/pages/` for the map page and `app/src/data/mockIndiaRegions.topojson`.

### 3. Brief tech-stack expectations (`challenge.md` §5)

The brief explicitly names tools — confirm each is being used (or document an honest "we substituted X for Y because Z").

- **Databricks Free Edition serverless compute** — confirm via `src/seahealth/db/databricks_resources.py` that the SQL warehouse is the Serverless Starter; confirm the Asset Bundle (`databricks.yml`) targets it.
- **Unity Catalog** — confirm 3 schemas exist under catalog `workspace` + UC volume + 7 Delta tables. Probe with `databricks_client.get_workspace().catalogs.list()` if needed.
- **Agent Bricks** — the brief calls this out specifically. **Are we using it?** If we're using direct LLM API calls (Anthropic via OpenRouter), document this as a substitution and decide whether to migrate.
- **Genie Code** — autonomous multi-step data tasks. Are we using it anywhere? If not, where could it slot in?
- **MLflow 3** — see dimension 2 above. Triple-check.
- **Mosaic AI Vector Search** — confirm endpoint `seahealth-vs` exists, the index over `bronze.chunks` exists, and the agent's Validator/Query path actually queries it. Or are we falling back to in-process FAISS over `tables/chunks.parquet`? Inspect `src/seahealth/db/retriever.py`.

### 4. Eval & honesty (challenge §6 — 35% weight)

- Read `docs/eval/naomi_run.md`. State the headline P/R/F1 numbers and which Naomi facilities map back to which extracted rows.
- Are predictions properly scoped to Naomi's labeled universe? (We had a bug here.)
- Contradiction recall is currently 0.000 — is that because Naomi's taxonomy is broader than ours, or because our heuristics aren't firing on her facilities? Compute by hand on 3 of her contradictions.
- Is there a confidence-interval analysis on aggregate claims (the brief's research question §4)? If so, where is it surfaced in the UI? If not, propose one.

### 5. Frontend integration with real data (challenge §6 — 25% utility + 10% UX)

- Walk `app/src/pages/Dashboard.tsx`, `Sidebar.tsx`, `Layout.tsx`, `PlannerQuery.tsx`, `FacilityAudit.tsx`, `desert_map.md` (UX doc).
- Does each surface fetch from the live API (`http://localhost:8000`) or read `app/src/data/demoData.ts`?
- For each of the four endpoints (`/summary`, `POST /query`, `/facilities/{id}`, `/map/aggregates`), state YES / NO whether the frontend currently hits it AND validates the response against a TS type.
- The locked demo query lives where in the UI? Is it pre-filled or just typeable?
- The "demo moment" is a contradiction reveal on CIMS Hospital Patna with score=5 for SURGERY_GENERAL and 2 contradictions. Does clicking through Map Workbench → Facility Audit actually show this, or is the demo currently powered by mock data?

### 6. Submission-readiness

- Does `README.md` Quickstart work on a clean clone? Walk it: `pip install -e ".[dev]"`, `pytest -q`, `uvicorn seahealth.api.main:app`. Any commands that depend on local `tables/*` parquets that aren't generated by the documented steps?
- Are there any hard-coded paths or secrets in committed code? Run `git ls-files | xargs grep -l 'dapi[a-f0-9]\{32\}\|sk-or\|sk-ant'` over the repo.
- Demo video / one-pager / submission packaging — none exist. Outline what each needs to contain to land the eval criteria.

### 7. What's "almost there" but not quite

- The MLT-1 schema field exists but the live 10k extraction predates the column → all `mlflow_trace_id` values are None. Is this fixable without re-extracting (e.g. synthesize in build_audits)?
- The validator's contradiction heuristics taxonomy is narrower than Naomi's — what's the smallest viable widening (add a `vague_claim` heuristic) that lifts contradiction recall above zero?
- The frontend currently has both a demo-data path and (presumably) a real-API path. Are they cleanly switchable, or is the demo data hard-coded in pages?

## REPORT STRUCTURE

Produce a single Markdown document called `docs/PRODUCT_READINESS_REPORT.md` with this structure:

```markdown
# Product Readiness Report

Generated: <YYYY-MM-DD HH:MM>
Branch: integrate/ship-12h @ <commit hash>
Tests: <count> passing

## Executive Summary

3 bullets max. The single sentence each that a judge would say. Be brutal about gaps.

## Verdict Matrix

| Dimension | Sub-requirement | Verdict | Citation | Notes |
|---|---|---|---|---|
| Brief MVP | Extraction over 10k | ... | tables/capabilities.parquet (M rows / N facilities) | ... |
| Brief MVP | Multi-attribute query | ... | src/seahealth/agents/query.py:NN | ... |
| Brief MVP | Trust Scorer | ... | ... | ... |
| Brief stretch | Citations | ... | ... | ... |
| Brief stretch | MLflow 3 Tracing | ... | ... | ... |
| ... | ... | ... | ... | ... |

(One row per sub-requirement from dimensions 1–7. Aim for 25–35 rows.)

## Top 5 blockers

Ranked by impact on the 35/30/25/10 eval-criteria weights. For each:
- One-sentence problem statement
- Concrete fix (file paths, function names, estimated LOC)
- Estimated wall-time and cost (LLM tokens if any)

## Recommended execution order (next ~6 hours)

A numbered list of tasks. Each:
- Task name
- Files to touch
- Acceptance criterion (single sentence)
- Estimate (min)

Group adjacent tasks under "Lane" headers (e.g. "Lane A — MLflow real wiring", "Lane B — Frontend live data").

## Risks & decisions deferred to the human

A short list of choices the auditor cannot make alone. Examples:
- Re-run extraction to populate trace_ids? Cost ~$30, ~15 min wall.
- Migrate from OpenRouter Anthropic to Databricks Agent Bricks? Cost / risk?
- Naomi's gold set has only 30 facilities — should we ask for more, or freeze and report?

## What we're NOT doing

A short list of things explicitly out of scope for the next push (mobile, auth, multi-user, etc.) — anchored to `docs/VISION.md` out-of-scope list.
```

## OPERATING CONSTRAINTS

- **Read-only.** Do not modify code or commit anything. Your only write is `docs/PRODUCT_READINESS_REPORT.md`.
- **No vague verdicts.** Every "✅" or "❌" needs a citation: a file path + line number, a commit hash, an actual probe of `tables/`, or an assertion you can verify with one shell command.
- **Cite numbers from data, not docs.** If the doc claims 10k extraction and the parquet has 87 rows, the parquet wins.
- **Distinguish "scaffolded" from "actually firing".** The MLflow gap is the canonical example: schema exists, code exists, but `MLFLOW_TRACKING_URI` is unset → no real spans. Catch every analogue.
- **Honest about substitutions.** If we used OpenRouter Anthropic instead of Databricks Agent Bricks, say so plainly with a one-line rationale (e.g. "Llama 3.3 70B on Databricks had 65% tool-call refusal rate; switched to Anthropic Haiku 4.5 for reliability").
- **Write the report at `docs/PRODUCT_READINESS_REPORT.md`** so it can be committed.

## STOP CRITERIA

You are done when:
1. The verdict matrix has a citation for every row.
2. The Top-5 blockers each have a concrete fix with file paths.
3. The execution order can be handed to a coding agent verbatim.

Begin.
