import { resolveApiBase } from './apiBase.ts'
import type {
  AccountRequest,
  AccountRequestComment,
  AccountRequestCommentInput,
  AccountRequestCreateInput,
  AccountRequestDetail,
  AccountRequestListParams,
  AccountRequestStatusInput,
  AdminDashboard,
  AdminUserUpdateInput,
  Attachment,
  Comment,
  CommentCreateInput,
  InternalMessageCreateInput,
  InternalMessageDetail,
  InternalMessageListParams,
  InternalMessageReceived,
  InternalMessageSummary,
  MarkReadResult,
  Notification,
  NotificationListParams,
  NotificationUnreadCount,
  ProfileUpdateInput,
  ReceivedMessageListParams,
  RecipientSearchParams,
  Role,
  StaffComment,
  StaffConversation,
  StaffConversationDetail,
  StaffConversationListParams,
  StaffMessage,
  Ticket,
  TicketContact,
  TicketCreateInput,
  TicketFeedback,
  TicketFeedbackInput,
  TicketFeedbackState,
  TicketHistoryEntry,
  TicketListParams,
  TicketStatus,
  TicketUpdateInput,
  User,
  UserListParams,
} from './types.ts'

/**
 * Base URL of the FastAPI backend.
 *
 * Development runs the API on port 8000 (see `VITE_API_URL`). All requests go
 * through `/api/v1` paths that the backend routers actually define.
 */
const API_BASE = resolveApiBase(import.meta.env.VITE_API_URL, import.meta.env.PROD)

export type TokenGetter = () => Promise<string | null>

export interface FieldError {
  field: string
  message: string
}

export class ApiError extends Error {
  readonly status: number
  readonly fieldErrors: FieldError[]
  readonly raw: unknown

  constructor(
    status: number,
    message: string,
    options: { fieldErrors?: FieldError[]; raw?: unknown } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fieldErrors = options.fieldErrors ?? []
    this.raw = options.raw
  }

  get isUnauthorized(): boolean {
    return this.status === 401
  }

  get isForbidden(): boolean {
    return this.status === 403
  }

  get isNotFound(): boolean {
    return this.status === 404
  }
}

export type QueryValue = string | number | boolean | undefined | null

export function buildQuery(query?: Record<string, QueryValue>): string {
  if (!query) return ''
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const serialized = params.toString()
  return serialized ? `?${serialized}` : ''
}

interface FastApiValidationError {
  loc?: unknown[]
  msg?: string
  type?: string
}

function parseErrorBody(status: number, body: unknown): ApiError {
  let message = defaultMessageForStatus(status)
  const fieldErrors: FieldError[] = []

  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail

    if (typeof detail === 'string') {
      message = detail
    } else if (Array.isArray(detail)) {
      for (const item of detail as FastApiValidationError[]) {
        const loc = Array.isArray(item.loc) ? item.loc : []
        const field = loc
          .filter((part) => typeof part === 'string' || typeof part === 'number')
          .filter((part) => part !== 'body' && part !== 'query')
          .join('.')
        if (item.msg) {
          fieldErrors.push({ field, message: item.msg })
        }
      }
      if (!message || fieldErrors.length > 0) {
        message = fieldErrors[0]?.message ?? 'Some fields need your attention.'
      }
    }
  }

  return new ApiError(status, message, { fieldErrors, raw: body })
}

