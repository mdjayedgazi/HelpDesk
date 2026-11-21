# HelpDesk — Motion & Visual Polish Implementation Report

Date: 2026-11-21
Branch: `feat/helpdesk-motion-visual-polish`
Base: `main` @ `4ea4a2e`
Companion audit: [`docs/motion-design-audit.md`](./motion-design-audit.md)
Screenshots: [`docs/motion-assets/`](./motion-assets/)

This report records what was actually built and verified. Anything that could not
be exercised is marked **unverified** rather than implied.

---

## 1. Initial audit

Full detail in `docs/motion-design-audit.md`. Key findings that drove the work:

- PR #19 and PR #22 are both **merged**; there were no open PRs and no open
  feature branch to stack on, so the branch was cut from `main`.
- The prior modernization had already built a strong monochrome token system,
  hand-written SVG charts, semantic status colour, accessible chart data tables,
  and a CSS/IntersectionObserver `Reveal`. No animation library was installed.
- Motion was defined but largely unused: `hd-float` / `hd-pulse` existed in
  `tokens.css` and were never referenced. Charts appeared fully drawn; KPI values
  appeared instantly; progress bars had no entrance; route changes were abrupt.
- There was no accent token at all — selection was expressed with ink.

---

## 2. Design research

Used as principles, not as assets to copy:

- **Motion for React / motion.dev** — the reference vocabulary (stagger, entrance,
  shared easing). Not installed: see §16.
- **Linear** — restraint; motion communicates state change, never ambience, inside
  a working surface.
- **Zendesk / Unex reference** — operational hierarchy: headline metrics → dominant
  trend → composition → queue.
- **Microsoft data-visualisation guidelines** — honest axes, zero baseline,
  direct labelling, no decorative motion on data.
- **MDN `prefers-reduced-motion` / W3C WCAG 2.2 animation from interactions** —
  motion must be suppressible and must never gate access to content.

---

## 3. Motion design direction

One vocabulary, three speeds of intent:

1. **Ambient (landing only)** — depth. 4–8 px vertical drift, 6–9 s cycles, offset
   per layer so nothing moves in lockstep. Desktop only.
2. **Entrance** — arrival. Headings and panels rise 10–20 px and fade over
   420–620 ms with a 70 ms sibling stagger.
3. **State** — feedback. 140–320 ms colour/elevation on hover, focus, selection.

Everything is CSS-driven (`transform` + `opacity`, SVG `stroke-dashoffset`,
`scaleX`) except two JS pieces: the count-up loop and the one-shot entrance flag.
No animation ever decides a value.

---

## 4. Colour decisions

The monochrome identity is unchanged. One controlled accent was added:

| Token | Light | Dark | Contrast |
| --- | --- | --- | --- |
| `--hd-accent` | `#4a6db8` | `#93b4ff` | 5.04:1 on white, 4.82:1 on page; 9.56:1 on dark page |
| `--hd-accent-soft` | `#eef2fb` | `rgba(74,109,184,.18)` | tint only |
| `--hd-accent-border` | `#c9d5ee` | `rgba(147,180,255,.3)` | 1 px outline |

The brief's `#5278C7` measures **4.31:1** on white — below the 4.5:1 text
threshold — so it was darkened to `#4a6db8` while keeping the muted cobalt
character. Accent is used only for: the sidebar active bar, the marketing eyebrow
dot, the selected product-tour tab, focus borders on interactive cards, and the
**non-semantic** "active work assigned" progress fill. Semantic progress keeps
its semantic colour (resolution → success, urgent workload → danger). No chart
series changed meaning and no rainbow was introduced.

---

## 5. Preserved visual identity

Verified in a headless Chromium against a build of `main` and a build of this
branch, rendered side by side:

| Property | Before | After |
| --- | --- | --- |
| Hero font stack | `Inter, ui-sans-serif, …` | identical |
| Hero font-size / weight | 60 px / 600 | identical |
| Hero line-height / tracking | 62.4 px / -2.1 px | identical |
| Hero text colour | `rgb(17,17,17)` | identical |
| Hero heading width @1440 | 580 px | 580 px |
| Page background | `rgb(250,250,250)` light / `rgb(11,11,13)` dark | identical |
| Section copy | — | word-for-word identical (word-diff: 0 removed) |

No font was added or downloaded. No layout, grid or navigation structure changed.

---

## 6. Floating animation implementation

