# AXON Health Intelligence — Design System

**Aesthetic:** Soft clinical glass command center — calm map intelligence with computational depth
**Status:** v1 for hackathon build

---

## 0. Design Principles

- **Clinical, not corporate.** Calm, precise, considered. No mascots or playfulness.
- **Evidence is the interface.** Trust scores, contradictions, and citations are first-class — never decoration.
- **Glass conveys depth, not decoration.** Use translucency to layer density on computed surfaces only.
- **Command-center, not cockpit cosplay.** Spatial and agent-controllable, but sober.
- **Restraint is credibility.** When in doubt, remove.
- **Show the seams.** Loading, partial results, and uncertainty are features.

---

## 1. Foundation Tokens

### 1.1 Color

**Surface (light, glass-friendly)**
- `surface/canvas` — `#F6FAFB` — page background
- `surface/canvas-tint` — `#EEF7F7` — map/control wash
- `surface/raised` — `rgba(255,255,255,0.92)` — solid-glass cards
- `surface/glass` — `rgba(255,255,255,0.58)` + blur — overlays, computed cards
- `surface/glass-strong` — `rgba(255,255,255,0.76)` — modals, focused glass
- `surface/glass-faint` — `rgba(255,255,255,0.38)` — ambient overlays over map
- `surface/sunken` — `rgba(235,242,244,0.72)` — input backgrounds

**Content**
- `content/primary` `#142126` · `content/secondary` `#52636B` · `content/tertiary` `#91A0A7` · `content/inverse` `#FFFFFF`

**Border**
- `border/subtle` `rgba(20,33,38,0.07)` · `border/default` `rgba(20,33,38,0.13)` · `border/strong` `rgba(20,33,38,0.26)` · `border/glass-highlight` `rgba(255,255,255,0.72)`

**Accent — softened teal, used sparingly**
- `accent/primary` `#176D6A` · `accent/primary-hover` `#105B58` · `accent/primary-soft` `#A9DBD7` · `accent/primary-subtle` `rgba(23,109,106,0.10)` · `accent/aura` `rgba(118,195,190,0.24)`

**Semantic — four-state trust system**
- `semantic/verified` `#0F7A4F` (+subtle `rgba(15,122,79,0.10)`)
- `semantic/flagged` `#9A6A25` (+subtle `rgba(154,106,37,0.12)`)
- `semantic/critical` `#A4473E` (+subtle `rgba(164,71,62,0.12)`)
- `semantic/insufficient` `#687782` (+subtle `rgba(104,119,130,0.12)`) — *the trust signal: "we couldn't tell"*

### 1.2 Typography

- `font/sans` — Inter — UI, body, headings
- `font/mono` — JetBrains Mono — IDs, citations, agent traces (signals "extracted data, not editorial")

| Token | Size / LH / Weight | Usage |
|---|---|---|
| `text/display` | 36 / 1.15 / 600 | Workspace headers, hero metrics |
| `text/heading-l` | 24 / 1.25 / 600 | Page titles |
| `text/heading-m` | 18 / 1.35 / 600 | Card titles |
| `text/heading-s` | 14 / 1.4 / 600 | Subsection labels |
| `text/body` | 14 / 1.5 / 400 | Default body |
| `text/body-l` | 16 / 1.55 / 400 | Evidence excerpts |
| `text/caption` | 12 / 1.4 / 500 | Metadata, badges |
| `text/mono` | 13 / 1.5 / 400 | Citations, IDs |
| `text/mono-s` | 11 / 1.4 / 500 | Inline tags |

### 1.3 Spacing — 8px base, 4px half-step

`0/0.5/1/1.5/2/3/4/5/6/8/10` → `0/4/8/12/16/24/32/40/48/64/80px`. Card padding `space/3`. Section gaps `space/5`. Page margins `space/6` desktop.

### 1.4 Radius

`sm` 6 · `md` 10 (default) · `lg` 14 (modals, glass) · `xl` 20 (feature cards) · `full` 9999 (avatars, pills only)

### 1.5 Elevation & glass

**Shadows**
- `elevation/1` — `0 1px 2px rgba(11,18,32,.04), 0 1px 3px rgba(11,18,32,.06)` — default
- `elevation/2` — raised/hover · `elevation/3` — popovers · `elevation/4` — modals
- `elevation/glass-map` — `0 18px 50px rgba(23,109,106,.12), 0 2px 10px rgba(20,33,38,.08)` — control panels over map

**Glass recipes**
- `glass/standard` — `surface/glass` + `blur(18px) saturate(1.35)` + subtle border + `elevation/1`
- `glass/elevated` — `surface/glass-strong` + `blur(28px) saturate(1.45)` + default border + `elevation/4`
- `glass/control` — vertical white gradient + `blur(24px) saturate(1.5)` + `elevation/glass-map`

