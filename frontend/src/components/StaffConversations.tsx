import { Box, Center, Flex, Stack, Text, chakra } from '@chakra-ui/react'
import { MessageSquare } from 'lucide-react'
import { useEffect, useRef } from 'react'

import { useMe } from '../hooks/useMe.ts'
import { useViewportBoundHeight } from '../hooks/useViewportBoundHeight.ts'
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
import { EmptyState, ErrorState, LoadingState } from './StateViews.tsx'
import { StaffMentionComposer } from './StaffMentionComposer.tsx'
import { Surface } from './Surface.tsx'
import { toaster } from './Toaster.tsx'
import { UserAvatar } from './UserAvatar.tsx'

/**
 * The 1:1 staff messaging thread UI, shared by every staff role. The backend
 * scopes every response to the caller's participant columns, so these
 * components only render what the API returned - they never decide access.
 */
export function ConversationList({
  conversations,
  activeId,
  onSelect,
  title = 'Conversations',
}: {
  conversations: StaffConversation[]
  activeId: string | undefined
  onSelect: (id: string) => void
  title?: string
}) {
  const pane = useViewportBoundHeight<HTMLDivElement>(true)
  return (
    <Surface
      ref={pane.ref}
      overflow='hidden'
      display='flex'
      flexDirection='column'
      maxH={pane.height ? `${pane.height}px` : undefined}
    >
      <Flex
        px='4'
        py='3'
        borderBottomWidth='1px'
        borderColor={palette.border}
        flexShrink={0}
      >
        <Text fontSize='sm' fontWeight='medium' color={palette.text}>
          {title}
        </Text>
      </Flex>
      <Stack gap='0' flex='1' minH='0' overflowY={{ base: 'visible', lg: 'auto' }}>
        {conversations.map((conversation) => (
          <ConversationRow
            key={conversation.id}
            conversation={conversation}
            selected={conversation.id === activeId}
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
  onSelect,
}: {
  conversation: StaffConversation
  selected: boolean
  onSelect: () => void
}) {
  const title = conversation.counterpart_full_name
  const preview = conversation.last_message_preview ?? 'No messages yet'
  const timestamp =
    conversation.last_message_at ?? conversation.created_at

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
        <UserAvatar name={title} src={conversation.counterpart_image_url} size='sm' />
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

          {conversation.counterpart_role ? (
            <RoleBadge role={conversation.counterpart_role} />
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
  viewerId,
}: {
  conversationId: string
  viewerId: string
}) {
  const detail = useStaffConversation(conversationId)
  const send = useSendStaffMessage(conversationId)
  const me = useMe()
  const { mutate: markConversationRead } = useMarkStaffConversationRead(conversationId)
  const lastMarked = useRef<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const pane = useViewportBoundHeight<HTMLDivElement>(true, {
    measureKey: detail.data?.conversation.id,
  })

  const conversation = detail.data?.conversation
  const unread = conversation?.unread_count ?? 0
  const messageCount = detail.data?.messages.length ?? 0

  useEffect(() => {
    if (!conversation || unread === 0) return
    const signature = `${conversation.id}:${unread}`
    if (lastMarked.current === signature) return
    lastMarked.current = signature
    markConversationRead()
  }, [conversation, unread, markConversationRead])

  // The pane scrolls itself now, so keep the newest message in view when the
  // thread loads or a message is sent (the surrounding page no longer grows).
  useEffect(() => {
    const node = scrollRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messageCount])

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
  const counterpart = conversation.counterpart_full_name
  const counterpartImage = conversation.counterpart_image_url

  const labelFor = (senderId: string) => (senderId === viewerId ? 'You' : counterpart)
  const imageFor = (senderId: string) =>
    senderId === viewerId ? me.data?.image_url : counterpartImage

  const submit = async (input: { body: string; mentionedUserIds: string[] }) => {
    try {
      await send.mutateAsync({
        body: input.body,
        mentioned_user_ids: input.mentionedUserIds,
      })
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
    <Surface
      ref={pane.ref}
      p={{ base: '5', md: '6' }}
      display='flex'
      flexDirection='column'
      maxH={pane.height ? `${pane.height}px` : undefined}
    >
      <Stack gap='5' flex='1' minH='0'>
        <Stack gap='1' flexShrink={0}>
          <Text fontSize='md' fontWeight='medium' color={palette.text}>
            {counterpart}
          </Text>
          <Text fontSize='xs' color={palette.textMuted}>
            {conversation.subject} · Started {formatDateTime(conversation.created_at)}
          </Text>
        </Stack>

        {/* The thread is the only scrolling region inside the panel, so a long
            conversation never pushes the composer out of view. */}
        <Box ref={scrollRef} flex='1' minH='0' overflowY={{ base: 'visible', lg: 'auto' }} pr={{ lg: '1' }}>
          {messages.length === 0 ? (
            <EmptyState
              compact
              icon={MessageSquare}
              title='No messages yet'
              description='Write the first message below. Type @ to mention a teammate.'
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
        </Box>

        <Box
          flexShrink={0}
          borderTopWidth='1px'
          borderColor={palette.borderSubtle}
          pt='4'
        >
          <StaffMentionComposer
            onSubmit={submit}
            isPending={send.isPending}
            placeholder={`Message ${counterpart}…`}
            submitLabel='Send message'
            ariaLabel={`Message ${counterpart}`}
            maxLength={5000}
          />
        </Box>
      </Stack>
    </Surface>
  )
}
