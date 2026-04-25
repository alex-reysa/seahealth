# UX_FLOWS

> Three flows, not a design system. Tailwind defaults + shadcn = done. No font system, no component library debates.
>
> **Out of scope for this hackathon:** mobile layouts and accessibility audits. Desktop only, judges-on-a-laptop only.

---

## Surface 1: Desert Map (the hook)

**The one task it enables:** Sarah picks a specialty (oncology / dialysis / trauma / neonatal / appendectomy) and instantly sees where in India that capability is missing or low-trust, ranked by population coverage gap.

**Wireframe:**
- Top bar: specialty dropdown (filters by `CapabilityType`), radius slider (30km / 60km / 120km), state filter.
- Main canvas: India choropleth by PIN code district. Color scale = capability gap (verified facilities per 100K population).
- Right rail: when a region is clicked, a ranked list of facilities appears with `TrustScore`, distance, and the gap quantified ("47K people, nearest verified dialysis: 94km").
- Bottom strip: top-line metric — "9,847 facilities verified · 153 flagged for human review."

**Data dependencies (from `DATA_CONTRACT.md`):**
- `FacilityAudit.location` (`GeoPoint` with `pin_code`)
- `FacilityAudit.capabilities[*].capability_type`
- `FacilityAudit.trust_scores[CapabilityType].score`
- `FacilityAudit.trust_scores[CapabilityType].confidence_interval`
- `FacilityAudit.total_contradictions`
- `MapRegionAggregate` per selected region/capability, including `capability_count_ci`
- `PopulationReference` per PIN/district (static reference dataset, loaded once)
- Verified/flagged summary: verified = score >= 80 and no HIGH contradictions for the selected capability; flagged = `total_contradictions > 0` or any HIGH contradiction.

**The demo moment:** judge picks "neonatal", map lights up red across 4 districts in Bihar, click → "Madhubani: 312K people, 0 verified neonatal facilities within 60km."

---

## Surface 2: Facility Audit View (the substance)

**The one task it enables:** Sarah picks one facility (from the map or a query result) and sees, claim by claim, what evidence supports it, what contradicts it, and what's silent — so she can decide whether to fund it.

**Wireframe:**
- Header: facility name, location, `FacilityAudit.mlflow_trace_id` link.
- Split pane:
  - **Left:** claimed capabilities checklist. Each row = one `Capability`, with a `TrustScore` badge (0–100), color-coded **green ≥80, yellow 50–79, red <50**. Click a row to expand.
  - **Right:** evidence trail for the selected capability. Each `EvidenceRef` shown as a card with the highlighted `EvidenceRef.snippet`, a `EvidenceRef.source_type` chip, and `EvidenceAssessment.stance` — **`verifies` (green) / `contradicts` (red) / `silent` (gray)**. `Contradiction` objects render as red banners with the `Contradiction.reasoning` field surfaced.
- Footer: "View MLflow trace" button → expands the span timeline (transparency feature).

**Data dependencies:**
- Full `FacilityAudit` record
- For each `Capability`: `Capability.evidence_refs` plus the matching `TrustScore.evidence` and `TrustScore.contradictions`
- `EvidenceAssessment.stance` values: `verifies`, `contradicts`, `silent`
- `EvidenceRef.snippet`, `EvidenceRef.source_type`, `EvidenceRef.span`
- `Contradiction.reasoning`, `Contradiction.contradiction_type`, `Contradiction.severity`
- `FacilityAudit.mlflow_trace_id` for trace expansion

**The demo moment:** judge clicks the appendectomy row on the top-ranked facility → right pane shows three `verifies` cards (claim text + matching equipment list snippet) and one red `MISSING_STAFF` contradiction: "claims appendectomy capability but no anesthesiologist on staff_roster."

---

## Surface 3: Planner Query Console (the agent)

**The one task it enables:** Sarah types a natural-language question and gets a ranked, exportable list of facilities — not chat prose. Each row carries the audit summary so she can scan 50 facilities in 30 seconds.

**Wireframe:**
- Top: single text input ("Ask anything about Indian healthcare facilities…"), submit button. **No chat bubbles, no conversation history.**
- Below: result table — sortable columns: rank, facility name, distance_km, `TrustScore` (0–100 with color badge), contradictions_flagged (red number), evidence_count, location pin.
- Each row: click → opens the Facility Audit View (Surface 2) for that facility.
- Top-right: "Export to CSV" button.
- Sidebar: parsed-intent panel showing the structured filter (`capability_type`, location, `radius_km`) — proves the agent understood the question.

**Data dependencies:**
- `QueryResult.query` (echoed back in the input)
- `QueryResult.parsed_intent` (sidebar)
- `QueryResult.ranked_facilities: list[RankedFacility]` (table rows)
- `RankedFacility.{facility_id, name, distance_km, trust_score, contradictions_flagged, evidence_count, rank, location}`
- `QueryResult.query_trace_id` (footer link)

**The demo moment:** judge types `Which facilities within 50km of Patna can perform an appendectomy?` → table populates with 7 ranked facilities, top row `TrustScore=72` with 1 contradiction flagged. CSV export downloads. Click the row → Facility Audit View opens with the contradiction visible.

---

## Cross-surface flow

Demo navigation:

**Desert Map (hook)** → click region → click facility → **Facility Audit View (substance)** → back → **Planner Query Console (agent)** → run `Which facilities within 50km of Patna can perform an appendectomy?` → click top result → **Facility Audit View** again, with the contradiction visible.

The same `FacilityAudit` is the canonical record across all three surfaces. The map aggregates it, the audit view drills into it, and the query console ranks it — but the underlying object is one and the same, addressable by `FacilityAudit.facility_id`.
