# HelpDesk — Full Review: Premium Motion Design, Floating UI & Animated Data Visualization

**Review date:** 2026-11-21 (QA pass: same day, later)
**Repository:** `mdjayedgazi/HelpDesk`
**Base branch:** `main` @ `4ea4a2e` (PR #19 and PR #22 both merged)
**Working branch:** `feat/helpdesk-motion-visual-polish`
**Verdict:** Implemented, QA-corrected and verified. One structural limitation
remains and is stated plainly in Part L: there is no authorised Clerk test
account, so authenticated screens were verified through tests, a rendered
fixture and source review rather than a live login.

> **Delivery note.** This document was originally written into `data.md`. The
> QA pass restored `data.md` to the PR #19 production-readiness review it
> belonged to and moved this review here, unchanged in substance. See Part N for
> the QA corrections (trend labels, bar proportions, progress normalization,
> mobile scroll verification).

This file is the complete review — the investigation, every decision, exactly
what changed, and the evidence. The engineering companions are
[`docs/motion-design-audit.md`](docs/motion-design-audit.md) and
[`docs/motion-design-implementation-report.md`](docs/motion-design-implementation-report.md).

---

## Part A — Repository state at the start

| Item | Finding |
| --- | --- |
| Branch | `main` |
| Working tree | `data.md` modified (emptied to 0 bytes). Preserved as found until this review was written. |
| Recent commits | `4ea4a2e` (merge of PR #22), `eeb9a41`, `8b3b508`, `ea073eb`, `cc30e4f`, `cd734e2` |
| PR #19 (`fix/production-readiness`) | **MERGED** 2026-11-21T10:45:49Z. Not touched. |
| PR #22 (`feat/helpdesk-ui-ux-modernization`) | **MERGED** 2026-11-21T14:02:06Z. Its work is already on `main`. |
| Open PRs | None. |
| Local feature branches | `feat/helpdesk-ui-ux-modernization` exists but is fully merged. Not reused. |
| Correct base | `main`. No stacked PR needed — the prior modernization already landed. |
| New branch | `feat/helpdesk-motion-visual-polish` |

The production site `https://helpdesk-web-production-d96f8e2b.up.railway.app`
responded **200** in ~0.66 s and serves the same bundle shape as `main`.

---

## Part B — What the frontend actually was

Verified from source, not assumed:

| Concern | Implementation |
| --- | --- |
| Framework | React 19.3.1 |
| Build | Vite Plus 1.2.0 (`@voidzero-dev/vite-plus-core`), TypeScript ~6.0.2 |
| Routing | react-router-dom 7.18.4, `BrowserRouter`, route-level `React.lazy` |
| UI system | Chakra UI 3.37.0 (`createSystem`) + Tailwind utilities only (no preflight) |
| Data | TanStack Query 5.104.3, central `queryKeys`, 15 s stale time, `keepPreviousData` on ticket lists |
| Auth | Clerk 6.17.8; the backend is the authorization source of truth |
| Icons | lucide-react 1.58.0 |
| Charts | Hand-written SVG/div charts. **No chart library.** |
| Animation | Hand-written CSS keyframes in `tokens.css` + one `Reveal` (IntersectionObserver). **No animation library.** |
| Tests | Vitest via `vp test` (jsdom): 13 files, 78 tests, all green pre-change |
| Lint/types | `vp lint` (oxlint, type-aware), `tsc --noEmit` — both clean pre-change |

### Typography (preserved exactly)

`src/theme/system.ts` and `src/pages/auth/clerkAppearance.ts` both use:

```
Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif
```

No `@font-face`, no Google Fonts link, no font asset. The identity is "Inter if
installed, system UI otherwise". **No font was introduced or changed.**

### Design tokens (already strong)

`tokens.css` already carried light/dark surfaces, text tones, ink, borders,
focus, overlays, five shadow steps, four semantic families
(info/success/warning/danger), a five-entry chart palette, a motion block
(`--hd-ease`, `--hd-ease-out`, `--hd-dur-1..3`), and layout widths.

Gaps identified:

- **No accent token.** Selection was expressed with ink.
- Motion durations stopped at 320 ms — too short for entrance choreography.
- `hd-float`, `hd-pulse`, `hd-shimmer`, `hd-drift` were **defined and never
  used**.
- `prefers-reduced-motion` was already handled twice (global Chakra rule +
  `tokens.css`), which is the right pattern to extend.

### Motion inventory before

| Pattern | Where | State |
| --- | --- | --- |
| Scroll reveal | Hero, features, workflow, security | Good basis; disconnect-once, reduced-motion safe |
| Ambient float | `tokens.css` only | **Unused** |
| Pulse | `tokens.css` only | **Unused** |
| Chart enter | Donut, Trend | Fade + `scaleY(0.96)` only; bars had none |
| Fade up | Showcase tab panel | One-shot |
| Menu in | Marketing mobile nav | One-shot |
| Sidebar indicator | Sidebar | Height 0→16 px (good) |
| Hover | Tables, cards, buttons | Colour only; no elevation |
| KPI values | MetricCard | **Instant** — no count-up |
| Progress | BarChart, WorkloadList | Width transitioned, but no 0→value entrance and no progressbar semantics |
| Page transitions | AppShell | **None** |
| Landing depth | ProductVisual | Flat static panel |

---

## Part C — Architecture decisions

### C1. No new animation dependency

Motion for React is not installed. The existing `Reveal` + CSS approach already
covers entrance, and the remaining needs are met by CSS transforms, SVG
`pathLength`/dash offsets, and two small hooks. Adding a 30–60 kB runtime for this
surface area would overlap the existing implementation without measurable
benefit. **`package.json` and `package-lock.json` are unchanged.**

### C2. One central configuration

`src/theme/motion.ts` owns:

- durations: fast 140, base 200, slow 320, reveal 420, entrance 560, count 800,
  chart 900, ambient 7500 ms;
- easing: `standard`, `out`, `inOut`;
- `stagger(index)` with a 70 ms step, clamped;
- float bounds (4–8 px, 6–9 s);
- `prefersReducedMotion()` — returns **true** when `matchMedia` is unavailable, so
  tests and non-browser environments always take the safe path.

CSS mirrors these as `--hd-dur-4/5/6`, `--hd-dur-chart`, `--hd-dur-ambient`,
`--hd-float-dist`, `--hd-ease-in-out`.

### C3. Naming

The brief's `StaggerContainer` / `StaggerItem` / `FadeUp` / `FloatIn` were **not**
added as new wrapper types. The existing `Reveal` already is the entrance
primitive and a stagger is a delay; extra containers would create redundant DOM
for no behavioural gain. Names actually introduced, matching the brief where they
were appropriate: `FloatingElement`, `TiltSurface`, `AnimatedNumber`,
`AnimatedProgress`, and `useEntrance` / `useDelayedEntrance`.

---

## Part D — Colour decisions

Monochrome identity unchanged; one controlled cobalt accent added.

| Token | Light | Dark |
| --- | --- | --- |
| `--hd-accent` | `#4a6db8` | `#93b4ff` |
| `--hd-accent-soft` | `#eef2fb` | `rgba(74,109,184,.18)` |
| `--hd-accent-border` | `#c9d5ee` | `rgba(147,180,255,.3)` |
| `--hd-accent-contrast` | `#ffffff` | `#0b0b0d` |

Measured contrast:

| Pair | Ratio |
| --- | --- |
| `#4a6db8` on white | **5.04** |
| `#4a6db8` on page `#fafafa` | **4.82** |
| `#4a6db8` on muted `#f5f5f5` | **4.62** |
| `#93b4ff` on dark page `#0b0b0d` | **9.56** |
| `#93b4ff` on dark surface `#131316` | **9.02** |
| `#93b4ff` on dark muted `#18181b` | **8.62** |

The brief's `#5278C7` measures **4.31:1** on white, below the 4.5:1 text
threshold, so it was darkened to `#4a6db8` — same muted cobalt character,
accessible at small sizes.

Accent is used only for:

1. the sidebar active indicator bar;
2. the marketing eyebrow dot;
3. the selected product-tour tab border and icon;
4. focus borders on interactive metric cards;
5. the **non-semantic** "active work assigned" progress fill.

Semantic progress keeps its semantic colour (resolution → success, urgent
workload → danger). Existing status/priority tone maps are untouched, so no chart
changed meaning. No gradients, no glow, no rainbow.

---

## Part E — Floating motion

### E1. Landing page

`FloatingElement` wraps the `hd-float` keyframes and takes `distance`,
`duration` and `delay`, so sibling layers desynchronise.

`ProductVisual`:

- Main dashboard preview drifts **7 px over 7.8 s**.
- Three satellite layers hang **below** the main panel's bottom edge in a
  staggered shelf: resolved-today card (5 px / 8.6 s / +900 ms), first-response
  card (6 px / 7.2 s / +1600 ms), sample pill (4 px / 6.4 s / +400 ms).
- Satellites are hidden below `xl`.
- The hero reserves extra bottom padding at `lg` so the shelf never touches the
  next section.

**Collision measurement (headless Chromium).** For every satellite, the script
compared its rect against every `p`/`span` rect inside the main dashboard:

| Width | Visible layers | Collisions with dashboard content | Overflow |
| --- | --- | --- | --- |
| 1440 | 4 | **0** | 0 |
| 1280 | 4 | **0** | 0 |
| 1024 | 2 | **0** | 0 |
| 768 | 1 | 0 | 0 |
| 390 | 1 | 0 | 0 |
| 360 | 1 | 0 | 0 |

Motion itself was confirmed to be real, not just declared: computed transform on
the first float layer moved from `matrix(1,0,0,1,0,-1.635)` to
`matrix(1,0,0,1,0,-6.518)` over 1.8 s, with `animation: hd-float 7.8s infinite`.

### E2. Depth / perspective

`TiltSurface` applies at most **4°** of rotation. It attaches only when
`(pointer: fine)` and `min-width: 1024px`, does nothing under reduced motion,
writes transforms directly to the node inside `requestAnimationFrame`, and
removes every listener on unmount. Verified: a synthetic pointer move produced
`perspective(1400px) rotateX(2.4deg) rotateY(2.4deg)`.

### E3. Workspace

Restrained by design. **No continuous floating.** Cards enter, settle, and lift
2 px on hover. A chart panel fades up 14 px once. Nothing in a ticket row, a
table, or the navigation drifts.

### E4. Responsive and reduced-motion rules

```css
@media (max-width: 1023px)  { .hd-float, .hd-float-slow { animation: none !important } }
@media (prefers-reduced-motion: reduce) { …all ambient + entrance animations: none !important }
```

Verified: at 768 / 390 / 360 px **0** floating layers are running; with reduced
motion **0** elements have a running animation at all.

---

## Part F — Headings, sections and page transitions

- `Reveal` was extended, not replaced:
  - new `as` prop;
  - a synchronous viewport check so content already on screen shows immediately
    (prevents a blank first frame on workspace pages);
  - still disconnects after the first intersection — verified that scrolling back
    up leaves the section at opacity `1`.
- Hero sequence: eyebrow → heading → description → CTAs → proof points, 70 ms
  apart. Everything is readable on the first frame; motion only softens arrival.
- Section headings staged on Features, Product tour, How it works, Security, CTA.
- Feature cards, workflow steps and security layers stagger by index.
- Workspace `PageHeader`: breadcrumb → title → description/meta → actions.
- Route changes: `hd-page-enter` (opacity + 6 px rise, **320 ms**) keyed on
  pathname, so navigation stays immediate. Deliberately shorter than a section
  reveal so a route change reads as "arrived", not "loading".

A copy diff between the old and new landing page found **0 removed words** — the
same 4,576-char copy, plus 7 words from the new sample satellite captions.

---

## Part G — Animated KPIs

`AnimatedNumber`:

- settles on **exactly** the prop value;
- animates from the previous value to the new one, not from zero, on refetch;
- restarts only when the target changes;
- keyed counters **resume from their last displayed value** after navigating away
  and back — a revisit does not replay the count from zero;
- visible digits are `aria-hidden`; a visually hidden copy of the final formatted
  value is what assistive technology reads;
- renders the final value instantly under reduced motion or when rAF is
  unavailable;
- renders the `—` loading placeholder untouched (never animates a dash into a
  number).

`MetricCard` uses it for numeric values, keeps string values as-is, enters with a
12 px rise, staggers across the grid, and lifts on hover/focus.

Verified final values on the dashboard fixture: `42`, `12`, `3`, `21`, `3`, plus
attention counts `2`, `1` and the two agent counts — each matching its input.

---

## Part H — Progress indicators

`AnimatedProgress`:

- full-width fill scaled by `transform: scaleX(value / max)`;
- starts at 0 and transitions **once** to the exact ratio over 900 ms;
- transitions from the previous ratio when the value changes;
- `role="progressbar"` with real `aria-valuemin` / `aria-valuemax` /
  `aria-valuenow` / `aria-valuetext`;
- percentage label counts up from the same numerator and denominator, so the
  label and the bar can never disagree;
- renders the final ratio on the first frame under reduced motion;
- clamps out-of-range values to full width rather than overflowing;
- renders as presentational if it has no accessible name (no unnamed controls).

### H1. Placements and the real numbers behind them

**Team workload** (per agent, relative to the busiest agent):

| Agent | `aria-valuenow` | `aria-valuemax` | Measured fill |
| --- | --- | --- | --- |
| Avery Bennett | 4 | 4 | 1.000 |
| Sam Okafor | 3 | 4 | 0.750 |
| Rae Lin | 1 | 4 | 0.250 |

**Admin queue snapshot — new measured-progress block**, using the existing
`resolutionShare` and `assignmentCoverage` helpers (no new backend field):

| Meter | Formula | Fixture data | Rendered | Measured fill |
| --- | --- | --- | --- | --- |
| Resolved of finished tickets | resolved / (resolved + closed) | 21 / 30 | 70% | 0.700 |
| Active work assigned | (open + waiting − unassigned) / (open + waiting) | 12 / 15 | 80% | 0.800 |

The fill colour never changes mid-animation, and the resting width is exactly
`value / max` — never rounded to a nicer figure, never looping after arrival.

---

## Part I — Charts

### I1. Bar chart

Each bar grows from `scaleX(0)` to exactly `value / max`, with a per-row stagger.
There is **no minimum width** (corrected in the QA pass, see N3): a 1-in-100
value occupies 1% of the track, and legibility comes from the exact count and
share printed beside the row. Tests assert the ratios directly — 1/100 → 0.01,
2/100 → 0.02, 30/100 → 0.30, 100/100 → 1.00, 1/99 → 0.0101 — plus the printed
`20%`/`80%` shares for a 2-and-8 split.

### I2. Donut chart

Each arc grows from zero dash length to exactly its real fraction, staggered
clockwise. Verified against the 8/4/3/21/6-of-42 fixture:

| Slice | Expected arc length | Rendered arc length |
| --- | --- | --- |
| 8 | 89.760 | 89.760 |
| 4 | 44.880 | 44.880 |
| 3 | 33.660 | 33.660 |
| 21 | 235.619 | 235.619 |
| 6 | 67.320 | 67.320 |

Mid-flight samples showed the computed dash length rising
(10.0 → 73.1 → 88.4 → 89.76 px), confirming a real progressive draw — not an
instant swap.

### I3. Trend chart

Each series draws left-to-right via a normalised `pathLength` dash offset, so it
works at any container width. The area fill fades in only after its line. Axes,
gridlines and labels stay fixed. The hover readout still shows exact values.

### I4. Sparkline

Draws once; the end-cap dot appears after the stroke. A single-point series renders
**nothing** rather than inventing a trend (tested).

### I5. Data changes

Filter and refetch transitions come from the existing React Query cache
(`keepPreviousData` on ticket lists). Bars, arcs and meters animate from their
previous values. Nothing simulates live updates.

---

## Part J — Accuracy guarantees ("make the data move, not the data lie")

1. Every animated target is a prop derived from `SupportAnalytics`, `Ticket[]`,
   or the existing `lib/analytics.ts` helpers.
2. No counter can settle anywhere except its input (tested).
3. No progress fill can rest anywhere except `value / max` (tested, including a
   non-100 denominator and an out-of-range value).
4. Bar and donut geometry is a pure function of the props (tested/measured).
5. Animation code never writes back to source data — it only reads.
6. The only sample numbers on the site remain the marketing illustrations, all
   labelled `SAMPLE DATA` or `SAMPLE`. No new sample values were added to the
   product.
7. A grep for `Math.random`, `setInterval`, fake timers and hardcoded metrics in
   product code found only the unrelated client-side upload id generator in
   `NewTicketPage.tsx`.

---

## Part K — Accessibility, reduced motion, responsive

### K1. Reduced motion (verified in Chromium with `prefers-reduced-motion: reduce`)

- 0 elements with a running CSS animation.
- Hero heading opacity `1`, transform `none`.
- Floats hold their resting position.
- Counters and progress render final values immediately.
- Charts render fully drawn.
- `scroll-behavior: auto`.

### K2. Semantics

Automated DOM sweep of the landing page:

| Check | Result |
| --- | --- |
| Unnamed interactive controls | **0** |
| Images without `alt` | **0** |
| `h1` count | **1** |
| Heading-level jumps | **0** |
| Unlabelled SVGs | **0** |
| Product-tour tabs | correct `aria-selected`, roving `tabindex`, labelled panel |
| Progress meters | real min/max/now/text |
| Chart data tables | present (4 tables on the dashboard fixture) |

### K3. Keyboard

First Tab lands on the HelpDesk home link with a visible 2 px solid focus ring.
Product-tour tabs keep arrow/Home/End support from the prior implementation.

### K4. Contrast

Accent: 5.04:1 (light) / 9.56:1 (dark). Existing semantic colours retained and
re-verified (success 5.02, warning 4.92, danger 6.47 on white; lifted values on
dark). Colour is always paired with an icon and a text label — never the only
signal.

### K5. Responsive matrix

| Width | Overflow | Floating layers running | Satellite layers visible | Tilt |
| --- | --- | --- | --- | --- |
| 1440 | 0 px | 4 | 4 | on (fine pointer) |
| 1280 | 0 px | 4 | 4 | on |
| 1024 | 0 px | 4 | 2 | on |
| 768 | 0 px | 0 | 1 | off |
| 390 | 0 px | 0 | 1 | off |
| 360 | 0 px | 0 | 1 | off |

No horizontal overflow at any width, before or after.

---

## Part L — Performance and limitations

### L1. Performance (side-by-side headless load, same machine, 1440 px)

| Metric | Before | After |
| --- | --- | --- |
| Long tasks during scroll-through | 1 (88 ms) | 1 (99 ms) |
| DOM nodes | 844 | 896 |
| JS heap (idle) | 15.6 MB | 17.2 MB |
| Cumulative layout shift | 0 | **0** |
| Asset bytes | 1,305,367 | 1,318,819 (+1.0%) |
| Main gzip chunk | 108.56 kB | 108.62 kB |

Only `transform`, `opacity`, SVG dash properties and the progress `scaleX` are
animated. One observer per reveal, disconnected after first intersection. One rAF
loop per counting value, cancelled on unmount. Tracked properties measured: 0
layout shifts.

### L2. Limitations (stated, not hidden)

1. **No authorised Clerk test account.** Authenticated dashboards were verified
   through the component test suite, a rendered fixture mounting the real
   components, and source review — not by signing into production. This
   limitation predates this work (`docs/FINAL_PRODUCTION_READINESS_REPORT.md`
   §L6).
2. **No real-time data source.** Dashboards update on React Query refetch and
   filter changes only. Nothing pretends otherwise.
3. **No SLA metric in the backend**, so no SLA progress bar was added. The
   progress meters use shares the API can actually compute.
4. **No E2E runner and no image-diff baselines in CI.** Browser verification used
   a temporary headless-Chromium script (not committed); screenshots are stored
   for human review.
5. **The accent is a design choice.** It is used narrowly and contrast-checked;
   reverting to the fully ink-based selection state is a one-line token change.

---

## Part M — Delivery

| Deliverable | State |
| --- | --- |
| Audit | `docs/motion-design-audit.md` |
| Implementation report | `docs/motion-design-implementation-report.md` |
| This review | `docs/motion-design-review.md` (moved out of `data.md` during QA) |
| QA screenshots | `docs/motion-assets/qa-2026-11-21/` plus refreshed top-level captures |
| Branch | `feat/helpdesk-motion-visual-polish` |
| Typecheck | clean |
| Lint | clean |
| Tests | **16 files / 136 tests passing** (after the QA pass) |
| Production build | succeeds with production-shaped env |
| Dependencies changed | **none** |
| PR #19 | untouched |
| `data.md` | restored byte-for-byte to the PR #19 review |

- Motion implementation: `ea5e2e8`
- Documentation follow-up: `3835b1d`
- QA corrections commit: `fd6dcae` (`fd6dcae77f32b48f7446fbc134b2f51cd498833b`)
- Pull request: https://github.com/mdjayedgazi/HelpDesk/pull/23

### PR state observed during QA

When the QA pass started, PR #23 had **already been merged** (merge commit
`8e6868d`, 2026-11-21T16:04:20Z) and `main` was at that merge. The QA changes
were therefore committed on the same `feat/helpdesk-motion-visual-polish`
branch (`fd6dcae`) and pushed, as instructed. A merged pull request cannot
accept new commits, so these corrections are **not** in `main` yet; they need a
small follow-up review PR. Creating one was explicitly out of scope for this
pass ("do not create another branch or PR"), so it was left to the requester.
This is stated plainly rather than claimed as delivered.

---

## Part N — QA corrections (this pass)

### N1. `data.md` preservation (merge-blocking finding)

The PR #23 diff replaced `data.md` — the PR #19 production-readiness review —
with the motion review. Corrected:

- The motion review was preserved verbatim as `docs/motion-design-review.md`
  (SHA-256 `d51965ac…` matched `HEAD:data.md` before the move).
- `data.md` was restored from `4ea4a2e:data.md` and is now byte-identical
  (SHA-256 `0313ae64a01b5aaba780e711f96f1b4cac51502c12449530480b5cf5f68fd1f6`,
  717 lines / 32,148 bytes), verified with `git diff 4ea4a2e -- data.md` → empty.

### N2. Trend chart date labels

**Finding.** The x-axis used a fixed `ceil(n / 6)` interval and then always
appended the final date, so a 14-day series could place the last two labels a
few pixels apart. Measured real glyph advance was ~8.5 px/char at 10 px — far
wider than the previous estimate assumed.

**Fix.** `selectTrendLabelIndices` in `TrendChart.tsx`:

- estimates each label's painted width at **9 px/char** (measured high end, so a
  wider fallback font still cannot collide);