`src/components/motion/FloatingElement.tsx` wraps the `hd-float` keyframes and
accepts `distance`, `duration` and `delay` so sibling layers desynchronise.

Landing page (`ProductVisual.tsx`):

- The main dashboard preview drifts 7 px over 7.8 s.
- Three satellite layers (resolved-today card, first-response card, sample
  preview pill) hang **below** the main panel's bottom edge in a staggered shelf,
  each on its own cycle (8.6 s / 7.2 s / 6.4 s, delays 900/1600/400 ms).
- Satellites are hidden below `xl`; the hero reserves extra bottom padding at
  `lg` so the shelf never collides with the next section.

Measured (headless Chromium, 1440/1280/1024): **0 collisions** between any
satellite and any label/number inside the dashboard, at every tested width.
Continuous drift is disabled below 1024 px via CSS (`animation: none`) and under
reduced motion. The workspace has **no** continuous floating.

`TiltSurface.tsx` adds a maximum 4° pointer tilt to the hero product surface.
Verified: only attaches when `(pointer: fine)` and `min-width: 1024px`; a
synthetic pointer move produced `rotateX(2.4deg) rotateY(2.4deg)`; it is disabled
under reduced motion and removes all listeners on unmount.

---

## 7. Heading and section animations

- `Reveal` was extended (not replaced) with an `as` prop and a viewport check so
  on-screen content shows immediately instead of waiting for the observer's first
  callback. It still disconnects after the first intersection, so scrolling back
  up never replays it (verified: section opacity stays `1` after scrolling up).
- Hero: eyebrow → heading → description → CTAs → proof points, 70 ms apart.
- Every marketing section heading is staged (eyebrow / title / lead).
- Feature cards, workflow steps and security layers stagger by index.
- Workspace `PageHeader` stages breadcrumb → title → description/meta → actions.
- Workspace route changes use `hd-page-enter` (opacity + 6 px rise, 320 ms),
  keyed on pathname. The route renders on the same tick; the animation only
  decorates arrival.

---

## 8. Dashboard animations

- `MetricCard` now counts numeric values up to their real number, enters with a
  12 px rise and staggers across the grid (0/70/140/210/280 ms), and lifts 2 px
  with a shadow on hover/focus.
- `ChartCard` panels reveal with a 14 px rise and a staggered delay, and pick up
  a border emphasis on hover.
- `AttentionList` rows count up; the healthy state and the list both reveal.
- `WorkloadList` rows use the accessible animated progress meter.
- The admin "Queue snapshot" panel gains a measured-progress block (see §9).

---

## 9. Progress-bar implementation

`src/components/motion/AnimatedProgress.tsx`:

- fill is a full-width bar scaled by `transform: scaleX(value / max)`;
- starts at 0 and transitions once to the exact ratio over 900 ms;
- updates transition from the previous ratio when the value changes;
- exposes `role="progressbar"` with real `aria-valuemin`, `aria-valuemax`,
  `aria-valuenow` and `aria-valuetext`;
- percentage label counts up from the same numerator/denominator;
- reduced motion renders the final ratio on the first frame.

Placed on:

- **Team workload** — each agent's active tickets relative to the busiest agent
  (`aria-valuenow = active_tickets`, `aria-valuemax = max`). Colour is danger if
  the agent has urgent tickets, else the accent.
- **Admin queue snapshot** — two real percentages derived in `lib/analytics.ts`:
  - *Resolved of finished tickets* = resolved / (resolved + closed), success colour.
  - *Active work assigned* = (open + waiting − unassigned) / (open + waiting),
    accent colour.
  Both reuse the existing helpers (`resolutionShare`, `assignmentCoverage`) —
  no new backend field, no estimate.

Browser-verified on the rendered admin dashboard fixture:

| Meter | Data | Rendered | Actual fill ratio |
| --- | --- | --- | --- |
| Resolved of finished | 21/30 | 70% | 0.700 |
| Active work assigned | 12/15 | 80% | 0.800 |
| Agent A workload | 4/4 | — | 1.000 |
| Agent B workload | 3/4 | — | 0.750 |
| Agent C workload | 1/4 | — | 0.250 |

---

## 10. Animated charts

- **BarChart** — each bar grows from `scaleX(0)` to exactly `value / max`, row
  stagger, real count and share printed beside it, `ChartDataTable` unchanged.
