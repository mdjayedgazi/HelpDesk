import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

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
  TicketUpdateInput,
} from '../lib/types.ts'
import { useApi } from '../lib/useApi.ts'

export function useTickets(params?: TicketListParams, enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.tickets.list(params),
    queryFn: () => api.request<Ticket[]>(endpoints.tickets(), { query: params }),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useAssignedTickets(params?: TicketListParams, enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.tickets.assigned(params),
    queryFn: () => api.request<Ticket[]>(endpoints.assignedTickets(), { query: params }),
    placeholderData: keepPreviousData,
    enabled,
  })
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

export function useCreateTicket() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: TicketCreateInput) =>
      api.request<Ticket>(endpoints.tickets(), { method: 'POST', body: input }),
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
