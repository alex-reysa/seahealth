# Product Readiness Execution Plan

This plan converts the original product-readiness audit into an execution roadmap for taking SeaHealth from the current `integrate/ship-12h` state to a fully production-ready, submission-ready, judge-defensible product.

It assumes the challenge definition in `challenge.md` is the source of truth, with current status tracked in `docs/ROADMAP.md` and `state.md`.

## Definition of Done

SeaHealth is complete when all of the following are true:

1. **Challenge requirements are demonstrably met**
   - 10k facility corpus is processed, auditable, and queryable.
   - Multi-attribute planning query works end-to-end on real data.
   - Trust scores are deterministic, explainable, and tied to citations.
   - Medical deserts are rendered geographically with useful planner actions.

2. **Databricks story is honest and strong**
   - Unity Catalog, Delta tables, serverless SQL, MLflow, and Vector Search are either live and used, or explicit substitutions are documented.
   - MLflow trace IDs in audit records resolve to real traces when a live extraction is run.
   - Any use of OpenRouter or direct LLM APIs is framed as an implementation decision, not hidden.

3. **Frontend is a real product surface**
   - Dashboard, Map Workbench, Planner Query, and Facility Audit views can run against live API data.
   - Demo data is a deliberate offline mode, not a hidden dependency.
   - Every recommendation shows evidence, contradiction status, and confidence.

4. **Evaluation is reproducible**
   - Naomi eval can be re-run from a clean checkout.
   - Precision, recall, F1, contradiction recall, and known limitations are reported.
   - Aggregate claims include uncertainty or clearly state the sample limitations.

5. **Submission is packaged**
   - README quickstart works on a clean clone.
   - Demo script, video, one-pager, and judge walkthrough are complete.
   - No secrets, local-only paths, or untracked required artifacts are needed.

## Phase Overview

| Phase | Goal | Parallelizable | Exit Gate |
|---|---|---:|---|
| 0 | Freeze baseline and execution rules | No | Current branch, data artifacts, tests, and known gaps are documented |
| 1 | Close critical data and traceability gaps | Yes | Real 10k-backed data, audits, citations, and traces are coherent |
| 2 | Strengthen Databricks-native architecture | Yes | Platform claims are either implemented or honestly documented |
| 3 | Productize frontend live-data flows | Yes | UI runs against live API with typed fallbacks and demo flow intact |
| 4 | Raise eval quality and product trust | Yes | Eval report is reproducible and limitations are defensible |
| 5 | Production hardening | Yes | Clean clone, env, API, CORS, error states, and artifact packaging are solid |
| 6 | Submission polish | Yes | Demo, one-pager, README, and final product-readiness report are complete |
| 7 | Final integration and release | No | One green release branch, tagged commit, and rollback notes |

## Branching Strategy

Use `integrate/ship-12h` as the integration branch until final release. Do not run large implementation directly on it.

### Branch Naming

Use short phase-prefixed branches:

| Work Type | Branch Pattern | Example |
|---|---|---|
| Baseline / coordination | `plan/<topic>` | `plan/product-readiness-roadmap` |
| Data / pipeline | `phase1/<lane>` | `phase1/mlflow-traces` |
| Databricks platform | `phase2/<lane>` | `phase2/vector-search-live` |
| Frontend | `phase3/<lane>` | `phase3/live-api-ui` |
| Eval / docs | `phase4/<lane>` | `phase4/eval-confidence` |
| Production hardening | `phase5/<lane>` | `phase5/clean-clone` |
| Submission | `phase6/<lane>` | `phase6/demo-package` |
| Release | `release/<date-or-tag>` | `release/seahealth-submission` |

### Worktree Layout

Create sibling worktrees outside the main repo so agents can run in parallel without overwriting each other:

```bash
mkdir -p ../seahealth-worktrees
git fetch origin
git worktree add ../seahealth-worktrees/phase1-mlflow -b phase1/mlflow-traces integrate/ship-12h
git worktree add ../seahealth-worktrees/phase1-citations -b phase1/citation-quality integrate/ship-12h
git worktree add ../seahealth-worktrees/phase3-frontend -b phase3/live-api-ui integrate/ship-12h
git worktree add ../seahealth-worktrees/phase4-eval -b phase4/eval-confidence integrate/ship-12h
```

Use one terminal per worktree. Each worktree owns a narrow file scope and must merge back through `integrate/ship-12h`.

### Merge Rules

