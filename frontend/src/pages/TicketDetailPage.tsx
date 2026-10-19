import {
  Box,
  Button,
  Dialog,
  Flex,
  NativeSelect,
  Portal,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Tooltip,
} from '@chakra-ui/react'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  Download,
  FileText,
  Hand,
  Inbox,
  Mail,
  Paperclip,
  Pencil,
  ShieldQuestion,
  Upload,
} from 'lucide-react'
import { useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '@clerk/react'

import { CommentThread } from '../components/CommentThread.tsx'
import { Composer } from '../components/Composer.tsx'
import {
  FormField,
  FormStack,
  SelectInput,
  TextAreaInput,
  TextInput,
} from '../components/FormField.tsx'
import { PageHeader } from '../components/PageHeader.tsx'
import { CategoryBadge, PriorityBadge, StatusBadge } from '../components/badges.tsx'
import { EmptyState, ErrorState, LoadingState } from '../components/StateViews.tsx'
import { Surface } from '../components/Surface.tsx'
import { toaster } from '../components/Toaster.tsx'
import { ApiError, endpoints } from '../lib/api.ts'
import { useApi } from '../lib/useApi.ts'
import { useAgents } from '../hooks/useAdmin.ts'
import { useCreateAccountRequest } from '../hooks/useAccountRequests.ts'
import { useMe } from '../hooks/useMe.ts'
import {
  useAssignTicket,
  useAttachments,
  useClaimTicket,
  useComments,
  useCreateComment,
  useTicket,
  useTicketContact,
  useTicketHistory,
  useUpdateTicket,
  useUploadAttachment,
} from '../hooks/useTickets.ts'
import { useUserDirectory } from '../hooks/useUserDirectory.ts'
import { errorFieldMap, errorMessage } from '../lib/errors.ts'
import {
  escalationCategoryLabels,
  formatBytes,
  formatDateTime,
  formatRelative,
  priorityLabels,
  statusLabels,
  ticketRef,
} from '../lib/format.ts'
import { isAdmin, isStaff } from '../lib/roles.ts'
import {
  ESCALATION_CATEGORIES,
  TICKET_PRIORITIES,
  type Attachment,
  type EscalationCategory,
  type Ticket,
  type TicketPriority,
  type TicketStatus,
} from '../lib/types.ts'
import { palette } from '../theme/palette.ts'

const ALLOWED_TRANSITIONS: Record<TicketStatus, TicketStatus[]> = {
  OPEN: ['IN_PROGRESS', 'CLOSED'],
  IN_PROGRESS: ['WAITING_ON_CUSTOMER', 'RESOLVED', 'CLOSED'],
  WAITING_ON_CUSTOMER: ['IN_PROGRESS', 'RESOLVED', 'CLOSED'],
  RESOLVED: ['IN_PROGRESS', 'CLOSED'],
  CLOSED: [],
}

const CUSTOMER_EDITABLE: TicketStatus[] = ['OPEN', 'IN_PROGRESS', 'WAITING_ON_CUSTOMER']

const ACCEPTED_TYPES =
  'image/png,image/jpeg,image/gif,image/webp,application/pdf,text/plain,text/csv,application/zip,.doc,.docx,.xlsx'

export function TicketDetailPage() {
  const params = useParams<{ ticketId: string }>()
  const ticketId = params.ticketId ?? ''

  const me = useMe()
  const ticket = useTicket(ticketId)
  const role = me.data?.role
  const staff = isStaff(role)
  const admin = isAdmin(role)
  const navigate = useNavigate()

  const comments = useComments(ticketId)
  const history = useTicketHistory(ticketId, staff)
  const attachments = useAttachments(ticketId)
  const contact = useTicketContact(ticketId, staff)
  const createComment = useCreateComment(ticketId)
  const updateTicket = useUpdateTicket(ticketId)
  const claimTicket = useClaimTicket()
  const assignTicket = useAssignTicket(ticketId)
  const agents = useAgents(admin)
  const directory = useUserDirectory()

  const [editing, setEditing] = useState(false)
  const [escalateOpen, setEscalateOpen] = useState(false)

  if (ticket.isPending) return <LoadingState label='Loading ticket…' />

  if (ticket.isError) {
    const error = ticket.error
    if (error instanceof ApiError && error.isNotFound) {
      return (
        <EmptyState
          icon={Inbox}
          title='Ticket not found'
          description='It may have been removed, or you may not have access to it.'
          action={
            <Button asChild size='sm' variant='outline' borderColor={palette.border}>
              <Link to='/tickets'>Back to tickets</Link>
            </Button>
          }
        />
      )
    }
    return (
      <ErrorState
        title='Could not load this ticket'
        description={errorMessage(error)}
        onRetry={() => void ticket.refetch()}
      />
    )
  }

  const data = ticket.data
  if (!data) return <LoadingState />

  const isOwner = me.data?.id === data.created_by_user_id
  const canEditText = isOwner && !staff && CUSTOMER_EDITABLE.includes(data.status)

  const submitComment = async (input: { body: string; is_internal: boolean }) => {
    try {
      await createComment.mutateAsync(input)
    } catch (error) {
      toaster.create({
        title: 'Could not post reply',
        description: errorMessage(error),
        type: 'error',
      })
      throw error
    }
  }

  const changeStatus = (status: TicketStatus) => {
    if (status === data.status) return
    updateTicket.mutate(
      { status },
      {
        onSuccess: () => toaster.create({ title: `Status set to ${statusLabels[status]}` }),
        onError: (error) =>
          toaster.create({
            title: 'Could not update status',
            description: errorMessage(error),
            type: 'error',
          }),
      },
    )
  }

  const changePriority = (priority: TicketPriority) => {
    if (priority === data.priority) return
    updateTicket.mutate(
      { priority },
      {
        onSuccess: () => toaster.create({ title: `Priority set to ${priorityLabels[priority]}` }),
        onError: (error) =>
          toaster.create({
            title: 'Could not update priority',
            description: errorMessage(error),
            type: 'error',
          }),
      },
    )
  }

  const claim = () => {
    claimTicket.mutate(data.id, {
      onSuccess: () => toaster.create({ title: 'Ticket claimed' }),
      onError: (error) =>
        toaster.create({
          title: 'Could not claim ticket',
          description: errorMessage(error),
          type: 'error',
        }),
    })
  }

  const assign = (assigneeId: string) => {
    assignTicket.mutate(assigneeId || null, {
      onSuccess: () => toaster.create({ title: 'Assignment updated' }),
      onError: (error) =>
        toaster.create({
          title: 'Could not update assignment',
          description: errorMessage(error),
          type: 'error',
        }),
    })
  }

  return (
    <>
      <PageHeader
        breadcrumb={
          <Link to='/tickets' style={{ textDecoration: 'none' }}>
            <Text fontSize='sm' color={palette.textMuted}>
              Tickets / {ticketRef(data.ticket_number)}
            </Text>
          </Link>
        }
        title={
          <Flex direction='column' gap='2'>
            <Text
              as='span'
              fontSize='sm'
              color={palette.textMuted}
              fontVariantNumeric='tabular-nums'
            >
              {ticketRef(data.ticket_number)}
            </Text>
            <Text as='span'>{data.title}</Text>
          </Flex>
        }
        actions={
          canEditText ? (
            <Button
              size='sm'
              variant='outline'
              borderColor={palette.border}
              onClick={() => setEditing(true)}
            >
              <Pencil size={14} aria-hidden />
              Edit ticket
            </Button>
          ) : null
        }
      />

      <SimpleGrid columns={{ base: 1, lg: 3 }} gap='6' alignItems='start'>
        <Stack gap='6' gridColumn={{ lg: 'span 2' }}>
          <Surface p={{ base: '5', md: '6' }}>
            <Stack gap='5'>
              <Flex gap='2' wrap='wrap'>
                <StatusBadge status={data.status} />
                <PriorityBadge priority={data.priority} />
                <CategoryBadge category={data.category} />
              </Flex>
              <Text fontSize='sm' color={palette.text} whiteSpace='pre-wrap' lineHeight='1.7'>
                {data.description}
              </Text>
            </Stack>
          </Surface>

          <Surface p={{ base: '5', md: '6' }}>
            <Stack gap='4'>
              <Flex align='baseline' justify='space-between' gap='4'>
                <Text fontSize='md' fontWeight='medium' color={palette.text}>
                  Conversation
                </Text>
                <Text fontSize='xs' color={palette.textMuted}>
                  {comments.data?.length ?? 0}{' '}
                  {(comments.data?.length ?? 0) === 1 ? 'message' : 'messages'}
                </Text>
              </Flex>

              {comments.isPending ? (
                <LoadingState label='Loading conversation…' minHeight='20vh' />
              ) : comments.isError ? (
                <ErrorState
                  title='Could not load the conversation'
                  description={errorMessage(comments.error)}
                  onRetry={() => void comments.refetch()}
                />
              ) : (comments.data?.length ?? 0) === 0 ? (
                <EmptyState
                  compact
                  title='No messages yet'
                  description={
                    staff
                      ? 'Start the conversation with the requester.'
                      : 'You will see replies from the support team here.'
                  }
                />
              ) : (
                <CommentThread
                  comments={comments.data ?? []}
                  viewerId={me.data?.id ?? ''}
                  viewerRole={role ?? 'customer'}
                  userLabel={directory.label}
                  userImage={(id) => directory.user(id)?.image_url}
                />
              )}

              <Box borderTopWidth='1px' borderColor={palette.borderSubtle} pt='5'>
                <Composer
                  onSubmit={submitComment}
                  isPending={createComment.isPending}
                  allowInternal={staff}
                  placeholder={staff ? 'Reply to the requester…' : 'Add a comment…'}
                />
              </Box>
            </Stack>
          </Surface>

          <AttachmentsPanel ticketId={ticketId} attachments={attachments} />
        </Stack>

        <Stack gap='4'>
          <Surface p='5'>
            <Stack gap='4'>
              <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                Details
              </Text>
              <Stack gap='3.5'>
                <MetaRow label='Requester'>
                  <Text fontSize='sm' color={palette.textSecondary}>
                    {isOwner ? 'You' : directory.label(data.created_by_user_id)}
                  </Text>
                </MetaRow>
                {staff ? (
                  <MetaRow label='Contact number'>
                    <Text
                      fontSize='sm'
                      color={
                        contact.data?.contact_phone ? palette.textSecondary : palette.textMuted
                      }
                    >
                      {contact.isPending
                        ? 'Loading…'
                        : (contact.data?.contact_phone ?? 'Not provided')}
                    </Text>
                  </MetaRow>
                ) : null}
                <MetaRow label='Assignee'>
                  <Text
                    fontSize='sm'
                    color={data.assignee_user_id ? palette.textSecondary : palette.textMuted}
                  >
                    {data.assignee_user_id ? directory.label(data.assignee_user_id) : 'Unassigned'}
                  </Text>
                </MetaRow>
                <MetaRow label='Created'>
                  <Text fontSize='sm' color={palette.textSecondary}>
                    {formatDateTime(data.created_at)}
                  </Text>
                </MetaRow>
                <MetaRow label='Updated'>
                  <Text fontSize='sm' color={palette.textSecondary}>
                    {formatRelative(data.updated_at)}
                  </Text>
                </MetaRow>
                {data.resolved_at ? (
                  <MetaRow label='Resolved'>
                    <Text fontSize='sm' color={palette.textSecondary}>
                      {formatDateTime(data.resolved_at)}
                    </Text>
                  </MetaRow>
                ) : null}
              </Stack>
            </Stack>
          </Surface>

          {staff ? (
            <Surface p='5'>
              <Stack gap='4'>
                <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                  Manage
                </Text>

                <Stack gap='1.5'>
                  <Text fontSize='xs' color={palette.textMuted}>
                    Status
                  </Text>
                  <NativeSelect.Root size='sm' disabled={updateTicket.isPending}>
                    <NativeSelect.Field
                      value={data.status}
                      onChange={(event) => changeStatus(event.target.value as TicketStatus)}
                      aria-label='Change status'
                      bg={palette.surface}
                      borderColor={palette.border}
                      borderRadius='l2'
                      fontSize='sm'
                    >
                      <option value={data.status}>{statusLabels[data.status]}</option>
                      {ALLOWED_TRANSITIONS[data.status].map((status) => (
                        <option key={status} value={status}>
                          {statusLabels[status]}
                        </option>
                      ))}
                    </NativeSelect.Field>
                    <NativeSelect.Indicator color={palette.textMuted} />
                  </NativeSelect.Root>
                  {ALLOWED_TRANSITIONS[data.status].length === 0 ? (
                    <Text fontSize='2xs' color={palette.textMuted}>
                      This ticket is closed and can no longer change status.
                    </Text>
                  ) : null}
                </Stack>

                <Stack gap='1.5'>
                  <Text fontSize='xs' color={palette.textMuted}>
                    Priority
                  </Text>
                  <NativeSelect.Root size='sm' disabled={updateTicket.isPending}>
                    <NativeSelect.Field
                      value={data.priority}
                      onChange={(event) => changePriority(event.target.value as TicketPriority)}
                      aria-label='Change priority'
                      bg={palette.surface}
                      borderColor={palette.border}
                      borderRadius='l2'
                      fontSize='sm'
                    >
                      {TICKET_PRIORITIES.map((priority) => (
                        <option key={priority} value={priority}>
                          {priorityLabels[priority]}
                        </option>
                      ))}
                    </NativeSelect.Field>
                    <NativeSelect.Indicator color={palette.textMuted} />
                  </NativeSelect.Root>
                </Stack>

                {admin ? (
                  <Stack gap='1.5'>
                    <Text fontSize='xs' color={palette.textMuted}>
                      Assignee
                    </Text>
                    <NativeSelect.Root size='sm' disabled={assignTicket.isPending}>
                      <NativeSelect.Field
                        value={data.assignee_user_id ?? ''}
                        onChange={(event) => assign(event.target.value)}
                        aria-label='Assign ticket'
                        bg={palette.surface}
                        borderColor={palette.border}
                        borderRadius='l2'
                        fontSize='sm'
                      >
                        <option value=''>Unassigned</option>
                        {(agents.data ?? []).map((agent) => (
                          <option key={agent.id} value={agent.id}>
                            {agent.full_name}
                          </option>
                        ))}
                      </NativeSelect.Field>
                      <NativeSelect.Indicator color={palette.textMuted} />
                    </NativeSelect.Root>
                  </Stack>
                ) : null}

                {!admin && !data.assignee_user_id ? (
                  <Button
                    size='sm'
                    bg={palette.ink}
                    color={palette.textOnInk}
                    _hover={{ bg: palette.inkHover }}
                    loading={claimTicket.isPending}
                    onClick={claim}
                  >
                    <Hand size={14} aria-hidden />
                    Claim ticket
                  </Button>
                ) : null}
              </Stack>
            </Surface>
          ) : null}

          {role === 'agent' || role === 'admin' ? (
            <Surface p='5'>
              <Stack gap='4'>
                <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                  Staff channels
                </Text>
                <Text fontSize='xs' color={palette.textMuted}>
                  These channels are private: the customer never sees staff messages or account
                  requests tied to this ticket.
                </Text>
                <Stack gap='2'>
                  <Button asChild size='sm' variant='outline' borderColor={palette.border}>
                    <Link to='/messages'>
                      <Mail size={14} aria-hidden />
                      Message the Owner
                    </Link>
                  </Button>
                  {role === 'agent' ? (
                    <Button
                      size='sm'
                      variant='outline'
                      borderColor={palette.border}
                      onClick={() => setEscalateOpen(true)}
                    >
                      <ShieldQuestion size={14} aria-hidden />
                      Request admin assistance
                    </Button>
                  ) : null}
                </Stack>
              </Stack>
            </Surface>
          ) : null}

          {staff ? (
            <Surface p='5'>
              <Stack gap='4'>
                <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                  Activity
                </Text>
                {history.isPending ? (
                  <LoadingState label='Loading activity…' minHeight='16vh' />
                ) : history.isError ? (
                  <Text fontSize='xs' color={palette.textMuted}>
                    Could not load activity.
                  </Text>
                ) : (history.data?.length ?? 0) === 0 ? (
                  <Text fontSize='xs' color={palette.textMuted}>
                    No activity recorded yet.
                  </Text>
                ) : (
                  <Stack gap='3'>
                    {(history.data ?? []).map((entry) => (
                      <HistoryItem
                        key={entry.id}
                        entry={entry}
                        actorLabel={directory.label(entry.actor_user_id)}
                      />
                    ))}
                  </Stack>
                )}
              </Stack>
            </Surface>
          ) : null}
        </Stack>
      </SimpleGrid>

      {editing ? <EditTicketDialog open={editing} onOpenChange={setEditing} ticket={data} /> : null}
      {escalateOpen ? (
        <RequestAdminAssistanceDialog
          open={escalateOpen}
          onOpenChange={setEscalateOpen}
          ticket={data}
          onCreated={(id) => void navigate(`/account-requests/${id}`)}
        />
      ) : null}
    </>
  )
}

/* -------------------------------------------------------------------------- */
/* Manage controls helpers                                                    */
/* -------------------------------------------------------------------------- */

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Flex align='center' justify='space-between' gap='4'>
      <Text fontSize='sm' color={palette.textMuted} flexShrink={0}>
        {label}
      </Text>
      <Text as='span' textAlign='right' minW='0'>
        {children}
      </Text>
    </Flex>
  )
}

