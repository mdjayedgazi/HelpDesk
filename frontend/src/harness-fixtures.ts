import type { Notification, SupportAnalytics, Ticket, User } from './lib/types.ts'

const owner: User = {
  id: 'u-owner',
  full_name: 'Jordan Avery',
  username: 'jordan',
  email: 'owner@example.test',
  role: 'owner',
  is_active: true,
  image_url: null,
  created_at: '2025-01-04T09:00:00Z',
  updated_at: '2026-11-20T09:00:00Z',
}

const people: User[] = [
  owner,
  ...['Avery Bennett', 'Priya Raman', 'Noah Fischer', 'Mei Tanaka', 'Lucas Moreau'].map(
    (full_name, index): User => ({
      id: `u-agent-${index + 1}`,
      full_name,
      username: full_name.toLowerCase().replace(/[^a-z]/g, ''),
      email: `agent${index + 1}@example.test`,
      role: 'agent',
      is_active: true,
      image_url: null,
      created_at: '2025-02-01T09:00:00Z',
      updated_at: '2026-11-19T09:00:00Z',
    }),
  ),
]

const titles = [
  'Unable to reset my password',
  'Billing invoice shows the wrong billing period',
  'SSO sign-in loop on the staging workspace',
  'Attachment upload fails for files over 8 MB',
  'Request access to the reporting dashboard',
  'Password reset email never arrives',
  'Outage page does not reflect the current incident',
  'Two accounts linked to the same verified email',
  'Exporting a ticket list loses the priority column',
  'Notification bell shows an out-of-date count',
  'Urgent: account locked before a client demo',
  'Add a second administrator to the workspace',
]

const statuses = ['OPEN', 'IN_PROGRESS', 'WAITING_ON_CUSTOMER', 'RESOLVED', 'CLOSED'] as const
const priorities = ['LOW', 'NORMAL', 'HIGH', 'URGENT'] as const
const categories = [
  'BILLING', 'ACCOUNT_ACCESS', 'TECHNICAL', 'OUTAGE', 'BUG', 'ACCOUNT_MANAGEMENT', 'OTHER',
] as const

const tickets: Ticket[] = Array.from({ length: 40 }, (_, index) => ({
  id: `t-${index + 1}`,
  ticket_number: 4821 - index,
  title: titles[index % titles.length]!,
  description: 'A realistic seeded request for layout verification.',
  status: statuses[index % statuses.length]!,
  priority: priorities[index % priorities.length]!,
  category: categories[index % categories.length]!,
  created_by_user_id: people[(index % 5) + 1]!.id,
  assignee_user_id: index % 4 === 0 ? null : people[(index % 5) + 1]!.id,
  created_at: '2026-11-18T10:00:00Z',
  updated_at: '2026-11-21T12:00:00Z',
  assigned_at: null,
  resolved_at: null,
}))

const analytics: SupportAnalytics = {
  generated_at: '2026-11-22T09:00:00Z',
  window_days: 14,
  totals: {
    total_tickets: 300,
    open_tickets: 68,
    unassigned_tickets: 14,
    resolved_tickets: 158,
    closed_tickets: 41,
    urgent_open_tickets: 6,
    total_users: 100,
    active_agents: 5,
    active_admins: 3,
  },
  tickets_by_status: { OPEN: 41, IN_PROGRESS: 27, WAITING_ON_CUSTOMER: 33, RESOLVED: 158, CLOSED: 41 },
  tickets_by_priority: { LOW: 62, NORMAL: 168, HIGH: 51, URGENT: 19 },
  tickets_by_category: {
    BILLING: 48, ACCOUNT_ACCESS: 33, TECHNICAL: 96, OUTAGE: 12, BUG: 61, ACCOUNT_MANAGEMENT: 22, OTHER: 28,
  },
  daily: Array.from({ length: 14 }, (_, index) => ({
    day: `2026-11-${String(index + 8).padStart(2, '0')}`,
    created: [12, 9, 15, 18, 7, 4, 6, 21, 17, 13, 11, 9, 16, 14][index]!,
    resolved: [8, 11, 10, 16, 12, 5, 4, 18, 19, 14, 9, 12, 13, 15][index]!,
  })),
  aging_over_7_days: 9,
  unassigned_over_24h: 7,
  waiting_on_customer: 33,
  agent_workload: people.slice(1).map((person, index) => ({
    user_id: person.id,
    full_name: person.full_name,
    image_url: null,
    active_tickets: [14, 11, 9, 6, 3][index]!,
    urgent_tickets: [3, 1, 2, 0, 0][index]!,
    resolved_tickets: [42, 31, 27, 18, 12][index]!,
  })),
}

const notifications: Notification[] = Array.from({ length: 8 }, (_, index) => ({
  id: `n-${index + 1}`,
  recipient_user_id: owner.id,
  related_ticket_id: tickets[index]!.id,
  related_conversation_id: null,
  related_internal_message_id: null,
  related_account_request_id: null,
  type: 'NEW_COMMENT',
  title: `New reply on #${tickets[index]!.ticket_number}`,
  message: 'A customer replied to the conversation.',
  is_read: index > 2,
  created_at: '2026-11-21T10:00:00Z',
}))

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })

