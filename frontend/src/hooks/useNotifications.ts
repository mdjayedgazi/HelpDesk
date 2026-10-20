import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { endpoints } from '../lib/api.ts'
import { queryKeys } from '../lib/queryKeys.ts'
import type {
  Notification,
  NotificationListParams,
  NotificationUnreadCount,
} from '../lib/types.ts'
import { useApi } from '../lib/useApi.ts'

export function useNotifications(params?: NotificationListParams) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.notifications.list(params),
    queryFn: () => api.request<Notification[]>(endpoints.notifications(), { query: params }),
  })
}

/** Unread notifications, used for the top-bar badge and the recent popover. */
export function useUnreadNotifications(limit = 50) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.notifications.list({ is_read: false, limit }),
    queryFn: () =>
      api.request<Notification[]>(endpoints.notifications(), {
        query: { is_read: false, limit },
      }),
  })
}

/**
 * The exact unread total for the bell badge.
 *
 * Counted by the backend so the badge is correct even when only a page of the
 * list has been loaded. Polled on the app's shared interval so a new event
 * shows up without a manual refresh.
 */
export function useUnreadNotificationCount() {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.notifications.unreadCount,
    queryFn: () =>
      api.request<NotificationUnreadCount>(endpoints.notificationUnreadCount()),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  })
}

export function useUpdateNotification() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, isRead }: { id: string; isRead: boolean }) =>
      api.request<Notification>(endpoints.notification(id), {
        method: 'PATCH',
        body: { is_read: isRead },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all })
    },
  })
}

export function useMarkAllNotificationsRead() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api.request<{ updated: number }>(endpoints.readAllNotifications(), {
        method: 'POST',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all })
    },
  })
}