const HISTORY_LABEL: Record<string, string> = {
  TICKET_CREATED: 'Ticket created',
  TICKET_ASSIGNED: 'Assignee changed',
  STATUS_CHANGED: 'Status changed',
  PRIORITY_CHANGED: 'Priority changed',
  TICKET_UPDATED: 'Ticket details edited',
  COMMENT_ADDED: 'Comment added',
}

function historySummary(entry: {
  event_type: string
  old_value: Record<string, unknown> | null
  new_value: Record<string, unknown> | null
}): string | null {
  const oldValue = entry.old_value ?? {}
  const newValue = entry.new_value ?? {}
  const first = (record: Record<string, unknown>) => Object.values(record)[0]

  if (entry.event_type === 'STATUS_CHANGED') {
    return `${String(first(oldValue))} → ${String(first(newValue))}`
  }
  if (entry.event_type === 'PRIORITY_CHANGED') {
    return `${String(first(oldValue))} → ${String(first(newValue))}`
  }
  return null
}

function HistoryItem({
  entry,
  actorLabel,
}: {
  entry: {
    id: string
    event_type: string
    old_value: Record<string, unknown> | null
    new_value: Record<string, unknown> | null
    created_at: string
  }
  actorLabel: string
}) {
  const label = HISTORY_LABEL[entry.event_type] ?? entry.event_type
  const summary = historySummary(entry)
  return (
    <Flex gap='3' align='flex-start'>
      <Box boxSize='1.5' borderRadius='full' bg={palette.ink} mt='1.5' flexShrink={0} />
      <Stack gap='0.5' minW='0'>
        <Text fontSize='xs' color={palette.text}>
          {label}
        </Text>
        {summary ? (
          <Text fontSize='2xs' color={palette.textMuted} fontVariantNumeric='tabular-nums'>
            {summary}
          </Text>
        ) : null}
        <Text fontSize='2xs' color={palette.textFaint}>
          {actorLabel} · {formatRelative(entry.created_at)}
        </Text>
      </Stack>
    </Flex>
  )
}