- **DonutChart** — each arc grows from zero dash length to exactly its real
  fraction of the circumference, staggered clockwise. Verified against the
  fixture: 8/4/3/21/6 of 42 produced arc lengths 89.760 / 44.880 / 33.660 /
  235.619 / 67.320 px, which are exactly `value/42 × circumference`.
- **TrendChart** — each series draws left-to-right via normalised `pathLength`
  dash offset, with the area fill fading in after the line; axes/labels stay
  fixed.
- **Sparkline** — draws once, end-cap dot follows the stroke.
- Data-change behaviour comes from the existing query cache (`keepPreviousData`
  on ticket lists); bars, donut arcs and progress meters animate from their
  previous values.

---

## 11. Actual backend data verification

- No chart, counter or meter introduces a value the API did not return. Every
  animated target is a prop derived from `SupportAnalytics`, `Ticket[]`, or the
  existing `lib/analytics.ts` helpers.
- Automated tests assert the final state, not the frames:
  - `motion.test.tsx`: counter settles on the value; progress `aria-valuenow`
    equals the input and the fill equals `value / max`; out-of-range clamps to
    full; zero renders zero; reduced motion renders instantly.
  - `dataAccuracy.test.tsx`: bars scale to `value / max`; percentages match the
    shares; `MetricCard` settles on 30 and formats 1284 as `1,284`; the `—`
    placeholder is never animated into a number; a single-point sparkline renders
    nothing rather than inventing a trend.
  - `AdminDashboard.test.tsx`: resolution meter is `70`, coverage is `80`, the
    workload meter is `4 / 4` — all computed from the fixture's real totals.
- Counters never restart from zero on an unrelated render, and keyed counters
  resume from their last displayed value when you navigate away and back.
- The only sample numbers on the site live in the marketing illustrations and
  are labelled `SAMPLE DATA` / `SAMPLE`. No new sample values were added.

---

## 12. Accessibility and reduced motion

- All new continuous motion is disabled under `prefers-reduced-motion: reduce`:
  floats, tilt, counters (instant), progress (instant), chart draw (instant),
  route transition (none). Verified in Chromium: 0 elements with a running
  animation, hero opacity `1`, no residual transform, scroll-behavior `auto`.
- Counters: animated digits are `aria-hidden`; a visually hidden final value is
  the accessible datum, so screen readers never announce intermediate numbers.
- Progress meters: real progressbar semantics with real min/max/now/text; a meter
  with no available name renders as presentational rather than an unnamed control.
- Charts keep their hidden `<table>` data alternative (count asserted in tests).
- Keyboard: first Tab lands on the home link with a visible 2 px focus ring;
  product-tour tabs keep roving `tabindex` and arrow-key support.
- Automated DOM sweep of the landing page: 0 unnamed interactive controls,
  0 images without `alt`, exactly one `h1`, no heading-level jumps, 0 unlabelled
  SVGs.
- Accent contrast measured at 5.04:1 (light) and 9.56:1 (dark). Status colour is
  always paired with an icon and a text label.

---

## 13. Performance analysis

- Only `transform`, `opacity`, SVG dash properties and the progress `scaleX` are
  animated; no layout-triggering properties.
- One `IntersectionObserver` per `Reveal`, disconnected after first intersection.
- One rAF loop per counting value, cancelled on unmount; on-screen content is
  detected synchronously so workspace pages do not flash blank.
- Ambient float is CSS-only and desktop-only; tilt writes transforms directly to
  the node inside rAF, with no React re-render per pointer move.
- Side-by-side headless load (1440 px, same machine):

| Metric | Before | After |
| --- | --- | --- |
| Long tasks during scroll-through | 1 (88 ms) | 1 (99 ms) |
| Max long task | 88 ms | 99 ms |
| DOM nodes | 844 | 896 |
| JS heap (idle) | 15.6 MB | 17.2 MB |
| Cumulative layout shift | 0 | **0** |
| JS + CSS asset bytes | 1,305,367 | 1,318,819 (+1.0%) |
| Main gzip chunk | 108.56 kB | 108.62 kB |

The +1% asset growth is the motion primitives and their imports; there is no new
dependency.

---

## 14. Responsive behaviour

Verified at 1440 / 1280 / 1024 / 768 / 390 / 360 px:

- Horizontal overflow: **0 px at every width**, before and after.
- Floating layers: 4 visible / 4 running at ≥1024 px; 1 visible / 0 running at
  ≤768 px (satellites hidden, drift disabled).
