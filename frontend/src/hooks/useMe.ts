import { useAuth } from '@clerk/react'
import { useQuery } from '@tanstack/react-query'

import { endpoints } from '../lib/api.ts'
import { queryKeys } from '../lib/queryKeys.ts'
import type { User } from '../lib/types.ts'
import { useApi } from '../lib/useApi.ts'

/**
 * Fetch the authenticated user's HelpDesk profile.
 *
 * The backend lazily provisions a local profile on the first call
 * (see `get_current_user` in `backend/app/core/auth.py`), so this single query
 * is also what "registers" a newly signed-in Clerk user with the app.
 */
export function useMe() {
  const api = useApi()
  const { isLoaded, isSignedIn } = useAuth()

  return useQuery({
    queryKey: queryKeys.me,
    queryFn: () => api.request<User>(endpoints.me()),
    enabled: isLoaded && Boolean(isSignedIn),
    staleTime: 60_000,
    retry: false,
  })
}
