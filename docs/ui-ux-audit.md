# HelpDesk — UI/UX Audit

Audit date: 2026-11-21
Branch audited: `main` @ `19a79c9` (working tree dirty: `data.md` emptied — left untouched)
Auditor: frontend modernization pass (Phase 1)

Everything below was verified from source, from the running production site, or
from both. Where something could not be verified it is called out explicitly.

---

## 1. Repository state and deployment

| Item | Finding |
| --- | --- |
| Current branch | `main` |
| Remote | `origin` → `https://github.com/mdjayedgazi/HelpDesk.git` |
| Working tree | `data.md` modified (717 lines deleted, 0 bytes now). Pre-existing; **not** touched or restored. |
| Last commits | `19a79c9` merge of PR #21, `bd596f8` merge of PR #20, `2ca6930` merge of PR #19 |
| PR #19 | `fix/production-readiness` → `main`, **MERGED** at 2026-11-21T12:06:07Z, merge commit `2ca6930`. Not modified. |
| PR #20, #21 | Merged. No open PRs remain. |
| Base branch for this work | `main` |
| Feature branch | `feat/helpdesk-ui-ux-modernization` (new, created from `main`) |

There is no open pull request to conflict with, and no unmerged local work other
than the emptied `data.md`. That file is preserved exactly as found.

### Production deployment

`https://helpdesk-web-production-d96f8e2b.up.railway.app` responded **200** in
~1.7 s. It serves the same Vite bundle shape as `main` (hashed ESM entry plus
lazy route chunks and the `theme-init.js` bootstrap), so the deployed frontend
matches the current `main` architecture. The exact deployed commit SHA cannot be
confirmed from the running site (no build metadata endpoint is exposed).

Deployment profile per `docs/RAILWAY_COLLEGE_DEMO.md`: Railway web + API,
Neon Postgres, Upstash Redis, Clerk **development** instance, and
`ATTACHMENTS_ENABLED=false` (no malware scanner).

---

## 2. Frontend architecture (verified)

| Concern | Implementation |
| --- | --- |
| Framework | React **19.3.1**, `react-dom` 19.3.1 |
| Build | Vite Plus (`vite-plus` 1.2.0 → `@voidzero-dev/vite-plus-core`), TypeScript ~6.0.2 |
| Routing | `react-router-dom` **7.18.4**, `BrowserRouter`, lazy route chunks via `React.lazy` in `src/App.tsx` |
| Component system | Chakra UI **3.37.0** (`createSystem`) + Tailwind **utilities only** (preflight deliberately omitted) |
| Icons | `lucide-react` 1.58.0 |
| Data | `@tanstack/react-query` 5.104.3, central `queryKeys`, `queryClient` with 15 s stale time |
| Forms | `react-hook-form` 7.90.0 + `zod` 4.6.7 + `@hookform/resolvers` |
| Auth | Clerk (`@clerk/react` 6.17.8). Backend is the authorization source of truth |
| Charts | **None installed** |
| Animation | Hand-written CSS keyframes in `src/theme/tokens.css` + an `IntersectionObserver` `Reveal` component. No motion library. |
| Tests | Vitest via `vp test` (jsdom). 8 files / 52 tests. No E2E runner in the repo or CI. |
| Lint/format | `vp lint` (oxlint, type-aware) and `vp fmt` (oxfmt) |

### Design tokens that already exist

`src/theme/tokens.css` defines a complete light/dark token set as CSS custom
properties (`--hd-page`, `--hd-surface`, `--hd-text*`, `--hd-border*`,
`--hd-ink`, shadows, layout widths). `src/theme/palette.ts` re-exports them under
stable names, and `src/theme/system.ts` maps them into Chakra semantic tokens.

Important finding: `system.ts` deliberately collapses **every** semantic colour
(`error`, `success`, `warning`, `info`) onto grayscale `--hd-inset`. That is a
good guardrail against accidental rainbow accents, but it also means:

- form validation errors are visually indistinguishable from helper text;
- status/priority carry **no** semantic colour, only an icon + label;
- charts (if added) would have no approved colour vocabulary.