- Tilt: only ≥1024 px with a fine pointer.
- Stagger depth is unchanged across breakpoints; no section is clipped.
- The hero reserves bottom space for the satellite shelf at `lg`; measured
  section-to-section positions show no overlap at any width.

---

## 15. Components changed

New:

- `src/theme/motion.ts` — durations, easing, stagger helper, reduced-motion probe.
- `src/hooks/useEntrance.ts` — `useEntrance`, `useDelayedEntrance`.
- `src/components/motion/AnimatedNumber.tsx`
- `src/components/motion/AnimatedProgress.tsx`
- `src/components/motion/FloatingElement.tsx`
- `src/components/motion/TiltSurface.tsx`
- `src/components/motion/motion.test.tsx`
- `src/components/charts/dataAccuracy.test.tsx`

Modified:

- Theme: `tokens.css` (accent + motion tokens, new keyframes, mobile/reduced
  guards, removed the unused `hd-chart-draw`), `palette.ts` (accent, motion).
- Chrome: `AppShell.tsx` (keyed page transition), `Sidebar.tsx` (accent indicator),
  `PageHeader.tsx`, `Surface.tsx` (SectionHeader reveal), `MetricCard.tsx`.
- Charts: `ChartCard.tsx`, `BarChart.tsx`, `DonutChart.tsx`, `TrendChart.tsx`,
  `Sparkline.tsx`.
- Dashboard: `dashboard/AttentionList.tsx`, `pages/admin/AdminDashboard.tsx`,
  `pages/admin/AdminDashboard.test.tsx`, `pages/agent/AgentDashboard.tsx`,
  `pages/customer/CustomerDashboard.tsx`.
- Marketing: `primitives.tsx`, `HeroSection.tsx`, `ProductVisual.tsx`,
  `FeatureSection.tsx`, `WorkflowSection.tsx`, `SecuritySection.tsx`,
  `ShowcaseSection.tsx`, `CtaSection.tsx`.
- `Reveal.tsx` (viewport fast-path + `as`).

No routing, API client, auth, authorization, query, validation or backend code
changed.

---

## 16. Dependencies changed

**None.** `package.json` and `package-lock.json` are untouched.

Motion for React was evaluated and deliberately not added: it is not installed,
the existing `Reveal` + CSS approach already covers entrance, and every remaining
need is met by CSS transforms plus two small hooks. Adding a runtime for this
surface area would overlap the existing implementation without a measurable
benefit.

---

## 17. Build results

```
tsc --noEmit                      clean
vp lint (oxlint, type-aware)      clean
vp build (production env)         ✓ built in ~0.75 s
```

Production build run with production-shaped env vars (`https://` API origin,
Clerk publishable key) so the config assertions in `vite.config.ts` were
exercised.

---

## 18. Test results

```
15 test files, 96 tests, all passing
```

Before this pass: 13 files / 78 tests. Added: 12 tests across
`motion.test.tsx`, `dataAccuracy.test.tsx`, and two progress assertions in
`AdminDashboard.test.tsx`.

The new tests cover: exact final counter values, `scaleX(value/max)` including a
non-100 denominator and an out-of-range value, progressbar ARIA, reduced-motion
instant rendering, bar proportionality, percentage labels, formatted numbers,
loading-placeholder handling, and a single-point sparkline rendering nothing.

---

## 19. Screenshots

Stored in `docs/motion-assets/`:

- `landing-1440-top`, `landing-1440-mid`, `landing-1440-bottom`, `landing-1440-full`
- `landing-baseline-1440-top` (pre-change `main`, for comparison)
- `landing-1280-top`, `landing-768-top`, `landing-390-top`, `landing-360-top`
- `landing-dark-1440`, `landing-reduced-motion-1440`
- `dashboard-1440-light`, `dashboard-1440-dark`, `dashboard-390-light`,
  `dashboard-reduced-motion-1440`

The dashboard images are rendered from a temporary preview harness that mounts the
real chart, metric and progress components with a fixed analytics fixture. The
harness was deleted after capture and is not part of the commit. Authenticated
screens could not be captured from the live app — see §23.

---

## 20. Git branch

`feat/helpdesk-motion-visual-polish`, created from `main` @ `4ea4a2e`.

---

## 21. Commit hash

`ea5e2e8ab8d09e262e85de3deac43abb69bb16a2` (`ea5e2e8`)
feat(frontend): add premium motion and animated data visualization

---

## 22. Pull request URL

