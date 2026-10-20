import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

import { useUnreadNotificationCount } from '../hooks/useNotifications.ts'
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
 * * the backend's exact unread count gates alerts: reading an item makes the
 *   count fall, so an older notification scrolling into the first page is
 *   never mistaken for a new arrival;
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
  const lastCount = useRef<number | null>(null)

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

  // Shares the bell's query, so this adds no extra polling. The exact count
  // tells us whether the change was an arrival (up) or a read (down); a page
  // swap caused by reading must never look like a new notification.
  const unread = useUnreadNotificationCount()

  useEffect(() => {
    const items = recent.data
    const count = unread.data?.count
    if (!items || count === undefined) return

    if (seenIds.current === null || lastCount.current === null) {
      seenIds.current = new Set(items.map((item) => item.id))
      lastCount.current = count
      return
    }

    const previous = lastCount.current

    if (count < previous) {
      // Items were read. Any id that scrolled into the page from below is
      // history, so remember it rather than alerting on it.
      for (const item of items) seenIds.current.add(item.id)
      lastCount.current = count
      return
    }

    if (count === previous) {
      // The count can lag a fresh list. Do not mark unseen ids as seen yet: a
      // genuinely new notification must not be swallowed by a stale count.
      return
    }

    // Wait for a list fetch at least as fresh as the count, otherwise the new
    // arrival may not be on this page yet and an older item could be mistaken
    // for it.
    if (recent.dataUpdatedAt < unread.dataUpdatedAt) return

    const arrivals = count - previous
    lastCount.current = count
    const fresh = items
      .filter((item) => !seenIds.current!.has(item.id))
      .slice(0, arrivals)
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
  }, [recent.data, recent.dataUpdatedAt, unread.data, unread.dataUpdatedAt])

  return null
}
