import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { AgentDashboard } from './AgentDashboard.tsx'
import { renderPage } from '../../test/renderPage.tsx'
import type { Ticket, User } from '../../lib/types.ts'

const { useAssignedTicketsMock, useTicketsMock } = vi.hoisted(() => ({
  useAssignedTicketsMock: vi.fn(),
  useTicketsMock: vi.fn(),
}))

vi.mock('../../hooks/useUserDirectory.ts', () => ({
  useUserDirectory: () => ({
    isResolved: true,
    user: (id: string) => ({ id, full_name: 'Requester Name' }),
    label: (id: string | null | undefined) => (id ? 'Requester Name' : '—'),
  }),
}))

vi.mock('../../hooks/useTickets.ts', () => ({
  useAssignedTickets: useAssignedTicketsMock,
  useTickets: useTicketsMock,
}))

const me: User = {
  id: 'agent-1',
  full_name: 'Avery Bennett',
  username: 'avery',
  email: 'avery@example.com',
  role: 'agent',
  is_active: true,
  image_url: null,
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
}

function ticket(overrides: Partial<Ticket>): Ticket {
  return {
    id: crypto.randomUUID(),
    ticket_number: 1001,
    title: 'Printer is broken',
    description: 'It stopped working.',
    status: 'OPEN',
    priority: 'NORMAL',
    category: 'TECHNICAL',
    created_by_user_id: 'customer-1',
    assignee_user_id: 'agent-1',
    created_at: '2026-11-20T00:00:00Z',
    updated_at: '2026-11-20T00:00:00Z',
    assigned_at: '2026-11-20T00:00:00Z',
    resolved_at: null,
    ...overrides,
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

describe('AgentDashboard', () => {
  beforeEach(() => {
    useAssignedTicketsMock.mockReset()
    useTicketsMock.mockReset()
  })

  it('prioritises urgent active work and shows the queue context', () => {
    useAssignedTicketsMock.mockReturnValue(
      queryResult([
        ticket({ ticket_number: 1001, status: 'IN_PROGRESS', priority: 'NORMAL' }),
        ticket({ ticket_number: 1002, status: 'OPEN', priority: 'URGENT', title: 'Site down' }),
        ticket({ ticket_number: 1003, status: 'WAITING_ON_CUSTOMER', title: 'Waiting reply' }),
      ]),
    )
    useTicketsMock.mockReturnValue(
      queryResult([
        ticket({ ticket_number: 1004, assignee_user_id: null, title: 'Unclaimed' }),
      ]),
    )

    renderPage(<AgentDashboard me={me} />)

    expect(screen.getByRole('heading', { name: /good to see you, avery/i })).toBeInTheDocument()
    expect(screen.getByText('Work on this next')).toBeInTheDocument()
    expect(screen.getByText('Your status mix')).toBeInTheDocument()
    expect(screen.getByText(/1 unassigned ticket is waiting to be claimed/i)).toBeInTheDocument()

    // The urgent ticket must appear before the normal-priority one.
    const titles = screen.getAllByText(/Site down|Waiting reply|Printer is broken/).map(
      (node) => node.textContent,
    )
    expect(titles[0]).toBe('Site down')
  })

  it('shows the empty state when the agent has nothing assigned', () => {
    useAssignedTicketsMock.mockReturnValue(queryResult([]))
    useTicketsMock.mockReturnValue(queryResult([]))

    renderPage(<AgentDashboard me={me} />)

    expect(screen.getByText('Nothing assigned to you')).toBeInTheDocument()
    expect(screen.getByText('The shared unassigned queue is clear.')).toBeInTheDocument()
  })
})