**Use glass for:** nav rail, dashboard control panels, agent-generated content, modals, drilldown panels.
**Don't use glass for:** form inputs, dense tables, anywhere readability is at risk.

### 1.6 Motion

- `instant` 0ms · `fast` 120ms ease-out · `standard` 200ms ease-out · `considered` 320ms cubic-bezier
- `agent` 600–1200ms ease-in-out — agent reasoning streaming/pulse
- `nav-spring` — Framer `{ type:"spring", bounce:0.2, duration:0.45 }` — nav pill, org switcher

Reduced-motion users get `instant` everywhere except agent indicators (subtle opacity pulse).

---

## 2. Component Conventions

### 2.1 Buttons — three variants
- **Primary** — solid `accent/primary`, max 1–2 per view
- **Secondary** — `surface/raised` + `border/default` (workhorse)
- **Ghost** — transparent, accent text (tertiary actions)

Sizes: `sm` 32 · `md` 40 (default) · `lg` 48. No icon-only except in toolbars.

### 2.2 Cards
- **Default** — `surface/raised` + `border/subtle` + `radius/md` + `elevation/1`
- **Glass** — `glass/standard` for agent output and computed surfaces
- **Action** — Default + hover lifts to `elevation/2` (Action Trio)
- **Stat** — minimal padding, large numeric + secondary label (Coverage Snapshot)

### 2.3 Inputs
- **Default** — `surface/sunken` + `border/subtle`; focus → `surface/raised` + `border/strong` + `2px ring accent/primary-subtle`
- **Search** — Default + leading icon, optional clear, optional dropdown
- **Ghost** — transparent, inline in tables

No floating labels. Focus ring always visible.

### 2.4 Badges & Tags
Verified · Flagged · Critical · Insufficient · Subtle — each uses its `semantic/*-subtle` background + `semantic/*` text + `radius/sm`. **Always include an icon** — color is never the sole signal.

### 2.5 Lists & tables
Dense by default. Row height 44px. No zebra striping — use `border/subtle` dividers. Sticky headers >10 rows. Row hover: `surface/sunken`.

### 2.6 Navigation — left vertical rail

**Expanded** `w-64` · **Collapsed** `w-16`. Background `bg-white`, `border-zinc-200`, `shadow-sm`, `radius/lg`. `transition-all duration-300`.

**Glass-like elevation:** thin pane comes from solid white + shadow + edge — *not* heavy blur on the rail itself.

**Nav item:** 44px min height, 20px icon, `text/body` label, hover `bg-zinc-100/80`, active = rounded pill behind icon+label.

**Animated active state:** Framer Motion shared layout — `layoutId="activeTab"`, `{ type:"spring", bounce:0.2 }`, pill at `-z-10`. Pill slides between items, never fades or jumps.

**Org switcher** (top of rail): scale `0.95 → 1` on enter, `{ opacity:0, y:10 }` on exit, wrapped in `AnimatePresence`.

Reduced motion: disable sliding/scale; switch active state instantly.

### 2.7 Command Control Panel

Home dashboard = map-first command panel. Planner operates a live intelligence surface, not a report.

- **`Panel/ControlGlass`** — `glass/control`, `radius/xl`, `space/2–3` padding, floats over map.
- **Command input** — typed planner commands in v1 (voice attaches later). Concrete placeholder: *"Focus Patna, appendectomy, 50 km"*. **Never render output as chat bubbles** — commands mutate map state, filters, selection, or route.
- **Command glow** — `accent/aura` soft radial behind input on focus or while executing. No pulsing neon.
- **Status affordance** — compact: "Agent ready", "Focusing Patna", "Selecting facilities". Every result reflects in UI state.

### 2.8 Map Canvas

The map is a primary workspace, not a card.
- Largest visual area on Dashboard and Desert Map.
- Glass panels float above; never nested in a map card.
- Soft, low-saturation choropleth ramps with clear labels.
- Subtle halos for facilities/regions, not saturated pins.
- For readability over the map: increase panel opacity before increasing text weight.

---

## 3. Domain-Specific Patterns

### 3.1 Trust Score — visual signature of the product
- Numeric 0–100 in `text/display` 600
- CI directly beneath in `text/caption` mono — e.g., `±7 (CI 95%)`
- Status badge (Verified / Flagged / Critical / Insufficient)
- Hover/expand: claimed match, evidence strength, contradiction penalty, staffing/equipment alignment

**Score → semantic:** 80–100 verified · 50–79 flagged · 0–49 critical · *insufficient evidence overrides everything: `semantic/insufficient` + score shown as `—`*. A facility with no extractable data must never get a misleading number.

