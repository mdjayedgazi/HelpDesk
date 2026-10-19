import { Button, Flex, Portal, Dialog, Stack, Text } from '@chakra-ui/react'
import { Ban, CheckCircle2, ClipboardCheck, Search, ShieldQuestion } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { EscalationStatusBadge } from '../../components/badges.tsx'
import { Composer } from '../../components/Composer.tsx'
import { FormField, TextAreaInput } from '../../components/FormField.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { EmptyState, ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { Surface } from '../../components/Surface.tsx'
import { toaster } from '../../components/Toaster.tsx'
import { UserAvatar } from '../../components/UserAvatar.tsx'
import {
  useAccountRequest,
  useAddAccountRequestComment,
  useUpdateAccountRequestStatus,
} from '../../hooks/useAccountRequests.ts'
import { useMe } from '../../hooks/useMe.ts'
import { useUserDirectory } from '../../hooks/useUserDirectory.ts'
import { ApiError } from '../../lib/api.ts'
import { errorMessage } from '../../lib/errors.ts'
import {
  escalationCategoryLabels,
  escalationStatusLabels,
  formatDateTime,
  formatRelative,
} from '../../lib/format.ts'
import { isAdmin } from '../../lib/roles.ts'
import type { AccountRequestEvent, EscalationStatus } from '../../lib/types.ts'
import { palette } from '../../theme/palette.ts'

const ALLOWED_TRANSITIONS: Record<EscalationStatus, EscalationStatus[]> = {
  PENDING: ['IN_REVIEW', 'APPROVED', 'REJECTED'],
  IN_REVIEW: ['APPROVED', 'REJECTED'],
  APPROVED: ['COMPLETED'],
  REJECTED: [],
  COMPLETED: [],
}

const COMMENTABLE: EscalationStatus[] = ['PENDING', 'IN_REVIEW', 'APPROVED']

const TRANSITION_LABELS: Partial<Record<EscalationStatus, string>> = {
  IN_REVIEW: 'Start review',
  APPROVED: 'Approve',
  REJECTED: 'Reject',
  COMPLETED: 'Mark completed',
}

const EVENT_LABELS: Record<string, string> = {
  REQUEST_CREATED: 'Request created',
  STATUS_CHANGED: 'Status changed',
}

/** Render an audit-trail status transition as `: Pending → In review`. */
function statusTransitionSuffix(event: AccountRequestEvent): string {
  const from = event.old_value?.status
  const to = event.new_value?.status
  if (typeof from !== 'string' || typeof to !== 'string') return ''
  const label = (value: string) => escalationStatusLabels[value as EscalationStatus] ?? value
  return `: ${label(from)} → ${label(to)}`
}

