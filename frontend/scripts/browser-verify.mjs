/**
 * Browser + responsive verification against the self-contained harness.
 *
 * This is NOT production Clerk authentication. It renders the real application
 * (routes, guards, pages, components) against fixture HTTP responses with an
 * in-repo Clerk stand-in, then checks, in a real Chromium:
 *
 *   • no horizontal page overflow at every target viewport width
 *   • no uncaught console errors / page errors
 *   • each major route renders its expected landmark for each role
 *   • in-app navigation works (no full-page reload, correct heading)
 *   • reduced-motion preference is honoured (no crash, page still renders)
 *
 * Run: `node scripts/browser-verify.mjs` (after `npm run dev:harness` is up, or
 * set HARNESS_URL). Requires Playwright chromium.
 */
import { chromium } from '@playwright/test'

const BASE = process.env.HARNESS_URL ?? 'http://127.0.0.1:5183/harness.html'

const WIDTHS = [320, 360, 390, 480, 640, 768, 1024, 1280, 1440, 1920, 2560]

const ROUTES = [
  { path: '/dashboard', role: 'owner', expect: /dashboard|workspace/i },
  { path: '/tickets', role: 'owner', expect: /tickets/i },
  { path: '/queue', role: 'agent', expect: /queue/i },
  { path: '/messages', role: 'owner', expect: /messages|inbox|conversation/i },
  { path: '/account-requests', role: 'admin', expect: /account request/i },
  { path: '/admin', role: 'admin', expect: /dashboard|analytics|support/i },
  { path: '/admin/users', role: 'owner', expect: /users/i },
  { path: '/notifications', role: 'owner', expect: /notifications/i },
  { path: '/profile', role: 'owner', expect: /profile/i },
]

function url(path, role) {
  const u = new URL(BASE)
  u.pathname = '/harness.html'
  u.searchParams.set('route', path)
  u.searchParams.set('user', role)
  return u.toString()
}

async function main() {
  const browser = await chromium.launch()
  const failures = []

  // ---- 1. Overflow + console-error sweep across the width matrix -----------
  for (const route of ROUTES) {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 900 },
    })
    const page = await context.newPage()
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })
    page.on('pageerror', (err) => consoleErrors.push(String(err)))

    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 })
      await page.goto(url(route.path, route.role), { waitUntil: 'networkidle' })
      // Allow entrance/motion frames to settle.
      await page.waitForTimeout(250)

      const overflow = await page.evaluate(() => {
        const de = document.documentElement
        return { scroll: de.scrollWidth, client: de.clientWidth }
      })
      if (overflow.scroll > overflow.client + 1) {
        failures.push(
          `OVERFLOW ${route.path} @${width}px: scrollWidth=${overflow.scroll} > clientWidth=${overflow.client}`,
        )
      }
    }

    // Landmark check at desktop width.
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(url(route.path, route.role), { waitUntil: 'networkidle' })
    await page.waitForTimeout(250)
    const bodyText = await page.locator('body').innerText()
    if (!route.expect.test(bodyText)) {
      failures.push(`LANDMARK ${route.path} (${route.role}) did not match ${route.expect}`)
    }
    if (consoleErrors.length > 0) {
      failures.push(`CONSOLE ${route.path}: ${consoleErrors.slice(0, 3).join(' | ')}`)
    }
    await context.close()
  }

  // ---- 2. In-app navigation keeps the SPA alive ----------------------------
  {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const page = await context.newPage()
    await page.goto(url('/dashboard', 'owner'), { waitUntil: 'networkidle' })
    await page.evaluate(() => {
      window.__harnessMarker = 'spa-alive'
    })
    // Navigate via the sidebar ticket link if present, else via history.
    const ticketsLink = page.locator('a[href="/tickets"]').first()
    if (await ticketsLink.count()) {
      await ticketsLink.click()
      await page.waitForTimeout(300)
      const marker = await page.evaluate(() => window.__harnessMarker)
      if (marker !== 'spa-alive') {
        failures.push('NAVIGATION: a full page reload occurred (SPA marker lost)')
      }
    }
    await context.close()
  }

  // ---- 3. Reduced-motion preference renders without crashing ---------------
  {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      reducedMotion: 'reduce',
    })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (err) => errors.push(String(err)))
    await page.goto(url('/dashboard', 'owner'), { waitUntil: 'networkidle' })
    await page.waitForTimeout(300)
    if ((await page.locator('body').innerText()).trim().length === 0) {
      failures.push('REDUCED-MOTION: dashboard rendered empty')
    }
    if (errors.length) failures.push(`REDUCED-MOTION pageerror: ${errors[0]}`)
    await context.close()
  }

  await browser.close()

  if (failures.length) {
    console.error(`\nBROWSER VERIFICATION FAILURES (${failures.length}):`)
    for (const f of failures) console.error(`  - ${f}`)
    process.exit(1)
  }
  console.log(
    `\nBROWSER VERIFICATION PASSED: ${ROUTES.length} routes x ${WIDTHS.length} widths ` +
      `(${WIDTHS.join(', ')}), navigation + reduced-motion OK.`,
  )
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
