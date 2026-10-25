/**
 * TypeScript mirrors of the backend's public Pydantic/SQLModel schemas.
 *
 * These were transcribed from `backend/app/schemas/*` and
 * `backend/app/enums/enums.py`. Keep them in sync with the API rather than
 * inventing fields the backend does not return.
 */

export type Role = 'customer' | 'agent' | 'admin' | 'owner'

/**
 * Roles the Owner may assign from the user-management UI. Deliberately excludes
 * `owner`: ownership is established only by the one-time backend bootstrap
 * command, never through an ordinary role change. Mirrors the backend's
 * `AssignableRole` enum.
 */
export const ASSIGNABLE_ROLES: readonly Role[] = ['customer', 'agent', 'admin'] as const

/** Every application role, including `owner`, for display and filtering only. */
export const ALL_ROLES: readonly Role[] = ['owner', 'admin', 'agent', 'customer'] as const

export type TicketStatus = 'OPEN' | 'IN_PROGRESS' | 'WAITING_ON_CUSTOMER' | 'RESOLVED' | 'CLOSED'

export const TICKET_STATUSES: readonly TicketStatus[] = [
  'OPEN',
  'IN_PROGRESS',
  'WAITING_ON_CUSTOMER',
  'RESOLVED',
  'CLOSED',
] as const

export type TicketPriority = 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT'

export const TICKET_PRIORITIES: readonly TicketPriority[] = [
  'LOW',
  'NORMAL',
  'HIGH',
  'URGENT',
] as const

/** Customer-facing issue categories. Required on ticket intake. */
export type TicketCategory =
  | 'BILLING'
  | 'ACCOUNT_ACCESS'
  | 'TECHNICAL'
  | 'OUTAGE'
  | 'BUG'
  | 'ACCOUNT_MANAGEMENT'
  | 'OTHER'

export const TICKET_CATEGORIES: readonly TicketCategory[] = [
  'BILLING',
  'ACCOUNT_ACCESS',
  'TECHNICAL',
  'OUTAGE',
  'BUG',
  'ACCOUNT_MANAGEMENT',
  'OTHER',
] as const

/**
 * The customer's stated real-world impact. This is *input* to the backend's
 * priority policy (`PRIORITY_BY_IMPACT`), not the priority itself.
 */
export type ImpactLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export const IMPACT_LEVELS: readonly ImpactLevel[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] as const

/** Lifecycle of an account-management (admin escalation) request. */
export type EscalationStatus = 'PENDING' | 'IN_REVIEW' | 'APPROVED' | 'REJECTED' | 'COMPLETED'

export const ESCALATION_STATUSES: readonly EscalationStatus[] = [
  'PENDING',
  'IN_REVIEW',
  'APPROVED',
  'REJECTED',
  'COMPLETED',
] as const

/** The kind of privileged account action a request asks for. */
export type EscalationCategory =
  | 'ACCOUNT_RECOVERY'
  | 'IDENTITY_LINKING'
  | 'PROFILE_CORRECTION'
  | 'ROLE_OR_STATUS_CHANGE'
  | 'OTHER'

export const ESCALATION_CATEGORIES: readonly EscalationCategory[] = [
  'ACCOUNT_RECOVERY',
  'IDENTITY_LINKING',
  'PROFILE_CORRECTION',
  'ROLE_OR_STATUS_CHANGE',
  'OTHER',
] as const

export type NotificationType =
  | 'TICKET_ASSIGNED'
  | 'NEW_COMMENT'
  | 'STATUS_CHANGED'
  | 'PRIORITY_CHANGED'
  | 'TICKET_NEEDS_ASSIGNMENT'
  | 'STAFF_MESSAGE_RECEIVED'
  | 'OWNER_MESSAGE_RECEIVED'
  | 'ESCALATION_CREATED'
  | 'ESCALATION_UPDATED'
  | 'TICKET_CREATED'
  | 'TICKET_RESOLVED'
  | 'INTERNAL_MESSAGE_RECEIVED'

export interface User {
  id: string
  full_name: string
  username: string
  email: string
  role: Role
  is_active: boolean
  /** Clerk-hosted profile image URL (cached server-side), or null. */
  image_url: string | null
  created_at: string
  updated_at: string
}

export interface Ticket {
  id: string
  ticket_number: number
  title: string
  description: string
  status: TicketStatus
  priority: TicketPriority
  category: TicketCategory
  created_by_user_id: string
  assignee_user_id: string | null
  created_at: string
  updated_at: string
  assigned_at: string | null
  resolved_at: string | null
}

