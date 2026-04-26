# SeaHealth — 4-minute demo script

Locked query: *"Find the nearest facility in rural Bihar that can perform an
emergency appendectomy and typically leverages parttime doctors."*
Locked facility: **CIMS Hospital Patna** (`vf_02239_cims-hospital-patna-a-un`).
Recording mode: `VITE_SEAHEALTH_API_MODE=demo` (deterministic fixtures).
Backend mode: `SEAHEALTH_API_MODE=fixture` (no live creds required).

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
> 95% Wilson confidence interval — we don't pretend to know more than the
> data shows. Bihar is amber: high gap_population, low verified count."

Show: choropleth severity layer; tooltip with `verified_facilities_count`,
`flagged_facilities_count`, `gap_population`.

## 1:30 – 2:45 — Planner Query: locked multi-attribute query

Open **Planner Query**. The query box is pre-filled with the locked query.
Run it.

> "The Query Agent parsed three signals: appendectomy as the capability,
> Bihar/rural as the location, parttime as the staffing qualifier — that
> last one is a closed-taxonomy field we added so the demo answers the
> exact question. Results are ranked by trust score, with a soft re-rank
> based on numberDoctors so 'parttime-leveraging' facilities float up."

Show: ranked results table with trust score, distance, contradiction count.
Top hit is in Patna; second hit is the demo target.

## 2:45 – 3:30 — Facility Audit: contradiction reveal

Click the demo target row.

> "CIMS Hospital Patna claims appendectomy capability with a trust score of
> ~70. The Validator caught a vague-claim contradiction (Phase 1C) — the
> supporting snippet is shorter than 12 chars, which is suspicious for a
> high-acuity claim. Every claim shows the exact evidence span and the
> MLflow trace classification — `live`, `synthetic`, or `missing` — so a
> planner knows whether to trust the trace link or treat the audit as
> offline-mode."

Show: TraceClassBadge in synthetic state with hover copy ("trace
unavailable — extraction ran without MLflow"); evidence card with the
short snippet highlighted; contradiction reasoning naming "Vague claim:
SURGERY_APPENDECTOMY supported only by N-char evidence snippet".

## 3:30 – 4:00 — Eval and Databricks story

> "We hand-labeled 30 facilities with a clinical reviewer. Capability
> extraction scores P=0.488, R=0.362, F1=0.416 against her labels (Phase
> 6 re-scoped). Contradiction recall lifts from zero in the first run to
> non-zero after Phase 1C — we can show the new heuristics in the
> repo. The demo runs against Unity Catalog Delta tables, Mosaic AI
> Vector Search, and MLflow 3 in live mode; we substituted OpenRouter
> Anthropic Haiku 4.5 for the 10k extraction because the free-tier
> Databricks endpoint hit a rate ceiling — that's documented in
> `docs/DECISIONS.md` and reversible by flipping a single env var."

Show: README architecture table side-by-side with the eval markdown.

---

## Shot list

1. Title slide.
2. Map Workbench in default capability filter.
3. Map Workbench with tooltip on Bihar.
4. Planner Query with the locked query pre-filled.
5. Planner Query results table.
6. Facility Audit page for CIMS Patna.
7. TraceClassBadge close-up.
8. README architecture table.
9. `docs/eval/naomi_run.md` per-capability table.

## Re-record checklist

- [ ] `pytest -q` is green from a fresh worktree.
- [ ] `cd app && npm install && npm run build` succeeds.
- [ ] `VITE_SEAHEALTH_API_MODE=demo` is set; `app/src/data/fixtures/*.json`
      match the four canonical demo fixtures.
- [ ] `SEAHEALTH_API_MODE=fixture` is set so `/health/data` reports
      `mode=fixture`.
- [ ] No real `dapi_*` or `sk-*` tokens are visible in any frame.