1. Rebase each lane on latest `integrate/ship-12h` before review.
2. Run the lane's tests from that worktree.
3. Confirm `git diff --name-only integrate/ship-12h...HEAD` only includes the lane's file scope.
4. Merge one lane at a time into `integrate/ship-12h`.
5. After each merge, run the shared gate:

```bash
pytest -q
ruff check src tests
cd app && npm test -- --run
```

If a lane cannot run a gate locally, its PR or merge note must state why.

## Phase 0 — Baseline Freeze

**Goal:** Make sure all parallel work starts from the same truth.

**Owner:** Integrator.

**Branch:** `plan/product-readiness-roadmap`.

**File scope:**

- `docs/PRODUCT_READINESS_AUDIT_PROMPT.md`
- `docs/ROADMAP.md`
- `state.md`
- `docs/PRODUCT_READINESS_REPORT.md` if generated

**Tasks:**

1. Record current branch, commit hash, test count, and data artifact inventory.
2. Confirm whether `docs/PRODUCT_READINESS_REPORT.md` exists; if not, generate it from the original audit criteria before implementation begins.
3. Turn unresolved audit findings into Phase 1-6 tasks.
4. Freeze demo query and demo facility:
   - Query: "Find the nearest facility in rural Bihar that can perform an emergency appendectomy and typically leverages parttime doctors."
   - Facility audit demo target: CIMS Hospital Patna, if still present in current data.

**Acceptance criteria:**

- `docs/ROADMAP.md` and `state.md` agree on current status.
- Product-readiness gaps are expressed as tasks with owner, files, and exit criteria.
- No implementation files are changed in this phase.

## Phase 1 — Data, Extraction, Citations, and MLflow

**Goal:** Make the core intelligence layer judge-defensible on real data.

### Lane 1A — Real MLflow Trace Propagation

**Branch:** `phase1/mlflow-traces`

**Worktree:** `../seahealth-worktrees/phase1-mlflow`

**File scope:**

- `src/seahealth/agents/`
- `src/seahealth/pipelines/extract.py`
- `src/seahealth/pipelines/build_audits.py`
- `src/seahealth/schemas/`
- `tests/`
- `docs/DATA_CONTRACT.md`

**Tasks:**

1. Ensure extraction starts real MLflow runs/spans when `MLFLOW_TRACKING_URI=databricks`.
2. Persist real trace IDs from extraction into `Capability` and `FacilityAudit`.
3. Add a trace-prefix validation check to the audit build.
4. Add tests for trace propagation with mocked MLflow objects.
5. Document the behavior when MLflow is unavailable.

**Acceptance criteria:**

- Fresh extraction can produce non-empty, non-`local::*` trace IDs.
- `facility_audits.parquet` preserves trace IDs.
- Frontend receives trace IDs through `/facilities/{id}`.
- Tests cover legacy parquet rows without trace IDs.

### Lane 1B — Citation and Span Quality

**Branch:** `phase1/citation-quality`

**Worktree:** `../seahealth-worktrees/phase1-citations`

**File scope:**

- `src/seahealth/agents/extractor.py`
- `src/seahealth/agents/validator.py`
- `src/seahealth/db/retriever.py`
- `src/seahealth/pipelines/`
- `tests/`
- `docs/DATA_CONTRACT.md`

**Tasks:**

1. Measure percentage of evidence refs with non-empty snippets and valid spans.
2. Reject or repair citations where spans do not match chunk text.
3. Add a citation quality report command.
4. Add regression tests for span normalization and substring checks.

**Acceptance criteria:**

- Citation QA reports total refs, valid refs, invalid refs, and top failure reasons.
- Invalid spans are not silently rendered as trustworthy evidence.
- Facility audit evidence can show exact supporting sentence snippets.

### Lane 1C — Contradiction Recall Lift

**Branch:** `phase1/contradiction-recall`

**Worktree:** `../seahealth-worktrees/phase1-contradictions`

**File scope:**

- `src/seahealth/agents/heuristics.py`
- `src/seahealth/agents/validator.py`
- `src/seahealth/eval/`
- `tests/`
- `docs/eval/naomi_run.md`

**Tasks:**

1. Compare Naomi contradiction taxonomy against current heuristics.
2. Add the smallest useful heuristics for `vague_claim`, `missing_staff`, and `equipment_mismatch`.
3. Re-run eval on Naomi labels.
4. Report precision impact separately from recall lift.

**Acceptance criteria:**

- Contradiction recall is above zero on Naomi labels.
- New heuristics include examples and tests.
- Eval report explains remaining false negatives honestly.

### Phase 1 Integration Gate