export interface Comment {
  id: string
  ticket_id: string
  author_user_id: string
  body: string
  created_at: string
  updated_at: string | null
}

export interface StaffComment extends Comment {
  is_internal: boolean
}

export interface Attachment {
  id: string
  ticket_id: string
  uploaded_by_user_id: string
  original_filename: string
  content_type: string
  size_bytes: number
  scan_status: 'PENDING' | 'CLEAN' | 'INFECTED'
  created_at: string
}

export interface TicketHistoryEntry {
  id: string
  ticket_id: string
  actor_user_id: string
  event_type: string
  old_value: Record<string, unknown> | null
  new_value: Record<string, unknown> | null
  created_at: string
}

export interface Notification {
  id: string
  recipient_user_id: string
  related_ticket_id: string | null
  related_conversation_id: string | null
  /** Set on Owner-composed internal message notifications (employee deep link). */
  related_internal_message_id: string | null
  /** Set on account-management (escalation) notifications. */
  related_account_request_id: string | null
  type: NotificationType
  title: string
  message: string
  is_read: boolean
  created_at: string
}

/** The optional phone number of a ticket, staff-only endpoint. */
export interface TicketContact {
  ticket_id: string
  contact_phone: string | null
}

/* -------------------------------------------------------------------------- */
/* Private staff <-> Owner messaging                                          */
/* -------------------------------------------------------------------------- */

export interface StaffConversation {
  id: string
  subject: string
  staff_user_id: string
  staff_full_name: string
  /** The staff participant's role, so the Owner inbox can show and filter it. */
  staff_role: Role | null
  staff_image_url: string | null
  owner_user_id: string
  owner_image_url: string | null
  created_at: string
  last_message_at: string | null
  message_count: number
  /** Messages addressed to the requesting user that are still unread. */
  unread_count: number
  last_message_preview: string | null
  last_message_sender_user_id: string | null
  /** The most recent message *received* by the viewer (never their own). */
  last_received_preview: string | null
  last_received_at: string | null
}

/**
 * Filters the Owner may apply to the conversation inbox. The sender-scoped
 * filters are only honoured for the Owner; an agent is always scoped to their
 * own single thread by the backend.
 */
export interface StaffConversationListParams {
  staff_role?: Role
  staff_user_id?: string
  unread_only?: boolean
}

export interface StaffMessage {
  id: string
  conversation_id: string
  sender_user_id: string
  body: string
  created_at: string
  read_at: string | null
}

export interface StaffConversationDetail {
  conversation: StaffConversation
  messages: StaffMessage[]
}

export interface MarkReadResult {
  updated: number
}

/* -------------------------------------------------------------------------- */
/* Owner-composed internal messages (Owner Inbox compose + sent)              */
/* -------------------------------------------------------------------------- */

/** Who an Owner-composed internal message is addressed to. */
export type InternalAudience = 'everyone' | 'agents' | 'admins' | 'individual'

export const INTERNAL_AUDIENCES: readonly InternalAudience[] = [
  'everyone',
  'agents',
  'admins',
  'individual',
] as const

export interface InternalMessageCreateInput {
  audience: InternalAudience
  subject: string
  body: string
  /** Required for (and only valid with) the `individual` audience. */
  recipient_user_id?: string | null
}

export interface InternalMessageRecipient {
  id: string
  recipient_user_id: string
  recipient_role_snapshot: Role
  recipient_full_name_snapshot: string
  recipient_email_snapshot: string
  read_at: string | null
}

export interface InternalMessageSummary {
  id: string
  sender_user_id: string
  audience: InternalAudience
  subject: string
  preview: string
  recipient_count: number
  /** How many recipients have actually opened it (never an invented state). */
  read_count: number
  created_at: string
}

export interface InternalMessageDetail {
  id: string
  sender_user_id: string
  audience: InternalAudience
  subject: string
  body: string
  recipient_count: number
  read_count: number
  created_at: string
  recipient_total: number
  recipients: InternalMessageRecipient[]
}

/** A message addressed to the requesting employee (their own row only). */
export interface InternalMessageReceived {
  id: string
  sender_user_id: string
  sender_full_name: string
  audience: InternalAudience
  subject: string
  body: string
  created_at: string
  read_at: string | null
}

export type InternalMessageListParams = {
  audience?: InternalAudience
  q?: string
  limit?: number
  offset?: number
}

export type RecipientSearchParams = {
  q?: string
  role?: Role
  limit?: number
  offset?: number
}

