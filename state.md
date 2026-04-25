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

### Phase 2 — Databricks Foundation + Agent Code — IN FLIGHT

| Task | Status | Worktree | Branch | Audit | Notes |
|---|---|---|---|---|---|
| F-1 Databricks foundation | Pending | `seahealth-wt-F1` | `phase2-F1-databricks` | — | UC + Delta + MLflow + VS (or FAISS fallback) |
| G-1 Extractor agent code | Pending | `seahealth-wt-G1` | `phase2-G1-extractor` | — | Code + mocked tests; live run after ANTHROPIC_API_KEY in place |
| H-1 Validator agent code | Pending | `seahealth-wt-H1` | `phase2-H1-validator` | — | Heuristic + mocked LLM path |
| R-2 Reviewer pass | Pending | — | — | — | End-of-phase independent diff audit |

### Phase 3 — Trust + Query — PENDING

| Task | Status | Notes |
|---|---|---|
| I-1 Trust Scorer + Audit Builder | Pending | After H-1 |
| J-1 Query Agent + locked demo run | Pending | After I-1 + ANTHROPIC_API_KEY |

### Phase 4 — Real API + Eval — PENDING

| Task | Status | Notes |
|---|---|---|
| K-1 Wire FastAPI to Delta | Pending | |
| L-1 Regenerate fixtures from real data | Pending | |
| M-1 Eval vs Naomi gold | Pending | When Naomi delivers labels |

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
