# HelpDesk — UI Width, Motion & Premium Interaction Report

- **Date:** 2026-11-22
- **Branch:** `feat/helpdesk-ui-width-motion-polish`
- **Base:** `main` @ `5a379d9` (merge of PR #27)
- **PR target:** `main`
- **Scope:** frontend-only. No backend, database, auth, or infrastructure changes.

This report describes what was actually implemented and verified in a real
browser against the seeded data shape. Anything that could not be exercised is
called out instead of implied.

---

## 1. Initial findings — the width problem

The symptom ("parts of the interface only use half the workspace") was not a
`50%` width and not a broken grid. It was a **single container cap**:

- The authenticated shell (`AppShell`) wrapped every page in
  `<Container size='content'>`, and `widths.content` was **`1200px`**.
- At 1920 px the fixed 256 px sidebar leaves a **1664 px** main column, but the
  container clamped it to 1200 px, centred, leaving **~232 px of dead space on
  each side**.
- At 1600 px it left ~72 px of dead space per side. At ≤1440 px the cap never
  bound, so the problem only appeared on the wide displays where the screen
  clearly had more room.

Measured before the fix (DOM geometry, 1000 px tall viewport):

| Viewport | Sidebar | Main column | Content container | Dead space / side |
| --- | --- | --- | --- | --- |
| 1366 | 256 | 1110 | 1110 | 0 |
| 1440 | 256 | 1184 | 1184 | 0 |
| 1600 | 256 | 1344 | 1200 | 72 |
| 1920 | 256 | 1664 | 1200 | 232 |

A second, compounding defect: the dashboard **composition row** was a fixed
`lg:3` grid. At 1024 px three chart cards were squeezed to ~177 px of inner
width each — which is what made charts look "half width". The five KPI cards
had the same problem (`lg:5` gave ~128 px cards at 1024 px).

A third defect surfaced during testing: the visually-hidden chart data table
(the accessible fallback) is a real `<table>`; with `width: 1px` on the table
itself it still expanded to its *min-content* width, pushing the document wider
than the viewport at some column widths. And a mobile filter tab strip
overflowed horizontally at 390 px.

---

## 2. Root cause of the width problem

`frontend/src/theme/layout.ts`:

```ts
export const widths = {
  content: '1200px', // ← used by the authenticated shell
  ...
}
```

and `frontend/src/components/AppShell.tsx`:

```tsx
<Container size='content' py={{ base: '6', md: '8' }}>
```

The marketing measure (1200 px) was reused for the application workspace, even
though the workspace has a different amount of available width and a different
job (tables and charts, not body copy).

---

## 3. Layout improvements

### 3.1 A dedicated workspace container

- Added `widths.workspace = '1680px'` and `widths.detail = '1120px'` to
  `theme/layout.ts`, plus a `workspaceGutter` scale (tighter on phones, roomier
  on 2xl).
- `Container` gained a `workspace` size that uses that gutter; the default
  `content` measure is unchanged for marketing.
- `AppShell` now uses `<Container size='workspace'>`.

Result: the workspace **fills the available main column** and only caps at
1680 px on ultra-wide displays. At 1920 px the content is now 1664 px
(dead space 0) instead of 1200 px.

Measured after the fix:

| Viewport | Main column | Content container | Overflow |
| --- | --- | --- | --- |
| 390 | 390 | 390 | none |
| 768 | 768 | 768 | none |
| 1024 | 768 | 768 | none |
| 1280 | 1024 | 1024 | none |
| 1366 | 1110 | 1110 | none |
| 1440 | 1184 | 1184 | none |
| 1600 | 1344 | 1344 | none |
| 1920 | 1664 | 1664 | none |

### 3.2 Responsive chart and metric grids

`pages/admin/AdminDashboard.tsx`:

- KPI row: `base:2 → md:3 → xl:5` (was `base:2 → lg:5`, giving 128 px cards at
  1024). Cards are now ~221 px at 1024 px.
- Composition row: `base:1 → md:2 → 2xl:3` (was `lg:3`). At 1024 px the charts
  are now ~336 px wide instead of ~177 px; they only return to three columns on
  genuinely wide displays (≥1536 px), where 512–544 px per chart is comfortable.

### 3.3 Detail pages

- `AccountRequestDetailPage` used `maxW='container.lg'` (the Chakra scale, *not*
  an app token) which capped the whole request at ~1024 px regardless of the
  viewport. It now uses `widths.detail` (1120 px) and an explicit `w='full'`, so
  it aligns to the workspace and stops floating narrow on wide displays.
- Verified detail (`/tickets/:id`), messages, owner inbox and user-detail pages
  use the wide shell and report no overflow at any tested width.

### 3.4 Overflow fixes

- `ChartDataTable` (accessible chart fallback): the clipping box is now the
  outer wrapper and the `<table>` lives inside it. Positioning + clipping the
  outer box contains the table's intrinsic width, so it can no longer widen the
  document. (Caught at 1024 px.)
- Notifications and queue tab strips: added an `hd-tabs-scroll` class
  (`overflow-x:auto`, contained overscroll, hidden scrollbar) and `minW='0'` on
  the tab roots. The Account-requests tab row no longer overflows at 390 px.

---

## 4. Chart and tooltip enhancements

No chart library was added. The existing hand-built SVG charts were kept and
their interaction layer was enriched.

### 4.1 Status composition (donut)

- A rich, positioned tooltip now appears on hover **and** keyboard focus of a
  segment or a legend row, showing:
  - status name and colour dot,
  - the exact ticket count (tabular figures),
  - the share of *all* tickets (e.g. "9% of 300 tickets"),
  - a one-line explanation of what the status means.
- Values are always real API numbers; percentages are computed from the same
  totals rendered elsewhere on the page, so the panel, the legend, the centre
  label and the accessible table cannot disagree.
- The donut now measures its own container width and **stacks the legend below
  the ring** when the card is narrow (≤424 px), fixing a case where legend
  labels collapsed to 0 px at 1024 px. It goes side-by-side when the card is wide.

### 4.2 Priority / category bars

- Hover and keyboard focus on an actionable row (priority mix) opens the same
  style of rich tooltip: label, exact count, share of total, and a short
  meaning line (e.g. "Blocking the requester; handle first.").
- Non-actionable rows (category mix) keep the hover panel as an enhancement but
  stay out of the tab order, because their exact counts and shares are already
  printed in the row and mirrored in the accessible data table.

### 4.3 Trend chart

- The existing hover readout (created vs resolved for the hovered day) was kept
  — it is already the correct interaction for a two-series line — and its
  surface was aligned to the new tooltip styling.

### 4.4 Tooltip positioning (shared)

- `lib/tooltipPosition.ts` provides pure placement math: prefer the right side,
  flip left at the edge, clamp on both axes, keep a 4 px safety padding, and
  never return a negative offset when the panel is wider than its container.
  It is unit-tested (6 cases).
- `components/charts/ChartTooltip.tsx` is rendered **inside the chart's own
  wrapper** (not a portal), so it can never be clipped by a card or hidden
  behind the next grid cell. `pointer-events: none` means moving toward it never
  flickers or steals the hover.
- Verified in-browser: at 390, 1024, 1280, 1366 and 1920 px, hovering "In
  progress" produced `In progress · 27 tickets · 9% of 300 tickets · <meaning>`
  with the panel fully inside both its host and the viewport.

---

## 5. Cursor interaction improvements

The project deliberately ships **no animation library** (confirmed against
`package.json` and the lockfile: no `motion`, no `framer-motion`). Rather than
add a dependency for a few interactions, the existing CSS + `requestAnimationFrame`
motion system was extended.

### 5.1 Spring-followed card spotlight

- New `hooks/usePointerSpotlight.ts` integrates a **critically-damped spring**
  per axis (stiffness 170, damping 26) inside a single rAF loop and writes
  `--hd-pointer-x/y/glow/radius` straight to the node's style. Because it never
  calls `setState`, moving the pointer **never re-renders the card or its
  charts**.
- New `components/PointerHighlight.tsx` paints a soft radial light **above** the
  opaque card surface (a glow behind an opaque panel would be invisible). At the
  default intensity the peak is ~20% of a low-alpha accent and fades to nothing
  at the edge — subtle, and with no measurable effect on text contrast.
- Applied only to **interactive** metric cards (the ones that navigate). Inert
  cards skip it, so the highlight never implies a click that is not there.
- The loop **stops itself** when the spring settles. Measured idle rAF after
  settle: **0 frames/second**. On leave it returns to rest and clears its inline
  values, leaving no faint residue.

### 5.2 Tilt surface (landing page)

- `components/motion/TiltSurface.tsx` (marketing product visual only) was
  upgraded from a fixed CSS easing to the same **spring integration**, so the
  tilt follows the pointer with a short, natural settle and zero overshoot. The
  4° cap, fine-pointer-only, ≥1024 px-only and reduced-motion guards are
  unchanged.

### 5.3 Hover / focus consistency

- Chart rows, legend rows, metric cards, navigation, buttons and tables already
  had hover/focus states; those were preserved. New interactive chart rows reuse
  the same `--hd-dur-1/-2` tokens and the shared focus-ring style, rather than
  inventing new timings.

---

## 6. Accessibility

- **Reduced motion:** `usePointerSpotlight` and `TiltSurface` bail out when
  `prefers-reduced-motion: reduce` is set. The global Chakra reduced-motion rule
  already zeroes animation/transition durations; the new `hd-tooltip-in`
  entrance was added to both the `prefers-reduced-motion` block in `tokens.css`
  and the global rule. Verified in a `reducedMotion: 'reduce'` browser context:
  the page-enter animation resolves to `1e-06s` and the spotlight writes nothing.
- **Keyboard:** tooltips are reachable by focusing a chart row/segment; the
  panel anchors to the focused element. Verified in-browser by focusing the
  "Urgent" priority row with the keyboard and reading the same panel content.
- **Touch:** pointer effects are disabled on coarse pointers
  (`pointer: fine` gate), so nothing depends on hover on phones. The printed
  counts, shares and the visually hidden `<table>` remain the source of truth.
- **Screen readers:** chart SVGs stay `aria-hidden`; the visually hidden data
  tables (still present, now correctly contained) carry real rows and headers.
  Tooltips are `aria-hidden` because they duplicate data the SR already has,
  which also stops double announcements.

---

## 7. Performance

- **No new runtime dependency.** The new interactions reuse the existing CSS +
  rAF approach; the production bundle gained no animation library.
- **No React renders on pointer movement:** the spotlight writes CSS custom
  properties from a ref'd node; charts keep memoized geometry.
- **No idle animation loop:** the spring cancels itself once settled (measured
  0 idle rAF/s). Cleanup removes every listener and inline property on unmount
  (asserted by a hook test).
- **Composited properties only:** pointer effects animate `transform`/custom
  properties consumed by a `radial-gradient` overlay and `opacity`; tooltips
  animate `opacity` + a 3 px `translateY`/`scale`. No width/height/top/left
  animation.
- **Charts remain dependency-free SVG** sized 1:1 from `ResizeObserver`, so the
  wider layout redraws the real data at the new width without distortion.

---

## 8. Responsive verification

Automated DOM-geometry sweep (Playwright + the project's fixtures harness) over
`390, 430, 768, 1024, 1280, 1366, 1440, 1600, 1920` px and the routes
`/dashboard, /admin, /admin/users, /tickets, /profile, /notifications, /queue,
/messages, /account-requests`:

- **Horizontal overflow:** 0 rows (was 3: `/notifications` @390, `/admin` and
  `/dashboard` @1024).
- **Console errors / React warnings:** none on any tested route/viewport
  (404s from deliberately unhandled harness endpoints filtered out).
- **Donut layout:** side-by-side on wide cards, stacked below ≤424 px; legend
  labels always render with real width (fixed the 0 px case at 1024 px).
- **Tooltips:** fully inside host and viewport at every tested width.

The fixture harness (`frontend/harness.html`, `src/harness-*.tsx`,
`vite.harness.config.ts`) routes requests to a local stub with the *shape* of the
seeded analytics payload so layout can be exercised without the live API. It is
**not** part of the app bundle and is not referenced by `main.tsx`. See the
deployment note in §10 — it is kept uncommitted to keep the PR frontend-only.

---

## 9. Quality checks

Run in `frontend/` on the final tree:

| Check | Command | Result |
| --- | --- | --- |
| TypeScript | `npm run typecheck` | pass |
| Lint | `npm run lint` | pass |
| Unit tests | `npm test` | **148 passed / 18 files** (was 136 / 16) |
| Production build | `npm run build` (with CI-style env) | pass |

New tests added:

- `src/lib/tooltipPosition.test.ts` — 6 placement/clamping cases.
- `src/hooks/usePointerSpotlight.test.tsx` — 4 cases: no listeners under
  reduced motion, coarse pointers, narrow viewports; full listener cleanup on
  unmount.
- `src/components/charts/dataAccuracy.test.tsx` — 2 donut cases: real count and
  share exposed for the focused slice; accessible table still exact.

Existing tests were not modified to force a pass; the two new donut cases were
added alongside them.

---

## 10. GitHub delivery

- Branch: `feat/helpdesk-ui-width-motion-polish` (base `main` @ `5a379d9`).
- Commit: `e6863fb` — `feat(frontend): widen workspace and add rich chart motion
  interactions`.
- PR: **https://github.com/mdjayedgazi/HelpDesk/pull/28** (targets `main`).
- CI (all pass): Backend lint + SQLite tests, Frontend typecheck/lint/tests/build,
  Alembic migrations, PostgreSQL integration, Docker image builds, Production
  dependency audit, Helm validation, Static security + secret scan, CodeQL,
  Trivy. CodeRabbit skipped review (manual review required for this OSS repo).

Note: the local ignored files `frontend/harness.html`,
`frontend/src/harness-main.tsx`, `frontend/src/harness-fixtures.ts` and
`frontend/vite.harness.config.ts` are verification tooling. They are **not**
committed, so the PR contains only production frontend changes.

---

## 11. Deployment status

**Not deployed. Awaiting review and merge.**

- No merge into `main` was performed.
- No production deployment was triggered.
- Verified Railway configuration (from `docs/RAILWAY_COLLEGE_DEMO.md`,
  `docs/DEPLOYMENT.md`, `frontend/Dockerfile`):
  - `helpdesk-web` is a dashboard-configured service (no `railway.toml/json`);
    repository root `/frontend`, built from `frontend/Dockerfile`
    (`npm ci && npm run build`).
  - Production deployment branch: **`main`**, **automatic** on push.
  - **Wait for CI** (`checkSuites=true`) gates deployment on required GitHub
    checks, so a failing `main` commit is not released.
  - Frontend healthcheck: `/healthz` on container port `8080`
    (`nginx.conf.template`).
  - No branch/PR preview-deployment mechanism exists.
- Expected post-merge behaviour: merging this PR to `main` triggers CI; once the
  required checks pass, Railway's `main` deployment builds and releases the
  frontend automatically. This branch has **not** entered that path.
- Post-deployment checklist:
  1. `/health/ready` on the API returns 200 (`database/redis ok`).
  2. `/dashboard` at ≥1600 px fills the main column (no ~230 px side gutters).
  3. Hovering an "Open" donut segment shows real count + share.
  4. Hovering/focusing a priority bar shows the rich tooltip; it is not clipped.
  5. Metric-card spotlight is subtle and disappears on leave; with OS reduced
     motion enabled it does not appear at all.
  6. No horizontal scrollbar at 390 px.
