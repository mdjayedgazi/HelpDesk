import { describe, expect, it } from 'vite-plus/test'

import {
  assignmentCoverage,
  attentionItems,
  compareHalves,
  openShare,
  parseDay,
  resolutionShare,
  shortDayLabel,
} from './analytics.ts'
import type { DailyTicketPoint, SupportAnalytics } from './types.ts'

function point(day: string, created: number, resolved: number): DailyTicketPoint {
  return { day, created, resolved }
}

function buildDaily(values: Array<[number, number]>): DailyTicketPoint[] {
  return values.map(([created, resolved], index) =>
    point(`2026-11-${String(index + 1).padStart(2, '0')}`, created, resolved),
  )
}

function buildAnalytics(overrides: Partial<SupportAnalytics> = {}): SupportAnalytics {
  return {
    generated_at: '2026-11-21T10:00:00Z',
    window_days: 14,
    totals: {
      total_tickets: 20,
      open_tickets: 8,
      unassigned_tickets: 2,
      resolved_tickets: 9,
      closed_tickets: 3,
      urgent_open_tickets: 1,
      total_users: 12,
      active_agents: 4,
      active_admins: 2,
    },
    tickets_by_status: {
      OPEN: 5,
      IN_PROGRESS: 3,
      WAITING_ON_CUSTOMER: 2,
      RESOLVED: 9,
      CLOSED: 3,
    },
    tickets_by_priority: { LOW: 2, NORMAL: 14, HIGH: 3, URGENT: 1 },
    tickets_by_category: {
      BILLING: 4,
      ACCOUNT_ACCESS: 2,
      TECHNICAL: 6,
      OUTAGE: 1,
      BUG: 2,
      ACCOUNT_MANAGEMENT: 1,
      OTHER: 4,
    },
    daily: buildDaily(Array.from({ length: 14 }, () => [1, 1] as [number, number])),
    aging_over_7_days: 0,
    unassigned_over_24h: 0,
    waiting_on_customer: 2,
    agent_workload: [],
    ...overrides,
  }
}

describe('day parsing', () => {
  it('parses a backend date without a timezone shift', () => {
    const date = parseDay('2026-11-21')
    expect(date.getFullYear()).toBe(2026)
    expect(date.getMonth()).toBe(10)
    expect(date.getDate()).toBe(21)
    expect(shortDayLabel('2026-11-21')).toBeTruthy()
  })
})

describe('compareHalves', () => {
  it('compares two equal halves of the window', () => {
    const daily = buildDaily([
      [1, 0],
      [1, 0],
      [0, 1],
      [0, 1],
      [3, 1],
      [3, 1],
      [3, 1],
      [3, 1],
    ])
    const comparison = compareHalves(daily, 'created')
    expect(comparison).not.toBeNull()
    expect(comparison!.current).toBe(12)
    expect(comparison!.previous).toBe(2)
    expect(comparison!.changePercent).toBe(500)
    expect(comparison!.direction).toBe('up')
  })

  it('reports no percentage when the previous half was empty', () => {
    const daily = buildDaily([
      [0, 0],
      [0, 0],
      [0, 0],
      [0, 0],
      [1, 0],
      [1, 0],
      [1, 0],
      [1, 0],
    ])
    const comparison = compareHalves(daily, 'created')
    expect(comparison!.changePercent).toBeNull()
    expect(comparison!.direction).toBe('up')
  })

  it('returns null for a window too short to compare honestly', () => {
    expect(compareHalves(buildDaily([[1, 1]]), 'created')).toBeNull()
  })
})

describe('shares', () => {
  it('computes resolution share over finished tickets only', () => {
    // 9 resolved / (9 resolved + 3 closed) = 75%
    expect(resolutionShare(buildAnalytics())).toBe(75)
  })

  it('returns null when nothing has finished', () => {
    const analytics = buildAnalytics({
      totals: {
        ...buildAnalytics().totals,
        resolved_tickets: 0,
        closed_tickets: 0,
      },
    })
    expect(resolutionShare(analytics)).toBeNull()
  })

  it('computes the open share of all tickets', () => {
    expect(openShare(buildAnalytics())).toBe(40)
  })

  it('computes assignment coverage over active work', () => {
    // active = open(8) + waiting(2) = 10; assigned = 10 - 2 unassigned = 8
    expect(assignmentCoverage(buildAnalytics())).toBe(80)
  })
})

describe('attentionItems', () => {
  it('returns nothing for a healthy queue', () => {
    const analytics = buildAnalytics({
      totals: { ...buildAnalytics().totals, urgent_open_tickets: 0 },
      aging_over_7_days: 0,
      unassigned_over_24h: 0,
      waiting_on_customer: 0,
    })
    expect(attentionItems(analytics)).toHaveLength(0)
  })

  it('orders items by severity and carries real counts', () => {
    const analytics = buildAnalytics({
      totals: { ...buildAnalytics().totals, urgent_open_tickets: 3 },
      aging_over_7_days: 4,
      unassigned_over_24h: 1,
      waiting_on_customer: 2,
    })
    const items = attentionItems(analytics)
    expect(items.map((item) => item.key)).toEqual([
      'urgent',
      'unassigned-aged',
      'aging',
      'waiting',
    ])
    expect(items[0]!.value).toBe(3)
    expect(items[0]!.tone).toBe('danger')
    expect(items.every((item) => item.to.startsWith('/tickets'))).toBe(true)
    // Aging spans three statuses, so it must not pretend a single-status
    // filter represents the number it shows.
    expect(items.find((item) => item.key === 'aging')!.to).toBe('/tickets')
  })
})
