import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite-plus'

function assertProductionEnvironment(env: Record<string, string>) {
  const apiUrl = env.VITE_API_URL?.trim()
  if (!apiUrl) throw new Error('VITE_API_URL is required for a production build')

  let parsed: URL
  try {
    parsed = new URL(apiUrl)
  } catch {
    throw new Error('VITE_API_URL must be an absolute URL')
  }
  if (parsed.protocol !== 'https:') {
    throw new Error('VITE_API_URL must use HTTPS in production')
  }
  if (['localhost', '127.0.0.1', '0.0.0.0', '::1'].includes(parsed.hostname)) {
    throw new Error('VITE_API_URL must not point at localhost in production')
  }
  if (parsed.pathname !== '/' || parsed.search || parsed.hash) {
    throw new Error('VITE_API_URL must be an origin without a path, query, or hash')
  }
  if (!env.VITE_CLERK_PUBLISHABLE_KEY?.trim()) {
    throw new Error('VITE_CLERK_PUBLISHABLE_KEY is required for a production build')
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'VITE_')
  if (mode === 'production') assertProductionEnvironment(env)

  return {
    plugins: [react(), tailwindcss()],
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.{test,spec}.{ts,tsx}'],
      restoreMocks: true,
    },
    fmt: {
      semi: false,
      singleQuote: true,
      jsxSingleQuote: true,
    },
    lint: {
      jsPlugins: [{ name: 'vite-plus', specifier: 'vite-plus/oxlint-plugin' }],
      rules: { 'vite-plus/prefer-vite-plus-imports': 'error' },
      options: { typeAware: true, typeCheck: true },
    },
  }
})
