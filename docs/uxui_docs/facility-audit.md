# Facility Audit View

Facility Audit View is the proof surface. It shows whether one facility's claimed capabilities can be trusted by connecting claims to evidence, contradictions, Trust Score reasoning, and the MLflow trace.

Shared rules live in `docs/uxui_docs/00_frontend_guidelines.md`; route behavior lives in `docs/uxui_docs/01_sitemap.md`.

## What this surface proves

The facility is not merely listed; it has been audited. Sarah can decide whether to fund, reject, or flag the facility for human review based on cited evidence.

Primary decision:

- Can this facility be trusted for the selected capability?

Secondary decisions:

- Which claim is unsupported or contradicted?
- Is the contradiction severe enough to change a funding recommendation?
- Can the agent trace be inspected if challenged?

## Entry points

Planner Query Console:

- Opens `/facilities/:facility_id?capability=<parsed capability>&from=planner-query`.
- The relevant capability row is selected by default.

Desert Map:

- Opens `/facilities/:facility_id?capability=<selected capability>&from=desert-map`.
- Back action returns to the selected region and map filters.

Direct URL:

- Opens the facility with the first HIGH contradiction selected if present.
- Otherwise selects the highest-priority claimed capability.

## Layout

Header:

- Facility name.
- PIN/location.
- Last audited timestamp.
- Overall contradiction count.
- "View trace" action for `FacilityAudit.mlflow_trace_id`.
- Back link that preserves source context.

Left pane: claimed capabilities checklist.

- One row per `Capability`.
- Capability name.
- Claimed state.
- Trust Score badge.
- Confidence interval.
- Evidence count.
- Contradiction count by severity.
- Selected row state.

Right pane: evidence and reasoning for the selected capability.

- Trust Score summary.
- Contradiction banners, sorted HIGH, MEDIUM, LOW.
- Evidence cards grouped by stance: verifies, contradicts, silent.
- Source metadata and highlighted snippets.
- Reasoning drawer for `TrustScore.reasoning`.

Footer or drawer:

- MLflow trace panel, collapsed by default.
- Extraction -> validation -> scoring span summary.
- Trace id shown as copyable text.

## Claim row anatomy

Each claim row should display:

- `Capability.capability_type`
- `Capability.claimed`
- `TrustScore.score`
- `TrustScore.confidence_interval`
- Count of `TrustScore.evidence`
- Count of `TrustScore.contradictions`
- Highest contradiction severity

Trust Score bands:

- Green: `80-100`
- Amber: `50-79`
- Red: `0-49`

Color must be paired with visible text. Do not show a bare number without band, CI, and evidence/contradiction context nearby.

## Evidence card anatomy

Each evidence card should display:

- `EvidenceAssessment.stance`: verifies, contradicts, or silent
- `EvidenceRef.snippet`, highlighted
- `EvidenceRef.source_type`
- `EvidenceRef.source_doc_id`
- `EvidenceRef.span`
- `EvidenceRef.source_observed_at` when available
- `EvidenceRef.retrieved_at`
- `EvidenceAssessment.rationale`

Label `silent` as "No confirming evidence found" or "Silent" with neutral styling. Silent does not mean safe.

If `EvidenceAssessment` is not embedded directly in the facility detail payload, the UI detail endpoint must join validator assessments to evidence refs by facility, capability, and source reference. Do not infer stance from score color.

## Contradiction banner anatomy

Each contradiction banner should display:

- `Contradiction.severity`
- `Contradiction.contradiction_type`
- `Contradiction.reasoning`
- Evidence for the original claim
- Evidence against the claim
- `Contradiction.detected_by`
- `Contradiction.detected_at`

HIGH contradictions should be pinned above evidence cards. LOW and MEDIUM contradictions remain visible but should not overwhelm evidence scanning.

## Trust Score rules

The UI must treat `TrustScore` as a structured object, not a scalar.

Required fields:

- `TrustScore.score`
- `TrustScore.confidence`
- `TrustScore.confidence_interval`
- `TrustScore.evidence`
- `TrustScore.contradictions`
- `TrustScore.reasoning`
- `TrustScore.computed_at`

Display the deterministic score logic in compact help text or the reasoning drawer:

`score = max(0, min(100, round(confidence * 100) - severity_penalty_sum))`

Severity penalties:

- LOW: `5`
- MEDIUM: `15`
- HIGH: `30`

## MLflow trace panel

Trace panel requirements:

- Uses `FacilityAudit.mlflow_trace_id`.
- Default collapsed.
- Shows span groups for extraction, validation, trust scoring, and FacilityAudit build.
- Shows agent/model names when available.
- Does not expose raw chain-of-thought.
- If unavailable, show "Trace unavailable for this audit" and keep evidence visible.

## Data dependencies

Canonical facility record:

- `FacilityAudit.facility_id`
- `FacilityAudit.name`
- `FacilityAudit.location`
- `FacilityAudit.capabilities`
- `FacilityAudit.trust_scores`
- `FacilityAudit.total_contradictions`
- `FacilityAudit.last_audited_at`
- `FacilityAudit.mlflow_trace_id`

Supporting schemas:

- `Capability`
- `TrustScore`
- `EvidenceRef`
- `EvidenceAssessment`
- `Contradiction`
- `ContradictionType`

## States

Loading:

- Header and split-pane skeletons preserve layout.

Facility not found:

- Show "Facility audit unavailable" and a back action.

No selected capability:

- Select the first HIGH contradiction, then the first claimed capability, then the first capability row.

No evidence:

- Show "No evidence refs were produced for this claim" and keep Trust Score reasoning visible if available.

No contradictions:

- Show a neutral "No contradictions found" state, not a celebratory success state.

Trace unavailable:

- Keep audit content visible and mark trace as unavailable.

Partial audit:

- Mark missing capability, evidence, or trace sections explicitly.

Failed validation:

- Show the facility record if available, but mark contradiction and score sections as incomplete.

## Demo moment

Appendectomy flow:

1. Planner Query Console ranks facilities within 50km of Patna.
2. User opens the top result.
3. Facility Audit selects `SURGERY_APPENDECTOMY`.
4. Right pane shows verifying evidence cards and one `MISSING_STAFF` contradiction.
5. Trust Score explains why a facility can rank with a score such as `72` despite evidence.
6. Trace panel shows extraction, validation, and scoring spans.

## Non-goals

- Chat UI
- Patient-facing hospital profile
- Saved notes or saved searches
- Manual adjudication workflow
- Mobile layout
- Dark mode
- Custom design-system polish