Run:

```bash
pytest -q
ruff check src tests
python -m seahealth.eval.run_eval --labels tables/naomi_labels.csv
```

Then regenerate fixtures from the latest data if schema or response shape changed.

## Phase 2 — Databricks-Native Platform Completion

**Goal:** Align the implementation with the challenge's named Databricks stack, or document substitutions explicitly.

### Lane 2A — Vector Search Reality Check

**Branch:** `phase2/vector-search-live`

**Worktree:** `../seahealth-worktrees/phase2-vector-search`

**File scope:**

- `src/seahealth/db/retriever.py`
- `src/seahealth/db/databricks_resources.py`
- `databricks.yml`
- `tests/`
- `docs/DECISIONS.md`
- `README.md`

**Tasks:**

1. Confirm endpoint `seahealth-vs` and chunk index exist.
2. Make retriever prefer Mosaic AI Vector Search when configured.
3. Keep local FAISS/parquet fallback explicit and tested.
4. Add `/health/data` detail for retriever mode.

**Acceptance criteria:**

- Live mode reports Vector Search as active.
- Offline mode remains deterministic with local fixtures.
- README explains both modes.

### Lane 2B — Agent Bricks and Genie Code Decision

**Branch:** `phase2/databricks-agent-story`

**Worktree:** `../seahealth-worktrees/phase2-agent-story`

**File scope:**

- `src/seahealth/agents/`
- `docs/DECISIONS.md`
- `docs/AGENT_ARCHITECTURE.md`
- `README.md`
- `docs/PRODUCT_READINESS_REPORT.md`

**Tasks:**

1. Decide whether to migrate any agent path to Agent Bricks before submission.
2. Decide whether Genie Code belongs in the product or only the development story.
3. Document LLM provider fallback behavior and why it exists.
4. If no migration is made, add a judge-facing substitution rationale.

**Acceptance criteria:**

- No deck, README, or report claims unsupported Databricks usage.
- The architecture doc clearly distinguishes Databricks-native components from provider substitutions.

## Phase 3 — Frontend Live Product Surface

**Goal:** Turn the UI into a trustworthy planner workflow that can use live API data or deliberate demo data.

### Lane 3A — API Mode and Typed Fetching

**Branch:** `phase3/live-api-ui`

**Worktree:** `../seahealth-worktrees/phase3-live-api-ui`

**File scope:**

- `app/src/api/`
- `app/src/data/`
- `app/src/pages/`
- `app/src/components/`
- `app/src/types/`
- `app/package.json`
- `app/package-lock.json`

**Tasks:**

1. Add a single API client for `/summary`, `/query`, `/facilities/{id}`, and `/map/aggregates`.
2. Validate responses with TypeScript types or runtime schemas.
3. Make demo data an explicit fallback mode.
4. Add empty, loading, and error states for every live surface.

**Acceptance criteria:**

- Frontend can run with `VITE_SEAHEALTH_API_MODE=live`.
- Frontend can run with `VITE_SEAHEALTH_API_MODE=demo`.
- No page imports `demoData.ts` directly except through the data provider.

### Lane 3B — Facility Audit Trace View

**Branch:** `phase3/facility-trace-view`

**Worktree:** `../seahealth-worktrees/phase3-trace-view`

**File scope:**

- `app/src/pages/FacilityAudit.tsx`
- `app/src/components/`
- `app/src/types/`
- `docs/ux/`

**Tasks:**

1. Render evidence snippets, contradiction reasons, and trace IDs together.
2. Add a compact span timeline or step list for the audit flow.
3. Clearly mark missing trace data as unavailable, not successful.
4. Preserve the CIMS Patna contradiction reveal if data still supports it.

**Acceptance criteria:**

- A user can explain why a facility was recommended or downranked without leaving the UI.
- Missing MLflow traces are visible as a data-quality state.
- Facility Audit works from Map Workbench and Planner Query click-throughs.

### Lane 3C — Map Workbench Choropleth

**Branch:** `phase3/desert-map`

**Worktree:** `../seahealth-worktrees/phase3-desert-map`

**File scope:**

- `app/src/pages/`
- `app/src/components/`
- `app/src/data/mockIndiaRegions.topojson`
- `app/src/types/`
- `docs/ux/desert_map.md`

**Tasks:**

1. Confirm `/map/aggregates` returns at least 5 regions in live or fixture mode.
2. Render medical desert severity as a choropleth or equivalent geographic layer.
3. Add planner-focused hover/click details for need, facility count, and confidence.
4. Make region geometry limitations explicit.

