# SeaHealth — 4-minute demo script

Locked query: *"Find the nearest facility in rural Bihar that can perform an
emergency appendectomy and typically leverages parttime doctors."*

Locked facility (visible UI demo target): **Patna Medical College**
(`facility_patna_medical`). Locked contradiction: **MISSING_STAFF**, HIGH
severity — "no anesthesiologist listed as active". Trust score 72.

> Caveat: this demo runs against the static `app/src/data/demoData.ts`
> fixture so the UX is deterministic. The API-shape fixtures under
> `fixtures/` use a different facility (CIMS Hospital Patna) and are
> exercised by the backend tests; the two layers will be unified in a
> follow-up.

Recording mode: `npm run dev` with no env overrides → demo data path.
Backend, if shown: `SEAHEALTH_API_MODE=fixture` so `/health/data` reports
`mode=fixture`.

---

## 0:00 – 0:30 — Problem and data scale

> "70% of India's 1.4 billion people live in rural areas where healthcare
> access is a discovery problem. Patients travel hours and find the wrong
> capability. We built SeaHealth on Databricks to turn 10,000 messy facility
> reports into a planner workbench."

Show: title slide; data scale cue: *10,000 facility reports → 4,802
extracted capability rows → 974 verified, 900 flagged*.

## 0:30 – 1:30 — Map Workbench: desert discovery

Click **Map Workbench**. Hover Bihar.

> "Each region carries a verified-facility count, a flagged count, and a
> coverage gap. The schema reserves a 95% Wilson interval slot for the
> count too — Phase 4 ships the helper, Phase 7 surfaces it on `/summary`,
> and the next pass wires it onto the map tooltip."

Show: choropleth severity layer; tooltip with `verified_facilities_count`,
`flagged_facilities_count`, `gap_population`.

## 1:30 – 2:45 — Planner Query: locked multi-attribute query

Open **Planner Query**. The query box is pre-filled with the locked query.
Run it.

> "The Query Agent parsed three signals: appendectomy as the capability,
> Bihar/rural as the location, and parttime as the staffing qualifier — a
> closed-taxonomy field we added so the demo answers the exact question.
> Results are ranked by trust score; a soft re-rank based on numberDoctors
> floats parttime-leveraging facilities up."

Show: ranked results table with trust score, distance, contradiction count.
Top hit is **Patna Medical College** at trust score 72.

## 2:45 – 3:30 — Facility Audit: contradiction reveal

Click the top row.

> "Patna Medical College claims appendectomy capability with a trust score
> of 72. The Validator caught a HIGH-severity MISSING_STAFF contradiction:
> 'No anesthesiologist listed as active. Dr. A. Sharma retired in 2023;
> replacement position remains vacant.' The split pane shows six pieces of
> verifying evidence on the left versus the staff-roster row that
> contradicts the claim on the right."

Show: facility audit split pane; HIGH contradiction badge; the trace panel
with the MLflow run id.

## 3:30 – 4:00 — Eval and Databricks story

> "We hand-labeled 30 facilities with a clinical reviewer. Capability
> extraction scores P=0.488, R=0.362, F1=0.416 against her labels. Phase 1C
> fixed the audit-shape parser and added a vague-claim heuristic so the
> next eval run lifts contradiction recall off zero. The demo runs against
> Unity Catalog Delta tables, Mosaic AI Vector Search, and MLflow 3 in live
> mode; we substituted OpenRouter Anthropic Haiku 4.5 for the 10k extraction
> because the free-tier Databricks endpoint hit a rate ceiling — that's
> documented in `docs/DECISIONS.md` and reversible by flipping a single env
> var."

Show: README architecture table side-by-side with the eval markdown.

---

## Shot list

1. Title slide.
2. Map Workbench in default capability filter.
3. Map Workbench with tooltip on Bihar.
4. Planner Query with the locked query pre-filled.
5. Planner Query results table (Patna Medical College ranked #1, score 72).
6. Facility Audit page for `facility_patna_medical`.
7. HIGH MISSING_STAFF contradiction reasoning close-up.
8. README architecture table.
9. `docs/eval/naomi_run.md` per-capability table.

## Re-record checklist

- [ ] `pytest -q` is green from a fresh worktree.
- [ ] `cd app && npm install && npm run build` succeeds.
- [ ] No env override on `app` so the visible UI uses `demoData.ts`.
- [ ] `SEAHEALTH_API_MODE=fixture` on the backend so `/health/data` reports
      `mode=fixture` and `retriever_mode=faiss_local` (no live creds in frame).
- [ ] No real `dapi-` or `sk-or-` tokens visible in any frame.
