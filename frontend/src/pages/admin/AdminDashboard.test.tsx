import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { AdminDashboard } from './AdminDashboard.tsx'
import { renderPage } from '../../test/renderPage.tsx'
import type { SupportAnalytics } from '../../lib/types.ts'

const { useSupportAnalyticsMock } = vi.hoisted(() => ({
  useSupportAnalyticsMock: vi.fn(),
}))

vi.mock('../../hooks/useAdmin.ts', () => ({
  useSupportAnalytics: useSupportAnalyticsMock,
}))

function buildAnalytics(): SupportAnalytics {
  return {
    generated_at: '2026-11-21T10:00:00Z',
    window_days: 14,
    totals: {
      total_tickets: 42,
      open_tickets: 12,
      unassigned_tickets: 3,
      resolved_tickets: 21,
      closed_tickets: 9,
      urgent_open_tickets: 2,
      total_users: 17,
      active_agents: 4,
      active_admins: 2,
    },
    tickets_by_status: {
      OPEN: 8,
      IN_PROGRESS: 4,
      WAITING_ON_CUSTOMER: 3,
      RESOLVED: 21,
      CLOSED: 6,
    },
    tickets_by_priority: { LOW: 4, NORMAL: 28, HIGH: 8, URGENT: 2 },
    tickets_by_category: {
      BILLING: 6,
      ACCOUNT_ACCESS: 3,
      TECHNICAL: 14,
      OUTAGE: 2,
      BUG: 7,
      ACCOUNT_MANAGEMENT: 2,
      OTHER: 8,
    },
    daily: Array.from({ length: 14 }, (_, index) => ({
      day: `2026-11-${String(index + 8).padStart(2, '0')}`,
      created: index % 4,
      resolved: index % 3,
    })),
    aging_over_7_days: 2,
    unassigned_over_24h: 1,
    answered_without_resolution: 3,
    agent_workload: [
      {
        user_id: 'agent-1',
        full_name: 'Avery Bennett',
        image_url: null,
        active_tickets: 4,
        urgent_tickets: 1,
        resolved_tickets: 12,
      },
    ],
  }
}

describe('AdminDashboard', () => {
  beforeEach(() => {
    useSupportAnalyticsMock.mockReset()
  })

  it('renders real totals, charts and the team workload', () => {
    useSupportAnalyticsMock.mockReturnValue({
      isPending: false,
      isError: false,
      error: null,
      data: buildAnalytics(),
      refetch: vi.fn(),
    })

    renderPage(<AdminDashboard />)

    expect(screen.getByRole('heading', { name: 'Support operations' })).toBeInTheDocument()
    expect(screen.getAllByText('42').length).toBeGreaterThan(0)
    expect(screen.getByText('Ticket volume')).toBeInTheDocument()
    expect(screen.getByText('Status composition')).toBeInTheDocument()
    expect(screen.getByText('Priority mix')).toBeInTheDocument()
    expect(screen.getByText('Team workload')).toBeInTheDocument()
    expect(screen.getByText('Avery Bennett')).toBeInTheDocument()
  })

  it('exposes chart data as an accessible table', () => {
    useSupportAnalyticsMock.mockReturnValue({
      isPending: false,
      isError: false,
      error: null,
      data: buildAnalytics(),
      refetch: vi.fn(),
    })

    renderPage(<AdminDashboard />)

    // Each chart ships a visually hidden table with a caption, so a screen
    // reader gets real numbers rather than an unlabelled graphic.
    const tables = screen.getAllByRole('table', { hidden: true })
    expect(tables.length).toBeGreaterThanOrEqual(3)
    expect(screen.getAllByText('Tickets by status').length).toBeGreaterThan(0)
  })

  it('shows an attention list only for real, non-zero problems', () => {
    useSupportAnalyticsMock.mockReturnValue({
      isPending: false,
      isError: false,
      error: null,
      data: buildAnalytics(),
      refetch: vi.fn(),
    })

    renderPage(<AdminDashboard />)

    expect(screen.getByText('Needs attention')).toBeInTheDocument()
    expect(screen.getByText('Urgent, still open')).toBeInTheDocument()
    expect(screen.getByText('Unassigned over 24h')).toBeInTheDocument()
  })

  it('shows the healthy state when nothing needs attention', () => {
    const healthy = buildAnalytics()
    healthy.totals.urgent_open_tickets = 0
    healthy.aging_over_7_days = 0
    healthy.unassigned_over_24h = 0
    healthy.answered_without_resolution = 0

    useSupportAnalyticsMock.mockReturnValue({
      isPending: false,
      isError: false,
      error: null,
      data: healthy,
      refetch: vi.fn(),
    })

    renderPage(<AdminDashboard />)

    expect(screen.getByText('Nothing is waiting on the team')).toBeInTheDocument()
    expect(screen.queryByText('Needs attention')).not.toBeInTheDocument()
  })

  it('shows the owner variant heading and inbox action', () => {
    useSupportAnalyticsMock.mockReturnValue({
      isPending: false,
      isError: false,
      error: null,
      data: buildAnalytics(),
      refetch: vi.fn(),
    })

    renderPage(<AdminDashboard variant='owner' />)

    expect(screen.getByRole('heading', { name: 'Owner overview' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /owner inbox/i })).toBeInTheDocument()
  })

  it('renders an error state with a retry when the request fails', () => {
    const refetch = vi.fn()
    useSupportAnalyticsMock.mockReturnValue({
      isPending: false,
      isError: true,
      error: new Error('network down'),
      data: undefined,
      refetch,
    })

    renderPage(<AdminDashboard />)

    expect(screen.getByText('Could not load dashboard')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })
})