One defect: `palette.logo` is a hard-coded `rgba(11,11,13,0.74)` value rather
than a themed custom property, so the logo plate does not flip in dark mode
(it is the only non-token colour in the palette).

### Typography

Both the Chakra system and the Clerk widget appearance use:

```
Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif
```

No `@font-face`, no Google Fonts link, no font asset in `public/`. The family is
therefore **declared** as Inter but rendered with the system UI font wherever
Inter is not installed. This is the existing typographic identity and it must be
preserved verbatim (no new font, no asset download). Type sizes in use range
from 10 px (`2xs`) to 60 px (hero `h1`); body text is `font-size: sm` (14 px).

### Routing and authorization

Public: `/`, `/sign-in/*`, `/sign-up/*`.
Protected (`ProtectedLayout`): `/dashboard`, `/tickets`, `/tickets/new`
(customer only), `/tickets/:id`, `/queue` (agent only), `/notifications`,
`/profile`, `/messages`, `/account-requests[/:id]`, `/admin`,
`/admin/users[/:id]`, plus `*` → 404.

Authorization is layered: Clerk proves identity; the backend returns the
application `role`; `RoleGate` only shapes navigation. Every backend endpoint
re-checks the role. This is correct and must not change.

### Role model (backend-verified)

- `customer` — own tickets, public comments, feedback, own profile.
- `agent` — assigned tickets + unassigned queue, comments (incl. internal),
  account-request creation, private Owner messaging.
- `admin` — all tickets, assignment, user directory (read), account-request
  review, admin dashboard.
- `owner` — everything an admin can do, **plus** the only role that can change
  roles/activation and the only recipient/author of owner-inbox broadcasts.

---

## 3. Backend capability audit (what the UI can honestly show)

Verified against routers and schemas.

### Available today

| Capability | Endpoint | Notes |
| --- | --- | --- |
| Ticket list (role-scoped) | `GET /api/v1/tickets` | `status`, `priority`, `category`, `assignee_user_id`, `created_by_user_id`, `q` (title only), `limit ≤ 100`, `offset` |
| Assigned tickets | `GET /api/v1/tickets/assigned` | agent only |
| Ticket detail | `GET /api/v1/tickets/{id}` | 404 for invisible tickets (no existence leak) |
| Mutations | `PATCH`, `claim`, `assign` | server-validated transition graph |
| Comments | `GET/POST /tickets/{id}/comments` | `is_internal` hidden from customers |
| History | `GET /tickets/{id}/history` | staff only, newest first |
| Attachments | list/upload/download | download requires `scan_status = CLEAN`; upload disabled in the demo profile |
| Notifications | list, unread count, mark one/all | count bucketed by `tickets/messages/account_requests` |
| User directory | `GET /api/v1/users` | admin/owner only |
| Admin dashboard | `GET /api/v1/admin/dashboard` | `total_tickets`, `tickets_by_status`, `tickets_by_priority`, `total_users`, `active_agents` |
| Assignable agents | `GET /api/v1/admin/agents` | active agents |
| Feedback | `GET/POST /tickets/{id}/feedback` | customer-only submission on `RESOLVED` |
| Staff/owner messaging | `/staff-messages`, `/internal-messages` | role-segregated |

### Not available (so must **not** be shown as real)

- Time-series of ticket volume. The dashboard returns only current totals.
- Per-agent workload / resolution counts.
- CSAT aggregate, SLA states, at-risk/breached tickets, remaining time.
- "Average first response" or "average resolution" — derivable from timestamps
  but not exposed by any endpoint.
- Ticket category distribution in the dashboard payload (the field exists, the
  aggregate does not).
- Global search beyond the ticket title.

**Decision:** the existing `/admin/dashboard` totals cannot support the required
visual analytics without inventing numbers. Because the requirement is a real
visual analytics experience, this pass adds a **read-only, role-guarded
aggregate endpoint** (`GET /api/v1/admin/analytics`). It introduces no schema
change, no migration and no change to any existing business rule: it only runs
`SELECT … GROUP BY` over columns that already exist. Everything it returns is
real data. Where a metric genuinely cannot be computed (SLA), the UI states the
limitation rather than faking it.

---

## 4. Browser audit (production)

