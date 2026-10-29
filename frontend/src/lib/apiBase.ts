/**
 * Resolve the backend base URL.
 *
 * Development may fall back to the local FastAPI port. A production bundle is
 * rejected unless VITE_API_URL is an absolute HTTPS origin: silently pointing a
 * deployed frontend at 127.0.0.1 produces a site that looks broken and can hide
 * a misconfigured release.
 */
export function resolveApiBase(rawValue: string | undefined, production: boolean): string {
  const raw = rawValue?.trim()

  if (!raw) {
    if (production) {
      throw new Error('VITE_API_URL is required for a production build')
    }
    return 'http://127.0.0.1:8000'
  }

  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    throw new Error('VITE_API_URL must be an absolute URL')
  }

  if (production) {
    if (parsed.protocol !== 'https:') {
      throw new Error('VITE_API_URL must use HTTPS in production')
    }
    if (['localhost', '127.0.0.1', '0.0.0.0', '::1'].includes(parsed.hostname)) {
      throw new Error('VITE_API_URL must not point at localhost in production')
    }
    if (parsed.pathname !== '/' || parsed.search || parsed.hash) {
      throw new Error('VITE_API_URL must be an origin without a path, query, or hash')
    }
  }

  return raw.replace(/\/$/, '')
}
