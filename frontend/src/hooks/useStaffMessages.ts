import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { endpoints } from '../lib/api.ts'
import { queryKeys } from '../lib/queryKeys.ts'
import type { Role } from '../lib/types.ts'
import type {
  MarkReadResult,
  StaffConversation,
  StaffConversationCreateInput,
  StaffConversationDetail,
  StaffConversationListParams,
  StaffMessage,
  StaffMessageCreateInput,
  User,
} from '../lib/types.ts'
import { useApi } from '../lib/useApi.ts'

/**
 * The private staff <-> Owner channel.
 *
 * The backend decides what is visible: agents and admins only ever receive
 * their own thread, while the Owner receives the whole inbox. Customers cannot
 * call these endpoints at all (403), so no customer page imports this hook.
 *
 * The optional `params` are the Owner inbox filters; they are only meaningful
 * for the Owner view (an agent is always scoped to their own thread).
 */
export function useStaffConversations(
  params?: StaffConversationListParams,
  enabled = true,
) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.staffMessages.conversations(params),
    queryFn: () =>
      api.request<StaffConversation[]>(endpoints.staffConversations(), {
        query: params as Record<string, string | number | boolean | undefined>,
      }),
    enabled,
  })
}

/**
 * Search the eligible internal employee directory (any staff member).
 *
 * Customers cannot call this endpoint (the backend returns 403), so a customer
 * page must never import this hook. Results are cached per query so typing a
 * name reuses the previous page while the next loads.
 */
export function useStaffDirectory(
  params?: { q?: string; role?: Role; limit?: number; offset?: number },
  enabled = true,
) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.staffMessages.directory(params),
    queryFn: () =>
      api.request<User[]>(endpoints.staffDirectory(), {
        query: params as Record<string, string | number | boolean | undefined>,
      }),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  })
}

/** Get or create a 1:1 conversation with another staff member. */
export function useStartStaffConversation() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: StaffConversationCreateInput) =>
      api.request<StaffConversation>(endpoints.staffConversations(), {
        method: 'POST',
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.staffMessages.all })
    },
  })
}

export function useStaffConversation(id: string | undefined, enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.staffMessages.conversation(id ?? ''),
    queryFn: () => api.request<StaffConversationDetail>(endpoints.staffConversation(id as string)),
    enabled: Boolean(id) && enabled,
  })
}

export function useSendStaffMessage(conversationId: string) {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: StaffMessageCreateInput) =>
      api.request<StaffMessage>(endpoints.staffConversationMessages(conversationId), {
        method: 'POST',
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.staffMessages.all })
    },
  })
}

export function useMarkStaffConversationRead(conversationId: string) {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api.request<MarkReadResult>(endpoints.staffConversationRead(conversationId), {
        method: 'POST',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.staffMessages.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all })
    },
  })
}