/* -------------------------------------------------------------------------- */
/* Attachments                                                                */
/* -------------------------------------------------------------------------- */

function AttachmentsPanel({
  ticketId,
  attachments,
}: {
  ticketId: string
  attachments: ReturnType<typeof useAttachments>
}) {
  const api = useApi()
  const { getToken } = useAuth()
  const upload = useUploadAttachment(ticketId)
  const inputRef = useRef<HTMLInputElement>(null)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)

  const items = attachments.data ?? []

  const handleFiles = (files: FileList | null) => {
    const file = files?.[0]
    if (!file) return
    upload.mutate(file, {
      onSuccess: () => toaster.create({ title: 'Attachment uploaded' }),
      onError: (error) =>
        toaster.create({ title: 'Upload failed', description: errorMessage(error), type: 'error' }),
      onSettled: () => {
        if (inputRef.current) inputRef.current.value = ''
      },
    })
  }

  const download = async (attachment: Attachment) => {
    setDownloadingId(attachment.id)
    try {
      const token = await getToken()
      const response = await fetch(api.url(endpoints.downloadAttachment(attachment.id)), {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })
      if (!response.ok) throw new Error('Download failed')
      const blob = await response.blob()
      const objectUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = objectUrl
      anchor.download = attachment.original_filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(objectUrl)
    } catch (error) {
      toaster.create({
        title: 'Could not download file',
        description: errorMessage(error),
        type: 'error',
      })
    } finally {
      setDownloadingId(null)
    }
  }

  return (
    <Surface p={{ base: '5', md: '6' }}>
      <Stack gap='4'>
        <Flex align='center' justify='space-between' gap='4'>
          <Flex align='center' gap='2' color={palette.text}>
            <Paperclip size={16} strokeWidth={1.9} aria-hidden />
            <Text fontSize='md' fontWeight='medium'>
              Attachments
            </Text>
          </Flex>
          <Button
            size='xs'
            variant='outline'
            borderColor={palette.border}
            loading={upload.isPending}
            onClick={() => inputRef.current?.click()}
          >
            <Upload size={13} aria-hidden />
            Upload
          </Button>
          <input
            ref={inputRef}
            type='file'
            accept={ACCEPTED_TYPES}
            hidden
            onChange={(event) => handleFiles(event.target.files)}
          />
        </Flex>

        {attachments.isPending ? (
          <Text fontSize='xs' color={palette.textMuted}>
            Loading attachments…
          </Text>
        ) : attachments.isError ? (
          <Text fontSize='xs' color={palette.textMuted}>
            Could not load attachments.
          </Text>
        ) : items.length === 0 ? (
          <Text fontSize='xs' color={palette.textMuted}>
            No files attached. Upload screenshots or documents up to the server size limit.
          </Text>
        ) : (
          <Table.Root size='sm'>
            <Table.Body>
              {items.map((attachment) => (
                <Table.Row key={attachment.id}>
                  <Table.Cell>
                    <Flex align='center' gap='2.5' minW='0'>
                      <FileText size={15} color={palette.textMuted} aria-hidden />
                      <Text fontSize='sm' color={palette.text} truncate>
                        {attachment.original_filename}
                      </Text>
                    </Flex>
                  </Table.Cell>
                  <Table.Cell
                    textAlign='right'
                    fontSize='xs'
                    color={palette.textMuted}
                    whiteSpace='nowrap'
                  >
                    {formatBytes(attachment.size_bytes)}
                  </Table.Cell>
                  <Table.Cell width='1%' textAlign='right'>
                    <Tooltip.Root openDelay={300}>
                      <Tooltip.Trigger asChild>
                        <Button
                          size='xs'
                          variant='ghost'
                          color={palette.textSecondary}
                          loading={downloadingId === attachment.id}
                          onClick={() => void download(attachment)}
                          aria-label={`Download ${attachment.original_filename}`}
                        >
                          <Download size={14} aria-hidden />
                        </Button>
                      </Tooltip.Trigger>
                      <Portal>
                        <Tooltip.Positioner>
                          <Tooltip.Content fontSize='xs'>Download</Tooltip.Content>
                        </Tooltip.Positioner>
                      </Portal>
                    </Tooltip.Root>
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table.Root>
        )}
      </Stack>
    </Surface>
  )
}

/* -------------------------------------------------------------------------- */
/* Customer edit dialog                                                       */
/* -------------------------------------------------------------------------- */

const editSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, 'Title is required')
    .max(180, 'Title must be 180 characters or fewer'),
  description: z
    .string()
    .trim()
    .min(1, 'Description is required')
    .max(10000, 'Description is too long'),
})

