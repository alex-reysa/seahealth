# SeaHealth Roadmap

Bird's-eye view of every phase from project zero to submission.
Pair this with **`state.md`** at the repo root, which is the detailed task log
(per-sub-agent commits, audit verdicts, conflict resolutions).

- **This file**: phase-level "are we done?" tracker.
- **`state.md`**: task-level "what changed in commit X?" log.

Updated as phases land. ✅ = merged on `integrate/ship-12h`. ⏳ = in flight. ☐ = TODO.

## Phases

| # | Phase | Status | Anchor commit | Notes |
|---|---|---|---|---|
| 0 | Tooling — pyproject, .python-version, databricks.yml | ✅ | `8c8245a` | Bundle validate green |
| 1 | Contracts + Local Golden Path — 13 schemas, normalize, FastAPI stub, OpenAPI, fixtures | ✅ | `00f54af` | 6 endpoints, 12 tests |
| 2 | Databricks Foundation + Agent Code — UC catalog, 7 Delta tables, MLflow, VS endpoint, Extractor, Validator + heuristics | ✅ | `da3f692` | UC catalog `workspace`, MLflow exp `405251052688464`, VS endpoint READY |
| 3 | Trust + Query — Trust Scorer, Audit Builder, Query Agent, Cleanup-2 R-2 follow-ups | ✅ | post `87a8ac0` | Deterministic score formula; tool-loop query |
| 4-K | Wire FastAPI to Delta — DELTA → PARQUET → FIXTURE auto-detect with fallback | ✅ | `c3c9c8e` | `/health/data`, `X-Query-Trace-Id` |
| 4-M | Naomi eval **harness** scaffold — synthetic 5-row sample | ✅ | `ccf1755` | Awaited real labels (Phase 5) |
| Audit Swarm | AUD-01..10 cross-cutting hardening (cherry-picked) | ✅ | `c481575` | All GREEN; cleanup backlog logged |
| DBX-1 + DBX-2 | LLM backend swap — Anthropic → Databricks Foundation Models → OpenRouter (Kimi K2.5) | ✅ | `8039aca` + `560c23e` | Provider auto-detected by model id |
| Map Workbench | Home-route Map Workbench + agent run panel + tool-call timeline + demo data | ✅ | `ccbbfc7` | `/` is now the agent surface |
| 4-L | Live extraction (250 facilities), build_audits, regenerate fixtures from real data | ✅ | `f23b456` | 13 ranked Patna facilities; CIMS demo target |
| **5** | **Naomi REAL eval — adapter (xlsx → CSV) + run_eval + report** | **⏳** | — | Naomi labels delivered (30 facilities, 25 cols) |
| 6 | Demo polish + submission (script, video, one-pager, packaging) | ☐ | — | Demo script locked at hour 24 per PHASES.md |
| Optional | R-3 Phase 3 reviewer, AUD-R audit-swarm reviewer, AUD-08 tautology cleanup | ☐ | — | Non-blocking; can run post-submission |

## Current state

- **Branch**: `integrate/ship-12h`
- **Latest test count**: 255 passing
- **Live data on disk**: `tables/{chunks.parquet, facilities_index.parquet, capabilities.parquet, facility_audits.parquet, demo_subset.json}` (all gitignored)
- **Live fixtures**: `fixtures/{summary,demo_query_appendectomy,facility_audit,map_aggregates}_demo.json` (real data, regenerated post-L-1)
- **Frontend**: `app/` — Map Workbench at `/`, demo data committed at `app/src/data/demoData.ts`

## Phase 5 — Naomi REAL eval (immediate next)

Naomi delivered `india_health_facilities_check_labels_final_v2.xlsx` — 30 facilities, 25 columns. Required adapter work because:

1. Her file uses `source_row_number` (e.g. 2164), not our `facility_id` (e.g. `vf_02164_<slug>`).
2. `claimed_capability` is multi-value semicolon-separated.
3. `evidence_status` includes `unclear`/`silent` in addition to `supports`/`contradicts`.

Adapter normalizes all three so `python -m seahealth.eval.run_eval --labels tables/naomi_labels.csv` writes a real precision/recall report to `docs/eval/naomi_run.md`.

## Phase 6 — Demo polish + submission

Outline (detailed plan deferred until Phase 5 lands):

- **Demo script** — 4-min, scripted to the second. Naomi drafts (per `PHASES.md` non-negotiable #2).
- **Demo video** — screen + voiceover walking through Map Workbench → Planner Query → Facility Audit View on CIMS Patna.
- **One-pager PDF** — judges' artifact: data left, product right, eval numbers (Naomi precision/recall) front and center.
- **Submission packaging** — README finalized, repo public, runtime instructions verified on a clean clone.
- **Optional reviewers** — AUD-R, R-3, AUD-08 tautology cleanup. None blocking.
