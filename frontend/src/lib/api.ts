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
  SupportAnalytics,
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

/**
 * Default per-request timeout.
 *
 * A hung connection (dead tunnel, sleeping backend that never wakes) would
 * otherwise leave a mutation pending forever and the UI stuck on a spinner.
 * Uploads are exempt because a legitimate multi-megabyte transfer can take
 * longer than a simple JSON call; callers can override either value.
 */
export const DEFAULT_REQUEST_TIMEOUT_MS = 20_000
export const DEFAULT_UPLOAD_TIMEOUT_MS = 120_000

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
  /**
   * Extra request headers. Used for protocol headers such as
   * `Idempotency-Key`; authorization and content type are always set here.
   */
  headers?: Record<string, string>
  /**
   * Per-request timeout in milliseconds. `0` disables the timeout. Defaults to
   * `DEFAULT_UPLOAD_TIMEOUT_MS` for multipart uploads and
   * `DEFAULT_REQUEST_TIMEOUT_MS` otherwise.
   */
  timeoutMs?: number
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
    const { method = 'GET', body, query, signal, formData, timeoutMs } = options

    const token = await getToken()
    if (!token) {
      throw new ApiError(401, defaultMessageForStatus(401))
    }

    const headers = new Headers(options.headers)
    headers.set('Accept', 'application/json')
    headers.set('Authorization', `Bearer ${token}`)

    let payload: BodyInit | undefined
    if (formData) {
      payload = formData
    } else if (body !== undefined) {
      headers.set('Content-Type', 'application/json')
      payload = JSON.stringify(body)
    }

    const effectiveTimeout =
      timeoutMs ?? (formData ? DEFAULT_UPLOAD_TIMEOUT_MS : DEFAULT_REQUEST_TIMEOUT_MS)

    // Combine the caller's signal (e.g. React Query cancellation) with our
    // timeout so either one can abort the fetch, while still rejecting with a
    // plain AbortError the caller can recognize.
    const controller = new AbortController()
    let timedOut = false
    const onExternalAbort = () => controller.abort()

    if (signal) {
      if (signal.aborted) controller.abort()
      else signal.addEventListener('abort', onExternalAbort, { once: true })
    }

    const timer =
      effectiveTimeout > 0
        ? setTimeout(() => {
            timedOut = true
            controller.abort()
          }, effectiveTimeout)
        : undefined

    // The timer and the caller's cancellation must stay active until the
    // response *body* has been consumed. `fetch()` resolves as soon as headers
    // arrive, so clearing them there would let a stalled body hang the request
    // (and any `await response.json()`) forever.
    let response: Response
    let parsed: unknown
    try {
      response = await fetch(url(`${path}${buildQuery(query)}`), {
        method,
        headers,
        body: payload,
        signal: controller.signal,
        credentials: 'omit',
      })

      if (response.status === 204) {
        return undefined as T
      }

      const contentType = response.headers.get('content-type') ?? ''
      const isJson = contentType.includes('application/json')
      // A malformed body still resolves to null (the caller reports the HTTP
      // status); a timeout or cancellation during the read must propagate.
      const swallowParseError = (error: unknown) => {
        if (
          timedOut ||
          (error instanceof DOMException && error.name === 'AbortError')
        ) {
          throw error
        }
        return null
      }
      parsed = isJson
        ? await response.json().catch(swallowParseError)
        : await response.text().catch(swallowParseError)
    } catch (error) {
      if (timedOut) {
        throw new ApiError(
          0,
          'The HelpDesk server took too long to respond. Please try again.',
        )
      }
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw error
      }
      throw new ApiError(0, 'Could not reach the HelpDesk server. Check your connection.')
    } finally {
      if (timer !== undefined) clearTimeout(timer)
      if (signal) signal.removeEventListener('abort', onExternalAbort)
    }

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

  staffDirectory: () => `${P}/staff-messages/directory`,
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
  adminAnalytics: () => `${P}/admin/analytics`,
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
  getSupportAnalytics: () => Promise<SupportAnalytics>
  listAgents: () => Promise<User[]>
  listUsers: (params?: UserListParams) => Promise<User[]>
  getUser: (id: string) => Promise<User>
  updateUser: (id: string, input: AdminUserUpdateInput) => Promise<User>
  updateUserRole: (id: string, role: Role) => Promise<User>
  updateUserStatus: (id: string, isActive: boolean) => Promise<User>
}

/** Maps a ticket status select value to the backend enum. */
export type { TicketStatus }
