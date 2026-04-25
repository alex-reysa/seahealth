# VISION

> The one-pager. ~30 minutes to write, then never edit again. This is the "are we still building the same thing" anchor.

## Pitch sentence

_One sentence. What we're building, for whom, and why it matters._

Other teams built search over 10K hospitals. We built an audit system. Our agent reads every facility note, extracts claimed capabilities, cross-checks them against staff and equipment lists, and flags contradictions with cited evidence. The output isn't a list — it's a map of where India's healthcare system is lying to itself, and where NGOs should fund next.

## Primary user

_Not the patient. The decision-maker._

- Role: NGO planner allocating large grants for rural healthcare equipment in India.
- Context they operate in: Sarah works at an NGO allocating $2M for rural healthcare equipment in Bihar. She has 3 weeks to recommend 5 facilities to fund. Today she does this with phone calls and Excel — facility self-reports are unreliable, and she has no way to verify claims at scale.
- Decision they need to make: Which facilities to fund, given that facility self-reports cannot be trusted at face value and there is no ground truth to check them against.

## The three surfaces

1. **Desert Map** — choropleth of India by PIN code, colored by capability gap for a chosen specialty (oncology, dialysis, trauma, neonatal); sliders for population coverage radius (30km / 60km / 120km); click region → list of facilities ranked by Trust Score with the gap quantified ("47K people, nearest verified dialysis: 94km"), backed by `PopulationReference` and `MapRegionAggregate`. The hook / demo screenshot.
2. **Facility Audit View** — pick any facility; split pane: left = claimed capabilities as a checklist; right = evidence trail per claim, with the actual sentence highlighted and `EvidenceAssessment.stance` tagged `verifies`, `contradicts`, or `silent`. MLflow 3 traces become user-facing.
3. **Planner Query Console** — natural language queries return ranked recommendations with structured rationale (NOT chat bubbles). Columns: facility, distance, trust score, contradictions flagged, evidence count. Export to CSV.

## Eval criteria → what we deliver

| Judging criterion | How this project addresses it |
|---|---|
| 35% Verification | Validator agent runs on every extraction; Trust Score is a structured object (score, claimed capability, evidence, contradictions, confidence interval, reasoning); contradiction taxonomy enum surfaces failure modes explicitly. |
| 30% Messy parsing | Extractor agent operates over 10K facility notes; aggregate claims expose confidence intervals via `MapRegionAggregate.capability_count_ci` (e.g., "Bihar has between 12 and 19 functional ICUs (95% CI)") rather than false precision. |
| 25% Utility / actionable insights for NGO planners | Three surfaces tuned for grant allocation — Desert Map (where to fund), Facility Audit (whom to trust), Planner Console (ranked recommendations with CSV export). |
| 10% UX | Choropleth + split-pane audit + spreadsheet-style rankings; reasoning is the product, not a hidden backend. No chat UI. |

## Explicitly out of scope

- Authentication, multi-user accounts, saved searches, dark mode.
- Mobile / responsive view.
- Patient-facing search ("hospital near me").
- ICU bed availability prediction (no time-series data in the corpus).
- Custom illustrations or design system polish.
- Chat UI / conversational interface.

## Demo target

_The single moment that has to land._

The appendectomy query — "Which facilities within 50km of Patna can perform an appendectomy?" — runs live, returns a ranked list with Trust Scores, then drilling into the top result reveals the evidence trail and a flagged contradiction. End-to-end traced.
