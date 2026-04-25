# DECISIONS

> Lightweight ADR log. ~5 min per entry. Future-you at hour 30 will thank you when tempted to re-litigate.

Format: `YYYY-MM-DD HH:MM — <decision>. Reason: <why>. Replaces: <what it kills/changes>.`

---

- `2026-04-25 22:15 — EvidenceAssessment.stance is the canonical evidence verdict field. Reason: support/contradiction/insufficient-evidence must be explicit and separate from confidence. Replaces: inferring stance from confidence or contradiction labels.`
- `2026-04-25 22:10 — Map aggregates use PopulationReference and MapRegionAggregate schemas. Reason: choropleths need population denominator, region metadata, capability counts, and lineage in a shared contract. Replaces: ad hoc map aggregate JSON.`
- `2026-04-25 22:05 — ParsedIntent is typed before retrieval and RankedFacility.location is carried through ranking. Reason: the Patna radius query needs explicit procedure, radius, location, and display coordinates downstream. Replaces: passing raw query text and rejoining location in the UI.`
- `2026-04-25 21:55 — Naomi (domain expert) hand-labels 30 facility records as gold eval set. Reason: brief says "no answer key"; expert labels are the only way to compute precision/recall. Replaces: eyeballing extraction outputs.`
- `2026-04-25 21:40 — Aggregate confidence intervals live in MapRegionAggregate.capability_count_ci. Reason: "Bihar has between 12 and 19 functional ICUs (95% CI)" is more credible than a point estimate and directly answers Section 4's open research question. Replaces: point-estimate aggregates.`
- `2026-04-25 21:20 — BAAI/bge-large-en-v1.5 embeddings (1024-dim) for the vector index. Reason: open-source, runs on Databricks, strong English retrieval baseline. Replaces: closed embeddings or undecided default.`
- `2026-04-25 21:00 — MLflow traces are user-facing, not dev-only. Reason: transparency is the product; the Facility Audit View renders trace spans as evidence. Replaces: MLflow as a backend-only debugging tool.`
- `2026-04-25 20:45 — Demo script locked at hour 24, not hour 36. Reason: forces alignment between what's built and what's shown, and reveals which features are vanity. Replaces: demo script written at the end.`
- `2026-04-25 20:30 — Hard scope freeze at hour 24. Reason: anything added after hour 24 won't make it into the polished demo; protects the final 12 hours for testing/recording. Replaces: continuous feature addition until end.`
- `2026-04-25 20:15 — Schema owner has veto power on DATA_CONTRACT.md after hour 4. Reason: schema drift mid-hackathon is fatal — three different Facility shapes by hour 12 without enforcement. Replaces: collaborative schema editing. (Owner: Alejandro (acting schema owner).)`
- `2026-04-25 20:00 — Tailwind defaults + shadcn, no custom design system. Reason: every minute on font/palette is a minute not on the Validator Agent. Replaces: custom design system.`
- `2026-04-25 19:45 — No authentication, multi-user, saved searches, dark mode, or mobile. Reason: hackathon scope; none of it changes the demo or the eval. Replaces: full product surface area.`
- `2026-04-25 19:30 — Killed ICU bed availability prediction. Reason: no time-series data available, can't validate. Replaces: bed-availability forecasting with capability-claimed-vs-verified scoring.`
- `2026-04-25 19:15 — Single demo query locked as "Which facilities within 50km of Patna can perform an appendectomy?", fully traced. Reason: judges will ask for a live run; one polished trace beats five rough ones. Replaces: demo with multiple sample queries.`
- `2026-04-25 19:00 — Closed contradiction taxonomy via ContradictionType enum (MISSING_EQUIPMENT, MISSING_STAFF, VOLUME_MISMATCH, TEMPORAL_UNVERIFIED, CONFLICTING_SOURCES, STALE_DATA). Reason: 36-hour scope; an open-ended taxonomy is unbounded. Replaces: free-text contradiction labels.`
- `2026-04-25 18:40 — Validator Agent runs on every extraction, not on-demand. Reason: lets the UI show a top-line "9,847 verified, 153 flagged for human review" metric — proves scale plus humility. Replaces: on-demand validation triggered from the audit view.`
- `2026-04-25 18:20 — Trust Score is a structured object, not a number. Reason: every team will compute a 0–100 score; differentiation is in the claimed/evidence/contradictions/confidence_interval/reasoning shape. Replaces: scalar trust score.`
- `2026-04-25 17:30 — Three connected surfaces, no chat UI. Reason: chat bubbles signal "demo project" — planners live in spreadsheets and maps. Replaces: conversational search interface.`
- `2026-04-25 17:00 — NGO planner is the user, not the patient. Reason: the brief explicitly calls for "actionable insights for NGO planners" in eval criteria — planners need confidence intervals and gaps, not a map pin. Replaces: generic patient-facing search UX.`

<!-- Add new entries above this line, newest at top -->
