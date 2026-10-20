/**
 * Temporary Vite config for isolated browser QA.
 *
 * Aliases Clerk to a local stub, points the app at the QA API through the dev
 * proxy, and serves on a dedicated port. Never used by the normal dev/build
 * pipeline; deleted after verification.
 */
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite-plus'

const clerkStub = fileURLToPath(
  new URL('./src/qa-harness/clerk-stub.tsx', import.meta.url),
)

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@clerk/react': clerkStub,
    },
  },
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8030',
        changeOrigin: false,
      },
    },
  },
})
