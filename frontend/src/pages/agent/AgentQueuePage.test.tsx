import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { AgentQueuePage } from './AgentQueuePage.tsx'
import { renderPage } from '../../test/renderPage.tsx'
import type { Ticket } from '../../lib/types.ts'

const { useTicketsMock, useAssignedTicketsMock, useClaimTicketMock } = vi.hoisted(() => ({
  useTicketsMock: vi.fn(),
  useAssignedTicketsMock: vi.fn(),
  useClaimTicketMock: vi.fn(),
}))

vi.mock('../../hooks/useTickets.ts', () => ({
  useTickets: useTicketsMock,
  useAssignedTickets: useAssignedTicketsMock,
  useClaimTicket: useClaimTicketMock,
}))

vi.mock('../../hooks/useUserDirectory.ts', () => ({
  useUserDirectory: () => ({
    isResolved: true,
    user: () => undefined,
    label: () => 'Requester Name',
  }),
}))

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

function ticket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    id: crypto.randomUUID(),
    ticket_number: 1001,
    title: 'Printer is broken',
    description: 'It stopped working.',
    status: 'OPEN',
    priority: 'NORMAL',
    category: 'TECHNICAL',
    created_by_user_id: 'customer-1',
    assignee_user_id: null,
    created_at: '2026-11-20T00:00:00Z',
    updated_at: '2026-11-20T00:00:00Z',
    assigned_at: null,
    resolved_at: null,
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

describe('AgentQueuePage', () => {
  beforeEach(() => {
    useTicketsMock.mockReset()
    useAssignedTicketsMock.mockReset()
    useClaimTicketMock.mockReset()
    useClaimTicketMock.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
  })

  it('shows the empty queue state when there are no unassigned tickets', () => {
    useTicketsMock.mockReturnValue(query({ data: ticketPage([]) }))
    useAssignedTicketsMock.mockReturnValue(query({ data: ticketPage([]) }))
    renderPage(<AgentQueuePage />, { route: '/queue' })
    expect(screen.getByText('The queue is clear')).toBeInTheDocument()
  })

  it('renders unassigned tickets with a Claim action', () => {
    useTicketsMock.mockReturnValue(query({ data: ticketPage([ticket()]) }))
    useAssignedTicketsMock.mockReturnValue(query({ data: ticketPage([]) }))
    renderPage(<AgentQueuePage />, { route: '/queue' })
    expect(screen.getByText('Printer is broken')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Claim' })).toBeInTheDocument()
  })

  it('claims a ticket via the mutation', async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined)
    useClaimTicketMock.mockReturnValue({ mutateAsync, isPending: false })
    const unassigned = ticket()
    useTicketsMock.mockReturnValue(query({ data: ticketPage([unassigned]) }))
    useAssignedTicketsMock.mockReturnValue(query({ data: ticketPage([]) }))
    renderPage(<AgentQueuePage />, { route: '/queue' })

    fireEvent.click(screen.getByRole('button', { name: 'Claim' }))
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith(unassigned.id))
  })

  it('shows an error state with retry when the queue fails to load', () => {
    useTicketsMock.mockReturnValue(
      query({ isError: true, error: new Error('boom'), refetch: vi.fn() }),
    )
    useAssignedTicketsMock.mockReturnValue(query({ data: ticketPage([]) }))
    renderPage(<AgentQueuePage />, { route: '/queue' })
    expect(screen.getByText('Could not load tickets')).toBeInTheDocument()
  })
})
