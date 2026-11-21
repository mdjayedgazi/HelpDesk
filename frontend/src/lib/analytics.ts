import type { DailyTicketPoint, SupportAnalytics } from './types.ts'

/**
 * Derived values for the dashboard.
 *
 * These helpers only transform numbers the backend actually returned. They
 * never estimate a missing metric: when there is not enough data to compute a
 * comparison, they return `null` so the UI can omit it rather than show a
 * misleading figure.
 */

const dayFormat = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' })
const weekdayFormat = new Intl.DateTimeFormat(undefined, { weekday: 'short' })

/** Parse a backend `YYYY-MM-DD` day into a local date at noon (DST-safe). */
export function parseDay(day: string): Date {
  const [year, month, date] = day.split('-').map(Number)
  return new Date(year!, (month ?? 1) - 1, date ?? 1, 12)
}

export function shortDayLabel(day: string): string {
  return dayFormat.format(parseDay(day))
}

export function weekdayLabel(day: string): string {
  return weekdayFormat.format(parseDay(day))
}

/** Sum a series over a slice of days. */
export function sumRange(
  daily: DailyTicketPoint[],
  key: 'created' | 'resolved',
  from: number,
  to: number,
): number {
  return daily.slice(from, to).reduce((sum, point) => sum + point[key], 0)
}

export interface WindowComparison {
  current: number
  previous: number
  /** Percentage change, rounded. `null` when the previous window was empty. */
  changePercent: number | null
  direction: 'up' | 'down' | 'flat'
}

/**
 * Compare the most recent half of the window with the half before it.
 *
 * A 14-day window becomes two 7-day halves. This is a real same-length
 * comparison; it is only returned when both halves exist.
 */
export function compareHalves(
  daily: DailyTicketPoint[],
  key: 'created' | 'resolved',
): WindowComparison | null {
  if (daily.length < 4) return null
  const half = Math.floor(daily.length / 2)
  const previous = sumRange(daily, key, 0, half)
  const current = sumRange(daily, key, daily.length - half, daily.length)
  const changePercent =
    previous === 0 ? null : Math.round(((current - previous) / previous) * 100)
  const direction =
    current === previous ? 'flat' : current > previous ? 'up' : 'down'
  return { current, previous, changePercent, direction }
}

/** The share of resolved tickets over all finished work (resolved + closed). */
export function resolutionShare(analytics: SupportAnalytics): number | null {
  const finished =
    analytics.totals.resolved_tickets + analytics.totals.closed_tickets
  if (finished === 0) return null
  return Math.round((analytics.totals.resolved_tickets / finished) * 100)
}

/** Share of all tickets currently awaiting team action. */
export function openShare(analytics: SupportAnalytics): number | null {
  const total = analytics.totals.total_tickets
  if (total === 0) return null
  return Math.round((analytics.totals.open_tickets / total) * 100)
}

/** Share of active tickets that are already assigned to someone. */
export function assignmentCoverage(analytics: SupportAnalytics): number | null {
  const activeWork =
    analytics.totals.open_tickets + analytics.answered_without_resolution
  if (activeWork === 0) return null
  const unassigned = analytics.totals.unassigned_tickets
  return Math.round(((activeWork - unassigned) / activeWork) * 100)
}

/**
 * Operational attention items, ordered by severity.
 *
 * Only non-zero items are returned, so a healthy queue produces an empty list
 * (the UI then shows a positive "nothing needs attention" state).
 */
export interface AttentionItem {
  key: string
  label: string
  detail: string
  value: number
  tone: 'danger' | 'warning' | 'info'
  to: string
}

export function attentionItems(analytics: SupportAnalytics): AttentionItem[] {
  const items: AttentionItem[] = []
  const { totals } = analytics

  if (totals.urgent_open_tickets > 0) {
    items.push({
      key: 'urgent',
      label: 'Urgent, still open',
      detail: 'Escalated tickets that have not been resolved',
      value: totals.urgent_open_tickets,
      tone: 'danger',
      to: '/tickets?priority=URGENT',
    })
  }
  if (analytics.unassigned_over_24h > 0) {
    items.push({
      key: 'unassigned-aged',
      label: 'Unassigned over 24h',
      detail: 'No agent owns these tickets yet',
      value: analytics.unassigned_over_24h,
      tone: 'warning',
      to: '/tickets?assignee=none',
    })
  }
  if (analytics.aging_over_7_days > 0) {
    items.push({
      key: 'aging',
      label: 'No activity for 7 days',
      detail: 'Active tickets that have gone quiet',
      value: analytics.aging_over_7_days,
      tone: 'warning',
      to: '/tickets?status=IN_PROGRESS',
    })
  }
  if (analytics.answered_without_resolution > 0) {
    items.push({
      key: 'waiting',
      label: 'Waiting on the customer',
      detail: 'The team replied and is blocked on a response',
      value: analytics.answered_without_resolution,
      tone: 'info',
      to: '/tickets?status=WAITING_ON_CUSTOMER',
    })
  }

  return items
}
