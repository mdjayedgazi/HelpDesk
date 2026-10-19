import {
  Button,
  Dialog,
  Flex,
  NativeSelect,
  Portal,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  chakra,
} from '@chakra-ui/react'
import { CheckCheck, Inbox, Mail, MessageSquare, PenLine, Send, Users } from 'lucide-react'
import { type ReactNode, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { ConversationList, ConversationPanel } from '../../components/StaffConversations.tsx'
import { ConfirmDialog } from '../../components/ConfirmDialog.tsx'
import { EmployeePicker } from '../../components/EmployeePicker.tsx'
import { FormField, FormStack, TextAreaInput, TextInput } from '../../components/FormField.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { Pagination } from '../../components/Pagination.tsx'
import { EmptyState, ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { SectionHeader, Surface } from '../../components/Surface.tsx'
import { Pill, RoleBadge } from '../../components/badges.tsx'
import { toaster } from '../../components/Toaster.tsx'
import {
  useComposeInternalMessage,
  useMessageRecipients,
  useSentMessage,
  useSentMessages,
} from '../../hooks/useInternalMessages.ts'
import { useDebounced } from '../../hooks/useDebounced.ts'
import { useMe } from '../../hooks/useMe.ts'
import { useStaffConversations } from '../../hooks/useStaffMessages.ts'
import { errorMessage } from '../../lib/errors.ts'
import { audienceLabels, formatDateTime, formatRelative, roleLabels } from '../../lib/format.ts'
import type {
  InternalAudience,
  InternalMessageSummary,
  Role,
  StaffConversationListParams,
  User,
} from '../../lib/types.ts'
import { palette } from '../../theme/palette.ts'

const PAGE_SIZE = 10

const selectStyles = {
  bg: palette.surface,
  borderColor: palette.border,
  borderRadius: 'l2',
  fontSize: 'sm',
  height: '9',
  _hover: { borderColor: palette.borderStrong },
  _focus: { borderColor: palette.ink },
} as const

/** A small controlled native select, mirroring `TicketFilterBar`'s idiom. */
function Select({
  value,
  onChange,
  children,
  minW,
  ariaLabel,
}: {
  value: string
  onChange: (value: string) => void
  children: ReactNode
  minW?: string
  ariaLabel: string
}) {
  return (
    <NativeSelect.Root size='sm' width='auto' minW={minW}>
      <NativeSelect.Field
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label={ariaLabel}
        {...selectStyles}
      >
        {children}
      </NativeSelect.Field>
      <NativeSelect.Indicator color={palette.textMuted} />
    </NativeSelect.Root>
  )
}

/**
 * The Owner Inbox: the internal-messaging hub for the single Owner.
 *
 * Three clear sections: the Inbox of messages received from agents/admins
 * (with the existing private threads), Compose (broadcast or a direct note) and
 * Sent. The backend enforces every permission; this page only presents what it
 * returns and never derives roles client-side.
 */
export function OwnerInbox() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const tab: 'inbox' | 'compose' | 'sent' =
    tabParam === 'compose' || tabParam === 'sent' ? tabParam : 'inbox'

  const setTab = (value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value === 'inbox') next.delete('tab')
    else next.set('tab', value)
    setSearchParams(next, { replace: true })
  }

  return (
    <>
      <PageHeader
        title='Owner inbox'
        description='Internal company messaging. Broadcast to staff, send a direct note, and read what agents and administrators send you.'
      />

      <Tabs.Root
        value={tab}
        onValueChange={(details) => {
          if (details.value) setTab(details.value)
        }}
      >
        <Tabs.List mb='6'>
          <Tabs.Trigger value='inbox' fontSize='sm'>
            <Inbox size={15} aria-hidden />
            Inbox
          </Tabs.Trigger>
          <Tabs.Trigger value='compose' fontSize='sm'>
            <PenLine size={15} aria-hidden />
            Compose
          </Tabs.Trigger>
          <Tabs.Trigger value='sent' fontSize='sm'>
            <Send size={15} aria-hidden />
            Sent
          </Tabs.Trigger>
          <Tabs.Indicator />
        </Tabs.List>

        <Tabs.Content value='inbox'>
          <InboxSection />
        </Tabs.Content>
        <Tabs.Content value='compose'>
          <ComposeSection onSent={() => setTab('sent')} />
        </Tabs.Content>
        <Tabs.Content value='sent'>
          <SentSection />
        </Tabs.Content>
      </Tabs.Root>
    </>
  )
}

