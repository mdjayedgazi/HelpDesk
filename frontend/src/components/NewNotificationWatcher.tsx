import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

import { endpoints } from '../lib/api.ts'
import { queryKeys } from '../lib/queryKeys.ts'
import type { Notification } from '../lib/types.ts'
import { useApi } from '../lib/useApi.ts'
import { toaster } from './Toaster.tsx'

const FEED_LIMIT = 10

/**
 * Raises one unobtrusive toast when a *new* notification arrives while the
 * signed-in user is working.
 *
 * Design notes:
 * * the first successful load only records what already exists - it never
 *   toasts history, including after a refresh or a reconnect;
 * * ids are remembered for the life of the signed-in session, so a toast is
 *   never replayed for the same notification;
 * * a burst collapses into a single toast (the bell stays the full history);
 * * polling is a modest 30s plus window focus/reconnect, matching the app's
 *   existing React Query conventions - no WebSockets, no service worker, and no
 *   browser-notification permission prompt.
 */
export function NewNotificationWatcher() {
  const api = useApi()
  const seenIds = useRef<Set<string> | null>(null)

  const recent = useQuery({
    queryKey: queryKeys.notifications.list({ is_read: false, limit: FEED_LIMIT }),
    queryFn: () =>
      api.request<Notification[]>(endpoints.notifications(), {
        query: { is_read: false, limit: FEED_LIMIT },
      }),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  })

  useEffect(() => {
    const items = recent.data
    if (!items) return

    if (seenIds.current === null) {
      seenIds.current = new Set(items.map((item) => item.id))
      return
    }

    const fresh = items.filter((item) => !seenIds.current!.has(item.id))
    for (const item of items) seenIds.current.add(item.id)

    if (fresh.length === 0) return

    const newest = fresh[0]!
    toaster.create(
      fresh.length === 1
        ? { title: newest.title, description: newest.message, type: 'info' }
        : {
            title: `${fresh.length} new notifications`,
            description: 'Open the bell to review them.',
            type: 'info',
          },
    )
  }, [recent.data])

  return null
}
