import { Button, Dialog, Flex, Portal, Stack, Text, chakra } from '@chakra-ui/react'
import { Megaphone } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import {
  useMarkInternalMessageRead,
  useReceivedMessage,
  useReceivedMessages,
} from '../hooks/useInternalMessages.ts'
import { errorMessage } from '../lib/errors.ts'
import { formatDateTime, formatRelative } from '../lib/format.ts'
import type { InternalMessageReceived } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'
import { Surface } from './Surface.tsx'
import { toaster } from './Toaster.tsx'

/**
 * Messages the Owner has sent to this employee (their own recipient rows only).
 *
 * The backend returns nothing for anybody who was not addressed, so this
 * renders nothing when the list is empty. Read state is per recipient and is
 * only ever set for the signed-in user's own copy.
 */
export function ReceivedMessagesPanel() {
  const received = useReceivedMessages({ limit: 20 })
  const items = received.data ?? []
  const [searchParams, setSearchParams] = useSearchParams()
  const requested = searchParams.get('message')
  const [openId, setOpenId] = useState<string | null>(null)

  // The list is capped, so a notification can point at a message older than the
  // newest page. Fetch that exact message instead of silently ignoring the
  // deep link; the backend still only returns the caller's own recipient row.
  const inPage = requested
    ? items.find((message) => message.id === requested) ?? null
    : null
  const detail = useReceivedMessage(requested && !inPage ? requested : null)

  const showList = !received.isPending && !received.isError && items.length > 0
  const active = openId
    ? items.find((message) => message.id === openId) ?? null
    : requested
      ? inPage ?? detail.data ?? null
      : null

  const clearRequest = () => {
    if (!requested) return
    const next = new URLSearchParams(searchParams)
    next.delete('message')
    setSearchParams(next, { replace: true })
  }

  const close = () => {
    setOpenId(null)
    clearRequest()
  }

  if (!showList && !requested) return null

  return (
    <Stack gap='3'>
      {showList ? (
        <>
          <Flex align='center' gap='2'>
            <Megaphone size={15} color={palette.textMuted} aria-hidden />
            <Text fontSize='sm' fontWeight='medium' color={palette.text}>
              From the Owner
            </Text>
          </Flex>
          <Surface overflow='hidden'>
            <Stack gap='0'>
              {items.map((message) => (
                <MessageRow
                  key={message.id}
                  message={message}
                  onSelect={() => setOpenId(message.id)}
                />
              ))}
            </Stack>
          </Surface>
        </>
      ) : null}

      {requested && !inPage && detail.isError ? (
        <Surface p='4'>
          <Stack gap='2' align='flex-start'>
            <Text fontSize='sm' color={palette.text}>
              Could not open that message
            </Text>
            <Text fontSize='xs' color={palette.textFaint}>
              {errorMessage(detail.error)}
            </Text>
            <Button
              size='xs'
              variant='outline'
              borderColor={palette.border}
              onClick={clearRequest}
            >
              Back to messages
            </Button>
          </Stack>
        </Surface>
      ) : null}

      {requested && !inPage && detail.isPending ? (
        <Flex px='4' py='6' justify='center'>
          <Text fontSize='xs' color={palette.textMuted}>
            Opening message…
          </Text>
        </Flex>
      ) : null}

      <MessageDialog message={active} onClose={close} />
    </Stack>
  )
}

function MessageRow({
  message,
  onSelect,
}: {
  message: InternalMessageReceived
  onSelect: () => void
}) {
  const unread = message.read_at === null
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
      aria-label={`${unread ? 'Unread message' : 'Message'}: ${message.subject}`}
    >
      <Stack gap='1' minW='0'>
        <Flex align='center' gap='2' justify='space-between'>
          <Flex align='center' gap='2' minW='0'>
            {unread ? (
              <chakra.span
                boxSize='7px'
                borderRadius='full'
                bg={palette.ink}
                flexShrink={0}
                aria-hidden
              />
            ) : null}
            <Text
              fontSize='sm'
              fontWeight={unread ? 'semibold' : 'medium'}
              color={palette.text}
              truncate
            >
              {message.subject}
            </Text>
          </Flex>
          <Text fontSize='2xs' color={palette.textFaint} whiteSpace='nowrap'>
            {formatRelative(message.created_at)}
          </Text>
        </Flex>
        <Text fontSize='xs' color={palette.textSecondary} truncate>
          {message.body}
        </Text>
      </Stack>
    </chakra.button>
  )
}

function MessageDialog({
  message,
  onClose,
}: {
  message: InternalMessageReceived | null
  onClose: () => void
}) {
  const markRead = useMarkInternalMessageRead()

  // Opening an unread message marks this recipient's own copy as read. The
  // mutation is guarded by `message.read_at`, so re-opening never re-posts.
  useEffect(() => {
    if (!message || message.read_at !== null) return
    markRead.mutate(message.id, {
      onError: (error) => {
        toaster.create({
          title: 'Could not update the read state',
          description: errorMessage(error),
          type: 'error',
        })
      },
    })
    // `markRead` is stable for the lifetime of the dialog; re-running only on
    // a new message id avoids a redundant request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [message?.id])

  return (
    <Dialog.Root open={Boolean(message)} onOpenChange={(details) => (details.open ? null : onClose())}>
      <Portal>
        <Dialog.Backdrop bg={palette.overlay} />
        <Dialog.Positioner>
          <Dialog.Content
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l3'
            maxW='xl'
            boxShadow={palette.shadowLg}
          >
            <Dialog.Header px='6' pt='6' pb='2'>
              <Dialog.Title fontSize='md' fontWeight='medium' color={palette.text}>
                {message?.subject ?? 'Message from the Owner'}
              </Dialog.Title>
              {message ? (
                <Text fontSize='xs' color={palette.textMuted} pt='2'>
                  From {message.sender_full_name} · {formatDateTime(message.created_at)}
                </Text>
              ) : null}
            </Dialog.Header>
            <Dialog.Body px='6' py='4'>
              <Text
                fontSize='sm'
                color={palette.text}
                whiteSpace='pre-wrap'
                wordBreak='break-word'
                lineHeight='1.6'
              >
                {message?.body}
              </Text>
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