- tries the largest sensible tick count first, then walks down;
- anchors the first label left and the last right, centring intermediate ones;
- accepts a candidate only when every box is inside the plot and no two are
  closer than 12 px;
- always keeps the first date; keeps the last whenever both ends fit.

**Browser measurement** (labels are the painted `getBoundingClientRect`s):

| Width | Labels | First | Last | Min gap | Collisions | Clipped |
| --- | --- | --- | --- | --- | --- | --- |
| 1440 | 7 | Nov 8 | Nov 21 | 52.4 px | 0 | 0 |
| 1280 | 7 | Nov 8 | Nov 21 | 35.9 px | 0 | 0 |
| 1024 | 8 | Nov 8 | Nov 21 | 17.4 px | 0 | 0 |
| 768 | 7 | Nov 8 | Nov 21 | 21.1 px | 0 | 0 |
| 390 | 3 | Nov 8 | Nov 21 | 46.3 px | 0 | 0 |
| 360 | 3 | Nov 8 | Nov 21 | 33.2 px | 0 | 0 |

The full 14-point series is still plotted and still present in the accessible
table (tested). Hover interaction is untouched.

**Regression test.** `trendLabels.test.tsx` reconstructs the chart's x scale for
9 widths, asserts every label box is inside the plot, asserts a ≥12 px gap
between neighbours, asserts first/last anchoring, covers 1-point, 7-point and
90-point series, and confirms the rendered chart keeps all 14 rows in its data
table. 24 tests.