/* -------------------------------------------------------------------------- */
/* A. Inbox                                                                    */
/* -------------------------------------------------------------------------- */

function InboxSection() {
  const me = useMe()
  const [searchParams, setSearchParams] = useSearchParams()
  const [roleFilter, setRoleFilter] = useState<Role | 'all'>('all')
  const [sender, setSender] = useState<User | null>(null)
  const [unreadOnly, setUnreadOnly] = useState(false)

  const params: StaffConversationListParams = {
    ...(roleFilter !== 'all' ? { staff_role: roleFilter } : {}),
    ...(sender ? { staff_user_id: sender.id } : {}),
    ...(unreadOnly ? { unread_only: true } : {}),
  }

  const conversations = useStaffConversations(params)
  const items = conversations.data ?? []
  const requested = searchParams.get('conversation')

  const activeId = useMemo(() => {
    if (requested && items.some((conversation) => conversation.id === requested)) {
      return requested
    }
    return items[0]?.id
  }, [requested, items])

  const select = (id: string) => {
    const next = new URLSearchParams(searchParams)
    next.set('conversation', id)
    setSearchParams(next, { replace: true })
  }

  const hasFilters = roleFilter !== 'all' || sender !== null || unreadOnly

  return (
    <Stack gap='6'>
      <Surface p='4'>
        <Flex wrap='wrap' gap='4' align='flex-end'>
          <FormField label='Sender role'>
            <Select
              value={roleFilter}
              onChange={(value) => setRoleFilter(value as Role | 'all')}
              minW='10rem'
              ariaLabel='Filter by sender role'
            >
              <option value='all'>All senders</option>
              <option value='agent'>Agents</option>
              <option value='admin'>Administrators</option>
            </Select>
          </FormField>

          <Stack gap='1.5' minW={{ base: 'full', md: '18rem' }} flex='1'>
            <Text fontSize='sm' fontWeight='medium' color={palette.text}>
              Specific sender
            </Text>
            <EmployeePicker
              value={sender}
              onChange={(user) => setSender(user)}
              showResultsWhenEmpty={false}
              placeholder='Search by name, email, or account ID…'
            />
          </Stack>

          <Button
            size='sm'
            variant={unreadOnly ? 'solid' : 'outline'}
            bg={unreadOnly ? palette.ink : undefined}
            color={unreadOnly ? palette.textOnInk : palette.textSecondary}
            borderColor={palette.border}
            aria-pressed={unreadOnly}
            onClick={() => setUnreadOnly((value) => !value)}
          >
            Unread only
          </Button>
        </Flex>
      </Surface>

      {conversations.isPending ? (
        <LoadingState label='Loading messages…' />
      ) : conversations.isError ? (
        <ErrorState
          title='Could not load messages'
          description={errorMessage(conversations.error)}
          onRetry={() => void conversations.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Mail}
          title={hasFilters ? 'No messages match these filters' : 'No messages yet'}
          description={
            hasFilters
              ? 'Try a different sender or clear the filters.'
              : 'When an agent or administrator messages you, it appears here.'
          }
        />
      ) : (
        <SimpleGrid columns={{ base: 1, lg: 3 }} gap='6' alignItems='start'>
          <BoxGridLeft>
            <ConversationList
              conversations={items}
              activeId={activeId}
              isOwnerViewer
              onSelect={select}
              title='Messages received'
            />
          </BoxGridLeft>

          <chakra.div gridColumn={{ lg: 'span 2' }} minW='0'>
            {activeId ? (
              <ConversationPanel
                key={activeId}
                conversationId={activeId}
                isOwnerViewer
                viewerId={me.data?.id ?? ''}
              />
            ) : (
              <EmptyState
                compact
                icon={MessageSquare}
                title='Select a message'
                description='Choose a sender on the left to read the conversation and reply.'
              />
            )}
          </chakra.div>
        </SimpleGrid>
      )}
    </Stack>
  )
}

/** Small helper so the conversation list can be the grid's first column. */
function BoxGridLeft({ children }: { children: ReactNode }) {
  return <chakra.div gridColumn={{ lg: 'span 1' }}>{children}</chakra.div>
}

/* -------------------------------------------------------------------------- */
/* B. Compose                                                                  */
/* -------------------------------------------------------------------------- */

