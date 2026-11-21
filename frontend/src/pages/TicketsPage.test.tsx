import { screen, waitFor } from '@testing-library/react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { TicketsPage } from './TicketsPage.tsx'
import { renderPage } from '../test/renderPage.tsx'
import type { Ticket, User } from '../lib/types.ts'

const { useMeMock, useTicketsMock, useAgentsMock } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  useTicketsMock: vi.fn(),
  useAgentsMock: vi.fn(),
}))

vi.mock('../hooks/useMe.ts', () => ({ useMe: useMeMock }))
vi.mock('../hooks/useTickets.ts', () => ({ useTickets: useTicketsMock }))
vi.mock('../hooks/useAdmin.ts', () => ({ useAgents: useAgentsMock }))
vi.mock('../hooks/useUserDirectory.ts', () => ({
  useUserDirectory: () => ({
    isResolved: true,
    user: () => undefined,
    label: (id: string | null | undefined) => (id ? 'Requester Name' : '—'),
  }),
}))

const admin: User = {
  id: 'admin-1',
  full_name: 'Ada Admin',
  username: 'ada',
  email: 'ada@example.com',
  role: 'admin',
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
    assignee_user_id: null,
    created_at: '2026-11-20T00:00:00Z',
    updated_at: '2026-11-20T00:00:00Z',
    assigned_at: null,
    resolved_at: null,
    ...overrides,
  }
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid='location'>{location.pathname + location.search}</div>
}

function renderTickets(route: string) {
  return renderPage(
    <Routes>
      <Route
        path='/tickets'
        element={
          <>
            <TicketsPage />
            <LocationProbe />
          </>
        }
      />
    </Routes>,
    { route },
  )
}

describe('TicketsPage URL filters', () => {
  beforeEach(() => {
    useMeMock.mockReset()
    useTicketsMock.mockReset()
    useAgentsMock.mockReset()
    useMeMock.mockReturnValue({
      isPending: false,
      data: admin,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    useAgentsMock.mockReturnValue({ data: [], isPending: false, isError: false })
    useTicketsMock.mockReturnValue({
      isPending: false,
      isError: false,
      error: null,
      data: [ticket({ title: 'Printer is broken' })],
      refetch: vi.fn(),
    })
  })

  it('adopts a status deep link and passes it to the tickets query', () => {
    renderTickets('/tickets?status=RESOLVED')

    expect(useTicketsMock).toHaveBeenCalled()
    const params = useTicketsMock.mock.calls.at(-1)![0]
    expect(params.status).toBe('RESOLVED')
    expect(
      screen.getByRole('combobox', { name: 'Filter by status' }),
    ).toHaveValue('RESOLVED')
  })

  it('ignores an unknown status value instead of forwarding it', () => {
    renderTickets('/tickets?status=BOGUS')

    const params = useTicketsMock.mock.calls.at(-1)![0]
    expect(params.status).toBeUndefined()
  })

  it('keeps the URL stable when nothing changes (no navigation loop)', async () => {
    renderTickets('/tickets?priority=URGENT')

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/tickets?priority=URGENT')
    })
    const params = useTicketsMock.mock.calls.at(-1)![0]
    expect(params.priority).toBe('URGENT')
  })

  it('does not forward the unassigned sentinel as a user id', () => {
    renderTickets('/tickets?assignee=none')

    const params = useTicketsMock.mock.calls.at(-1)![0]
    expect(params.assignee_user_id).toBeUndefined()
    expect(screen.getByText(/does not expose a server-side unassigned filter/i)).toBeInTheDocument()
  })
})