### 3.2 Evidence Trail — cited-sentence pattern
- Source label (doc, page) in `text/mono-s`
- Quoted sentence in `text/body-l` with 3px `accent/primary` left border + `accent/primary-subtle` background
- Inline verdict tag: `Verifies` / `Contradicts` / `Silent`
- Optional confidence indicator on right edge

Stack vertically with `space/1`. **Never inside other glass surfaces** (glass-on-glass is muddy).

### 3.3 Contradiction Indicator
Severity icon (filled triangle = critical, outlined = moderate) · one-line claim · one-line counter-evidence · taxonomy tag (e.g., "Staffing mismatch"). Lists sorted by severity, never recency.

### 3.4 Agent Reasoning Trace
Inspectable record of retrieval, extraction, validation, scoring, ranking — *not* raw chain-of-thought. Collapsed by default. Expanded: `font/mono` steps, each in `glass/standard` card. Step icons by type. Cost/latency per step in `text/caption` mono. This is where MLflow trace data becomes user-facing — promote it.

### 3.5 Confidence intervals & uncertainty
Show CI wherever a number derives from incomplete data. Format: `87 ±5` or `87 (95% CI: 82–92)`. CI text in `content/secondary` mono. Aggregates use range form: `12–17 (95% CI)`.

### 3.6 Empty, loading, error states
- **Loading** — `surface/sunken` skeletons, 1.6s linear shimmer. Glass cards stay glass during load.
- **Empty** — single line `content/secondary`, optional `content/tertiary` icon. Never illustrated mascots.
- **Error** — inline (not page-level), `semantic/critical-subtle` background, retry as `Button/Ghost`.
- **Insufficient data** — distinct from empty. "Extracted this facility but found no evidence for [capability]." Uses `semantic/insufficient`.

---

## 4. Layout & Density

- **Page max-width:** none for map/control routes; 1440px centered for reading-heavy secondary pages
- **Reading max-width:** 720px (rare in this app)
- **Gutter:** 48px desktop · 24px tablet
- **Grid:** 12-column, 24px gutters; 8/12 spans most layouts

High density by default — planners scan, not browse. Dashboard trades static whitespace for layered map space.

---

## 5. Iconography

Single library: Lucide *or* Phosphor. Outlined default; filled = active/selected only. Sizes: 16 inline · 20 default · 24 nav/prominent · 32 feature only.

Hackathon vocabulary: map pin · stethoscope/activity · search/filter · check · alert · question · clock · document · chevron · user. **No emoji in product UI.**

---

## 6. Accessibility — hard requirements

- WCAG AA contrast against actual background (test glass against the *blurred resolved color*)
- Color never the sole carrier of state — always paired with icon/label
- Focus rings always visible (no `outline:none` without replacement)
- Keyboard navigable in document order
- Reduced-motion respected
- ARIA live regions for streaming agent output and banners
- Min tap target 44×44
- When in doubt on glass, increase opacity until text passes AA

---

## 7. Voice & Microcopy

The product speaks like a senior analyst, not a marketer.

**Do:** *"94 facilities verified · 12 flagged for review"* · *"Insufficient evidence to confirm ICU capability"* · *"Last extraction: 14:32 UTC, 3 hours ago"* · *"This facility claims surgical capacity but no anesthesiologist appears in staffing notes"*

**Don't:** *"We've got 94 facilities all checked!"* · *"Oops, something went wrong"* · *"Awesome — query complete!"* · *"Sorry, we couldn't find what you're looking for"*

Numbers always have units. Times always have time zones. Claims always have evidence. Uncertainty is named.

Errors are direct: *"Couldn't reach extraction service. Retry?"*

---

## 8. Explicitly not doing (v1)

Dark mode · brand illustrations · custom charting design (use Recharts/D3 + token palette) · onboarding tours · themeable customer branding · marketing surfaces.

---

## 9. Implementation notes

Tailwind + shadcn. Color tokens → CSS custom properties on `:root`, consumed via `theme.extend.colors`. Glass recipes → utility classes (`glass-standard`, `glass-elevated`, `glass-control`). Typography → Tailwind utilities aliased to token names. Motion → CSS variables for duration/easing.

Use shadcn primitives (Card, Button, Input, Dialog) re-skinned via tokens — don't rebuild. **Build velocity > customization.**

---

## 10. Open questions for v2

- Adaptive glass intensity over busy backgrounds?
- Second accent color for Earn Layer surfaces, or stay single-accent?
- CI visualization in charts — error bars, shaded bands, both?
- Mobile breakpoint — adapt or punt to web-only?

---

This system should feel like *credible health intelligence software in 2026* — calm, data-dense, transparent about uncertainty, distinct from both legacy clinical software and generic AI products. Glass and restraint do the heavy lifting; everything else gets out of the way.
