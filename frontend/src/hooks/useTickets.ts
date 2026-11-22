import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import { endpoints } from '../lib/api.ts'
import { queryKeys } from '../lib/queryKeys.ts'
import type {
  Attachment,
  Comment,
  CommentCreateInput,
  StaffComment,
  Ticket,
  TicketContact,
  TicketCreateInput,
  TicketHistoryEntry,
  TicketListParams,
  TicketPage,
  TicketUpdateInput,
} from '../lib/types.ts'
import { useApi } from '../lib/useApi.ts'

/**
 * Ticket list pages stay "fresh" for a short window so returning to a page you
 * just viewed (pagination back/forward, or a quick filter toggle) is served from
 * the cache instead of re-hitting the API. The value is deliberately short: ticket
 * data changes often, and mutations already invalidate the ticket queries, so this
 * only avoids redundant refetches of an unchanged page — it does not hide updates.
 */
const TICKET_LIST_STALE_MS = 30_000

export function useTickets(params?: TicketListParams, enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.tickets.list(params),
    queryFn: () => api.request<TicketPage>(endpoints.tickets(), { query: params }),
    placeholderData: keepPreviousData,
    staleTime: TICKET_LIST_STALE_MS,
    enabled,
  })
}

export function useAssignedTickets(params?: TicketListParams, enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.tickets.assigned(params),
    queryFn: () =>
      api.request<TicketPage>(endpoints.assignedTickets(), { query: params }),
    placeholderData: keepPreviousData,
    staleTime: TICKET_LIST_STALE_MS,
    enabled,
  })
}

/**
 * Prefetch an adjacent ticket-list page so a predictable Next/Previous click
 * renders from cache immediately.
 *
 * It fires at most one page ahead, only when that page is not already cached,
 * and uses the same query key and fetch function as the visible query, so it can
 * never show different data. It is intentionally conservative (one page, no
 * loops) to avoid background-fetch churn on metered infrastructure.
 */
export function usePrefetchTicketPage(params?: TicketListParams) {
  const api = useApi()
  const queryClient = useQueryClient()
  // ``params`` is memoized by the caller (the ticket page), so its identity only
  // changes when a filter/page actually changes. The callback therefore stays
  // stable and the caller's effect does not loop on unrelated re-renders.
  return useCallback(
    (page: number) => {
      if (!params) return
      const nextParams = { ...params, page }
      const key = queryKeys.tickets.list(nextParams)
      if (queryClient.getQueryData(key) !== undefined) return
      void queryClient.prefetchQuery({
        queryKey: key,
        queryFn: () =>
          api.request<TicketPage>(endpoints.tickets(), { query: nextParams }),
        staleTime: TICKET_LIST_STALE_MS,
      })
    },
    [api, queryClient, params],
  )
}

export function useTicket(id: string | undefined) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.tickets.detail(id ?? ''),
    queryFn: () => api.request<Ticket>(endpoints.ticket(id as string)),
    enabled: Boolean(id),
  })
}

/**
 * The optional contact number of a ticket (staff-only endpoint).
 *
 * Customers never call this: the number is deliberately excluded from the
 * public ticket payload, and the endpoint rejects non-staff callers.
 */
export function useTicketContact(ticketId: string | undefined, enabled: boolean) {
  const api = useApi()
  return useQuery({
    queryKey: [...queryKeys.tickets.detail(ticketId ?? ''), 'contact'],
    queryFn: () => api.request<TicketContact>(endpoints.ticketContact(ticketId as string)),
    enabled: Boolean(ticketId) && enabled,
  })
}

export type CreateTicketInput = TicketCreateInput & {
  /** Optional idempotency key so a retried submit cannot open a duplicate. */
  idempotencyKey?: string
}

export function useCreateTicket() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ idempotencyKey, ...input }: CreateTicketInput) =>
      api.request<Ticket>(endpoints.tickets(), {
        method: 'POST',
        body: input,
        headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.all })
    },
  })
}

export function useUpdateTicket(id: string) {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: TicketUpdateInput) =>
      api.request<Ticket>(endpoints.ticket(id), { method: 'PATCH', body: input }),
    onSuccess: (ticket) => {
      queryClient.setQueryData(queryKeys.tickets.detail(id), ticket)
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.history(id) })
    },
  })
}

export function useClaimTicket() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.request<Ticket>(endpoints.claimTicket(id), { method: 'POST' }),
    onSuccess: (ticket) => {
      queryClient.setQueryData(queryKeys.tickets.detail(ticket.id), ticket)
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.all })
    },
  })
}

export function useAssignTicket(id: string) {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (assigneeUserId: string | null) =>
      api.request<Ticket>(endpoints.assignTicket(id), {
        method: 'POST',
        body: { assignee_user_id: assigneeUserId },
      }),
    onSuccess: (ticket) => {
      queryClient.setQueryData(queryKeys.tickets.detail(id), ticket)
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.history(id) })
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Comments                                                                   */
/* -------------------------------------------------------------------------- */

export function useComments(ticketId: string | undefined) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.tickets.comments(ticketId ?? ''),
    queryFn: () =>
      api.request<Array<Comment | StaffComment>>(endpoints.comments(ticketId as string)),
    enabled: Boolean(ticketId),
  })
}

export function useCreateComment(ticketId: string) {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CommentCreateInput) =>
      api.request<Comment | StaffComment>(endpoints.comments(ticketId), {
        method: 'POST',
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.tickets.comments(ticketId),
      })
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all })
    },
  })
}

/* -------------------------------------------------------------------------- */
/* History                                                                    */
/* -------------------------------------------------------------------------- */

export function useTicketHistory(ticketId: string | undefined, enabled: boolean) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.tickets.history(ticketId ?? ''),
    queryFn: () => api.request<TicketHistoryEntry[]>(endpoints.history(ticketId as string)),
    enabled: Boolean(ticketId) && enabled,
  })
}

/* -------------------------------------------------------------------------- */
/* Attachments                                                                */
/* -------------------------------------------------------------------------- */

export function useAttachments(ticketId: string | undefined) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.tickets.attachments(ticketId ?? ''),
    queryFn: () => api.request<Attachment[]>(endpoints.attachments(ticketId as string)),
    enabled: Boolean(ticketId),
  })
}

export function useUploadAttachment(ticketId: string) {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return api.request<Attachment>(endpoints.attachments(ticketId), {
        method: 'POST',
        formData,
      })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.tickets.attachments(ticketId),
      })
    },
  })
}
