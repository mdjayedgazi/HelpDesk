import { Box, Center, Flex, Stack, Text, chakra } from '@chakra-ui/react'
import { MessageSquare } from 'lucide-react'
import { useEffect, useRef } from 'react'

import { useMe } from '../hooks/useMe.ts'
import {
  useMarkStaffConversationRead,
  useSendStaffMessage,
  useStaffConversation,
} from '../hooks/useStaffMessages.ts'
import { errorMessage } from '../lib/errors.ts'
import { formatDateTime, formatRelative } from '../lib/format.ts'
import type { StaffConversation } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'
import { RoleBadge } from './badges.tsx'
import { Composer } from './Composer.tsx'
import { EmptyState, ErrorState, LoadingState } from './StateViews.tsx'
import { Surface } from './Surface.tsx'
import { toaster } from './Toaster.tsx'
import { UserAvatar } from './UserAvatar.tsx'

/**
 * The private staff <-> Owner *thread* UI, shared by the agent/admin view and
 * the Owner inbox. The backend scopes every response by role, so these
 * components only render what the API returned - they never decide access.
 */
export function ConversationList({
  conversations,
  activeId,
  isOwnerViewer,
  onSelect,
  title = 'Conversations',
}: {
  conversations: StaffConversation[]
  activeId: string | undefined
  isOwnerViewer: boolean
  onSelect: (id: string) => void
  title?: string
}) {
  return (
    <Surface overflow='hidden'>
      <Flex px='4' py='3' borderBottomWidth='1px' borderColor={palette.border}>
        <Text fontSize='sm' fontWeight='medium' color={palette.text}>
          {title}
        </Text>
      </Flex>
      <Stack gap='0'>
        {conversations.map((conversation) => (
          <ConversationRow
            key={conversation.id}
            conversation={conversation}
            selected={conversation.id === activeId}
            isOwnerViewer={isOwnerViewer}
            onSelect={() => onSelect(conversation.id)}
          />
        ))}
      </Stack>
    </Surface>
  )
}

function ConversationRow({
  conversation,
  selected,
  isOwnerViewer,
  onSelect,
}: {
  conversation: StaffConversation
  selected: boolean
  isOwnerViewer: boolean
  onSelect: () => void
}) {
  const title = isOwnerViewer
    ? conversation.staff_full_name
    : (conversation.subject ?? 'Conversation with the Owner')

  // The Owner inbox lists messages *received*, so it prefers the last incoming
  // message over the Owner's own latest reply.
  const preview = isOwnerViewer
    ? (conversation.last_received_preview ??
      conversation.last_message_preview ??
      'No messages yet')
    : (conversation.last_message_preview ?? 'No messages yet')

  const timestamp = isOwnerViewer
    ? (conversation.last_received_at ??
      conversation.last_message_at ??
      conversation.created_at)
    : (conversation.last_message_at ?? conversation.created_at)

  const unreadLabel =
    conversation.unread_count > 0
      ? `, ${conversation.unread_count} unread message${conversation.unread_count === 1 ? '' : 's'}`
      : ''

  return (
    <chakra.button
      type='button'
      onClick={onSelect}
      aria-current={selected ? 'true' : undefined}
      aria-label={`${title}${unreadLabel}`}
      textAlign='start'
      width='full'
      px='4'
      py='3.5'
      borderBottomWidth='1px'
      borderColor={palette.borderSubtle}
      bg={selected ? palette.surfaceMuted : 'transparent'}
      _hover={{ bg: palette.hover }}
      _focusVisible={{ outline: '2px solid', outlineColor: palette.ink, outlineOffset: '-2px' }}
      transition='background 0.16s ease'
    >
      <Flex gap='3' minW='0' align='flex-start'>
        <UserAvatar
          name={title}
          src={isOwnerViewer ? conversation.staff_image_url : conversation.owner_image_url}
          size='sm'
        />
        <Stack gap='1' minW='0' flex='1'>
          <Flex align='center' gap='2' justify='space-between'>
            <Text fontSize='sm' fontWeight='medium' color={palette.text} truncate>
              {title}
            </Text>
            {conversation.unread_count > 0 ? (
              <Center
                minW='4'
                height='4'
                px='1'
                borderRadius='full'
                bg={palette.ink}
                color={palette.textOnInk}
                fontSize='2xs'
                fontWeight='semibold'
                flexShrink={0}
              >
                {conversation.unread_count > 9 ? '9+' : conversation.unread_count}
              </Center>
            ) : null}
          </Flex>

          {isOwnerViewer ? (
            <Flex align='center' gap='2' wrap='wrap'>
              {conversation.staff_role ? (
                <RoleBadge role={conversation.staff_role} />
              ) : null}
              <Text
                fontSize='2xs'
                color={palette.textFaint}
                fontFamily='mono'
                title={conversation.staff_user_id}
              >
                ID {conversation.staff_user_id.slice(0, 8)}
              </Text>
            </Flex>
          ) : null}

          <Flex align='center' gap='2' justify='space-between'>
            <Text fontSize='xs' color={palette.textSecondary} truncate>
              {preview}
            </Text>
            <Text fontSize='2xs' color={palette.textFaint} whiteSpace='nowrap' flexShrink={0}>
              {formatRelative(timestamp)}
            </Text>
          </Flex>
        </Stack>
      </Flex>
    </chakra.button>
  )
}