type EditValues = z.infer<typeof editSchema>

function EditTicketDialog({
  open,
  onOpenChange,
  ticket,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  ticket: Ticket
}) {
  const update = useUpdateTicket(ticket.id)
  const form = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: { title: ticket.title, description: ticket.description },
  })

  const onSubmit = form.handleSubmit(async (data) => {
    try {
      await update.mutateAsync(data)
      toaster.create({ title: 'Ticket updated' })
      onOpenChange(false)
    } catch (error) {
      const fields = errorFieldMap(error)
      let matched = false
      for (const [field, message] of Object.entries(fields)) {
        if (field in editSchema.shape) {
          form.setError(field as keyof EditValues, { message })
          matched = true
        }
      }
      toaster.create({
        title: matched ? 'Please review the highlighted fields' : 'Could not update ticket',
        description: matched ? undefined : errorMessage(error),
        type: 'error',
      })
    }
  })

  return (
    <Dialog.Root open={open} onOpenChange={(details) => onOpenChange(details.open)}>
      <Portal>
        <Dialog.Backdrop bg='rgba(17,17,17,0.32)' />
        <Dialog.Positioner>
          <Dialog.Content
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l3'
            maxW='xl'
            boxShadow='0 24px 60px -24px rgba(0,0,0,0.28)'
          >
            <form onSubmit={onSubmit} noValidate>
              <Dialog.Header px='6' pt='6' pb='2'>
                <Dialog.Title fontSize='md' fontWeight='medium' color={palette.text}>
                  Edit ticket
                </Dialog.Title>
              </Dialog.Header>
              <Dialog.Body px='6' py='4'>
                <FormStack>
                  <FormField
                    label='Title'
                    htmlFor='edit-title'
                    required
                    error={form.formState.errors.title?.message}
                  >
                    <TextInput id='edit-title' maxLength={180} {...form.register('title')} />
                  </FormField>
                  <FormField
                    label='Description'
                    htmlFor='edit-description'
                    required
                    error={form.formState.errors.description?.message}
                  >
                    <TextAreaInput
                      id='edit-description'
                      minH='40'
                      {...form.register('description')}
                    />
                  </FormField>
                </FormStack>
              </Dialog.Body>
              <Dialog.Footer px='6' pb='6' pt='2' gap='2'>
                <Button
                  size='sm'
                  variant='ghost'
                  color={palette.textSecondary}
                  onClick={() => onOpenChange(false)}
                  disabled={update.isPending}
                >
                  Cancel
                </Button>
                <Button
                  type='submit'
                  size='sm'
                  bg={palette.ink}
                  color={palette.textOnInk}
                  _hover={{ bg: palette.inkHover }}
                  loading={update.isPending}
                  disabled={!form.formState.isDirty}
                >
                  Save changes
                </Button>
              </Dialog.Footer>
            </form>
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
  )
}