Method: Playwright (Chromium) against the production URL at 1440×900, 1280×800,
768×1024, 390×844 and 360×780; DOM/computed-style inspection plus screenshots
saved in `docs/ui-ux-audit-assets/before/`.

### Results that were verified

| Check | Result |
| --- | --- |
| HTTP status | 200 |
| Console / page errors | none |
| Horizontal overflow @ all 5 widths | none (`scrollWidth == clientWidth`) |
| Section order | hero → features → product → how-it-works → security → CTA → footer |
| `<h1>` | "Customer support, without the chaos." |
| Heading scale | h1 60 px, h2 36 px, h3 24 px (desktop) |
| Unlabelled inputs (home) | 0 |
| Images without `alt` | 0 |
| Buttons with no accessible name | 0 |
| Nav section links | 21 px tall (below the 24 px target-size guidance) |
| `/dashboard`, `/tickets` while anonymous | redirect to `/sign-in` (correct) |
| Attachments demo notice | present on ticket detail (honest limitation) |

Accessibility limits: no authorized Clerk test account was available, so
authenticated screens (dashboard, ticket detail, admin, owner) were **not**
exercised against production. This was also recorded as unverified in
`docs/FINAL_PRODUCTION_READINESS_REPORT.md` (L6). Role dashboards were therefore
reviewed from source and from the local build only.

### Problems found

**Shell / navigation**

1. Admin & owner sidebars are five sections with overlapping concepts
   ("Overview → Dashboard" next to "Administration → Admin overview"), and both
   routes render the same component. Redundant, low-clarity navigation.
2. No breadcrumbs anywhere except a single hand-written one on ticket detail.
3. The active sidebar state is a flat grey fill; hierarchy between sections and
   items is weak.
4. Top bar repeats the page title on desktop but has no context (workspace, role,
   or scope).

**Dashboards**

5. Admin/owner dashboard is 5 metric tiles + 2 identical proportional-bar lists.
   No trend, no queue depth, no unassigned/aging signal, no team workload — it
   does not answer "what needs attention now".
6. Agent dashboard shows three counts and five rows. No priority/urgency
   signal, no overdue/aging view, no queue load.
7. Customer dashboard shows four counts and five rows; "waiting on you" is good
   but invisible in the tile (no direct link), and there is no status
   composition view.
8. All three roles share the same visual pattern, so the workspace never signals
   what the role is for.

**Tickets**

9. Ticket rows put `#1234` and the title on one line and then repeat
   status/priority on small screens; scannability of the list is limited by 10 px
   metadata and no requester context on mobile.
10. Ticket detail's conversation, attachments, feedback and metadata are
    separated by uniform panels; the conversation does not visually dominate and
    internal vs public messages rely on a dashed chip.
11. Filters have no active-filter summary (only a "Filters applied" text) and no
    way to clear all filters at once.

**Landing page**

12. Hero product visual is a static mock with decorative floating cards; it does
    not demonstrate analytics, and three of the four "features" are icon + text.
13. Motion is limited to a scroll reveal and two floating cards; there is no
    entrance choreography for the header or a state transition for the product
    tour.
14. Section rhythm is even but flat: every band is the same surface value, so
    the page has no depth hierarchy.
15. The hero CTA pair and the closing CTA are duplicated with slightly different
    wording ("Get started" / "Make every support conversation count").

**Design system**

16. No semantic status/priority colour vocabulary (all grayscale).
17. `palette.logo` is not theme-aware.
18. No motion tokens (durations/easings are repeated inline in several
    components).
19. No chart primitives at all, so any dashboard work would otherwise ship
    one-off markup.

---

## 5. Reference analysis (applied as principles only)

Studied the supplied references for **information design**, not for visual
copying:

- **Unex helpdesk**: a compact metric row followed by one dominant trend chart,
  then status composition and a workload strip; each widget answers one
  operational question. Adopted: metric → trend → composition → queue order.
- **Help-desk ticket management / admin dashboard references**: filterable
  operational tables and role-separated navigation.
- **Linear**: restrained surfaces, dense-but-airy rows, tiny type only for
  metadata, motion used for state change rather than decoration.