**Acceptance criteria:**

- Map is not a placeholder.
- Region interactions connect to facilities or query filters.
- UI copy explains what the severity score means.

### Phase 3 Integration Gate

Run:

```bash
cd app
npm test -- --run
npm run build
```

Then smoke-test the browser flow:

1. Map Workbench loads.
2. Locked query runs.
3. Facility row opens Facility Audit.
4. Evidence and contradictions are visible.

## Phase 4 — Evaluation, Honesty, and Research Claims

**Goal:** Make the product's claims measurable and defensible.

### Lane 4A — Naomi Eval Reproducibility

**Branch:** `phase4/naomi-eval-repro`

**Worktree:** `../seahealth-worktrees/phase4-naomi`

**File scope:**

- `src/seahealth/eval/`
- `tests/`
- `docs/eval/`
- `README.md`

**Tasks:**

1. Ensure eval commands work from a clean checkout with documented inputs.
2. Report per-capability precision, recall, F1, and support.
3. Report contradiction recall with examples.
4. Add a "known limitations" section judges can trust.

**Acceptance criteria:**

- `docs/eval/naomi_run.md` can be regenerated.
- Metrics are scoped to Naomi's labeled universe.
- Report distinguishes extraction failures, unsupported labels, and model errors.

### Lane 4B — Aggregate Confidence Intervals

**Branch:** `phase4/confidence-intervals`

**Worktree:** `../seahealth-worktrees/phase4-confidence`

**File scope:**

- `src/seahealth/eval/`
- `src/seahealth/api/`
- `app/src/pages/`
- `app/src/components/`
- `docs/DATA_CONTRACT.md`

**Tasks:**

1. Define uncertainty for aggregate desert claims.
2. Add confidence interval fields to map or summary responses where appropriate.
3. Render uncertainty in the UI without overcomplicating the demo.
4. Document the statistical method and assumptions.

**Acceptance criteria:**

- Product does not present aggregate estimates as exact truth.
- UI includes at least one uncertainty cue for map or summary insights.
- Tests cover the interval calculation.

## Phase 5 — Production Hardening

**Goal:** Make the repo and app safe to run, inspect, and submit.

### Lane 5A — Clean Clone and Runtime

**Branch:** `phase5/clean-clone`

**Worktree:** `../seahealth-worktrees/phase5-clean-clone`

**File scope:**

- `README.md`
- `.env.example`
- `pyproject.toml`
- `app/package.json`
- `scripts/`
- `tests/`

**Tasks:**

1. Walk README quickstart on a fresh clone.
2. Add missing setup commands for data fixtures or local demo mode.
3. Confirm `pytest -q`, API startup, and frontend startup.
4. Remove or document local-only paths.

**Acceptance criteria:**

- A judge can run a demo without private data or secrets.
- Missing live Databricks credentials degrade to documented fixture mode.
- `.env.example` covers all required configuration.

### Lane 5B — API Robustness and Security

**Branch:** `phase5/api-hardening`

**Worktree:** `../seahealth-worktrees/phase5-api`

**File scope:**

- `src/seahealth/api/`
- `src/seahealth/db/`
- `tests/`
- `README.md`

**Tasks:**

1. Review CORS defaults and production configuration.
2. Ensure endpoint errors are structured and user-actionable.
3. Add health checks for data mode, retriever mode, and artifact freshness.
4. Run secret scan and dependency checks.

**Acceptance criteria:**

- API does not expose stack traces for expected data/config errors.
- `/health/data` explains whether live, parquet, or fixture mode is active.
- Secret scan is clean.

## Phase 6 — Submission Package

**Goal:** Package the product so judges understand the story quickly.

### Lane 6A — Demo Script and Video

**Branch:** `phase6/demo-package`

**Worktree:** `../seahealth-worktrees/phase6-demo`

**File scope:**

- `docs/demo/`
- `README.md`
- `app/src/data/` if demo fixture needs a final update

**Tasks:**

1. Write a 4-minute script:
   - 0:00-0:30 problem and data scale.
   - 0:30-1:30 map workbench and desert discovery.
   - 1:30-2:45 locked multi-attribute query.
   - 2:45-3:30 facility audit and contradiction reveal.
   - 3:30-4:00 evaluation numbers and Databricks architecture.
2. Record video against a deterministic data mode.
3. Store script, shot list, and final video link.

**Acceptance criteria:**

- Demo can be re-recorded without improvising.
- Script names the exact query, facility, and eval metrics.
- Video shows evidence and trust scoring, not just search results.

