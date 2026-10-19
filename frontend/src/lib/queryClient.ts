import { QueryClient } from '@tanstack/react-query'

import { ApiError } from './api.ts'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      gcTime: 5 * 60_000,
      retry: (failureCount, error) => {
        // Never retry auth/permission/not-found errors; do retry transient ones.
        if (error instanceof ApiError) {
          if (error.status === 0) return failureCount < 2
          if (error.status >= 400 && error.status < 500) return false
        }
        return failureCount < 1
      },
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
})
