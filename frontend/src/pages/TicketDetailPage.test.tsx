import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { TicketDetailPage } from './TicketDetailPage.tsx'
import { renderPage } from '../test/renderPage.tsx'
import { ApiError } from '../lib/api.ts'
import type { Ticket, User } from '../lib/types.ts'

const {
  useMeMock,
  useTicketMock,
  useCommentsMock,
  useHistoryMock,
  useAttachmentsMock,
  useContactMock,
  useAgentsMock,
} = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  useTicketMock: vi.fn(),
  useCommentsMock: vi.fn(),
  useHistoryMock: vi.fn(),
  useAttachmentsMock: vi.fn(),
  useContactMock: vi.fn(),
  useAgentsMock: vi.fn(),
}))

vi.mock('@clerk/react', () => ({ useAuth: () => ({ getToken: vi.fn() }) }))
vi.mock('../hooks/useMe.ts', () => ({ useMe: useMeMock }))
vi.mock('../hooks/useAdmin.ts', () => ({ useAgents: useAgentsMock }))
vi.mock('../hooks/useAccountRequests.ts', () => ({
  useCreateAccountRequest: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../hooks/useTickets.ts', () => ({
  useTicket: useTicketMock,
  useComments: useCommentsMock,
  useTicketHistory: useHistoryMock,
  useAttachments: useAttachmentsMock,
  useTicketContact: useContactMock,
  useCreateComment: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateTicket: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useClaimTicket: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAssignTicket: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUploadAttachment: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../hooks/useUserDirectory.ts', () => ({
  useUserDirectory: () => ({
    isResolved: true,
    user: () => undefined,
    label: () => 'Requester Name',
  }),
}))

const customer: User = {
  id: 'customer-1',
  full_name: 'Casey Customer',
  username: 'casey',
  email: 'casey@example.test',
  role: 'customer',
  is_active: true,
  image_url: null,
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
}

function ticket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    id: 'ticket-1',
    ticket_number: 1001,
    title: 'Printer is broken',
    description: 'It stopped working this morning.',
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

function q(data?: unknown, extra: Record<string, unknown> = {}) {
  return {
    data,
    isPending: data === undefined && !('isError' in extra),
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
    ...extra,
  }
}

function primeDetail(me: User, data: unknown, extra: Record<string, unknown> = {}) {
  useMeMock.mockReturnValue(q(me))
  useTicketMock.mockReturnValue(q(data, extra))
  useCommentsMock.mockReturnValue(q([]))
  useHistoryMock.mockReturnValue(q([]))
  useAttachmentsMock.mockReturnValue(q([]))
  useContactMock.mockReturnValue(q(undefined, { isPending: false }))
  useAgentsMock.mockReturnValue(q([]))
}

function renderDetail(ticketId = 'ticket-1') {
  return renderPage(
    <Routes>
      <Route path='/tickets/:ticketId' element={<TicketDetailPage />} />
    </Routes>,
    { route: `/tickets/${ticketId}` },
  )
}

describe('TicketDetailPage', () => {
  beforeEach(() => {
    useMeMock.mockReset()
    useTicketMock.mockReset()
    useCommentsMock.mockReset()
    useHistoryMock.mockReset()
    useAttachmentsMock.mockReset()
    useContactMock.mockReset()
    useAgentsMock.mockReset()
  })

  it('renders a not-found state for a 404 ticket', () => {
    primeDetail(customer, undefined, {
      isPending: false,
      isError: true,
      error: new ApiError(404, 'Ticket not found'),
    })
    renderDetail()
    expect(screen.getByText('Ticket not found')).toBeInTheDocument()
  })

  it('renders a generic error state for a server failure', () => {
    primeDetail(customer, undefined, {
      isPending: false,
      isError: true,
      error: new ApiError(500, 'Server error'),
    })
    renderDetail()
    expect(screen.getByText('Could not load this ticket')).toBeInTheDocument()
  })

  it('renders the ticket title and public details for the owning customer', () => {
    primeDetail(customer, ticket())
    renderDetail()
    expect(screen.getByText('Printer is broken')).toBeInTheDocument()
    expect(screen.getByText('It stopped working this morning.')).toBeInTheDocument()
  })

  it('does not offer staff-only history to a customer', () => {
    primeDetail(customer, ticket())
    renderDetail()
    // useTicketHistory is called with enabled=false for a customer.
    expect(useHistoryMock).toHaveBeenCalledWith('ticket-1', false)
  })
})