- **Stripe**: neutral chrome with colour reserved for meaning; charts with
  honest axes and legends.
- **Zendesk**: practical support vocabulary (queue, assignment, waiting on
  customer) over marketing language.

Deliberately **not** adopted: green brand palette, glossy gradients, large
decorative hero cards, glassmorphism, floating 3D shapes, oversized dashboard
numbers.

---

## 6. Design direction for this pass

**Linear's interaction quality + Stripe's information clarity + Zendesk's support
practicality**, on top of the existing monochrome identity.

Concretely:

1. **Keep**: font stack and loading, black/white/grey foundation, page
   background, ink primary action, 4/6/8/12/16 px radii, flat 1 px borders,
   container widths (1200/1440), existing route and permission behaviour.
2. **Add**: a controlled semantic vocabulary — blue = informational, green =
   resolved/healthy, amber = waiting/warning, red = urgent/critical, neutral =
   inactive — used *only* for status, priority and data visualisation. Colour is
   always paired with an icon and a text label.
3. **Add**: chart tokens (series colours + grid/axis) and motion tokens
   (durations/easings), so no component invents its own values.
4. **Build** a tiny in-house SVG chart kit (area/line, donut, horizontal bars,
   sparkline) instead of adding a chart dependency. Requirements: responsive,
   accessible (`role="img"` + text summary + table fallback), loading/empty/error
   aware, semantic colours, no misleading scales.
5. **Restructure** the dashboards by role so each one answers its own question:
   - Owner/Admin: operational command centre — headline metrics, 14-day volume
     trend, status composition, priority pressure, unassigned/aging queue, team
     workload, category mix.
   - Agent: my workload — assigned active, urgent, waiting on customer, queue
     depth, worklist.
   - Customer: my requests — totals, awaiting-reply, resolved, status
     composition, recent tickets, create action.
6. **Tighten** the shell: one coherent admin navigation (drop the duplicate
   "Admin overview"), consistent active states, contextual page header, mobile
   drawer parity, and a visible focus ring on every interactive element.
7. **Landing page**: keep the sections that already communicate something, raise
   the hero's information quality, make the product preview an honest *sample*
   of the real dashboard, and use one motion vocabulary (entrance + scroll
   reveal + state transition) with `prefers-reduced-motion` respected.

---

## 7. Components that must not change behaviour

`ProtectedLayout`, `RoleGate`, `navSectionsForRole` role routing, `useApi`,
`ApiClient`, `queryKeys`, `queryClient`, `useMe`, every mutation hook, the
comment composer's `is_internal` handling, the attachment `scan_status` gate,
the status-transition map in `TicketDetailPage`, Clerk configuration, and all
backend authorization.

`App.tsx` route paths stay identical. The only app-level addition is a nested
admin route structure that preserves every existing URL.

---

## 8. Implementation plan

| # | Work | Risk |
| --- | --- | --- |
| 1 | Design tokens: semantic status/priority/chart colours, motion tokens, fix `palette.logo`; map them into Chakra | Low |
| 2 | Backend: additive read-only `GET /api/v1/admin/analytics` + schema + pytest coverage | Low (no schema/migration change) |
| 3 | Chart kit: `ChartCard`, `TrendChart`, `DonutChart`, `BarChart`, `Sparkline`, `ChartLegend`, accessible fallbacks | Medium (new code) |
| 4 | Dashboard components: `MetricCard`, `InsightRow`, `WorkloadList`, role dashboards | Medium |
| 5 | Shell: sidebar sections/active states, top bar context, mobile drawer, page header breadcrumbs | Medium |
| 6 | Ticket list/detail hierarchy and states | Medium |
| 7 | Landing page hero/preview/sections/motion | Medium |
| 8 | QA: typecheck, lint, unit tests, build, Playwright responsive + overflow + a11y checks | — |

### Explicit limitations carried forward

- No SLA tracking exists → the UI will not claim SLA compliance.
- No first-response metric endpoint → not shown.
- Authenticated production flows cannot be exercised without authorized test
  credentials → verified from source, unit tests and local build only.
- Attachments remain disabled in the demo deployment; the existing honest notice
  is preserved.
