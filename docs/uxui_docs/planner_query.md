# Planner Query Console

Planner Query Console is the agent surface: natural language in, structured ranked facility results out. It must never become chat. Its job is to prove the Query Agent can parse intent, retrieve candidates, rank by trust, expose rationale, export planner-grade results, and route to Facility Audit View.

Shared rules live in `docs/uxui_docs/00_frontend_guidelines.md`; route behavior lives in `docs/uxui_docs/01_sitemap.md`.

## Purpose

Enable one task: answer a planner's facility-funding question with a ranked, exportable, auditable result table.

Locked demo query:

`Which facilities within 50km of Patna can perform an appendectomy?`

Hard rule: no chat bubbles, no conversation history, no prose-only answer.

## Layout

Top query area:

- Visible input label.
- Single natural-language input.
- Submit button.
- Example query chips, including the locked appendectomy query.
- Running state that preserves input width and disables duplicate submits.

Main result area:

- Spreadsheet-style ranked table.
- Sticky header.
- Sortable columns where sorting is meaningful.
- Row click opens Facility Audit View.

Right sidebar:

- Parsed intent panel.
- Query trace disclosure.
- Export status.

Footer or drawer:

- Query trace panel, collapsed by default.

## Parsed intent panel

Display `QueryResult.parsed_intent` as structured fields:

- Capability: `ParsedIntent.capability_type`
- Location: `ParsedIntent.location`
- Radius: `ParsedIntent.radius_km`
- Raw query: `QueryResult.query`
- Generated at: `QueryResult.generated_at`
- Candidates considered: `QueryResult.total_candidates`

Ambiguous parsing:

- If capability, location, or radius is missing, show the missing field and ask for a more specific query.
- Do not silently guess a location or capability for the user.
- Example chips may guide correction, but they are not chat replies.

## Results table

Default sort:

- `RankedFacility.rank` ascending.

Columns:

- Rank
- Facility name
- Distance km
- Trust Score badge
- Confidence interval
- Contradictions flagged
- Evidence count
- PIN/location
- Audit action

Row behavior:

- Click opens `/facilities/:facility_id?capability=<parsed capability>&from=planner-query`.
- Facility Audit View should open with the relevant capability expanded and contradictions visible.
- Keyboard row focus and Enter activation must work.

Expandable row rationale:

- Optional, compact, and structured.
- Shows `TrustScore.reasoning`, contradiction summary, and evidence count.
- Does not duplicate the full Facility Audit evidence trail.

## Export behavior

Export action:

- Label: "Export CSV"
- Exports the current ranked result set.
- Disabled until a complete or partial structured `QueryResult` exists.

CSV should include:

- query
- query_trace_id
- generated_at
- parsed capability
- parsed latitude
- parsed longitude
- parsed PIN code if available
- radius_km
- rank
- facility_id
- facility name
- distance_km
- trust_score
- confidence_interval_low
- confidence_interval_high
- contradictions_flagged
- evidence_count
- facility latitude
- facility longitude
- facility PIN code if available
- audit URL

Do not implement saved queries. Saved searches are out of scope.

## Query trace

Trace panel requirements:

- Uses `QueryResult.query_trace_id`.
- Default collapsed.
- Shows geocode, search, audit fetch, ranking, and output construction steps when available.
- Does not expose raw chain-of-thought.
- If unavailable, show "Query trace unavailable" without blocking results.

## Data dependencies

Planner output:

- `QueryResult.query`
- `QueryResult.parsed_intent`
- `QueryResult.ranked_facilities`
- `QueryResult.total_candidates`
- `QueryResult.query_trace_id`
- `QueryResult.generated_at`

Parsed intent:

- `ParsedIntent.capability_type`
- `ParsedIntent.location`
- `ParsedIntent.radius_km`

Ranked rows:

- `RankedFacility.facility_id`
- `RankedFacility.name`
- `RankedFacility.location`
- `RankedFacility.distance_km`
- `RankedFacility.trust_score`
- `RankedFacility.contradictions_flagged`
- `RankedFacility.evidence_count`
- `RankedFacility.rank`

Click-through:

- `FacilityAudit.facility_id`
- `FacilityAudit.trust_scores`
- `FacilityAudit.total_contradictions`
- `FacilityAudit.mlflow_trace_id`

## States

Idle:

- Input is empty or prefilled.
- Example query chips are visible.
- No result table yet.

Parsing:

- Submit button disabled.
- Parsed intent panel shows "Parsing query."

Geocoding:

- Location field shows loading state.
- Results table remains empty.

Ranking/loading rows:

- Table skeleton appears with stable column widths.
- Parsed intent remains visible once available.

Partial structured results:

- Render rows already returned.
- Mark totals as incomplete.
- Export is allowed only if rows have required CSV fields; otherwise disabled with reason.

Complete:

- Table, parsed intent, trace id, and export are available.

No results:

- Show the parsed intent and "No matching facilities found within this radius."
- Offer radius/capability correction through input or chips, not chat.

Ambiguous query:

- Show which field is missing or ambiguous.
- Keep focus on the input.

Agent failed:

- Show failure state with retry.
- Show `query_trace_id` if one exists.
- Do not clear the user's query.

Export failed:

- Keep results visible and show retry for export only.

Trace unavailable:

- Keep results visible and mark trace as unavailable.

## Acceptance criteria

- Locked appendectomy query returns a structured table, not prose.
- Parsed intent visibly shows appendectomy capability, Patna location, and 50km radius.
- Result row opens Facility Audit View with selected capability preserved.
- CSV export includes query metadata, IDs, trust score, confidence interval, contradictions, evidence count, and audit URL.
- There is no save-query feature, no chat UI, and no conversation history.
