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

**Merged-branch pytest after Phase 4 K-1+M-1: 190 passing.**

### Audit Swarm — 2026-04-26 (cherry-picked into integrate/ship-12h)

| Task | Commit | Verdict | Notes |
|---|---|---|---|
| AUD-01 schemas & contract | `b93b400` | Merged GREEN | +287 / -71; new `_datetime.py` helper, hardened invariants |
| AUD-02 extractor/validator/heuristics | `7b7182c` | Merged GREEN | +284 / -16 hardening (prompt injection guards, span normalization, threshold fixes) |
| AUD-03 trust + audit builder | `e932076` | Merged GREEN | +171 / -16 (atomic parquet write w/ uuid + cleanup, `mlflow_trace_id` param, edge-case tests) |
| AUD-04 query + tools + geocode | `cdfa9a3` | Merged GREEN | +315 / -57 (synonyms, more cities, tie-break, empty-state) |
| AUD-05 databricks + retriever | `2c02d2d` | Merged GREEN | +465 / -43 (largest delta — DDL injection guards, idempotency, FAISS chain) |
| AUD-06 pipelines | `cab1981` | Merged GREEN | +254 / -23 (`--limit` CLI; conflict-resolved against AUD-03) |
| AUD-07 api + fixtures + openapi | `4a01585` | Merged GREEN | +129 / -25; regenerated openapi.yaml after AUD-01 hardening; +9 tests (fixture validity parametrize, 503/422/404 paths, body-vs-header trace-id); CORS production TODO comment; `/facilities` `limit` validated 1–50 |
| AUD-08 tests quality | `49004cf` | Merged GREEN | NEW `tests/conftest.py` (84 LOC, registers `slow` marker, deterministic seeds), `_helpers.py` (191 LOC, 5 factories), `README.md` (154 LOC). 8 tautology cases identified (read-only); coverage gaps: sql_warehouse 67%, validator 70%, data_access 70%, databricks_resources 76%, query 77% |
| AUD-09 docs drift + state | `9f58093` | Merged GREEN | README Quickstart added; 6 new ADRs in DECISIONS.md; PHASES.md checkboxes synced; UX schema-name drift annotated (rich-vs-slim variant note in dashboard.md/desert_map.md) |
| AUD-10 security/tooling/deps | `c481575` | Merged GREEN | Zero project-dep CVEs (only `pip` itself flagged); secret-scan clean across full history; `databricks bundle validate -t dev` ✓; +4 `.gitignore` entries (`.coverage`, `.coverage.*`, `htmlcov/`, `__main__.py.cache`) |
| AUD-R consolidated reviewer | — | Not run | Optional; can be re-launched |

**Merged-branch pytest after full audit swarm integration: 255 passing.**

### Phase 4-L — Live extraction + fixtures regen — MERGED (2026-04-26)

| Task | Status | Commit | Notes |
|---|---|---|---|
| Lane A doc hygiene | Merged | `333d4d0` | DATA_CONTRACT EvidenceAssessment revert; Anthropic→Databricks doc drift |
| Lane B spot-check | Merged | (Lane A's commit) | Al-Shifa Surgical & Maternity → MATERNAL claimed=True |
| Lane C full pipeline (250 facilities, Kimi K2.5) | Merged | `f23b456` | 36 facilities w/ caps; 67 capability rows; 13 ranked Patna facilities |
| Lane D fixtures from real data | Merged | `f23b456` | summary/query/audit/map all regenerated; tests deterministic via SEAHEALTH_API_MODE=fixture |

**Merged-branch pytest after Phase 4-L: 255 passing.**

### Phase 5 — Naomi REAL eval — MERGED (2026-04-26)

| Task | Status | Commit | Notes |
|---|---|---|---|
| Phase 5-A docs/ROADMAP.md | Merged | (this commit) | Bird's-eye phase tracker |
| Phase 5-B Naomi label adapter + 7 tests | Merged | (this commit) | xlsx → CSV; explode multi-value caps; row_index = source_row_number - 1 |
| Phase 5-C Real eval run | Merged | (this commit) | Cap precision 0.196, recall 0.345, F1 0.250. ONCOLOGY F1=0.714 (best); contradiction recall 0 (heuristic taxonomy narrower than Naomi's). |
| Re-extracted Naomi's 30 facilities (Kimi K2.5) | — | — | 20/30 succeeded → 43 cap rows; merged with demo extraction → 56 facilities total in capabilities.parquet |

**Merged-branch pytest after Phase 5: 262 passing.**

### Phase 6 — Demo polish + submission — TODO

| Task | Status | Notes |
|---|---|---|
| Demo script (4 min, scripted) | Pending | Naomi drafts per PHASES.md non-negotiable |
| Demo video (screen + voiceover) | Pending | Walkthrough: Map Workbench → Planner Query → Facility Audit on CIMS Patna |
| One-pager PDF | Pending | Eval numbers (P=0.196, R=0.345 + per-cap F1) front and centre |
| Submission packaging | Pending | README finalized, runtime verified on clean clone |
| Optional: AUD-R, R-3, AUD-08 cleanup | Deferred | Non-blocking |

#### Conflict resolution log
- `src/seahealth/pipelines/build_audits.py` (AUD-03 vs AUD-06): kept AUD-03's atomic-write-with-uuid, kept BOTH `mlflow_trace_id` and `limit` params, both CLI flags, both docstring lines. Added one-line fix: `facility_ids` is now also filtered by `keep_ids` inside the `limit` block (was missed by auto-merge; surfaced by `test_build_audits_respects_limit`).
- `tests/test_build_audits.py`: kept all three new tests (`test_build_audits_includes_zero_capability_facility_once`, `test_build_audits_threads_trace_and_json_roundtrips`, `test_build_audits_respects_limit`).

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
