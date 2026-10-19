import type {
  EscalationCategory,
  EscalationStatus,
  ImpactLevel,
  InternalAudience,
  NotificationType,
  Role,
  TicketCategory,
  TicketPriority,
  TicketStatus,
} from './types.ts'

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
})

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
})

const relativeFormatter = new Intl.RelativeTimeFormat(undefined, {
  numeric: 'auto',
})

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return dateFormatter.format(date)
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return dateTimeFormatter.format(date)
}

const UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ['year', 365 * 24 * 60 * 60 * 1000],
  ['month', 30 * 24 * 60 * 60 * 1000],
  ['week', 7 * 24 * 60 * 60 * 1000],
  ['day', 24 * 60 * 60 * 1000],
  ['hour', 60 * 60 * 1000],
  ['minute', 60 * 1000],
]

/** Compact relative time such as "just now", "3h ago" or "in 2 days". */
export function formatRelative(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'

  const diff = date.getTime() - Date.now()
  const abs = Math.abs(diff)
  if (abs < 45 * 1000) return 'just now'

  for (const [unit, ms] of UNITS) {
    if (abs >= ms || unit === 'minute') {
      return relativeFormatter.format(Math.round(diff / ms), unit)
    }
  }
  return formatDate(value)
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '—'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let size = bytes / 1024
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(size >= 10 || index === 0 ? 0 : 1)} ${units[index]}`
}

export function ticketRef(ticketNumber: number): string {
  return `#${ticketNumber}`
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase()
  return `${parts[0]![0] ?? ''}${parts[parts.length - 1]![0] ?? ''}`.toUpperCase()
}

export const statusLabels: Record<TicketStatus, string> = {
  OPEN: 'Open',
  IN_PROGRESS: 'In progress',
  WAITING_ON_CUSTOMER: 'Waiting on customer',
  RESOLVED: 'Resolved',
  CLOSED: 'Closed',
}

export const priorityLabels: Record<TicketPriority, string> = {
  LOW: 'Low',
  NORMAL: 'Normal',
  HIGH: 'High',
  URGENT: 'Urgent',
}

export const roleLabels: Record<Role, string> = {
  customer: 'Customer',
  agent: 'Agent',
  admin: 'Administrator',
  owner: 'Owner',
}

/** Human labels for the Owner Inbox compose audiences. */
export const audienceLabels: Record<InternalAudience, string> = {
  everyone: 'Everyone',
  agents: 'All agents',
  admins: 'All administrators',
  individual: 'One employee',
}

export const ticketCategoryLabels: Record<TicketCategory, string> = {
  BILLING: 'Billing',
  ACCOUNT_ACCESS: 'Account access',
  TECHNICAL: 'Technical',
  OUTAGE: 'Outage',
  BUG: 'Bug',
  ACCOUNT_MANAGEMENT: 'Account management',
  OTHER: 'Other',
}

export const impactLabels: Record<ImpactLevel, string> = {
  LOW: 'Low — minor inconvenience',
  MEDIUM: 'Medium — work is slowed down',
  HIGH: 'High — work is blocked',
  CRITICAL: 'Critical — business stopped',
}

export const escalationStatusLabels: Record<EscalationStatus, string> = {
  PENDING: 'Pending',
  IN_REVIEW: 'In review',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  COMPLETED: 'Completed',
}

export const escalationCategoryLabels: Record<EscalationCategory, string> = {
  ACCOUNT_RECOVERY: 'Account recovery',
  IDENTITY_LINKING: 'Identity linking',
  PROFILE_CORRECTION: 'Profile correction',
  ROLE_OR_STATUS_CHANGE: 'Role or status change',
  OTHER: 'Other',
}

export const notificationTypeLabels: Record<NotificationType, string> = {
  TICKET_ASSIGNED: 'Assignment',
  NEW_COMMENT: 'Comment',
  STATUS_CHANGED: 'Status',
  PRIORITY_CHANGED: 'Priority',
  TICKET_NEEDS_ASSIGNMENT: 'Needs assignment',
  STAFF_MESSAGE_RECEIVED: 'Private message',
  OWNER_MESSAGE_RECEIVED: 'Private message',
  ESCALATION_CREATED: 'Account request',
  ESCALATION_UPDATED: 'Account request',
}
