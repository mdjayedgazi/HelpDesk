import { useAuth } from '@clerk/react'
import { useMemo } from 'react'

import { createApiClient, type ApiClient } from './api.ts'

/**
 * Returns an API client wired to the current Clerk session.
 *
 * The token getter is called per request so short-lived session tokens are
 * always refreshed by the Clerk SDK; nothing is persisted by us.
 */
export function useApi(): ApiClient {
  const { getToken } = useAuth()
  return useMemo(() => createApiClient(() => getToken()), [getToken])
}