/* -------------------------------------------------------------------------- */
/* Request admin assistance dialog                                            */
/* -------------------------------------------------------------------------- */

const escalationSchema = z.object({
  category: z.enum([...ESCALATION_CATEGORIES] as [string, ...string[]], {
    message: 'Choose what kind of account action is needed',
  }),
  justification: z
    .string()
    .trim()
    .min(1, 'Explain why this account action is needed')
    .max(4000, 'Keep the justification under 4000 characters'),
  internal_details: z.string().trim().max(4000, 'Keep internal details under 4000 characters'),
})

type EscalationValues = z.infer<typeof escalationSchema>

/**
 * A structured account-management request, always tied to this ticket.
 *
 * The backend takes the target account from the ticket's requester record, so
 * there is no way to type an arbitrary user id here, and an administrator (not
 * the requester) reviews and decides the request. Approval only authorizes the
 * action; the identity change itself happens through the supported process.
 */
function RequestAdminAssistanceDialog({
  open,
  onOpenChange,
  ticket,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  ticket: Ticket
  onCreated: (id: string) => void
}) {
  const create = useCreateAccountRequest()
  const form = useForm<EscalationValues>({
    resolver: zodResolver(escalationSchema),
    defaultValues: { category: '', justification: '', internal_details: '' },
  })

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const request = await create.mutateAsync({
        category: values.category as EscalationCategory,
        justification: values.justification,
        internal_details: values.internal_details || undefined,
        ticket_id: ticket.id,
      })
      toaster.create({
        title: 'Request submitted',
        description: 'An administrator will review it; you can follow it under Account requests.',
      })
      onOpenChange(false)
      form.reset()
      onCreated(request.id)
    } catch (error) {
      const fields = errorFieldMap(error)
      let matched = false
      for (const [field, message] of Object.entries(fields)) {
        if (field in escalationSchema.shape) {
          form.setError(field as keyof EscalationValues, { message })
          matched = true
        }
      }
      toaster.create({
        title: matched ? 'Please review the highlighted fields' : 'Could not submit the request',
        description: matched ? undefined : errorMessage(error),
        type: 'error',
      })
    }
  })

  return (
    <Dialog.Root open={open} onOpenChange={(details) => onOpenChange(details.open)}>
      <Portal>
        <Dialog.Backdrop bg='rgba(17,17,17,0.32)' />
        <Dialog.Positioner>
          <Dialog.Content
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l3'
            maxW='xl'
            boxShadow='0 24px 60px -24px rgba(0,0,0,0.28)'
          >
            <form onSubmit={onSubmit} noValidate>
              <Dialog.Header px='6' pt='6' pb='2'>
                <Dialog.Title fontSize='md' fontWeight='medium' color={palette.text}>
                  Request admin assistance
                </Dialog.Title>
                <Text fontSize='xs' color={palette.textMuted} pt='2'>
                  For {ticketRef(ticket.ticket_number)}. The request targets the ticket requester;
                  an administrator reviews it and records the decision.
                </Text>
              </Dialog.Header>
              <Dialog.Body px='6' py='4'>
                <FormStack>
                  <FormField
                    label='Category'
                    htmlFor='escalation-category'
                    required
                    error={form.formState.errors.category?.message}
                  >
                    <SelectInput id='escalation-category' {...form.register('category')}>
                      <option value=''>Select a category…</option>
                      {ESCALATION_CATEGORIES.map((category) => (
                        <option key={category} value={category}>
                          {escalationCategoryLabels[category]}
                        </option>
                      ))}
                    </SelectInput>
                  </FormField>

                  <FormField
                    label='Justification'
                    htmlFor='escalation-justification'
                    required
                    error={form.formState.errors.justification?.message}
                    helperText='What happened and why the customer cannot be helped without this action.'
                  >
                    <TextAreaInput
                      id='escalation-justification'
                      minH='28'
                      maxLength={4000}
                      {...form.register('justification')}
                    />
                  </FormField>

                  <FormField
                    label='Internal details (optional)'
                    htmlFor='escalation-details'
                    error={form.formState.errors.internal_details?.message}
                    helperText='Only reviewers can see this. Never include passwords or tokens.'
                  >
                    <TextAreaInput
                      id='escalation-details'
                      minH='20'
                      maxLength={4000}
                      {...form.register('internal_details')}
                    />
                  </FormField>
                </FormStack>
              </Dialog.Body>
              <Dialog.Footer px='6' pb='6' pt='2' gap='2'>
                <Button
                  size='sm'
                  variant='ghost'
                  color={palette.textSecondary}
                  onClick={() => onOpenChange(false)}
                  disabled={create.isPending}
                >
                  Cancel
                </Button>
                <Button
                  type='submit'
                  size='sm'
                  bg={palette.ink}
                  color={palette.textOnInk}
                  _hover={{ bg: palette.inkHover }}
                  loading={create.isPending}
                >
                  Submit request
                </Button>
              </Dialog.Footer>
            </form>
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
  )
}
