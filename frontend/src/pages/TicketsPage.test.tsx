import { fireEvent, screen, waitFor } from '@testing-library/react'
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
vi.mock('../hooks/useTickets.ts', () => ({
  useTickets: useTicketsMock,
  usePrefetchTicketPage: () => vi.fn(),
}))
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
      isFetching: false,
      isError: false,
      error: null,
      data: {
        items: [ticket({ title: 'Printer is broken' })],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
        has_next: false,
        has_previous: false,
      },
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
    // The unassigned deep link is now a server-side filter, not a client-side
    // one, so the page count and totals are exact.
    expect(params.unassigned).toBe(true)
    expect(screen.getByText(/applied across the whole result set/i)).toBeInTheDocument()
  })
})

describe('TicketsPage pagination integration', () => {
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
  })

  function pageResult(overrides: Record<string, unknown> = {}) {
    return {
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
      data: {
        items: [ticket({ title: 'Printer is broken' })],
        total: 300,
        page: 1,
        page_size: 20,
        total_pages: 15,
        has_next: true,
        has_previous: false,
        ...overrides,
      },
      refetch: vi.fn(),
    }
  }

  it('requests page 1 with the fixed page size on first load', () => {
    useTicketsMock.mockReturnValue(pageResult())
    renderTickets('/tickets')

    const params = useTicketsMock.mock.calls.at(-1)![0]
    expect(params.page).toBe(1)
    expect(params.page_size).toBe(20)
  })

  it('advances to the next page when Next is clicked', () => {
    useTicketsMock.mockReturnValue(pageResult())
    renderTickets('/tickets')

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))

    const params = useTicketsMock.mock.calls.at(-1)![0]
    expect(params.page).toBe(2)
  })

  it('wraps from the last page back to page 1', () => {
    // Two pages: page 1 -> 2 -> wraps back to 1.
    useTicketsMock.mockReturnValue(
      pageResult({ page: 1, total: 30, total_pages: 2, has_next: true }),
    )
    renderTickets('/tickets')

    fireEvent.click(screen.getByRole('button', { name: 'Next page' })) // -> 2
    fireEvent.click(screen.getByRole('button', { name: 'Next page' })) // -> wrap to 1

    const requested = useTicketsMock.mock.calls.map((call) => call[0]?.page)
    expect(requested).toContain(2)
    expect(requested.at(-1)).toBe(1)
  })

  it('wraps from page 1 back to the last page', () => {
    useTicketsMock.mockReturnValue(pageResult())
    renderTickets('/tickets')

    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }))

    const params = useTicketsMock.mock.calls.at(-1)![0]
    expect(params.page).toBe(15)
  })

  it('resets to page 1 when the status filter changes', () => {
    useTicketsMock.mockReturnValue(pageResult())
    renderTickets('/tickets')

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter by status' }), {
      target: { value: 'OPEN' },
    })

    const params = useTicketsMock.mock.calls.at(-1)![0]
    expect(params.status).toBe('OPEN')
    expect(params.page).toBe(1)
  })

  it('resets to page 1 when the search changes', async () => {
    useTicketsMock.mockReturnValue(pageResult())
    renderTickets('/tickets')

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Search tickets by title' }), {
      target: { value: 'printer' },
    })

    await waitFor(() => {
      const params = useTicketsMock.mock.calls.at(-1)![0]
      expect(params.q).toBe('printer')
      expect(params.page).toBe(1)
    })
  })

  it('reconciles an out-of-range page with the server total', () => {
    // The user walks forward while the set looks large, then the server reports
    // that records were deleted and only 3 pages remain. Landing on page 5 must
    // snap back to the last valid page (3) instead of showing an empty page 5.
    useTicketsMock.mockImplementation((params: { page?: number }) => {
      const requested = params?.page ?? 1
      if (requested >= 5) {
        return pageResult({
          items: [],
          total: 55,
          page: requested,
          total_pages: 3,
          has_next: false,
          has_previous: true,
        })
      }
      return pageResult({ page: requested, total: 100, total_pages: 5, has_next: true })
    })
    renderTickets('/tickets')

    for (let step = 0; step < 4; step += 1) {
      fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    }

    // After the out-of-range response the page snaps to the last valid page.
    const pages = useTicketsMock.mock.calls.map((call) => call[0]?.page)
    expect(pages).toContain(3)
  })

  it('never requests a page beyond the reported total_pages', () => {
    useTicketsMock.mockReturnValue(
      pageResult({ page: 1, total_pages: 15, has_next: true }),
    )
    renderTickets('/tickets')

    // Cycle Next through the whole set once and confirm every requested page
    // stays within 1..15 (the wrap returns to 1, never 16).
    for (let step = 0; step < 20; step += 1) {
      fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    }
    const requested = useTicketsMock.mock.calls.map((call) => call[0]?.page)
    for (const page of requested) {
      expect(page).toBeGreaterThanOrEqual(1)
      expect(page).toBeLessThanOrEqual(15)
    }
  })
})
