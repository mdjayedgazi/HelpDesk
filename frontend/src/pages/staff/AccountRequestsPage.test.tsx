import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { AccountRequestsPage } from './AccountRequestsPage.tsx'
import { renderPage } from '../../test/renderPage.tsx'
import type { AccountRequest, User } from '../../lib/types.ts'

const { useMeMock, useAccountRequestsMock } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  useAccountRequestsMock: vi.fn(),
}))

vi.mock('../../hooks/useMe.ts', () => ({ useMe: useMeMock }))
vi.mock('../../hooks/useAccountRequests.ts', () => ({
  useAccountRequests: useAccountRequestsMock,
  useCreateAccountRequest: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../hooks/useTickets.ts', () => ({
  useTickets: () => ({ data: undefined, isPending: false }),
}))
vi.mock('../../hooks/useAdmin.ts', () => ({
  useUserDirectoryList: () => ({ data: [] }),
}))
vi.mock('../../hooks/useUserDirectory.ts', () => ({
  useUserDirectory: () => ({ isResolved: true, user: () => undefined, label: () => '—' }),
}))

function user(role: User['role']): User {
  return {
    id: `u-${role}`,
    full_name: 'Test Person',
    username: role,
    email: `${role}@example.test`,
    role,
    is_active: true,
    image_url: null,
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
  }
}

function request(overrides: Partial<AccountRequest> = {}): AccountRequest {
  return {
    id: 'req-1',
    target_user_id: 'target-1',
    target_full_name_snapshot: 'Target Person',
    target_email_snapshot: 'target@example.test',
    ticket_id: null,
    category: 'ACCOUNT_RECOVERY',
    justification: 'Needs account recovery.',
    internal_details: null,
    status: 'PENDING',
    decision_reason: null,
    decided_by_user_id: null,
    decided_at: null,
    completed_by_user_id: null,
    completed_at: null,
    created_by_user_id: 'agent-1',
    created_at: '2026-11-20T00:00:00Z',
    updated_at: '2026-11-20T00:00:00Z',
    ...overrides,
  }
}

function q(data: unknown, extra: Record<string, unknown> = {}) {
  return {
    data,
    isPending: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
    ...extra,
  }
}

describe('AccountRequestsPage', () => {
  beforeEach(() => {
    useMeMock.mockReset()
    useAccountRequestsMock.mockReset()
  })

  it('lists account requests for an admin', () => {
    useMeMock.mockReturnValue(q(user('admin')))
    useAccountRequestsMock.mockReturnValue(q([request()]))
    renderPage(<AccountRequestsPage />, { route: '/account-requests' })
    expect(screen.getByText('Account requests')).toBeInTheDocument()
    expect(screen.getByText('Account recovery')).toBeInTheDocument()
  })

  it('shows an empty state when there are no requests', () => {
    useMeMock.mockReturnValue(q(user('admin')))
    useAccountRequestsMock.mockReturnValue(q([]))
    renderPage(<AccountRequestsPage />, { route: '/account-requests' })
    expect(screen.getByText('No account requests yet')).toBeInTheDocument()
  })

  it('shows an error state when the list fails', () => {
    useMeMock.mockReturnValue(q(user('admin')))
    useAccountRequestsMock.mockReturnValue(
      q(undefined, { isError: true, error: new Error('boom'), refetch: vi.fn() }),
    )
    renderPage(<AccountRequestsPage />, { route: '/account-requests' })
    expect(screen.getByText('Could not load account requests')).toBeInTheDocument()
  })

  it('offers "New request" to agents but not to owners (who cannot create)', () => {
    useMeMock.mockReturnValue(q(user('agent')))
    useAccountRequestsMock.mockReturnValue(q([]))
    const { unmount } = renderPage(<AccountRequestsPage />, { route: '/account-requests' })
    expect(screen.getAllByRole('button', { name: /New request/i }).length).toBeGreaterThan(0)
    unmount()

    useMeMock.mockReturnValue(q(user('owner')))
    useAccountRequestsMock.mockReturnValue(q([]))
    renderPage(<AccountRequestsPage />, { route: '/account-requests' })
    expect(screen.queryByRole('button', { name: /New request/i })).not.toBeInTheDocument()
  })
})
