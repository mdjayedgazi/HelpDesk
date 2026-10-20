import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { endpoints } from '../lib/api.ts'
import { queryKeys } from '../lib/queryKeys.ts'
import type {
  InternalMessageCreateInput,
  InternalMessageDetail,
  InternalMessageListParams,
  InternalMessageReceived,
  InternalMessageSummary,
  ReceivedMessageListParams,
  RecipientSearchParams,
  User,
} from '../lib/types.ts'
import { useApi } from '../lib/useApi.ts'

/**
 * Owner-composed internal messages.
 *
 * The backend is the source of truth for who may do what: only the Owner may
 * search recipients or read the sent folder; an employee may only list and mark
 * read the messages addressed to them. Every hook here is therefore imported by
 * the Owner Inbox (and the small "From the Owner" view for staff), never by a
 * customer page.
 */

/** Owner-only: search the eligible employee directory (active agents/admins). */
export function useMessageRecipients(params?: RecipientSearchParams, enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.internalMessages.recipients(params),
    queryFn: () =>
      api.request<User[]>(endpoints.messageRecipients(), {
        query: params as Record<string, string | number | boolean | undefined>,
      }),
    enabled,
    placeholderData: keepPreviousData,
  })
}

/** Owner-only: compose and send a message to an audience. */
export function useComposeInternalMessage() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: InternalMessageCreateInput) =>
      api.request<InternalMessageSummary>(endpoints.internalMessages(), {
        method: 'POST',
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.internalMessages.all })
    },
  })
}

/** Owner-only: the sent folder, newest first. */
export function useSentMessages(params?: InternalMessageListParams, enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.internalMessages.sent(params),
    queryFn: () =>
      api.request<InternalMessageSummary[]>(endpoints.sentMessages(), {
        query: params as Record<string, string | number | boolean | undefined>,
      }),
    enabled,
    placeholderData: keepPreviousData,
  })
}

/** Owner-only: one sent message with its body and a page of recipients. */
export function useSentMessage(
  id: string | undefined,
  params?: { limit?: number; offset?: number },
  enabled = true,
) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.internalMessages.sentDetail(id ?? '', params),
    queryFn: () =>
      api.request<InternalMessageDetail>(endpoints.sentMessage(id as string), {
        query: params as Record<string, string | number | boolean | undefined>,
      }),
    enabled: Boolean(id) && enabled,
  })
}

/** Messages addressed to the signed-in employee (their own rows only). */
export function useReceivedMessages(
  params?: ReceivedMessageListParams,
  enabled = true,
) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.internalMessages.received,
    queryFn: () =>
      api.request<InternalMessageReceived[]>(endpoints.receivedMessages(), {
        query: params as Record<string, string | number | boolean | undefined>,
      }),
    enabled,
  })
}

/** One message addressed to the caller, used by notification deep links. */
export function useReceivedMessage(
  id: string | null | undefined,
  enabled = true,
) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.internalMessages.receivedDetail(id ?? ''),
    queryFn: () =>
      api.request<InternalMessageReceived>(endpoints.receivedMessage(id as string)),
    enabled: Boolean(id) && enabled,
  })
}

/** Mark the signed-in recipient's own copy as read. */
export function useMarkInternalMessageRead() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      api.request<{ updated: number }>(endpoints.markMessageRead(id), {
        method: 'POST',
      }),
    onSuccess: () => {
      // The backend also clears this message's notification in the same
      // transaction, so refresh the bell/panel as well as the message list.
      void queryClient.invalidateQueries({ queryKey: queryKeys.internalMessages.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all })
    },
  })
}