### N3. Bar chart exact proportions

**Finding.** A `Math.max(4, …)` floor forced any non-zero bar to at least 4% of
the track, so a 1/100 value painted as 4/100. That is a falsified chart.

**Fix.** Geometry is now exactly `value / max`, clamped only to `[0, 1]`.
No minimum width, no hairline floor. Small values stay legible through the exact
count and share printed beside the row and in the accessible table.

**Tests** (`dataAccuracy.test.tsx`, 15 tests): 1/100 → 0.01, 2/100 → 0.02,
30/100 → 0.30, 100/100 → 1.00, 1/99 beside 99/99 → 0.0101 and 1.0 (the old code
would have produced 0.04), zero → 0, all-zero → all zero with no division by
zero, empty dataset → no rows.

**Browser check.** Every painted bar ratio equals its inline transform exactly
(e.g. `scaleX(0.142857)` → painted 0.1429, `scaleX(0.0714286)` → 0.0714).

### N4. Progress normalization

**Finding.** The fill ratio was clamped but `aria-valuenow` received the raw
value, so `value=120, max=100` announced 120 while painting 100%, and
non-finite input could poison both.

**Fix.** A single normalization pass now feeds the fill, the label and ARIA:

- non-finite/negative/zero `max` falls back to a documented `DEFAULT_MAX = 100`;
- non-finite `value` is treated as `0`;
- the value is clamped into `[0, max]`;
- `aria-valuenow` uses the **normalized** value, so it always agrees with the
  painted ratio and the percentage text.