function defaultMessageForStatus(status: number): string {
  switch (status) {
    case 400:
      return 'That request was not valid.'
    case 401:
      return 'Your session has expired. Please sign in again.'
    case 403:
      return 'You do not have permission to do that.'
    case 404:
      return 'We could not find what you were looking for.'
    case 409:
      return 'That action conflicts with the current state. Please refresh.'
    case 413:
      return 'That file is too large.'
    case 415:
      return 'That file type is not supported.'
    case 422:
      return 'Some fields need your attention.'
    case 429:
      return 'Too many requests. Please slow down and try again.'
    default:
      if (status >= 500) {
        return 'Something went wrong on our side. Please try again.'
      }
      return 'Request failed.'
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  query?: Record<string, QueryValue>
  signal?: AbortSignal
  /** Raw multipart payload; takes precedence over `body`. */
  formData?: FormData
}

export interface ApiClient {
  request: <T>(path: string, options?: RequestOptions) => Promise<T>
  /** Absolute URL to the backend for a given API path. */
  url: (path: string) => string
}

/**
 * Build an API client bound to a Clerk session-token getter.
 *
 * The backend verifies a Clerk *session token* passed as
 * `Authorization: Bearer <token>` (see `backend/app/core/auth.py`), so we fetch
 * a fresh token per request rather than caching it in localStorage.
 */
export function createApiClient(getToken: TokenGetter): ApiClient {
  const url = (path: string) => `${API_BASE}${path}`

  async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, query, signal, formData } = options

    const token = await getToken()
    if (!token) {
      throw new ApiError(401, defaultMessageForStatus(401))
    }

    const headers = new Headers()
    headers.set('Accept', 'application/json')
    headers.set('Authorization', `Bearer ${token}`)

    let payload: BodyInit | undefined
    if (formData) {
      payload = formData
    } else if (body !== undefined) {
      headers.set('Content-Type', 'application/json')
      payload = JSON.stringify(body)
    }

    let response: Response
    try {
      response = await fetch(url(`${path}${buildQuery(query)}`), {
        method,
        headers,
        body: payload,
        signal,
        credentials: 'omit',
      })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw error
      }
      throw new ApiError(0, 'Could not reach the HelpDesk server. Check your connection.')
    }

    if (response.status === 204) {
      return undefined as T
    }

    const contentType = response.headers.get('content-type') ?? ''
    const isJson = contentType.includes('application/json')
    const parsed: unknown = isJson
      ? await response.json().catch(() => null)
      : await response.text().catch(() => null)

    if (!response.ok) {
      throw parseErrorBody(response.status, parsed)
    }

    return parsed as T
  }

  return { request, url }
}

/* -------------------------------------------------------------------------- */
/* Typed endpoint helpers                                                     */
/* -------------------------------------------------------------------------- */

const P = '/api/v1'

export const endpoints = {
  me: () => `${P}/users/me`,
  syncAvatar: () => `${P}/users/me/avatar`,

  tickets: () => `${P}/tickets`,
  ticket: (id: string) => `${P}/tickets/${id}`,
  ticketContact: (id: string) => `${P}/tickets/${id}/contact`,
  assignedTickets: () => `${P}/tickets/assigned`,
  claimTicket: (id: string) => `${P}/tickets/${id}/claim`,
  assignTicket: (id: string) => `${P}/tickets/${id}/assign`,

  comments: (ticketId: string) => `${P}/tickets/${ticketId}/comments`,
  history: (ticketId: string) => `${P}/tickets/${ticketId}/history`,
  attachments: (ticketId: string) => `${P}/tickets/${ticketId}/attachments`,
  downloadAttachment: (attachmentId: string) => `${P}/attachments/${attachmentId}/download`,

  notifications: () => `${P}/notifications`,
  notificationUnreadCount: () => `${P}/notifications/unread-count`,
  notification: (id: string) => `${P}/notifications/${id}`,
  readAllNotifications: () => `${P}/notifications/read-all`,

  ticketFeedback: (ticketId: string) => `${P}/tickets/${ticketId}/feedback`,

  staffConversations: () => `${P}/staff-messages/conversations`,
  staffConversation: (id: string) => `${P}/staff-messages/conversations/${id}`,
  staffConversationMessages: (id: string) => `${P}/staff-messages/conversations/${id}/messages`,
  staffConversationRead: (id: string) => `${P}/staff-messages/conversations/${id}/read`,

  messageRecipients: () => `${P}/internal-messages/recipients`,
  internalMessages: () => `${P}/internal-messages`,
  sentMessages: () => `${P}/internal-messages/sent`,
  sentMessage: (id: string) => `${P}/internal-messages/sent/${id}`,
  receivedMessages: () => `${P}/internal-messages/received`,
  receivedMessage: (id: string) => `${P}/internal-messages/received/${id}`,
  markMessageRead: (id: string) => `${P}/internal-messages/${id}/read`,

  accountRequests: () => `${P}/account-requests`,
  accountRequest: (id: string) => `${P}/account-requests/${id}`,
  accountRequestComments: (id: string) => `${P}/account-requests/${id}/comments`,
  accountRequestStatus: (id: string) => `${P}/account-requests/${id}/status`,

  adminDashboard: () => `${P}/admin/dashboard`,
  adminAgents: () => `${P}/admin/agents`,
} as const

