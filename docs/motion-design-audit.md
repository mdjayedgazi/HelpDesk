# HelpDesk — Motion & Visual Polish Audit

Audit date: 2026-11-21
Branch audited: `main` @ `4ea4a2e` (working tree had `data.md` emptied — left untouched
until the final review was written to it)
Base branch for this work: `main` (PR #19 and PR #22 are both **merged**)
Feature branch created: `feat/helpdesk-motion-visual-polish`

This audit is the Phase 1 deliverable. It records what already exists, what is
missing, and the motion architecture chosen before any code changed. The
implementation report is `docs/motion-design-implementation-report.md`.

---

## 1. Repository and pull-request state

| Item | Finding |
| --- | --- |
| Current branch before work | `main` |
| Working tree | `data.md` modified (emptied). Preserved as found until the final review was written into it. |
| Recent commits | `4ea4a2e` merge of PR #22 (UI/UX modernization), `eeb9a41`, `8b3b508`, `ea073eb`, `cc30e4f`, `cd734e2` |
| PR #19 | `fix/production-readiness` → `main`, **MERGED** 2026-11-21T10:45:49Z. Not modified. |
| PR #22 | `feat/helpdesk-ui-ux-modernization` → `main`, **MERGED** 2026-11-21T14:02:06Z. The prior UI/UX work is already on `main`. |
| Open pull requests | None. |
| Local feature branches | `feat/helpdesk-ui-ux-modernization` exists locally and remotely, but is fully merged. Not reused. |
| Correct base | `main` — no stacked PR is required because the prior modernization landed. |
| New branch | `feat/helpdesk-motion-visual-polish` (created from `main`) |

### Production site

`https://helpdesk-web-production-d96f8e2b.up.railway.app` returned **200** in
~0.66 s. The served HTML matches the current `main` bundle shape (hashed ESM
entry, lazy route chunks, `theme-init.js`). Authenticated screens could not be
exercised: the repository has no authorised Clerk test account
(also recorded as unverified in `docs/FINAL_PRODUCTION_READINESS_REPORT.md` §L6).
Local frontend `.env` points at `http://127.0.0.1:8000`, and the backend needs a
live Postgres/Clerk pair, so role workspaces were reviewed from source and from
the test suite rather than by live login.

---

## 2. Existing frontend architecture (verified from source)

| Concern | Implementation |
| --- | --- |
| Framework | React **19.3.1** |
| Build | Vite Plus (`vite-plus` 1.2.0) + TypeScript ~6.0.2 |
| Routing | `react-router-dom` 7.18.4, `BrowserRouter`, route-level `React.lazy` |
| Component system | Chakra UI 3.37.0 (`createSystem`) + Tailwind utilities only (no preflight) |
| Data | TanStack Query 5.104.3, central `queryKeys`, 15 s stale time, `keepPreviousData` on ticket lists |
| Auth | Clerk 6.17.8; the backend is the authorization source of truth |
| Icons | lucide-react 1.58.0 |
| Charts | Hand-written SVG / div charts, no charting library |
| Animation | Hand-written CSS keyframes in `src/theme/tokens.css` + one `Reveal` component (IntersectionObserver) |
| Tests | Vitest via `vp test` (jsdom): 13 files, 78 tests, all passing before changes |
| Lint / types | `vp lint` (oxlint, type-aware), `tsc --noEmit` — both clean before changes |

### Typography (must be preserved)

`src/theme/system.ts` and `src/pages/auth/clerkAppearance.ts` both use:

```
Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif
```

There is no `@font-face`, no Google Fonts link, and no font asset in
`frontend/public/`. The identity is therefore "Inter if installed, system UI
otherwise" and it must stay exactly that. No font was introduced in this pass.

### Design tokens

`src/theme/tokens.css` already declares a complete light/dark token set:
surfaces, text tones, ink, borders, focus, overlays, five shadow steps, four
semantic families (info/success/warning/danger), a five-entry chart palette, a
motion block (`--hd-ease`, `--hd-ease-out`, `--hd-dur-1..3`), and layout widths.
`src/theme/palette.ts` re-exports these as stable names and
`src/theme/system.ts` maps them into Chakra semantic tokens.

Findings:

- The monochrome identity is strong and consistent. Colour is already reserved
  for status meaning, paired with icon + text (never colour alone).
- There is **no accent token**. Selection is expressed with ink
  (`--hd-ink: #111` in light). The request's muted cobalt accent is absent.
- Motion tokens stop at 320 ms (`--hd-dur-3`). Entrance choreography needs
  longer durations, so a 4/5/6 step was added.
- `prefers-reduced-motion` is already handled twice: a global Chakra rule zeroes
  animation/transition durations, and `tokens.css` disables the named
  animations. This is the right pattern to extend, not replace.

### Current motion inventory

| Pattern | Where | Quality |
| --- | --- | --- |
| Scroll reveal (`Reveal`) | Hero, features, workflow, security | Good basis; one observer per instance, `once`-like disconnect, reduced-motion safe |
| Ambient float (`hd-float`, `hd-float-slow`) | Defined in `tokens.css` | **Defined but never used** |
| Pulse (`hd-pulse`) | Defined | **Defined but never used** |
| Chart enter (`hd-chart-enter`) | Donut + Trend | Fade + `scaleY(0.96)` only; bars have no entrance |
| Fade up (`hd-fade-up`) | Showcase tab panel | One-shot CSS |
| Menu in (`hd-menu-in`) | Marketing mobile nav | One-shot CSS |
| Sidebar active bar | `Sidebar.tsx` | Height 0→16px transition (good) |
| Row/button hover | Tables, cards, buttons | Colour/background transitions only; no elevation |
| Charts | Bar/Donut/Trend/Sparkline | Static values; tooltips on trend only |
| Counters | MetricCard | **None** — numbers appear instantly |
| Progress bars | BarChart, WorkloadList | Width already animates via CSS transition, but there is no 0→value entrance and no `role="progressbar"` |
| Page transitions | AppShell | **None** — routes swap abruptly |
| Landing showcase | ProductVisual | Flat, static panel; no floating layers, no depth, no pointer response |

### Existing chart behaviour (important for the "no fabricated data" rule)

- `SupportAnalytics` is computed server-side from real ticket rows. The UI adds
  only derived transforms in `src/lib/analytics.ts` (shares, half-window deltas,
  coverage) and returns `null` when a denominator is zero.
- Admin dashboard: Donut (status), BarChart (priority, category), TrendChart
  (created vs resolved), Sparkline (created series), WorkloadList bars.
- Agent dashboard: Donut (own status), BarChart (own priority).
- Customer dashboard: Donut (own status), BarChart (own status counts).
- Charts render a visually hidden `<table>` (`ChartDataTable`) as the accessible
  representation. This must be preserved for every new visual.
- `MetricCard` shows a literal `'—'` while loading, so a counter must not treat
  `'—'` as a number.
- Test `AdminDashboard.test.tsx` asserts real totals (e.g. `42`) are in the DOM
  synchronously. Counters therefore must render the final value immediately
  when animation is unavailable or reduced, and must never invent a target.

### Landing-page visuals

`ProductVisual` is an illustrative sample workspace, explicitly labelled
`SAMPLE DATA`, built from the same tokens as the product. It is static. There
are no floating secondary layers, no depth stack, no pointer response, and no
scroll storytelling beyond `Reveal`.

---

## 3. Missing motion and visual depth

Ordered by user impact:

1. **Hero choreography** — everything fades in as one block. No sequence, no
   depth, no floating product surface.
2. **Ambient floating** — keyframes exist but are unused. Nothing conveys depth.
3. **Animated KPI values** — no count-up, no meaningful transition on data change.
4. **Animated progress** — no 0→real-value entrance; no accessible progress
   semantics; no percentage indicator for resolution/coverage.
5. **Progressive charts** — trend lines appear fully drawn; bars/donut have no
   growth; no update transition when filters change.
6. **Section stagger** — feature cards and security layers reveal individually
   with no stagger relationship.
7. **Workspace page transitions** — abrupt route swaps.
8. **Card elevation** — metric cards and chart panels have no hover lift.
9. **Accent** — no controlled accent for selected/active states.
10. **Reduced motion** — handled for CSS but would need explicit handling in any
    JS-driven counter/entrance.

---

## 4. Proposed motion architecture

**Decision: no new animation dependency.**

Motion for React is not installed. The existing `Reveal` + CSS approach already
covers entrance, and every new need (counters, progress, chart draw, tilt) is
achievable with CSS transforms, SVG `pathLength`, and a few small hooks. Adding
a ~30–60 kB animation runtime for this surface area is not justified and would
overlap the existing implementation. The dependency budget stays unchanged.

### Configuration (`src/theme/motion.ts`)

One source of truth for:

- durations (fast 140 ms, base 200 ms, slow 320 ms, reveal 620 ms, count 800 ms,
  chart 900 ms, ambient 6–9 s);
- easing (`standard`, `out`/decelerate, `inOut`);
- stagger step (70 ms) and a clamped `stagger(index)` helper;
- the ambient float range (4–8 px) and duration range;
- `prefersReducedMotion()` — returns `true` when `matchMedia` is unavailable, so
  tests and non-browser environments always render final values.

### Reusable primitives

| Name | Responsibility |
| --- | --- |
| `Reveal` (existing, extended) | Viewport entrance. Fires once, cleans up its observer. |
| `FloatingElement` | CSS-only ambient vertical float with per-instance distance/duration/delay. Disabled by reduced motion. |
| `TiltSurface` | Small pointer-responsive 3D tilt for the hero product surface only. Fine pointer + `lg` + motion allowed; off on touch/reduced motion. |
| `AnimatedNumber` | Counts from the previous displayed value to the real value; format-aware; no restart on unrelated renders; instant when motion is reduced. |
| `AnimatedProgress` | Track + fill that grows 0→real percentage, exposes `role="progressbar"` with real min/max/now, and transitions on value change. |
| `useEntrance(delay)` | One-shot mount flag that triggers CSS transitions (charts, bars, donut) and respects reduced motion. |

Naming note: the brief's `StaggerContainer`/`StaggerItem`/`FadeUp`/`FloatIn` are
not introduced as new wrapper types — the existing `Reveal` already is the
entrance primitive, and a stagger is a delay. Adding containers would create
redundant component trees for no behavioural gain.

### Motion categories → implementation

| Category | Approach |
| --- | --- |
| Page entrance | `hd-page-enter` on the keyed outlet wrapper (opacity + 6 px rise, 240 ms) |
| Section entrance | `Reveal`, once per section |
| Heading entrance | `Reveal` with staged delays (eyebrow → heading → lead → CTA) |
| Ambient float | `FloatingElement` (4–8 px, 6–9 s, varied delay) |
| Card entrance | `Reveal` with stagger on metric grids |
| Card hover | translateY(-2 px) + border/shadow token change |
| Button interaction | Existing Chakra states + press scale (CSS) |
| Chart entrance | `useEntrance` + SVG `pathLength` draw / bar `scaleX` / donut dash offset |
| Progress | `AnimatedProgress` |
| Number counting | `AnimatedNumber` |
| Navigation | Existing sidebar indicator + accent token |
| Dialog / dropdown | Existing Chakra transitions (unchanged) |
| Loading | Existing skeletons/spinners (unchanged) |
| Notification | Existing Chakra Toast transitions (unchanged) |

### Accessibility rules for the new motion

- All continuous motion is disabled under `prefers-reduced-motion: reduce`.
- Counters and progress render the exact final value immediately when motion is
  reduced; the final width always equals `value / max`.
- Progress elements carry real `aria-valuemin` / `aria-valuemax` /
  `aria-valuenow`; animated digits are `aria-hidden` with a visually hidden
  final value alongside, so assistive technology never announces intermediate
  numbers.
- Tilt is disabled for coarse pointers and below `lg`.
- No element relies on animation to become visible: the base state is the final
  state and animations only decorate the transition into it.

---

## 5. Proposed colour refinement

Current identity: page `#fafafa`, surface `#ffffff`, ink `#111111`, neutral
borders/shadows. Dark: page `#0b0b0d`, surface `#131316`, ink `#f5f5f5`.

Add one restrained cobalt accent family, used only for **selected/active
interaction**, never for decoration:

| Token | Light | Dark | Verification |
| --- | --- | --- | --- |
| `--hd-accent` | `#4a6db8` | `#93b4ff` | 5.04:1 on white / 4.82:1 on page; 9.56:1 on dark page |
| `--hd-accent-soft` | `#eef2fb` | `rgba(74,109,184,.18)` | background tint for selected rows |
| `--hd-accent-border` | `#c9d5ee` | `rgba(147,180,255,.3)` | 1 px selected outline |

The brief's suggested `#5278C7` measures 4.31:1 on white, just under the 4.5:1
text threshold, so the accent value was darkened slightly to `#4a6db8` while
keeping the same muted cobalt character. Existing semantic colours
(info/success/warning/danger) are untouched; `statusTone` and `priorityTone`
mappings stay identical, so no chart changes meaning.

Accent usage is limited to:

- the sidebar active indicator bar;
- the marketing eyebrow dot and selected showcase tab marker;
- the fill of **non-semantic** progress (assignment coverage);
- selected/active borders where a neutral border would be ambiguous.

Semantic progress (resolution → success, waiting → warning, urgent → danger)
keeps its semantic colour; the fill colour never changes during an animation.

---

## 6. Components that require change

| File | Change |
| --- | --- |
| `src/theme/tokens.css` | Accent tokens, longer motion durations, float/enter/page/chart keyframes, reduced-motion guards |
| `src/theme/palette.ts` | Export accent values |
| `src/theme/motion.ts` | **New** — central motion configuration and reduced-motion helper |
| `src/components/Reveal.tsx` | Extend with `as`, `once`, and a manual stagger-friendly API; keep current props |
| `src/components/motion/FloatingElement.tsx` | **New** |
| `src/components/motion/TiltSurface.tsx` | **New** |
| `src/components/motion/AnimatedNumber.tsx` | **New** |
| `src/components/motion/AnimatedProgress.tsx` | **New** |
| `src/hooks/useEntrance.ts` | **New** |
| `src/components/MetricCard.tsx` | Animated value, entrance, hover lift |
| `src/components/PageHeader.tsx` | Staged heading/description/actions entrance |
| `src/components/Surface.tsx` | SectionHeader entrance |
| `src/components/charts/ChartCard.tsx` | Panel entrance |
| `src/components/charts/BarChart.tsx` | 0→value bar growth, exact widths preserved |
| `src/components/charts/DonutChart.tsx` | Arc progression from 0 to real slices |
| `src/components/charts/TrendChart.tsx` | Progressive stroke draw + delayed area fill |
| `src/components/charts/Sparkline.tsx` | Draw-on-mount |
| `src/components/dashboard/AttentionList.tsx` | Animated workload progress + accessible progress semantics |
| `src/components/AppShell.tsx` | Keyed page-transition class |
| `src/components/Sidebar.tsx` | Accent active indicator |
| `src/components/marketing/primitives.tsx` | Accent eyebrow dot, hover lift on panels |
| `src/components/marketing/HeroSection.tsx` | Staged choreography |
| `src/components/marketing/ProductVisual.tsx` | Floating layers, depth stack, tilt |
| `src/components/marketing/FeatureSection.tsx` | Staggered card reveals |
| `src/components/marketing/SecuritySection.tsx` | Staggered layer reveals |
| `src/components/marketing/WorkflowSection.tsx` | Staggered steps (already delayed) |
| `src/components/marketing/CtaSection.tsx` | Reveal entrance |
| `src/components/marketing/SiteHeader.tsx` | Header settle |
| `src/components/marketing/ShowcaseSection.tsx` | Panel transition + accent tab marker |
| `src/pages/admin/AdminDashboard.tsx` | Animated metrics, entrance stagger, real-percentage progress panel |
| `src/pages/agent/AgentDashboard.tsx` | Animated metrics, stagger |
| `src/pages/customer/CustomerDashboard.tsx` | Animated metrics, stagger |

---

## 7. Performance plan

- Animate only `transform`, `opacity`, SVG stroke/dash properties and width
  where the value itself is the data (progress fill final width).
- One IntersectionObserver per `Reveal`; disconnected after first intersection.
- Counters use a single `requestAnimationFrame` loop per value, cancelled on
  unmount and cancelled/restarted only when the *target* changes.
- Bar/donut/trend entrances are one-shot CSS transitions; no loop, no timer
  pool. Ambient float is CSS-only and limited to the landing page.
- Tilt uses one pointer listener with rAF throttling, attached only on the hero
  visual and only for fine pointers at `lg+`.
- No virtualization changes; ticket tables do not animate per row.
- No new dependency, so bundle size is unchanged apart from a few kB of
  component code.

---

## 8. Verification plan

- `npm run typecheck`, `npm run lint`, `npm test`, production build with
  production-shaped env vars.
- Unit tests for: final counter value, final progress width/`aria-valuenow`,
  reduced-motion instant rendering, and that no animation changes source data.
- Browser review of the public landing page at 1440/1280/1024/768/390/360 with
  screenshots, reduced-motion mode, and console/overflow checks.
- Authenticated dashboards verified through the existing component tests plus
  source review; live login remains blocked by the absence of test credentials
  (documented, not fabricated).
- `data.md` receives the complete review.
