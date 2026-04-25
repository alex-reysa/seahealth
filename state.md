# state.md — pm-go orchestration log

Source of truth for sprint task status. Resume work from the last `Merged` row.

- Plan: `/Users/alejandro/.claude/plans/let-s-tackle-all-these-glowing-kazoo.md`
- Branch: `integrate/ship-12h`
- Tag: `spec-2026-04-25` (contract freeze)
- Budget: rough sub-agent token usage logged per task; running total below.

## Status legend

- **Pending** — defined, not started
- **Running** — sub-agent active in its worktree
- **Auditing** — sub-agent returned, Auditor (me) running pytest + fileScope check
- **Reviewing** — Reviewer sub-agent doing independent diff-audit (end-of-phase only)
- **Merged** — auditor + reviewer green, branch merged to `integrate/ship-12h`, worktree removed

## Phases

### Phase 0 — Tooling — MERGED

| Task | Status | Commit | Notes |
|---|---|---|---|
| A-1 Package scaffold | Merged | `8c8245a` | pyproject, .env.example, src/seahealth |
| B-1 databricks.yml | Merged | `8c8245a` | bundle validate -t dev OK |

### Phase 1 — Contracts + Local Golden Path — MERGED

| Task | Status | Commit | Notes |
|---|---|---|---|
| C-1 Schemas (Codex) | Merged | `4e02522` | 12 modules, 28 tests |
| D-1 Normalize (Codex) | Merged | `4e02522` | normalize.py + 7 tests |
| E-1 FastAPI + OpenAPI | Merged | `00f54af` | 6 endpoints, 12 tests, fixtures |

### Phase 2 — Databricks Foundation + Agent Code — IN FLIGHT (Reviewer pending)

| Task | Status | Commit | Audit | Notes |
|---|---|---|---|---|
| F-1 Databricks foundation | Merged | `5568362` | pytest 64 ✓, ruff ✓, fileScope ✓ | UC catalog `workspace`, 3 schemas, volume + 10MB CSV, 7 Delta tables, MLflow exp 405251052688464, VS endpoint READY (chunks_index DELTA_SYNC) |
| G-1 Extractor agent code | Merged | `260e2cf` | pytest 57 ✓, ruff ✓, fileScope ✓ | Mocked tests pass without ANTHROPIC_API_KEY |
| H-1 Validator agent code | Merged | `da3f692` | pytest 82 ✓, ruff ✓, fileScope ✓ | Heuristics + mocked LLM path |
| R-2 Reviewer pass | Done | — | YELLOW verdict | Phase 3 not blocked. 3 cleanup items tracked below. |

**Merged-branch pytest: 107 passing.**

#### R-2 cleanup backlog (handled by Cleanup-2 sub-agent in parallel with Phase 3)

1. **`evidence_ref_id` format**: validator builds `f"{source_doc_id}:{chunk_id}"` but the schema doesn't document this contract. Risk: Phase 3 Trust Scorer / Audit Builder may reinvent the join key. Fix: add a one-line note under `EvidenceAssessment` in `DATA_CONTRACT.md` and expose a helper `evidence_ref_id(ref)` in `seahealth.schemas`.
2. **Absolute laptop paths** in `db/retriever.py:303-306` (`DEFAULT_CHUNKS_PARQUET_PATHS`) and `db/databricks_resources.py:52-55` (`DEFAULT_CSV_PATH`). Fix: env-var first (`SEAHEALTH_CHUNKS_PARQUET`, `SEAHEALTH_VF_CSV`), absolute path becomes last fallback.
3. **Mixed tz datetimes**: `extractor.py:198` strips tz, validator/heuristics keep tz-aware UTC. Fix: keep `tzinfo=UTC` in extractor.

### Phase 3 — Trust + Query — MERGED (live run pending API key)

| Task | Status | Commit | Audit | Notes |
|---|---|---|---|---|
| Cleanup-2 (R-2 backlog) | Merged | (post 87a8ac0) | pytest 109 ✓, ruff ✓, fileScope ✓ | evidence_ref_id helper + DATA_CONTRACT note + env paths + tz fix |
| I-1 Trust Scorer + Audit Builder | Merged | (post 87a8ac0) | pytest 123 ✓, ruff ✓, fileScope ✓ | Deterministic scores: clean=95, flagged=35, mixed=60 |
| J-1 Query Agent code | Merged | (post 87a8ac0) | pytest 124 ✓, ruff ✓, fileScope ✓ | Mocked tests pass without ANTHROPIC_API_KEY |
| R-3 Phase 3 Reviewer pass | Pending | — | — | End-of-phase audit |

**Merged-branch pytest: 142 passing.**

**Blocker for live demo run**: `ANTHROPIC_API_KEY` not yet in `.env`. Drop in `sk-ant-...` to unblock the locked appendectomy query against real data.

### Phase 4 — Real API + Eval — K-1 + M-1 MERGED (alongside Audit Swarm)

| Task | Status | Commit | Audit | Notes |
|---|---|---|---|---|
| K-1 Wire FastAPI to Delta | Merged | `c3c9c8e` | pytest 153 ✓, ruff ✓, fileScope ✓ | data_access.py with DELTA→PARQUET→FIXTURE; /query heuristic-path; X-Query-Trace-Id; /health/data |
| M-1 Eval vs Naomi gold | Merged | `ccf1755` | pytest 179 ✓, ruff ✓, fileScope ✓ | naomi_mapping + metrics + run_eval CLI + 21 tests + skeleton report |
| Hotfix `.gitignore` for test fixtures | Merged | `f4d5bde` | pytest 190 ✓ | `*.csv` was excluding the synthetic Naomi sample; added `!tests/fixtures/**/*.csv` exception |
| L-1 Regenerate fixtures from real data | Pending | — | — | After ANTHROPIC_API_KEY in `.env` and a live extract+validate+score+build run. |

**Merged-branch pytest: 190 passing.**

## Budget

| Phase | Sub-agent tokens (approx) | Wall time |
|---|---|---|
| 0 | ~85k | ~5 min |
| 1 | ~70k | ~7 min |
| 2 | running | running |

## Resume rules

If a task crashes mid-flight:

1. Read this file. Find the last `Running` or `Auditing` row.
2. `git worktree list` — confirm the worktree still exists.
3. `cd <worktree> && git status --short` — see what was done.
4. If <50% complete, blow away the worktree (`git worktree remove --force`) and re-spawn the sub-agent with the same fileScope.
5. If ≥50% complete, hand the partial diff back to the sub-agent with a "continue from here" prompt.

## Mandatory invariants (Auditor must check after every task)

1. `pytest -q` is green from the worktree.
2. `git diff --name-only HEAD~1 HEAD` ⊆ task `fileScope`. No out-of-scope edits.
3. Every file listed in task's "Deliverables" exists.
4. `ruff check src/ tests/` passes (zero errors).
5. No new file > 500 LOC unless the deliverable explicitly says so.
6. No secrets committed (`git ls-files | xargs grep -l 'dapi\|sk-ant-' || true` returns empty).

## Reviewer rubric (end-of-phase)

The Reviewer is a fresh sub-agent that reads the merged diff vs the plan and answers, in <300 words:
- Does the diff implement the phase's deliverables? (yes/no per task)
- Cross-doc consistency: schemas in `src/` ↔ `DATA_CONTRACT.md` ↔ fixtures still aligned?
- Any commits that smell like out-of-scope work?
- Any test that's tautological (asserts mock returns mock)?
- Verdict: GREEN / YELLOW / RED. RED = block next phase until fixed.