export type ReceivedMessageListParams = {
  is_read?: boolean
  limit?: number
  offset?: number
}

/* -------------------------------------------------------------------------- */
/* Account-management (admin escalation) requests                             */
/* -------------------------------------------------------------------------- */

export interface AccountRequest {
  id: string
  target_user_id: string
  target_full_name_snapshot: string
  target_email_snapshot: string
  ticket_id: string | null
  category: EscalationCategory
  justification: string
  internal_details: string | null
  status: EscalationStatus
  decision_reason: string | null
  decided_by_user_id: string | null
  decided_at: string | null
  completed_by_user_id: string | null
  completed_at: string | null
  created_by_user_id: string
  created_at: string
  updated_at: string
}

export interface AccountRequestComment {
  id: string
  request_id: string
  author_user_id: string
  body: string
  created_at: string
}

export interface AccountRequestEvent {
  id: string
  request_id: string
  actor_user_id: string
  event_type: string
  old_value: Record<string, unknown> | null
  new_value: Record<string, unknown> | null
  created_at: string
}

export interface AccountRequestDetail {
  request: AccountRequest
  comments: AccountRequestComment[]
  events: AccountRequestEvent[]
}

export interface AdminDashboard {
  total_tickets: number
  tickets_by_status: Record<TicketStatus, number>
  tickets_by_priority: Record<TicketPriority, number>
  total_users: number
  active_agents: number
}

/* -------------------------------------------------------------------------- */
/* Request payloads                                                           */
/* -------------------------------------------------------------------------- */

export interface TicketCreateInput {
  title: string
  description: string
  category: TicketCategory
  /**
   * The only urgency input a customer provides. The backend maps it to the
   * ticket priority through the support policy.
   */
  impact?: ImpactLevel
  /** Optional contact number. Never returned by public ticket responses. */
  contact_phone?: string
}

export interface TicketUpdateInput {
  title?: string
  description?: string
  status?: TicketStatus
  priority?: TicketPriority
  category?: TicketCategory
  contact_phone?: string
}

export interface AccountRequestCreateInput {
  category: EscalationCategory
  justification: string
  internal_details?: string
  /** Required for agents: the ticket this escalation is about. */
  ticket_id?: string
  /** Admins only: a target account when the request is not ticket-bound. */
  target_user_id?: string
}

export interface AccountRequestStatusInput {
  status: EscalationStatus
  reason?: string
}

export interface AccountRequestCommentInput {
  body: string
}

export interface CommentCreateInput {
  body: string
  is_internal?: boolean
}

export interface ProfileUpdateInput {
  full_name?: string
  username?: string
}

export interface AdminUserUpdateInput {
  full_name?: string
  username?: string
  role?: Role
  is_active?: boolean
}

/* -------------------------------------------------------------------------- */
/* Query parameters                                                           */
/* -------------------------------------------------------------------------- */

// These are declared as type aliases (not interfaces) so they remain assignable
// to `Record<string, QueryValue>` when passed as query parameters.
export type TicketListParams = {
  status?: TicketStatus
  priority?: TicketPriority
  assignee_user_id?: string
  created_by_user_id?: string
  q?: string
  limit?: number
  offset?: number
}

export type UserListParams = {
  role?: Role
  is_active?: boolean
  q?: string
  limit?: number
  offset?: number
}

export type NotificationListParams = {
  is_read?: boolean
  /** Server-side grouping of notification types for the panel filters. */
  category?: NotificationCategory
  limit?: number
  offset?: number
}

export type NotificationCategory = 'tickets' | 'messages' | 'account_requests'

/** The current user's unread totals, bucketed for the panel filters. */
export interface NotificationUnreadCount {
  count: number
  tickets: number
  messages: number
  account_requests: number
}

/* -------------------------------------------------------------------------- */
/* Customer feedback on a resolved ticket                                     */
/* -------------------------------------------------------------------------- */

export interface TicketFeedback {
  id: string
  ticket_id: string
  customer_user_id: string
  rating: number
  comment: string | null
  created_at: string
}

export interface TicketFeedbackInput {
  rating: number
  comment?: string | null
}

/** What the current viewer may see and do for a ticket's feedback. */
export interface TicketFeedbackState {
  feedback: TicketFeedback | null
  /** True only when the backend would accept a submission right now. */
  can_submit: boolean
  /** True when the ticket is resolved and the customer has not answered yet. */
  awaiting_feedback: boolean
}

export type AccountRequestListParams = {
  status?: EscalationStatus
  category?: EscalationCategory
  mine?: boolean
  limit?: number
  offset?: number
}
