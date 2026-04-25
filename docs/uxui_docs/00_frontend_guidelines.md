# Frontend Guidelines

This is the UI/UX source of truth for the SeaHealth front end. It translates `docs/VISION.md`, `docs/UX_FLOWS.md`, `docs/DATA_CONTRACT.md`, `docs/AGENT_ARCHITECTURE.md`, and `docs/DECISIONS.md` into implementation guidance.

## Product posture

SeaHealth is a healthcare audit workbench for NGO planners allocating rural healthcare grants in India. The interface should feel like a serious planning and verification control panel: map-first, softly glassed, calm, evidence-forward, and optimized for scanning.

The product is not a patient search app, not a hospital marketplace, and not a chat product. Recommendations must be ranked, cited, and inspectable. The reasoning trail is the product.

## Scope constraints

Ship only the route set required for the demo:

- Dashboard / home
- Desert Map
- Planner Query Console
- Facility Audit View

Out of scope for this build:

- Authentication, account settings, teams, permissions
- Mobile-first responsive work
- Dark mode
- Saved searches
- Patient-facing facility search
- Chat bubbles or conversation history
- Custom illustration, branding polish, or a bespoke component library

Use Tailwind defaults plus shadcn-style components. Do not spend effort on a custom design system beyond the shared rules below.

## Navigation model

Use a persistent desktop app shell:

- Left nav rail: product name, Dashboard, Planner Query, Desert Map, run/demo status.
- Primary route content: one surface at a time.
- Trace drawer: contextual overlay inside Planner Query Console or Facility Audit View, not a separate page.
- Back behavior: preserve the source context when moving from map or query results into a facility audit.

The UI should make the canonical object model obvious:

- Desert Map aggregates `FacilityAudit` records through `MapRegionAggregate`.
- Planner Query Console ranks facilities through `QueryResult`.
- Facility Audit View drills into one `FacilityAudit`.

## Visual system

Default to a data-dense dashboard style:

- Soft near-white page background, glass surfaces, restrained borders, and low shadows.
- Tight but readable spacing; avoid oversized hero sections.
- Tables, maps, split panes, and side rails are the core layouts.
- Primary navigation is a vertical left rail, not a top bar.
- The Dashboard should present the India choropleth directly as the main canvas.
- Glass control panels may float over maps; do not wrap the map itself in a decorative card.
- Use Lucide icons for buttons and utility actions when icons are needed.
- Do not use emoji as status icons.
- Use cards only for repeated items, evidence snippets, contradiction banners, and modal/drawer content. Do not nest cards inside cards.

Semantic color rules:

- Trust Score green: `80-100`
- Trust Score amber: `50-79`
- Trust Score red: `0-49`
- Contradictions: red, with severity label visible.
- Silent or insufficient evidence: neutral gray.
- Verified evidence: green.
- Selected region/query context: blue/cyan accent.

Color must carry meaning, but labels must carry the decision. Never rely on color alone.

## Component standards

Trust Score badge:

- Always show numeric score and band.
- Expose confidence interval nearby when space allows.
- Click or expand opens the `TrustScore.reasoning`, evidence count, and contradiction count.

Evidence chip/card:

- Shows `EvidenceRef.source_type`, short source label, and highlighted `EvidenceRef.snippet`.
- Shows `EvidenceAssessment.stance` as verifies, contradicts, or silent.
- Preserves enough context for the planner to judge the claim without opening a raw document.

Contradiction banner:

- Shows `Contradiction.severity`, `Contradiction.contradiction_type`, and one-sentence `Contradiction.reasoning`.
- Links or anchors to the evidence for and evidence against when available.

Trace affordance:

- Label as "View trace" or "Trace".
- Default collapsed.
- Shows the relevant MLflow trace id from `FacilityAudit.mlflow_trace_id` or `QueryResult.query_trace_id`.
- If a trace is unavailable, show a neutral unavailable state, not an error-looking failure.

Tables:

- Use sticky headers for long result lists.
- Default sorting must match the domain logic: rank or highest Trust Score first, tie-broken by distance where relevant.
- Row click opens Facility Audit View.
- Include visible row focus and hover states.

Forms:

- Inputs require visible labels.
- The Planner Query input must submit on Enter and with a button.
- Async buttons disable while running and keep their width stable.

Left navigation rail:

- Default to an expanded `w-64` rail on desktop.
- Support a collapsed `w-16` state if implementation time allows.
- Use `bg-white`, `shadow-sm`, and `border-zinc-200` for glass-like elevation.
- Inactive items use `hover:bg-zinc-100/80`.
- Active item uses a rounded pill behind icon and label.
- If using Framer Motion, animate the active pill with `layoutId="activeTab"` and a spring transition with `bounce: 0.2`.
- Width changes use `transition-all duration-300`.
- Respect reduced-motion by disabling sliding/scale animation.

Agent/voice command control:

- Treat typed commands, voice transcripts, and agent actions as the same `MapCommand` pipeline.
- Commands mutate UI state: map camera, selected region, capability filter, radius, highlighted facilities, or opened audit.
- Do not render command control as chat bubbles.
- Show compact execution status such as "Focusing Patna" or "Filtering appendectomy".
- Keep a visible manual equivalent for every command-controlled action.

## Content rules

Use planner-facing language, not backend jargon, unless the exact field name matters to implementation.

Good labels:

- "Trust Score"
- "Contradictions"
- "Evidence"
- "Within 50 km of Patna"
- "No verified appendectomy facilities found"

Avoid vague labels:

- "AI result"
- "Maybe"
- "Hospital quality"
- "Chain of thought"
- "Chat"

Reasoning copy should be concise and evidence-based. Do not imply ground truth when the data only supports a confidence interval or contradiction flag.

## States every surface should specify

Every surface doc must define:

- Ready / loaded
- Loading
- Empty
- No results
- Partial or low-confidence data
- Error / failed agent call
- Missing trace
- Export unavailable, if the surface has export

Errors should state what failed, what data remains usable, and what the user can do next.

## Accessibility baseline

The hackathon build is desktop-only, but it still needs basic accessibility:

- 4.5:1 text contrast for normal text.
- Visible focus rings on all interactive elements.
- Keyboard-accessible tabs, tables, filters, and drawers.
- Minimum 44px hit target for icon buttons.
- Labels for all inputs and icon-only buttons.
- Respect `prefers-reduced-motion`.
- Do not place critical information only inside hover tooltips.

## Data-contract discipline

Do not invent display fields that drift from `docs/DATA_CONTRACT.md`.

All surface docs must name the canonical schema they read from:

- `FacilityAudit`
- `Capability`
- `TrustScore`
- `EvidenceRef`
- `EvidenceAssessment`
- `Contradiction`
- `QueryResult`
- `RankedFacility`
- `ParsedIntent`
- `MapRegionAggregate`
- `PopulationReference`

If the UI needs a field that is not in the contract, document it as a derived display value and define the derivation.
