import type { Notification } from './types.ts'

/** Cap the bell badge the way the panel header caps it: `12`, `99+`. */
export function formatUnreadBadge(count: number): string | null {
  if (count <= 0) return null
  return count > 99 ? '99+' : String(count)
}

/**
 * Return the notifications that are genuinely new, capped to the number of
 * arrivals reported by the unread count.
 *
 * The cap prevents an older item that scrolled into the first page from being
 * mistaken for a new arrival when several notifications arrived at once. The
 * caller owns the seen-id set and marks the returned page as seen afterwards.
 */
export function unseenNotifications(
  items: Notification[],
  seenIds: ReadonlySet<string>,
  arrivals: number,
): Notification[] {
  if (arrivals <= 0) return []
  return items.filter((item) => !seenIds.has(item.id)).slice(0, arrivals)
}
