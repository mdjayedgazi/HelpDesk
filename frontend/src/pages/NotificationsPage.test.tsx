import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { NotificationsPage } from './NotificationsPage.tsx'
import { renderPage } from '../test/renderPage.tsx'
import type { Notification } from '../lib/types.ts'

const { useNotificationsMock, useUpdateNotificationMock, useMarkAllMock } = vi.hoisted(() => ({
  useNotificationsMock: vi.fn(),
  useUpdateNotificationMock: vi.fn(),
  useMarkAllMock: vi.fn(),
}))

vi.mock('../hooks/useNotifications.ts', () => ({
  useNotifications: useNotificationsMock,
  useUpdateNotification: useUpdateNotificationMock,
  useMarkAllNotificationsRead: useMarkAllMock,
}))

function notification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: crypto.randomUUID(),
    recipient_user_id: 'me',
    related_ticket_id: 'ticket-1',
    related_conversation_id: null,
    related_internal_message_id: null,
    related_account_request_id: null,
    type: 'STATUS_CHANGED',
    title: 'Ticket status updated',
    message: 'Ticket #1001 is now IN_PROGRESS.',
    is_read: false,
    created_at: '2026-11-20T00:00:00Z',
    ...overrides,
  }
}

function query(overrides: Record<string, unknown> = {}) {
  return {
    data: undefined,
    isPending: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  }
}

describe('NotificationsPage', () => {
  beforeEach(() => {
    useNotificationsMock.mockReset()
    useUpdateNotificationMock.mockReset()
    useMarkAllMock.mockReset()
    useUpdateNotificationMock.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
    useMarkAllMock.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
  })

  it('shows the empty state when there are no notifications', () => {
    useNotificationsMock.mockReturnValue(query({ data: [] }))
    renderPage(<NotificationsPage />, { route: '/notifications' })
    expect(screen.getByText('No notifications yet')).toBeInTheDocument()
  })

  it('renders notification rows', () => {
    useNotificationsMock.mockReturnValue(query({ data: [notification()] }))
    renderPage(<NotificationsPage />, { route: '/notifications' })
    expect(screen.getByText('Ticket status updated')).toBeInTheDocument()
  })

  it('shows an error state with retry', () => {
    useNotificationsMock.mockReturnValue(
      query({ isError: true, error: new Error('boom'), refetch: vi.fn() }),
    )
    renderPage(<NotificationsPage />, { route: '/notifications' })
    expect(screen.getByText('Could not load notifications')).toBeInTheDocument()
  })

  it('offers "Mark all read" when an unread notification exists and calls it', async () => {
    const mutate = vi.fn()
    useMarkAllMock.mockReturnValue({ mutate, isPending: false })
    useNotificationsMock.mockReturnValue(query({ data: [notification({ is_read: false })] }))
    renderPage(<NotificationsPage />, { route: '/notifications' })

    fireEvent.click(screen.getByRole('button', { name: /Mark all read/i }))
    await waitFor(() => expect(mutate).toHaveBeenCalled())
  })

  it('passes the unread filter to the query when the Unread tab is selected', async () => {
    useNotificationsMock.mockReturnValue(query({ data: [] }))
    renderPage(<NotificationsPage />, { route: '/notifications' })

    fireEvent.click(screen.getByRole('tab', { name: 'Unread' }))
    await waitFor(() =>
      expect(useNotificationsMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ is_read: false, limit: 30, offset: 0 }),
      ),
    )
  })
})
