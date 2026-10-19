import { useMutation, useQueryClient } from '@tanstack/react-query'

import { endpoints } from '../lib/api.ts'
import { queryKeys } from '../lib/queryKeys.ts'
import type { ProfileUpdateInput, User } from '../lib/types.ts'
import { useApi } from '../lib/useApi.ts'

export function useUpdateProfile() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: ProfileUpdateInput) =>
      api.request<User>(endpoints.me(), { method: 'PATCH', body: input }),
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.me, user)
    },
  })
}

/**
 * Refresh the cached Clerk profile image for the signed-in user.
 *
 * Clerk owns the photo; after the client uploads a new one through Clerk this
 * re-reads the verified image URL from the backend so other participants
 * (comments, conversations, staff tables) render the updated avatar.
 */
export function useSyncAvatar() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.request<User>(endpoints.syncAvatar(), { method: 'POST' }),
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.me, user)
    },
  })
}