export function AccountRequestDetailPage() {
  const params = useParams<{ requestId: string }>()
  const requestId = params.requestId ?? ''

  const me = useMe()
  const detail = useAccountRequest(requestId)
  const directory = useUserDirectory()
  const updateStatus = useUpdateAccountRequestStatus(requestId)
  const addComment = useAddAccountRequestComment(requestId)

  const [rejectOpen, setRejectOpen] = useState(false)

  if (detail.isPending) return <LoadingState label='Loading request…' />

  if (detail.isError) {
    const error = detail.error
    if (error instanceof ApiError && error.isNotFound) {
      return (
        <EmptyState
          icon={ShieldQuestion}
          title='Request not found'
          description='It may have been removed, or you may not have access to it.'
          action={
            <Button asChild size='sm' variant='outline' borderColor={palette.border}>
              <Link to='/account-requests'>Back to account requests</Link>
            </Button>
          }
        />
      )
    }
    return (
      <ErrorState
        title='Could not load this request'
        description={errorMessage(error)}
        onRetry={() => void detail.refetch()}
      />
    )
  }

  const data = detail.data
  if (!data) return <LoadingState />

  const { request, comments, events } = data
  const admin = isAdmin(me.data?.role)
  const isCreator = me.data?.id === request.created_by_user_id
  const canDecide = admin && !isCreator
  const commentable = COMMENTABLE.includes(request.status)

  const move = (status: EscalationStatus, reason?: string) => {
    updateStatus.mutate(
      { status, reason },
      {
        onSuccess: () =>
          toaster.create({
            title: `Request set to ${escalationStatusLabels[status]}`,
            description:
              status === 'APPROVED'
                ? 'The identity change is performed separately through the verified Clerk process.'
                : undefined,
          }),
        onError: (error) =>
          toaster.create({
            title: 'Could not update the request',
            description: errorMessage(error),
            type: 'error',
          }),
      },
    )
  }

  const submitComment = async (input: { body: string }) => {
    try {
      await addComment.mutateAsync({ body: input.body })
    } catch (error) {
      toaster.create({
        title: 'Could not add the comment',
        description: errorMessage(error),
        type: 'error',
      })
      throw error
    }
  }

  return (
    <>
      <PageHeader
        breadcrumb={
          <Link to='/account-requests' style={{ textDecoration: 'none' }}>
            <Text fontSize='sm' color={palette.textMuted}>
              Account requests / {escalationCategoryLabels[request.category]}
            </Text>
          </Link>
        }
        title={
          <Flex direction='column' gap='2'>
            <Text as='span' fontSize='sm' color={palette.textMuted}>
              {escalationCategoryLabels[request.category]}
            </Text>
            <Text as='span'>{request.target_full_name_snapshot}</Text>
          </Flex>
        }
        actions={<EscalationStatusBadge status={request.status} />}
      />

      <Stack gap='6' maxW='container.lg'>
        <Surface p={{ base: '5', md: '6' }}>
          <Stack gap='5'>
            <Flex gap='2' wrap='wrap' align='center'>
              <EscalationStatusBadge status={request.status} />
              <Text fontSize='xs' color={palette.textMuted}>
                Opened {formatRelative(request.created_at)} by{' '}
                {directory.label(request.created_by_user_id)}
              </Text>
            </Flex>

            <Stack gap='1'>
              <Text fontSize='xs' color={palette.textMuted}>
                Justification
              </Text>
              <Text fontSize='sm' color={palette.text} whiteSpace='pre-wrap' lineHeight='1.7'>
                {request.justification}
              </Text>
            </Stack>

            {request.internal_details ? (
              <Stack gap='1'>
                <Text fontSize='xs' color={palette.textMuted}>
                  Internal details (reviewers only)
                </Text>
                <Text
                  fontSize='sm'
                  color={palette.textSecondary}
                  whiteSpace='pre-wrap'
                  lineHeight='1.7'
                >
                  {request.internal_details}
                </Text>
              </Stack>
            ) : null}

            <Flex gap='8' wrap='wrap'>
              <MetaItem label='Target account' value={request.target_email_snapshot} />
              <MetaItem
                label='Related ticket'
                value={
                  request.ticket_id ? (
                    <Link
                      to={`/tickets/${request.ticket_id}`}
                      style={{ textDecoration: 'underline' }}
                    >
                      Open ticket
                    </Link>
                  ) : (
                    'None'
                  )
                }
              />
              <MetaItem label='Last update' value={formatDateTime(request.updated_at)} />
            </Flex>

            {request.decided_at ? (
              <Flex gap='8' wrap='wrap'>
                <MetaItem label='Decided by' value={directory.label(request.decided_by_user_id)} />
                <MetaItem label='Decided at' value={formatDateTime(request.decided_at)} />
                {request.decision_reason ? (
                  <MetaItem label='Decision reason' value={request.decision_reason} />
                ) : null}
              </Flex>
            ) : null}

            {request.completed_at ? (
              <Flex gap='8' wrap='wrap'>
                <MetaItem
                  label='Completed by'
                  value={directory.label(request.completed_by_user_id)}
                />
                <MetaItem label='Completed at' value={formatDateTime(request.completed_at)} />
              </Flex>
            ) : null}

            <Text
              fontSize='xs'
              color={palette.textMuted}
              borderTopWidth='1px'
              borderColor={palette.borderSubtle}
              pt='4'
            >
              Approving a request records an authorization decision only. Identity changes are
              performed separately through the verified Clerk process; this workflow never edits a
              user record.
            </Text>
          </Stack>
        </Surface>

        {canDecide ? (
          <Surface p={{ base: '5', md: '6' }}>
            <Stack gap='4'>
              <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                Review
              </Text>
              {ALLOWED_TRANSITIONS[request.status].length === 0 ? (
                <Text fontSize='xs' color={palette.textMuted}>
                  This request is {escalationStatusLabels[request.status].toLowerCase()} and can no
                  longer change state.
                </Text>
              ) : (
                <Flex gap='2' wrap='wrap'>
                  {ALLOWED_TRANSITIONS[request.status].map((status) =>
                    status === 'REJECTED' ? (
                      <Button
                        key={status}
                        size='sm'
                        variant='outline'
                        borderColor={palette.border}
                        onClick={() => setRejectOpen(true)}
                        loading={
                          updateStatus.isPending && updateStatus.variables?.status === status
                        }
                      >
                        <Ban size={14} aria-hidden />
                        {TRANSITION_LABELS[status]}
                      </Button>
                    ) : (
                      <Button
                        key={status}
                        size='sm'
                        bg={palette.ink}
                        color={palette.textOnInk}
                        _hover={{ bg: palette.inkHover }}
                        onClick={() => move(status)}
                        loading={
                          updateStatus.isPending && updateStatus.variables?.status === status
                        }
                      >
                        {status === 'IN_REVIEW' ? (
                          <Search size={14} aria-hidden />
                        ) : status === 'COMPLETED' ? (
                          <ClipboardCheck size={14} aria-hidden />
                        ) : (
                          <CheckCircle2 size={14} aria-hidden />
                        )}
                        {TRANSITION_LABELS[status]}
                      </Button>
                    ),
                  )}
                </Flex>
              )}
              {isCreator ? (
                <Text fontSize='xs' color={palette.textMuted}>
                  You created this request, so only another administrator can decide it.
                </Text>
              ) : null}
            </Stack>
          </Surface>
        ) : isCreator ? (
          <Text fontSize='xs' color={palette.textMuted} px='1'>
            You created this request: a different administrator reviews and decides it.
          </Text>
        ) : null}

        <Surface p={{ base: '5', md: '6' }}>
          <Stack gap='4'>
            <Text fontSize='sm' fontWeight='medium' color={palette.text}>
              Discussion
            </Text>
            {comments.length === 0 ? (
              <EmptyState
                compact
                title='No comments yet'
                description='Use comments to ask for or provide additional context.'
              />
            ) : (
              <Stack gap='0'>
                {comments.map((comment, index) => {
                  const isOwn = comment.author_user_id === me.data?.id
                  const authorName = isOwn ? 'You' : directory.label(comment.author_user_id)
                  return (
                    <Flex
                      key={comment.id}
                      gap='3.5'
                      py='4'
                      borderTopWidth={index === 0 ? '0' : '1px'}
                      borderColor={palette.borderSubtle}
                    >
                      <UserAvatar
                        name={authorName}
                        src={isOwn ? me.data?.image_url : directory.user(comment.author_user_id)?.image_url}
                        tone={isOwn ? 'ink' : 'neutral'}
                      />
                      <Stack gap='1' minW='0' flex='1'>
                        <Flex align='center' gap='2' wrap='wrap'>
                          <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                            {authorName}
                          </Text>
                          <Text fontSize='xs' color={palette.textFaint}>
                            {formatDateTime(comment.created_at)}
                          </Text>
                        </Flex>
                        <Text
                          fontSize='sm'
                          color={palette.text}
                          whiteSpace='pre-wrap'
                          wordBreak='break-word'
                          lineHeight='1.6'
                        >
                          {comment.body}
                        </Text>
                      </Stack>
                    </Flex>
                  )
                })}
              </Stack>
            )}

            {commentable ? (
              <Composer
                onSubmit={submitComment}
                isPending={addComment.isPending}
                placeholder='Add context for the reviewers…'
                submitLabel='Add comment'
                maxLength={4000}
              />
            ) : (
              <Text fontSize='xs' color={palette.textMuted}>
                This request is closed for further comments.
              </Text>
            )}
          </Stack>
        </Surface>

        <Surface p={{ base: '5', md: '6' }}>
          <Stack gap='4'>
            <Text fontSize='sm' fontWeight='medium' color={palette.text}>
              Audit trail
            </Text>
            <Stack gap='3'>
              {events.map((event) => (
                <Flex key={event.id} gap='3' align='flex-start'>
                  <Flex
                    align='center'
                    justify='center'
                    boxSize='6'
                    borderRadius='full'
                    borderWidth='1px'
                    borderColor={palette.border}
                    bg={palette.surfaceMuted}
                    color={palette.textSecondary}
                    flexShrink={0}
                    mt='0.5'
                  >
                    <ShieldQuestion size={12} aria-hidden />
                  </Flex>
                  <Stack gap='0.5' minW='0'>
                    <Text fontSize='xs' color={palette.text}>
                      {EVENT_LABELS[event.event_type] ?? event.event_type}
                      {statusTransitionSuffix(event)}
                    </Text>
                    <Text fontSize='2xs' color={palette.textFaint}>
                      {directory.label(event.actor_user_id)} · {formatDateTime(event.created_at)}
                    </Text>
                  </Stack>
                </Flex>
              ))}
            </Stack>
          </Stack>
        </Surface>
      </Stack>

      <RejectDialog
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        isPending={updateStatus.isPending}
        onConfirm={(reason) => {
          move('REJECTED', reason)
          setRejectOpen(false)
        }}
      />
    </>
  )
}