**Tests** (`motion.test.tsx`, 17 tests): 30→30%, 70→70%, 100→100%, 120→clamped
to 100/100%, −10→0%, 0→0%, `max=0`→documented 100-range fallback,
`NaN`→0%, `Infinity` max→fallback with 50/100, non-100 denominator (3/4 →
0.75), unnamed meter kept out of the a11y tree, reduced motion instant.

### N5. Mobile dashboard full-scroll verification

**Finding.** The committed `dashboard-390-light.png` showed a large empty band.
A pixel analysis of that file found a 90 px fully blank window (ink score 0;
48 of 99 30 px bands near-empty).

**Root cause.** It was a **capture artifact**, not a UI defect. The screenshot
was taken at `fullPage` without scrolling, and `Reveal` content below the fold
was still at `opacity: 0`. The reveal logic was already correct.

**Verification** (real browser, 390 and 360 px, stepping down the page in
500 px increments with a 700 ms settle at each step):

- all 11 required sections present: Support operations, Total tickets, Ticket
  volume, Needs attention, Aging tickets, Active agents, Status composition,
  Priority mix, Where requests come from, Team workload, Measured progress;
- **0** reveal containers left at `opacity: 0`;
- returning to the top keeps every section visible (`hiddenRevealContainers: 0`);
- horizontal overflow 0 px.

