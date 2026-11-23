import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { endpoints } from '../lib/api.ts'
import { queryKeys } from '../lib/queryKeys.ts'
import type {
  AdminDashboard,
  AdminUserUpdateInput,
  Role,
  SupportAnalytics,
  User,
  UserListParams,
  UserPage,
} from '../lib/types.ts'
import { useApi } from '../lib/useApi.ts'

export function useAdminDashboard(enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.admin.dashboard,
    queryFn: () => api.request<AdminDashboard>(endpoints.adminDashboard()),
    enabled,
  })
}

/**
 * Aggregated support analytics for the admin/owner dashboard.
 *
 * The payload is computed server-side from real ticket rows. A short stale time
 * keeps the dashboard current without hammering the API; the query is only
 * enabled for callers that pass `true` (the dashboard), so non-admin routes pay
 * nothing.
 */
export function useSupportAnalytics(enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.admin.analytics,
    queryFn: () => api.request<SupportAnalytics>(endpoints.adminAnalytics()),
    enabled,
    staleTime: 60_000,
  })
}

export function useAgents(enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.admin.agents,
    queryFn: () => api.request<User[]>(endpoints.adminAgents()),
    enabled,
    staleTime: 60_000,
  })
}

/**
 * One page of the user directory, with authoritative pagination metadata.
 *
 * The backend returns a `UserPage` envelope; consumers must use its `total` /
 * `total_pages` / `has_next` rather than inferring a page from the row count.
 * `keepPreviousData` keeps the current page visible while the next loads.
 */
export function useAdminUsers(params?: UserListParams, enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.admin.users.list(params),
    queryFn: () => api.request<UserPage>('/api/v1/users', { query: params }),
    placeholderData: keepPreviousData,
    enabled,
  })
}

/**
 * A flat list of users for lookups (display names, pickers), NOT pagination.
 *
 * These callers need the whole eligible set at once, so this fetches the
 * directory with the maximum page size and unwraps `items`. It is only enabled
 * for admins/owners (the backend returns 403 to everyone else). For a paginated
 * directory view use `useAdminUsers` instead.
 */
export function useUserDirectoryList(enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.admin.users.list({ page: 1, page_size: 100 }),
    queryFn: () =>
      api.request<UserPage>('/api/v1/users', { query: { page: 1, page_size: 100 } }),
    enabled,
    staleTime: 60_000,
    select: (page) => page.items,
  })
}

export function useAdminUser(id: string | undefined) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.admin.users.detail(id ?? ''),
    queryFn: () => api.request<User>(`/api/v1/users/${id}`),
    enabled: Boolean(id),
  })
}

function invalidateUsers(queryClient: ReturnType<typeof useQueryClient>, id?: string) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.admin.users.all })
  if (id) {
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.users.detail(id) })
  }
  void queryClient.invalidateQueries({ queryKey: queryKeys.admin.agents })
}

export function useUpdateUser(id: string) {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: AdminUserUpdateInput) =>
      api.request<User>(`/api/v1/users/${id}`, { method: 'PATCH', body: input }),
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.admin.users.detail(id), user)
      invalidateUsers(queryClient, id)
    },
  })
}

export function useUpdateUserRole(id: string) {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (role: Role) =>
      api.request<User>(`/api/v1/users/${id}/role`, {
        method: 'PATCH',
        body: { role },
      }),
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.admin.users.detail(id), user)
      invalidateUsers(queryClient, id)
    },
  })
}

export function useUpdateUserStatus(id: string) {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (isActive: boolean) =>
      api.request<User>(`/api/v1/users/${id}/status`, {
        method: 'PATCH',
        body: { is_active: isActive },
      }),
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.admin.users.detail(id), user)
      invalidateUsers(queryClient, id)
    },
  })
}
