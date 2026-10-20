import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { endpoints } from '../lib/api.ts'
import { queryKeys } from '../lib/queryKeys.ts'
import type { TicketFeedback, TicketFeedbackInput, TicketFeedbackState } from '../lib/types.ts'
import { useApi } from '../lib/useApi.ts'

/**
 * Customer feedback for a resolved ticket.
 *
 * The backend decides eligibility (`can_submit`) and enforces it on the write,
 * so these hooks only mirror what the server already allows.
 */
export function useTicketFeedback(ticketId: string | undefined, enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.tickets.feedback(ticketId ?? ''),
    queryFn: () =>
      api.request<TicketFeedbackState>(endpoints.ticketFeedback(ticketId as string)),
    enabled: Boolean(ticketId) && enabled,
  })
}

export function useSubmitTicketFeedback(ticketId: string) {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: TicketFeedbackInput) =>
      api.request<TicketFeedback>(endpoints.ticketFeedback(ticketId), {
        method: 'POST',
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.tickets.feedback(ticketId),
      })
      // Answering the feedback request clears its notification, so the bell and
      // list must reflect the new read state.
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all })
    },
  })
}