**Gap check.** The largest measured vertical span between labelled anchors was
488 px, between "Status composition" and "Priority mix" — and that is the donut
card's own content (a 220 px donut plus five legend rows; 459 px card measured).
It is content, not whitespace. A pixel scan of the new capture finds **no** blank
band at all (longest fully-blank row run: 0 px).

**Evidence.** `docs/motion-assets/dashboard-390-light-BEFORE-scroll.png` (the
old capture, with the artefact) beside `dashboard-390-light.png` (the new one,
captured after progressive scrolling).

**Sparkline.** Kept. It is labelled "Daily created tickets" and paired with the
text "14-day arrival trend" in the status-composition legend, so it is a dated,
explained trend, not decoration. At 390 px it stacks above its caption without
clipping.

### N6. Animation frame verification

Intermediate computed styles captured at ~0/120/280/520/850/1300 ms:

| Frame | KPI | Bar 1 | Progress 1 | Donut arc 1 | Trend dash |
| --- | --- | --- | --- | --- | --- |
| 0 ms | 0 | 0 | 0 | 0 px | 1 px |
| 120 ms | 16 | 0.056 | 0.392 | 35.18 px | 0 |
| 280 ms | 31 | 0.120 | 0.837 | 75.09 px | 0 |
| 520 ms | 40 | 0.140 | 0.979 | 87.89 px | 0 |
| 850 ms | 42 | 0.143 | 0.9999 | 89.751 px | 0 |
| 1300 ms | 42 | 0.142857 | 1 | 89.7598 px | 0 |

