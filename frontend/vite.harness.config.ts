import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite-plus'

/**
 * Browser-harness config.
 *
 * `npm run dev:harness` serves `harness.html`, which renders the real app with
 * fixture HTTP responses and an in-repo Clerk stand-in (no real identity, no
 * production code path). `@clerk/react` is aliased to that stand-in so the
 * harness is fully self-contained and reproducible on any checkout.
 *
 * The alias path is derived with the web-standard `URL` API (no Node typings
 * needed), keeping this config type-clean under the project's `vite/client`
 * tsconfig without pulling `@types/node` into application code.
 */
const clerkStub = decodeURIComponent(
  new URL('./src/test/harness-clerk.tsx', import.meta.url).pathname,
)

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@clerk/react': clerkStub,
    },
  },
  // Bind explicitly to IPv4 loopback. CI runners may resolve `localhost` to
  // IPv6 (::1) first, so a probe against 127.0.0.1 would never connect.
  server: { host: '127.0.0.1', port: 5183, strictPort: true },
})
