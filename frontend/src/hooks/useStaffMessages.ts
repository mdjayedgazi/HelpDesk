import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { endpoints } from '../lib/api.ts'
import { queryKeys } from '../lib/queryKeys.ts'
import type {
  MarkReadResult,
  StaffConversation,
  StaffConversationDetail,
  StaffConversationListParams,
  StaffMessage,
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

/** Get or create the caller's conversation with the Owner (agents/admins). */
export function useStartStaffConversation() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (subject?: string) =>
      api.request<StaffConversation>(endpoints.staffConversations(), {
        method: 'POST',
        body: { subject: subject || undefined },
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
    mutationFn: (body: string) =>
      api.request<StaffMessage>(endpoints.staffConversationMessages(conversationId), {
        method: 'POST',
        body: { body },
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