export function ConversationPanel({
  conversationId,
  isOwnerViewer,
  viewerId,
}: {
  conversationId: string
  isOwnerViewer: boolean
  viewerId: string
}) {
  const detail = useStaffConversation(conversationId)
  const send = useSendStaffMessage(conversationId)
  const me = useMe()
  const { mutate: markConversationRead } = useMarkStaffConversationRead(conversationId)
  const lastMarked = useRef<string | null>(null)

  const conversation = detail.data?.conversation
  const unread = conversation?.unread_count ?? 0

  useEffect(() => {
    if (!conversation || unread === 0) return
    const signature = `${conversation.id}:${unread}`
    if (lastMarked.current === signature) return
    lastMarked.current = signature
    markConversationRead()
  }, [conversation, unread, markConversationRead])

  if (detail.isPending) return <LoadingState label='Loading conversation…' minHeight='40vh' />

  if (detail.isError || !conversation) {
    return (
      <ErrorState
        title='Could not load this conversation'
        description={detail.error ? errorMessage(detail.error) : undefined}
        onRetry={() => void detail.refetch()}
      />
    )
  }

  const messages = detail.data?.messages ?? []
  const counterpart = isOwnerViewer ? conversation.staff_full_name : 'Owner'
  const counterpartImage = isOwnerViewer
    ? conversation.staff_image_url
    : conversation.owner_image_url

  const labelFor = (senderId: string) => {
    if (senderId === viewerId) return 'You'
    return counterpart
  }

  const imageFor = (senderId: string) =>
    senderId === viewerId ? me.data?.image_url : counterpartImage

  const submit = async (input: { body: string }) => {
    try {
      await send.mutateAsync(input.body)
    } catch (error) {
      toaster.create({
        title: 'Could not send message',
        description: errorMessage(error),
        type: 'error',
      })
      throw error
    }
  }

  return (
    <Surface p={{ base: '5', md: '6' }}>
      <Stack gap='5'>
        <Stack gap='1'>
          <Text fontSize='md' fontWeight='medium' color={palette.text}>
            {isOwnerViewer ? conversation.staff_full_name : conversation.subject}
          </Text>
          <Text fontSize='xs' color={palette.textMuted}>
            Started {formatDateTime(conversation.created_at)}
          </Text>
        </Stack>

        {messages.length === 0 ? (
          <EmptyState
            compact
            icon={MessageSquare}
            title='No messages yet'
            description={
              isOwnerViewer ? 'Reply below to start the thread.' : 'Write the first message below.'
            }
          />
        ) : (
          <Stack gap='0'>
            {messages.map((message, index) => {
              const isOwn = message.sender_user_id === viewerId
              const authorName = labelFor(message.sender_user_id)
              return (
                <Flex
                  key={message.id}
                  gap='3.5'
                  py='4'
                  borderTopWidth={index === 0 ? '0' : '1px'}
                  borderColor={palette.borderSubtle}
                >
                  <UserAvatar
                    name={authorName}
                    src={imageFor(message.sender_user_id)}
                    tone={isOwn ? 'ink' : 'neutral'}
                  />
                  <Box flex='1' minW='0'>
                    <Flex align='center' gap='2' wrap='wrap'>
                      <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                        {authorName}
                      </Text>
                      <Text fontSize='xs' color={palette.textFaint}>
                        {formatDateTime(message.created_at)}
                      </Text>
                    </Flex>
                    <Text
                      mt='1.5'
                      fontSize='sm'
                      color={palette.text}
                      whiteSpace='pre-wrap'
                      wordBreak='break-word'
                      lineHeight='1.6'
                    >
                      {message.body}
                    </Text>
                  </Box>
                </Flex>
              )
            })}
          </Stack>
        )}

        <Box borderTopWidth='1px' borderColor={palette.borderSubtle} pt='5'>
          <Composer
            onSubmit={submit}
            isPending={send.isPending}
            placeholder={
              isOwnerViewer
                ? `Reply to ${conversation.staff_full_name}…`
                : 'Write a private message to the Owner…'
            }
            submitLabel='Send message'
            maxLength={5000}
          />
        </Box>
      </Stack>
    </Surface>
  )
}
