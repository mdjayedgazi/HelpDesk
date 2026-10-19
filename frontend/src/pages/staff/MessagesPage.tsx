import { Button, Dialog, Portal, SimpleGrid, Stack, Text } from '@chakra-ui/react'
import { Mail, MessageSquare, PenLine } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { ReceivedMessagesPanel } from '../../components/ReceivedMessagesPanel.tsx'
import { ConversationList, ConversationPanel } from '../../components/StaffConversations.tsx'
import { FormField, TextInput } from '../../components/FormField.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { EmptyState, ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { toaster } from '../../components/Toaster.tsx'
import { useMe } from '../../hooks/useMe.ts'
import {
  useStaffConversations,
  useStartStaffConversation,
} from '../../hooks/useStaffMessages.ts'
import { errorMessage } from '../../lib/errors.ts'
import type { StaffConversation } from '../../lib/types.ts'
import { palette } from '../../theme/palette.ts'
import { OwnerInbox } from './OwnerInbox.tsx'

/**
 * The private staff <-> Owner channel.
 *
 * The Owner gets the full internal-messaging hub (Inbox / Compose / Sent); an
 * agent or admin sees their own single thread with the Owner plus any internal
 * messages addressed to them. The backend scopes both lists by the
 * authenticated role, so this page simply renders what it gets.
 */
export function MessagesPage() {
  const me = useMe()
  const role = me.data?.role

  if (role === 'owner') return <OwnerInbox />

  return <StaffMessagesPage viewerId={me.data?.id ?? ''} />
}

function StaffMessagesPage({ viewerId }: { viewerId: string }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const conversations = useStaffConversations()
  const [startOpen, setStartOpen] = useState(false)

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

  return (
    <>
      <PageHeader
        title='Message the Owner'
        description='Private channel between you and the Owner, plus internal messages the Owner sends you. Customers never see these messages.'
        actions={
          items.length === 0 && !conversations.isPending ? (
            <Button
              size='sm'
              bg={palette.ink}
              color={palette.textOnInk}
              _hover={{ bg: palette.inkHover }}
              onClick={() => setStartOpen(true)}
            >
              <PenLine size={14} aria-hidden />
              Message the Owner
            </Button>
          ) : null
        }
      />

      <Stack gap='6'>
        <ReceivedMessagesPanel />

        {conversations.isPending ? (
          <LoadingState label='Loading conversations…' />
        ) : conversations.isError ? (
          <ErrorState
            title='Could not load conversations'
            description={errorMessage(conversations.error)}
            onRetry={() => void conversations.refetch()}
          />
        ) : items.length === 0 ? (
          <EmptyState
            icon={Mail}
            title='No conversation with the Owner yet'
            description='Start a private thread to ask the Owner about an account or a case you cannot resolve yourself.'
            action={
              <Button
                size='sm'
                bg={palette.ink}
                color={palette.textOnInk}
                _hover={{ bg: palette.inkHover }}
                onClick={() => setStartOpen(true)}
              >
                <PenLine size={14} aria-hidden />
                Message the Owner
              </Button>
            }
          />
        ) : (
          <SimpleGrid columns={{ base: 1, lg: 3 }} gap='6' alignItems='start'>
            <ConversationList
              conversations={items}
              activeId={activeId}
              isOwnerViewer={false}
              onSelect={select}
              title='Your thread'
            />

            <Stack gridColumn={{ lg: 'span 2' }} minW='0'>
              {activeId ? (
                <ConversationPanel
                  key={activeId}
                  conversationId={activeId}
                  isOwnerViewer={false}
                  viewerId={viewerId}
                />
              ) : (
                <EmptyState
                  compact
                  icon={MessageSquare}
                  title='Select a conversation'
                  description='Choose a thread on the left to read and reply.'
                />
              )}
            </Stack>
          </SimpleGrid>
        )}
      </Stack>

      <StartConversationDialog
        open={startOpen}
        onOpenChange={setStartOpen}
        onStarted={(conversation) => select(conversation.id)}
      />
    </>
  )
}

function StartConversationDialog({
  open,
  onOpenChange,
  onStarted,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onStarted: (conversation: StaffConversation) => void
}) {
  const start = useStartStaffConversation()
  const [subject, setSubject] = useState('')

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    try {
      const conversation = await start.mutateAsync(subject.trim() || undefined)
      toaster.create({
        title: 'Conversation ready',
        description: 'The Owner can see your message thread now.',
      })
      onOpenChange(false)
      setSubject('')
      onStarted(conversation)
    } catch (error) {
      toaster.create({
        title: 'Could not start the conversation',
        description: errorMessage(error),
        type: 'error',
      })
    }
  }

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
            maxW='md'
            boxShadow='0 24px 60px -24px rgba(0,0,0,0.28)'
          >
            <form onSubmit={submit} noValidate>
              <Dialog.Header px='6' pt='6' pb='2'>
                <Dialog.Title fontSize='md' fontWeight='medium' color={palette.text}>
                  Message the Owner
                </Dialog.Title>
                <Text fontSize='xs' color={palette.textMuted} pt='2'>
                  One private thread per staff member. The Owner replies inside it; customers and
                  other agents can never read it.
                </Text>
              </Dialog.Header>
              <Dialog.Body px='6' py='4'>
                <FormField
                  label='Subject (optional)'
                  htmlFor='conversation-subject'
                  helperText='A short line so the Owner can triage, for example “Refund approval request”.'
                >
                  <TextInput
                    id='conversation-subject'
                    maxLength={180}
                    value={subject}
                    onChange={(event) => setSubject(event.target.value)}
                    placeholder='What is this about?'
                  />
                </FormField>
              </Dialog.Body>
              <Dialog.Footer px='6' pb='6' pt='2' gap='2'>
                <Button
                  size='sm'
                  variant='ghost'
                  color={palette.textSecondary}
                  onClick={() => onOpenChange(false)}
                  disabled={start.isPending}
                >
                  Cancel
                </Button>
                <Button
                  type='submit'
                  size='sm'
                  bg={palette.ink}
                  color={palette.textOnInk}
                  _hover={{ bg: palette.inkHover }}
                  loading={start.isPending}
                >
                  Start conversation
                </Button>
              </Dialog.Footer>
            </form>
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
  )
}