Each series progresses monotonically and settles on the exact data value. The
settled bar ratio `0.142857` is `2/14`; the settled arc length `89.7598 px` is
`8/42 ×` circumference.

### N7. Reduced motion

With `prefers-reduced-motion: reduce`: 0 elements with a running animation,
0 hidden reveal containers, KPI shows `42` immediately, every progress fill at
its final ratio, bars at final ratio, donut arc complete (89.76 px), trend line
fully drawn. No content is withheld.

### N8. Accessibility re-check

Landing and dashboard: 0 unnamed interactive controls, 0 unnamed progressbars,
0 images without `alt`, exactly one `h1`, 0 heading-level jumps, 4 data tables
on the dashboard. First Tab lands on a link with a 2 px solid focus ring.

### N9. Performance re-check

| Page | CLS | Long tasks | Max | DOM nodes | Heap |
| --- | --- | --- | --- | --- | --- |
| Landing | 0 | 1 | 87 ms | 895 | 12.9 MB |
| Dashboard fixture | 0 | 2 | 172 ms | 1403 | 39.3 MB |

No new dependencies; the only new code is the label selector and the
normalization pass.

---

## Part O — QA evidence and remaining gaps

**Screenshots** in `docs/motion-assets/qa-2026-11-21/`: landing at 1440/390,
landing dark, landing reduced-motion, landing full-page, dashboard light/dark/
390/reduced, and trend-chart close-ups at desktop and mobile. These were
inspected **programmatically** (dimensions, pixel ink density, blank-band
detection, overflow) rather than by eye, because the reviewing model in this
session cannot decode images. That is stated plainly rather than implying a
human visual pass.

**Motion evidence.** A temporary WebM recording of the landing page
(floating hero + scroll reveals) was produced during QA and kept outside the
repository (`/tmp/qa-video`), per the instruction to avoid committing large
binary traces. The frame-level proof above is the durable evidence.

**Still unverified.**

- No authorised Clerk test account, so authenticated production screens remain
  unverified at runtime; the dashboard was exercised through a fixture mounting
  the real components.
- No live Railway deployment check was attempted or implied.