function ticketPage(url: URL, source: Ticket[]) {
  const page = Math.max(1, Number(url.searchParams.get('page') ?? 1))
  const pageSize = Math.max(1, Number(url.searchParams.get('page_size') ?? 20))
  const status = url.searchParams.get('status')
  const priority = url.searchParams.get('priority')
  const unassigned = url.searchParams.get('unassigned') === 'true'
  const q = url.searchParams.get('q')?.toLowerCase()

  let filtered = source
  if (status) filtered = filtered.filter((t) => t.status === status)
  if (priority) filtered = filtered.filter((t) => t.priority === priority)
  if (unassigned) filtered = filtered.filter((t) => !t.assignee_user_id)
  if (q) filtered = filtered.filter((t) => t.title.toLowerCase().includes(q))

  const total = filtered.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const offset = (page - 1) * pageSize
  return {
    items: filtered.slice(offset, offset + pageSize),
    total,
    page,
    page_size: pageSize,
    total_pages: totalPages,
    has_next: page < totalPages,
    has_previous: page > 1,
  }
}

export function installFixtureFetch() {
  const original = window.fetch.bind(window)
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(raw, window.location.origin)
    const path = url.pathname
    console.info('[harness]', init?.method ?? 'GET', path + url.search)
    if (path.endsWith('/users/me')) {
      const roleParam = new URLSearchParams(window.location.search).get('user')
      if (roleParam && roleParam !== 'owner') {
        const base = roleParam === 'customer'
          ? { ...people[1]!, id: 'u-customer', role: 'customer', full_name: 'Casey Customer', username: 'casey', email: 'casey@example.test' }
          : roleParam === 'admin'
            ? { ...people[1]!, id: 'u-admin', role: 'admin', full_name: 'Dana Admin', username: 'dana', email: 'dana@example.test' }
            : people.find((u) => u.role === roleParam)
        if (base) return json(base)
      }
      return json(owner)
    }
    if (path.endsWith('/admin/analytics')) return json(analytics)
    if (path.endsWith('/admin/agents')) return json(people.slice(1))
    if (path.endsWith('/notifications/unread-count')) return json({ count: 5 })
    if (path.endsWith('/notifications')) return json(notifications)
    if (path.endsWith('/tickets/assigned')) return json(ticketPage(url, tickets.slice(0, 12)))
    if (path.endsWith('/tickets')) return json(ticketPage(url, tickets))
    if (path.endsWith('/users')) return json(people)
    if (path.endsWith('/staff-messages/directory')) {
      const q = (url.searchParams.get('q') ?? '').toLowerCase().replace(/^@/, '')
      const staff = people.filter((u) => u.role !== 'customer')
      const matched = q
        ? staff.filter((u) => u.full_name.toLowerCase().includes(q) || u.username.toLowerCase().includes(q))
        : staff
      return json(matched.slice(0, Number(url.searchParams.get('limit') ?? 20)))
    }
    if (url.pathname.match(/\/staff-messages\/conversations\/[^/]+$/)) {
      return json({
        conversation: {
          id: 'conv-1', subject: 'Shift handover',
          participant_a_id: 'u-agent-1', participant_b_id: 'u-owner',
          counterpart_user_id: 'u-agent-1', counterpart_full_name: 'Avery Bennett',
          counterpart_role: 'agent', counterpart_image_url: null,
          created_at: '2026-11-20T09:00:00Z', last_message_at: '2026-11-21T10:00:00Z',
          message_count: 1, unread_count: 0,
          last_message_preview: 'Thanks, will do.',
          last_message_sender_user_id: 'u-owner',
          last_received_preview: 'Can you cover the 3pm queue?',
          last_received_at: '2026-11-21T09:00:00Z',
        },
        messages: [
          { id: 'm-1', conversation_id: 'conv-1', sender_user_id: 'u-owner', body: 'Can you cover the 3pm queue?', created_at: '2026-11-21T09:00:00Z', read_at: null, mentioned_user_ids: [] },
          { id: 'm-2', conversation_id: 'conv-1', sender_user_id: 'u-agent-1', body: 'Thanks, will do.', created_at: '2026-11-21T10:00:00Z', read_at: null, mentioned_user_ids: [] },
        ],
      })
    }
    if (path.endsWith('/staff-messages/conversations')) {
      return json([
        {
          id: 'conv-1',
          subject: 'Shift handover',
          participant_a_id: 'u-agent-1',
          participant_b_id: 'u-owner',
          counterpart_user_id: 'u-agent-1',
          counterpart_full_name: 'Avery Bennett',
          counterpart_role: 'agent',
          counterpart_image_url: null,
          created_at: '2026-11-20T09:00:00Z',
          last_message_at: '2026-11-21T10:00:00Z',
          message_count: 1,
          unread_count: 0,
          last_message_preview: 'Thanks, will do.',
          last_message_sender_user_id: 'u-owner',
          last_received_preview: 'Can you cover the 3pm queue?',
          last_received_at: '2026-11-21T09:00:00Z',
        },
      ])
    }
    if (path.endsWith('/internal-messages/received')) return json([])
    if (path.endsWith('/account-requests')) return json([])
    if (path.endsWith('/attachments')) return json([])
    if (path.endsWith('/comments')) return json([])
    if (path.endsWith('/history')) return json([])
    if (path.endsWith('/feedback')) return json({ can_submit: false, feedback: null })
    return original(input, init)
  }
}
