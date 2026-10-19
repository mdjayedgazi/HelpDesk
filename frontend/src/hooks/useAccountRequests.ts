import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { endpoints } from '../lib/api.ts'
import { queryKeys } from '../lib/queryKeys.ts'
import type {
  AccountRequest,
  AccountRequestComment,
  AccountRequestCommentInput,
  AccountRequestCreateInput,
  AccountRequestDetail,
  AccountRequestListParams,
  AccountRequestStatusInput,
} from '../lib/types.ts'
import { useApi } from '../lib/useApi.ts'

/**
 * Account-management (admin escalation) requests.
 *
 * The backend scopes the list by role: agents only see their own requests,
 * admins and the Owner see the whole queue. Escalations never carry identity
 * changes - approving a request is an authorization decision that a human
 * then performs through the supported Clerk process.
 */
export function useAccountRequests(params?: AccountRequestListParams, enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.accountRequests.list(params),
    queryFn: () => api.request<AccountRequest[]>(endpoints.accountRequests(), { query: params }),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useAccountRequest(id: string | undefined) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.accountRequests.detail(id ?? ''),
    queryFn: () => api.request<AccountRequestDetail>(endpoints.accountRequest(id as string)),
    enabled: Boolean(id),
  })
}

export function useCreateAccountRequest() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: AccountRequestCreateInput) =>
      api.request<AccountRequest>(endpoints.accountRequests(), { method: 'POST', body: input }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.accountRequests.all })
    },
  })
}

export function useAddAccountRequestComment(id: string) {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: AccountRequestCommentInput) =>
      api.request<AccountRequestComment>(endpoints.accountRequestComments(id), {
        method: 'POST',
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.accountRequests.all })
    },
  })
}

export function useUpdateAccountRequestStatus(id: string) {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: AccountRequestStatusInput) =>
      api.request<AccountRequest>(endpoints.accountRequestStatus(id), {
        method: 'POST',
        body: input,
      }),
    onSuccess: (request) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.accountRequests.all })
      void queryClient.setQueryData<AccountRequestDetail | undefined>(
        queryKeys.accountRequests.detail(id),
        (current) => (current ? { ...current, request } : current),
      )
    },
  })
}