### Lane 6B — One-Pager and Judge Notes

**Branch:** `phase6/one-pager`

**Worktree:** `../seahealth-worktrees/phase6-one-pager`

**File scope:**

- `docs/submission/`
- `README.md`
- `docs/PRODUCT_READINESS_REPORT.md`

**Tasks:**

1. Create a one-page product brief.
2. Summarize architecture, eval, limitations, and impact.
3. Add a judge walkthrough with commands and screenshots.
4. Include explicit "what is real vs fixture" notes.

**Acceptance criteria:**

- Judges can understand value, architecture, and evidence in under 2 minutes.
- Claims match the code and eval report.
- Known limitations are framed as honest scope, not hidden failures.

## Phase 7 — Final Integration and Release

**Goal:** Produce one green, tagged release state.

**Owner:** Integrator.

**Branch:** `release/seahealth-submission`.

**Tasks:**

1. Merge final lanes into `integrate/ship-12h`.
2. Create `release/seahealth-submission` from the final integration commit.
3. Run full gates:

```bash
pytest -q
ruff check src tests
python -m seahealth.eval.run_eval --labels tables/naomi_labels.csv
cd app && npm test -- --run && npm run build
```

4. Run the UI smoke test against demo mode and, if credentials are present, live mode.
5. Generate final `docs/PRODUCT_READINESS_REPORT.md`.
6. Tag the final commit:

```bash
git tag submission-YYYYMMDD
```

**Acceptance criteria:**

- Release branch has no unrelated dirty files.
- All required artifacts are linked from README.
- Final report lists any residual risks and why they are acceptable for submission.

## Parallel Execution Matrix

| Lane | Can Run With | Must Wait For | Primary Conflict Risk |
|---|---|---|---|
| 1A MLflow traces | 1B, 1C, 2A | Phase 0 | Schemas, audit builder |
| 1B Citation quality | 1A, 1C, 2A | Phase 0 | Extractor/validator contracts |
| 1C Contradiction recall | 1A, 1B, 4A | Phase 0 | Validator heuristics |
| 2A Vector Search | 1A, 1B, 3A | Phase 0 | Retriever health behavior |
| 2B Agent story | Any docs lane | Phase 0 | Docs consistency |
| 3A Live API UI | 2A, 4A | Phase 0 | Shared frontend data types |
| 3B Facility trace view | 1A, 3A | Trace response shape | Shared FacilityAudit components |
| 3C Desert map | 4B, 3A | Map response shape | Shared map types |
| 4A Eval repro | 1C | Phase 0 | Eval docs |
| 4B Confidence intervals | 3C | Aggregate schema decision | API response schema |
| 5A Clean clone | Most lanes | Late Phase 3 | README churn |
| 5B API hardening | 2A, 3A | Stable API shape | API tests |
| 6A Demo | 3A, 3B, 3C, 4A | Stable UI flow | Demo fixture updates |
| 6B One-pager | 2B, 4A, 6A | Final metrics | Submission docs |

## Agent Prompt Template

Use this template when assigning a lane to a coding agent:

```markdown
You are implementing <lane name> for SeaHealth.

Base branch: integrate/ship-12h
Working branch: <branch>
Worktree: <path>
Allowed file scope:
- <paths>

Read first:
1. challenge.md
2. docs/ROADMAP.md
3. state.md
4. docs/DATA_CONTRACT.md
5. docs/AGENT_ARCHITECTURE.md
6. This plan section for <lane name>

Implement only the tasks in this lane.

Acceptance criteria:
- <copy criteria>

Required verification:
- <commands>

Before final response:
1. Show changed files.
2. State tests run and results.
3. State any residual risks.
4. Do not commit secrets or private data.
```

## Quality Gates

Every implementation lane must satisfy:

1. Tests pass for the touched surface.
2. New behavior has at least one regression test unless it is docs-only.
3. Docs are updated when APIs, schemas, commands, or demo behavior change.
4. No required artifact exists only in an ignored local file unless README explains how to generate it.
5. No claims in README, one-pager, or demo script exceed what the code can show.

## Stop Criteria

Stop parallel work and move to final integration when:

1. Phase 1 data and traceability gates are green or residual gaps are documented.
2. Phase 3 UI smoke test works in demo mode.
3. Phase 4 eval report is reproducible.
4. Phase 5 clean-clone path is documented.
5. Phase 6 demo package has script, video link, and one-pager.

At that point, only release-critical bug fixes should be accepted into `integrate/ship-12h`.
