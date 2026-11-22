import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { CustomerDashboard } from './CustomerDashboard.tsx'
import { renderPage } from '../../test/renderPage.tsx'
import type { Ticket, User } from '../../lib/types.ts'

const { useTicketsMock } = vi.hoisted(() => ({ useTicketsMock: vi.fn() }))

vi.mock('../../hooks/useUserDirectory.ts', () => ({
  useUserDirectory: () => ({
    isResolved: true,
    user: (id: string) => ({ id, full_name: 'Requester Name' }),
    label: (id: string | null | undefined) => (id ? 'Requester Name' : '—'),
  }),
}))

vi.mock('../../hooks/useTickets.ts', () => ({
  useTickets: useTicketsMock,
}))

const me: User = {
  id: 'customer-1',
  full_name: 'Jordan Lee',
  username: 'jordan',
  email: 'jordan@example.com',
  role: 'customer',
  is_active: true,
  image_url: null,
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
}

function ticket(overrides: Partial<Ticket>): Ticket {
  return {
    id: crypto.randomUUID(),
    ticket_number: 1001,
    title: 'My request',
    description: 'Details',
    status: 'OPEN',
    priority: 'NORMAL',
    category: 'OTHER',
    created_by_user_id: 'customer-1',
    assignee_user_id: null,
    created_at: '2026-11-20T00:00:00Z',
    updated_at: '2026-11-20T00:00:00Z',
    assigned_at: null,
    resolved_at: null,
    ...overrides,
  }
}

function ticketPage(items: Ticket[]) {
  return {
    items,
    total: items.length,
    page: 1,
    page_size: 100,
    total_pages: 1,
    has_next: false,
    has_previous: false,
  }
}

function queryResult<T>(data: T) {
  return {
    isPending: false,
    isError: false,
    error: null,
    data,
    refetch: vi.fn(),
  }
}

describe('CustomerDashboard', () => {
  beforeEach(() => {
    useTicketsMock.mockReset()
  })

  it('summarises the customer’s own tickets and calls out a waiting reply', () => {
    useTicketsMock.mockReturnValue(
      queryResult(
        ticketPage([
          ticket({ ticket_number: 1001, status: 'OPEN' }),
          ticket({ ticket_number: 1002, status: 'IN_PROGRESS' }),
          ticket({ ticket_number: 1003, status: 'WAITING_ON_CUSTOMER', title: 'Need your reply' }),
          ticket({ ticket_number: 1004, status: 'RESOLVED' }),
          ticket({ ticket_number: 1005, status: 'CLOSED' }),
        ]),
      ),
    )

    renderPage(<CustomerDashboard me={me} />)

    expect(screen.getByRole('heading', { name: /welcome back, jordan/i })).toBeInTheDocument()
    expect(screen.getByText('The team is waiting on you')).toBeInTheDocument()
    expect(screen.getByText('Where your requests stand')).toBeInTheDocument()
    expect(screen.queryByText('Team workload')).not.toBeInTheDocument()
  })

  it('shows the empty state when the customer has no tickets', () => {
    useTicketsMock.mockReturnValue(queryResult(ticketPage([])))

    renderPage(<CustomerDashboard me={me} />)

    expect(screen.getByText('No tickets yet')).toBeInTheDocument()
    expect(screen.queryByText('The team is waiting on you')).not.toBeInTheDocument()
  })
})
