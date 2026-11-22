import { Button, SimpleGrid, Stack } from '@chakra-ui/react'
import { Mail, MessageSquare, PenLine } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { ReceivedMessagesPanel } from '../../components/ReceivedMessagesPanel.tsx'
import { StartConversationDialog } from '../../components/StartConversationDialog.tsx'
import { ConversationList, ConversationPanel } from '../../components/StaffConversations.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { EmptyState, ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { useMe } from '../../hooks/useMe.ts'
import { useStaffConversations } from '../../hooks/useStaffMessages.ts'
import { errorMessage } from '../../lib/errors.ts'
import { palette } from '../../theme/palette.ts'
import { OwnerInbox } from './OwnerInbox.tsx'

/**
 * Universal internal staff messaging.
 *
 * The Owner additionally gets the full messaging hub (Inbox / Compose / Sent);
 * every staff member (Owner, Admin, Agent) gets the universal conversation
 * workspace: their 1:1 threads with any other staff member, the ability to
 * start new ones, and any internal messages addressed to them. The backend
 * scopes everything to the authenticated user, so this page simply renders what
 * it is given.
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
        title='Team messages'
        description='Private direct messages with any teammate. Customers never see these conversations.'
        actions={
          <Button
            size='sm'
            bg={palette.ink}
            color={palette.textOnInk}
            _hover={{ bg: palette.inkHover }}
            onClick={() => setStartOpen(true)}
          >
            <PenLine size={14} aria-hidden />
            New message
          </Button>
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
            title='No conversations yet'
            description='Start a private thread with a teammate to coordinate work customers should never see.'
            action={
              <Button
                size='sm'
                bg={palette.ink}
                color={palette.textOnInk}
                _hover={{ bg: palette.inkHover }}
                onClick={() => setStartOpen(true)}
              >
                <PenLine size={14} aria-hidden />
                New message
              </Button>
            }
          />
        ) : (
          <SimpleGrid columns={{ base: 1, lg: 3 }} gap='6' alignItems='start'>
            <ConversationList
              conversations={items}
              activeId={activeId}
              onSelect={select}
              title='Your conversations'
            />

            <Stack gridColumn={{ lg: 'span 2' }} minW='0'>
              {activeId ? (
                <ConversationPanel
                  key={activeId}
                  conversationId={activeId}
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