/* -------------------------------------------------------------------------- */
/* Convenience call signatures (documentation of the real backend contract)   */
/* -------------------------------------------------------------------------- */

export interface HelpDeskApi {
  getMe: () => Promise<User>
  updateMe: (input: ProfileUpdateInput) => Promise<User>
  /** Refresh the cached profile image from Clerk after an upload. */
  syncMyAvatar: () => Promise<User>

  listTickets: (params?: TicketListParams) => Promise<Ticket[]>
  getTicket: (id: string) => Promise<Ticket>
  createTicket: (input: TicketCreateInput) => Promise<Ticket>
  updateTicket: (id: string, input: TicketUpdateInput) => Promise<Ticket>
  getTicketContact: (id: string) => Promise<TicketContact>
  listAssignedTickets: (params?: TicketListParams) => Promise<Ticket[]>
  claimTicket: (id: string) => Promise<Ticket>
  assignTicket: (id: string, assigneeUserId: string | null) => Promise<Ticket>

  listComments: (ticketId: string) => Promise<Array<Comment | StaffComment>>
  createComment: (ticketId: string, input: CommentCreateInput) => Promise<Comment | StaffComment>
  listHistory: (ticketId: string) => Promise<TicketHistoryEntry[]>

  listAttachments: (ticketId: string) => Promise<Attachment[]>
  uploadAttachment: (ticketId: string, file: File) => Promise<Attachment>

  listNotifications: (params?: NotificationListParams) => Promise<Notification[]>
  unreadNotificationCount: () => Promise<NotificationUnreadCount>
  updateNotification: (id: string, isRead: boolean) => Promise<Notification>
  markAllNotificationsRead: () => Promise<{ updated: number }>

  getTicketFeedback: (ticketId: string) => Promise<TicketFeedbackState>
  submitTicketFeedback: (ticketId: string, input: TicketFeedbackInput) => Promise<TicketFeedback>

  listStaffConversations: (params?: StaffConversationListParams) => Promise<StaffConversation[]>
  startStaffConversation: (subject?: string) => Promise<StaffConversation>
  getStaffConversation: (id: string) => Promise<StaffConversationDetail>
  sendStaffMessage: (conversationId: string, body: string) => Promise<StaffMessage>
  markStaffConversationRead: (conversationId: string) => Promise<MarkReadResult>

  /** Owner Inbox: search eligible recipients (active agents/admins). */
  listMessageRecipients: (params?: RecipientSearchParams) => Promise<User[]>
  /** Owner Inbox: compose an internal message to an audience. */
  composeInternalMessage: (input: InternalMessageCreateInput) => Promise<InternalMessageSummary>
  listSentMessages: (params?: InternalMessageListParams) => Promise<InternalMessageSummary[]>
  getSentMessage: (
    id: string,
    params?: { limit?: number; offset?: number },
  ) => Promise<InternalMessageDetail>
  /** Messages addressed to the signed-in employee (their own rows only). */
  listReceivedMessages: (
    params?: ReceivedMessageListParams,
  ) => Promise<InternalMessageReceived[]>
  markInternalMessageRead: (id: string) => Promise<{ updated: number }>

  listAccountRequests: (params?: AccountRequestListParams) => Promise<AccountRequest[]>
  getAccountRequest: (id: string) => Promise<AccountRequestDetail>
  createAccountRequest: (input: AccountRequestCreateInput) => Promise<AccountRequest>
  addAccountRequestComment: (
    id: string,
    input: AccountRequestCommentInput,
  ) => Promise<AccountRequestComment>
  updateAccountRequestStatus: (
    id: string,
    input: AccountRequestStatusInput,
  ) => Promise<AccountRequest>

  getAdminDashboard: () => Promise<AdminDashboard>
  listAgents: () => Promise<User[]>
  listUsers: (params?: UserListParams) => Promise<User[]>
  getUser: (id: string) => Promise<User>
  updateUser: (id: string, input: AdminUserUpdateInput) => Promise<User>
  updateUserRole: (id: string, role: Role) => Promise<User>
  updateUserStatus: (id: string, isActive: boolean) => Promise<User>
}

/** Maps a ticket status select value to the backend enum. */
export type { TicketStatus }
