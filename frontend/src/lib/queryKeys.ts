import type {
  AccountRequestListParams,
  InternalMessageListParams,
  NotificationListParams,
  RecipientSearchParams,
  StaffConversationListParams,
  TicketListParams,
  UserListParams,
} from './types.ts'

/**
 * Central query-key factory so that mutations invalidate the exact caches they
 * affect. Keys are hierarchical: invalidating `['tickets']` clears every
 * ticket list and detail view.
 */
export const queryKeys = {
  me: ['me'] as const,

  tickets: {
    all: ['tickets'] as const,
    list: (params?: TicketListParams) => ['tickets', 'list', params ?? {}] as const,
    assigned: (params?: TicketListParams) => ['tickets', 'assigned', params ?? {}] as const,
    detail: (id: string) => ['tickets', 'detail', id] as const,
    comments: (id: string) => ['tickets', 'comments', id] as const,
    history: (id: string) => ['tickets', 'history', id] as const,
    attachments: (id: string) => ['tickets', 'attachments', id] as const,
    feedback: (id: string) => ['tickets', 'feedback', id] as const,
  },

  notifications: {
    all: ['notifications'] as const,
    list: (params?: NotificationListParams) => ['notifications', 'list', params ?? {}] as const,
    unreadCount: ['notifications', 'unread-count'] as const,
  },

  staffMessages: {
    all: ['staff-messages'] as const,
    conversations: (params?: StaffConversationListParams) =>
      ['staff-messages', 'conversations', params ?? {}] as const,
    conversation: (id: string) => ['staff-messages', 'conversation', id] as const,
  },

  internalMessages: {
    all: ['internal-messages'] as const,
    recipients: (params?: RecipientSearchParams) =>
      ['internal-messages', 'recipients', params ?? {}] as const,
    sent: (params?: InternalMessageListParams) =>
      ['internal-messages', 'sent', params ?? {}] as const,
    sentDetail: (id: string, params?: { limit?: number; offset?: number }) =>
      ['internal-messages', 'sent-detail', id, params ?? {}] as const,
    received: ['internal-messages', 'received'] as const,
    receivedDetail: (id: string) =>
      ['internal-messages', 'received-detail', id] as const,
  },

  accountRequests: {
    all: ['account-requests'] as const,
    list: (params?: AccountRequestListParams) =>
      ['account-requests', 'list', params ?? {}] as const,
    detail: (id: string) => ['account-requests', 'detail', id] as const,
  },

  admin: {
    dashboard: ['admin', 'dashboard'] as const,
    agents: ['admin', 'agents'] as const,
    users: {
      all: ['admin', 'users'] as const,
      list: (params?: UserListParams) => ['admin', 'users', 'list', params ?? {}] as const,
      detail: (id: string) => ['admin', 'users', 'detail', id] as const,
    },
  },
} as const
