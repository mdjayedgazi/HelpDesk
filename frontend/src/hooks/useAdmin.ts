import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { endpoints } from '../lib/api.ts'
import { queryKeys } from '../lib/queryKeys.ts'
import type {
  AdminDashboard,
  AdminUserUpdateInput,
  Role,
  User,
  UserListParams,
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

export function useAgents(enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.admin.agents,
    queryFn: () => api.request<User[]>(endpoints.adminAgents()),
    enabled,
    staleTime: 60_000,
  })
}

export function useAdminUsers(params?: UserListParams, enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.admin.users.list(params),
    queryFn: () => api.request<User[]>('/api/v1/users', { query: params }),
    placeholderData: keepPreviousData,
    enabled,
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