https://github.com/mdjayedgazi/HelpDesk/pull/23
(`feat/helpdesk-motion-visual-polish` → `main`, open, mergeable, not merged)

---

## 23. Remaining limitations

- **No authorised Clerk test account exists**, so the authenticated dashboards
  were verified through the component test suite, a rendered fixture, and source
  review — not by signing into the production app. This limitation predates this
  work and is recorded in `docs/FINAL_PRODUCTION_READINESS_REPORT.md` §L6.
- **No real-time data source.** The dashboards update on React Query refetch and
  on filter changes. Nothing simulates live updates; there is no websocket or
  polling animation.
- **No SLA metric exists in the backend**, so no SLA progress bar was added. The
  progress meters use resolved/coverage shares the API can actually compute.
- **No E2E runner in the repository.** Browser verification was performed with a
  temporary headless-Chromium script; it is not committed as a test suite.
- **No image-diff baselines in CI.** Screenshots are stored for human review, not
  enforced by automation.
- **The accent is new.** It is used narrowly and contrast-checked, but a design
  owner may still prefer the fully ink-based selection state; reverting is a
  one-line token change (`--hd-accent` → `--hd-ink`).

---

## 24. QA pass corrections (post-review)

A dedicated QA pass inspected the merged implementation and corrected three
genuine defects plus one merge-blocking documentation error. The full narrative
and measurements are in `docs/motion-design-review.md` Part N; this section is
the change log.

### 24.1 `data.md` preserved (merge-blocking)

`data.md` had been overwritten with the motion review, replacing the PR #19
production-readiness review. Corrected by moving the motion review to
`docs/motion-design-review.md` (verified against `HEAD:data.md` by SHA-256) and
restoring `data.md` from `4ea4a2e`. `data.md` is now byte-identical to the base
(`git diff 4ea4a2e -- data.md` is empty).

### 24.2 Trend chart x-axis labels

`TrendChart.tsx` gained `selectTrendLabelIndices`, which estimates label width
(calibrated to a measured 9 px/char at 10 px), anchors the first and last dates,
and only accepts a tick set where every box fits inside the plot with a ≥12 px
gap. Verified in Chromium at 1440/1280/1024/768/390/360: first and last dates
present, **0 collisions, 0 clipped labels** at every width. The plotted series
and its accessible table are unchanged.

New test file: `frontend/src/components/charts/trendLabels.test.tsx` (24 tests).

### 24.3 Bar chart exact proportions

Removed the `Math.max(4, …)` minimum-width floor. Bar geometry is now exactly
`value / max`. Tests cover 1/100, 2/100, 30/100, 100/100, 1/99, zero, all-zero
and empty datasets. Browser check: painted ratio equals the inline transform for
every bar.

### 24.4 Progress value normalization

`AnimatedProgress.tsx` now normalizes once and uses the normalized value for the
fill, the percentage label, `aria-valuenow` and `aria-valuetext`. Non-finite
values become 0; a non-finite or non-positive maximum falls back to a documented
`DEFAULT_MAX = 100`; the value is clamped into range. Tests cover 120→clamped,
−10→0, 0/0, NaN and Infinity, and assert that ARIA never disagrees with the
painted ratio.

### 24.5 Mobile scroll verification

The blank band in the committed 390 px screenshot was proven to be a capture
artifact (the screenshot was taken at full page height without scrolling, while
below-the-fold reveals were still transparent). A real progressive-scroll test at
390 and 360 px confirms every section appears, nothing stays hidden after
returning to the top, and there is no blank band in the new capture. No
production code change was required, and reveal animations were **not** disabled.

### 24.6 Test and build state after QA

```
tsc --noEmit                      clean
vp lint (oxlint, type-aware)      clean
vp test run                       16 files / 136 tests passing
vp build (production env)         succeeds
```

Was 15 files / 96 tests before this pass; the 40 new tests cover trend-label
geometry, exact bar ratios and progress normalization.

### 24.7 PR state

PR #23 had already been merged (`8e6868d`) before this QA pass began. The
corrections were committed on the same `feat/helpdesk-motion-visual-polish`
branch as instructed — QA commit `fd6dcae`
(`fd6dcae77f32b48f7446fbc134b2f51cd498833b`) — and pushed. A merged pull request
cannot accept new commits, so these corrections are **not** in `main` yet and
require a small follow-up review PR, which was explicitly out of scope for this
pass ("do not create another branch or PR").
