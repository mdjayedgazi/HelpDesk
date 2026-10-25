import { describe, expect, it } from 'vite-plus/test'

import { formatUnreadBadge, unseenNotifications } from './notificationLogic.ts'
import type { Notification } from './types.ts'

function notification(id: string): Notification {
  return {
    id,
    recipient_user_id: 'user-1',
    related_ticket_id: null,
    related_conversation_id: null,
    related_internal_message_id: null,
    related_account_request_id: null,
    type: 'TICKET_ASSIGNED',
    title: `Notification ${id}`,
    message: 'Body',
    is_read: false,
    created_at: '2026-10-23T00:00:00Z',
  }
}

describe('formatUnreadBadge', () => {
  it('hides the badge at zero and shows one-digit counts', () => {
    expect(formatUnreadBadge(0)).toBeNull()
    expect(formatUnreadBadge(-2)).toBeNull()
    expect(formatUnreadBadge(1)).toBe('1')
    expect(formatUnreadBadge(9)).toBe('9')
  })

  it('caps the badge at 99+', () => {
    expect(formatUnreadBadge(99)).toBe('99')
    expect(formatUnreadBadge(100)).toBe('99+')
  })
})

describe('unseenNotifications', () => {
  it('returns only ids not already seen', () => {
    const items = [notification('new-2'), notification('old-1'), notification('new-1')]
    expect(unseenNotifications(items, new Set(['old-1']), 2).map((item) => item.id)).toEqual([
      'new-2',
      'new-1',
    ])
  })

  it('never reports more than the unread-count increase', () => {
    const items = [notification('a'), notification('b'), notification('c')]
    expect(unseenNotifications(items, new Set(), 1).map((item) => item.id)).toEqual(['a'])
  })

  it('returns nothing when the count did not increase', () => {
    expect(unseenNotifications([notification('a')], new Set(), 0)).toEqual([])
    expect(unseenNotifications([notification('a')], new Set(), -1)).toEqual([])
  })

  it('returns nothing when every visible item was already seen', () => {
    expect(unseenNotifications([notification('a')], new Set(['a']), 1)).toEqual([])
  })
})
