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
      // The default 5s is too tight when the whole suite runs under coverage:
      // many jsdom worker environments start in parallel and the first render of
      // chart-heavy pages can briefly queue. This is a startup allowance, not a
      // licence for a genuine hang (a stuck test still fails, just later).
      testTimeout: 15_000,
      coverage: {
        // v8 is the Vitest-native provider and needs no separate instrumentation.
        provider: 'v8',
        reporter: ['text-summary', 'lcov', 'json-summary'],
        reportsDirectory: './coverage',
        // Count application code, not tests, fixtures, main entrypoints or
        // test scaffolding. `include` is explicit so a new module is measured
        // by default rather than silently dropped from the report.
        include: ['src/**/*.{ts,tsx}'],
        exclude: [
          'src/**/*.test.{ts,tsx}',
          'src/**/*.d.ts',
          'src/test/**',
          'src/main.tsx',
          'src/harness-main.tsx',
          'src/harness-fixtures.ts',
          'src/test/harness-clerk.tsx',
          'src/vite-env.d.ts',
        ],
        // Regression floor, not an aspiration. The measured baseline is ~40%
        // lines (see docs/final-remediation-report.md); much of the remainder
        // is lazy-loaded page positioning/JSX that unit tests do not exercise
        // and that Browser E2E covers instead. The floor sits just below the
        // baseline so routine churn does not break CI, while dropping a whole
        // covered module does. Raise deliberately with new tests; never lower
        // it to make a red build green.
        thresholds: {
          lines: 38,
          statements: 38,
          functions: 30,
          branches: 40,
        },
      },
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