function ComposeSection({ onSent }: { onSent: () => void }) {
  const compose = useComposeInternalMessage()
  const agents = useMessageRecipients({ role: 'agent', limit: 100 })
  const admins = useMessageRecipients({ role: 'admin', limit: 100 })

  const [audience, setAudience] = useState<InternalAudience>('everyone')
  const [recipient, setRecipient] = useState<User | null>(null)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [reviewOpen, setReviewOpen] = useState(false)
  const [errors, setErrors] = useState<{ subject?: string; body?: string; recipient?: string }>({})

  const agentCount = agents.data?.length ?? 0
  const adminCount = admins.data?.length ?? 0
  const recipientCount =
    audience === 'agents'
      ? agentCount
      : audience === 'admins'
        ? adminCount
        : audience === 'everyone'
          ? agentCount + adminCount
          : recipient
            ? 1
            : 0

  const validate = () => {
    const next: typeof errors = {}
    if (!subject.trim()) next.subject = 'Add a subject.'
    else if (subject.trim().length > 180) next.subject = 'Subjects are limited to 180 characters.'
    if (!body.trim()) next.body = 'Write a message.'
    else if (body.trim().length > 5000) next.body = 'Messages are limited to 5000 characters.'
    if (audience === 'individual' && !recipient) {
      next.recipient = 'Choose the employee to send this to.'
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const startReview = () => {
    if (!validate()) return
    setReviewOpen(true)
  }

  const send = async () => {
    if (compose.isPending) return
    try {
      const created = await compose.mutateAsync({
        audience,
        subject: subject.trim(),
        body: body.trim(),
        recipient_user_id: audience === 'individual' ? (recipient?.id ?? null) : null,
      })
      toaster.create({
        title: 'Message sent',
        description: `Delivered to ${created.recipient_count} ${
          created.recipient_count === 1 ? 'recipient' : 'recipients'
        } (${audienceLabels[created.audience]}).`,
        type: 'success',
      })
      setReviewOpen(false)
      setSubject('')
      setBody('')
      setRecipient(null)
      setAudience('everyone')
      setErrors({})
      onSent()
    } catch (error) {
      toaster.create({
        title: 'Could not send the message',
        description: errorMessage(error),
        type: 'error',
      })
    }
  }

  return (
    <Surface p={{ base: '5', md: '6' }}>
      <Stack gap='6'>
        <SectionHeader
          title='Compose a message'
          description='Send an internal message to everyone, all agents, all administrators, or one employee.'
        />

        <FormStack>
          <FormField label='Recipients' required>
            <Select
              value={audience}
              onChange={(value) => {
                setAudience(value as InternalAudience)
                setErrors((prev) => ({ ...prev, recipient: undefined }))
              }}
              ariaLabel='Message recipients'
            >
              <option value='everyone'>Everyone (all staff, excluding customers)</option>
              <option value='agents'>All agents</option>
              <option value='admins'>All administrators</option>
              <option value='individual'>One employee</option>
            </Select>
          </FormField>

          {audience === 'individual' ? (
            <FormField label='Employee' error={errors.recipient} required>
              <EmployeePicker value={recipient} onChange={setRecipient} />
            </FormField>
          ) : (
            <Surface px='4' py='3' bg={palette.surfaceMuted}>
              <Text fontSize='xs' color={palette.textSecondary}>
                {recipientCount} recipient{recipientCount === 1 ? '' : 's'} will receive this
                message. Customers are never included.
              </Text>
            </Surface>
          )}

          <FormField label='Subject' htmlFor='compose-subject' error={errors.subject} required>
            <TextInput
              id='compose-subject'
              maxLength={180}
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              placeholder='What is this about?'
            />
          </FormField>

          <FormField label='Message' htmlFor='compose-body' error={errors.body} required>
            <TextAreaInput
              id='compose-body'
              rows={6}
              maxLength={5000}
              value={body}
              onChange={(event) => setBody(event.target.value)}
              placeholder='Write your message…'
            />
          </FormField>
        </FormStack>

        <Flex justify='flex-end' gap='3'>
          <Button
            size='sm'
            bg={palette.ink}
            color={palette.textOnInk}
            _hover={{ bg: palette.inkHover }}
            onClick={startReview}
            disabled={compose.isPending}
          >
            <Send size={14} aria-hidden />
            Review &amp; send
          </Button>
        </Flex>
      </Stack>

      <ConfirmDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        title='Send this message?'
        confirmLabel='Send message'
        loading={compose.isPending}
        description={
          audience === 'individual'
            ? `This sends “${subject.trim()}” to ${recipient?.full_name ?? 'the selected employee'} (${recipient ? roleLabels[recipient.role] : ''}).`
            : `This sends “${subject.trim()}” to ${recipientCount} ${
                recipientCount === 1 ? 'recipient' : 'recipients'
              } — ${audienceLabels[audience]}.`
        }
        onConfirm={() => void send()}
      />
    </Surface>
  )
}

/* -------------------------------------------------------------------------- */
/* C. Sent                                                                     */
/* -------------------------------------------------------------------------- */

function SentSection() {
  const [page, setPage] = useState(1)
  const [audience, setAudience] = useState<InternalAudience | 'all'>('all')
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search, 300)
  const [detailId, setDetailId] = useState<string | null>(null)

  const params = {
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    ...(audience !== 'all' ? { audience } : {}),
    ...(debouncedSearch.trim() ? { q: debouncedSearch.trim() } : {}),
  }
  const sent = useSentMessages(params)
  const items = sent.data ?? []

  return (
    <Stack gap='6'>
      <Surface p='4'>
        <Flex wrap='wrap' gap='4' align='flex-end'>
          <FormField label='Audience'>
            <Select
              value={audience}
              onChange={(value) => {
                setAudience(value as InternalAudience | 'all')
                setPage(1)
              }}
              minW='12rem'
              ariaLabel='Filter by audience'
            >
              <option value='all'>All audiences</option>
              <option value='everyone'>Everyone</option>
              <option value='agents'>All agents</option>
              <option value='admins'>All administrators</option>
              <option value='individual'>One employee</option>
            </Select>
          </FormField>

          <FormField label='Search subject'>
            <TextInput
              value={search}
              onChange={(event) => {
                setSearch(event.target.value)
                setPage(1)
              }}
              placeholder='Search sent messages…'
              minW={{ base: 'full', md: '20rem' }}
            />
          </FormField>
        </Flex>
      </Surface>

      {sent.isPending ? (
        <LoadingState label='Loading sent messages…' />
      ) : sent.isError ? (
        <ErrorState
          title='Could not load sent messages'
          description={errorMessage(sent.error)}
          onRetry={() => void sent.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Send}
          title='Nothing sent yet'
          description='Messages you compose appear here with their audience and read counts.'
        />
      ) : (
        <Surface overflow='hidden'>
          <Flex px='4' py='3' borderBottomWidth='1px' borderColor={palette.border}>
            <Text fontSize='sm' fontWeight='medium' color={palette.text}>
              Sent messages
            </Text>
          </Flex>
          <Stack gap='0'>
            {items.map((message) => (
              <SentRow key={message.id} message={message} onSelect={() => setDetailId(message.id)} />
            ))}
          </Stack>
          <Flex px='4' pb='4'>
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              itemCount={items.length}
              hasNext={items.length === PAGE_SIZE}
              onPageChange={setPage}
            />
          </Flex>
        </Surface>
      )}

      <SentDetailDialog id={detailId} onClose={() => setDetailId(null)} />
    </Stack>
  )
}

function AudienceBadge({ audience }: { audience: InternalAudience }) {
  return <Pill tone={audience === 'everyone' ? 'ink' : 'default'}>{audienceLabels[audience]}</Pill>
}

function SentRow({
  message,
  onSelect,
}: {
  message: InternalMessageSummary
  onSelect: () => void
}) {
  return (
    <chakra.button
      type='button'
      onClick={onSelect}
      textAlign='start'
      width='full'
      px='4'
      py='3.5'
      borderBottomWidth='1px'
      borderColor={palette.borderSubtle}
      _hover={{ bg: palette.hover }}
      _focusVisible={{ outline: '2px solid', outlineColor: palette.ink, outlineOffset: '-2px' }}
    >
      <Stack gap='1.5' minW='0'>
        <Flex align='center' gap='2' justify='space-between' wrap='wrap'>
          <Flex align='center' gap='2' minW='0'>
            <Text fontSize='sm' fontWeight='medium' color={palette.text} truncate>
              {message.subject}
            </Text>
            <AudienceBadge audience={message.audience} />
          </Flex>
          <Text fontSize='2xs' color={palette.textFaint} whiteSpace='nowrap'>
            {formatRelative(message.created_at)}
          </Text>
        </Flex>
        <Text fontSize='xs' color={palette.textSecondary} truncate>
          {message.preview}
        </Text>
        <Flex gap='4' wrap='wrap'>
          <Flex align='center' gap='1.5' color={palette.textMuted}>
            <Users size={13} aria-hidden />
            <Text fontSize='2xs'>
              {message.recipient_count} recipient{message.recipient_count === 1 ? '' : 's'}
            </Text>
          </Flex>
          <Flex align='center' gap='1.5' color={palette.textMuted}>
            <CheckCheck size={13} aria-hidden />
            <Text fontSize='2xs'>
              {message.read_count} of {message.recipient_count} read
            </Text>
          </Flex>
        </Flex>
      </Stack>
    </chakra.button>
  )
}

function SentDetailDialog({ id, onClose }: { id: string | null; onClose: () => void }) {
  const detail = useSentMessage(id ?? undefined, { limit: 100 })
  const message = detail.data

  return (
    <Dialog.Root open={Boolean(id)} onOpenChange={(details) => (details.open ? null : onClose())}>
      <Portal>
        <Dialog.Backdrop bg='rgba(17,17,17,0.32)' />
        <Dialog.Positioner>
          <Dialog.Content
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l3'
            maxW='2xl'
            boxShadow='0 24px 60px -24px rgba(0,0,0,0.28)'
          >
            <Dialog.Header px='6' pt='6' pb='2'>
              <Dialog.Title fontSize='md' fontWeight='medium' color={palette.text}>
                {message?.subject ?? 'Sent message'}
              </Dialog.Title>
            </Dialog.Header>
            <Dialog.Body px='6' py='4'>
              {detail.isPending ? (
                <LoadingState label='Loading message…' minHeight='12rem' />
              ) : detail.isError || !message ? (
                <ErrorState
                  title='Could not load this message'
                  description={detail.error ? errorMessage(detail.error) : undefined}
                  onRetry={() => void detail.refetch()}
                />
              ) : (
                <Stack gap='5'>
                  <Flex align='center' gap='2' wrap='wrap'>
                    <AudienceBadge audience={message.audience} />
                    <Text fontSize='xs' color={palette.textMuted}>
                      Sent {formatDateTime(message.created_at)}
                    </Text>
                    <Text fontSize='xs' color={palette.textMuted}>
                      · {message.recipient_count} recipient
                      {message.recipient_count === 1 ? '' : 's'} · {message.read_count} read
                    </Text>
                  </Flex>

                  <Text
                    fontSize='sm'
                    color={palette.text}
                    whiteSpace='pre-wrap'
                    wordBreak='break-word'
                    lineHeight='1.6'
                  >
                    {message.body}
                  </Text>

                  <Stack gap='2'>
                    <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                      Recipients
                    </Text>
                    <Stack
                      gap='0'
                      borderWidth='1px'
                      borderColor={palette.borderSubtle}
                      borderRadius='l2'
                      maxH='18rem'
                      overflowY='auto'
                    >
                      {message.recipients.map((recipient, index) => (
                        <Flex
                          key={recipient.id}
                          align='center'
                          gap='3'
                          px='3'
                          py='2.5'
                          borderBottomWidth={index === message.recipients.length - 1 ? '0' : '1px'}
                          borderColor={palette.borderSubtle}
                        >
                          <Stack gap='0.5' minW='0' flex='1'>
                            <Flex align='center' gap='2' wrap='wrap'>
                              <Text fontSize='sm' color={palette.text} truncate>
                                {recipient.recipient_full_name_snapshot}
                              </Text>
                              <RoleBadge role={recipient.recipient_role_snapshot} />
                            </Flex>
                            <Text fontSize='2xs' color={palette.textMuted} truncate>
                              {recipient.recipient_email_snapshot}
                            </Text>
                          </Stack>
                          <Text
                            fontSize='2xs'
                            color={recipient.read_at ? palette.textSecondary : palette.textFaint}
                            whiteSpace='nowrap'
                          >
                            {recipient.read_at
                              ? `Read ${formatRelative(recipient.read_at)}`
                              : 'Unread'}
                          </Text>
                        </Flex>
                      ))}
                    </Stack>
                    {message.recipient_total > message.recipients.length ? (
                      <Text fontSize='2xs' color={palette.textMuted}>
                        Showing the first {message.recipients.length} of {message.recipient_total}{' '}
                        recipients.
                      </Text>
                    ) : null}
                  </Stack>
                </Stack>
              )}
            </Dialog.Body>
            <Dialog.Footer px='6' pb='6' pt='2'>
              <Button size='sm' variant='ghost' color={palette.textSecondary} onClick={onClose}>
                Close
              </Button>
            </Dialog.Footer>
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
  )
}