function MetaItem({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Stack gap='0.5'>
      <Text fontSize='xs' color={palette.textMuted}>
        {label}
      </Text>
      <Text fontSize='sm' color={palette.textSecondary}>
        {value}
      </Text>
    </Stack>
  )
}

function RejectDialog({
  open,
  onOpenChange,
  isPending,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  isPending: boolean
  onConfirm: (reason: string) => void
}) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const trimmed = reason.trim()
    if (!trimmed) {
      setError('A rejection reason is required.')
      return
    }
    if (trimmed.length > 2000) {
      setError('Keep the reason under 2000 characters.')
      return
    }
    setError(null)
    onConfirm(trimmed)
    setReason('')
  }

  return (
    <Dialog.Root open={open} onOpenChange={(details) => onOpenChange(details.open)}>
      <Portal>
        <Dialog.Backdrop bg={palette.overlay} />
        <Dialog.Positioner>
          <Dialog.Content
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l3'
            maxW='md'
            boxShadow={palette.shadowLg}
          >
            <form onSubmit={submit} noValidate>
              <Dialog.Header px='6' pt='6' pb='2'>
                <Dialog.Title fontSize='md' fontWeight='medium' color={palette.text}>
                  Reject this request
                </Dialog.Title>
              </Dialog.Header>
              <Dialog.Body px='6' py='4'>
                <FormField
                  label='Reason'
                  htmlFor='reject-reason'
                  required
                  error={error ?? undefined}
                  helperText='Recorded in the audit trail and sent to the requester.'
                >
                  <TextAreaInput
                    id='reject-reason'
                    minH='28'
                    maxLength={2000}
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                  />
                </FormField>
              </Dialog.Body>
              <Dialog.Footer px='6' pb='6' pt='2' gap='2'>
                <Button
                  size='sm'
                  variant='ghost'
                  color={palette.textSecondary}
                  onClick={() => onOpenChange(false)}
                  disabled={isPending}
                >
                  Cancel
                </Button>
                <Button
                  type='submit'
                  size='sm'
                  bg={palette.ink}
                  color={palette.textOnInk}
                  _hover={{ bg: palette.inkHover }}
                  loading={isPending}
                >
                  Reject request
                </Button>
              </Dialog.Footer>
            </form>
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
  )
}
