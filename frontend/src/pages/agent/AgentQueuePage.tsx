import { Button, Flex, Tabs } from '@chakra-ui/react'
import { Inbox, Layers } from 'lucide-react'
import { useMemo, useState } from 'react'

import { PageHeader } from '../../components/PageHeader.tsx'
import { TicketFilterBar } from '../../components/TicketFilterBar.tsx'
import { TicketListPanel } from '../../components/TicketListPanel.tsx'
import { toaster } from '../../components/Toaster.tsx'
import { useDebounced } from '../../hooks/useDebounced.ts'
import { useAssignedTickets, useClaimTicket, useTickets } from '../../hooks/useTickets.ts'
import { errorMessage } from '../../lib/errors.ts'
import type { TicketStatus, TicketPriority } from '../../lib/types.ts'
import { palette } from '../../theme/palette.ts'

type QueueTab = 'unassigned' | 'assigned'

export function AgentQueuePage() {
  const [tab, setTab] = useState<QueueTab>('unassigned')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<TicketStatus | ''>('')
  const [priority, setPriority] = useState<TicketPriority | ''>('')
  const [claimingId, setClaimingId] = useState<string | null>(null)

  const debouncedSearch = useDebounced(search)
  const params = {
    limit: 100,
    q: debouncedSearch || undefined,
    status: status || undefined,
    priority: priority || undefined,
  }

  const visibleTickets = useTickets(params)
  const assignedTickets = useAssignedTickets(params)
  const claimTicket = useClaimTicket()

  const unassigned = useMemo(
    () => (visibleTickets.data ?? []).filter((ticket) => !ticket.assignee_user_id),
    [visibleTickets.data],
  )
  const assigned = assignedTickets.data ?? []

  const activeQuery = tab === 'unassigned' ? visibleTickets : assignedTickets
  const items = tab === 'unassigned' ? unassigned : assigned

  const handleClaim = async (id: string) => {
    setClaimingId(id)
    try {
      await claimTicket.mutateAsync(id)
      toaster.create({ title: 'Ticket claimed', description: 'It is now in your queue.' })
    } catch (error) {
      toaster.create({
        title: 'Could not claim ticket',
        description: errorMessage(error),
        type: 'error',
      })
    } finally {
      setClaimingId(null)
    }
  }

  return (
    <>
      <PageHeader
        title='My queue'
        description='Claim unassigned tickets or continue work on the ones already yours.'
      />

      <Flex mb='5' wrap='wrap' gap='4' align='center' justify='space-between'>
        <Tabs.Root
          value={tab}
          onValueChange={(details) => {
            if (details.value) setTab(details.value as QueueTab)
          }}
        >
          <Tabs.List>
            <Tabs.Trigger value='unassigned' fontSize='sm'>
              Unassigned
              {unassigned.length > 0 ? ` (${unassigned.length})` : ''}
            </Tabs.Trigger>
            <Tabs.Trigger value='assigned' fontSize='sm'>
              Assigned to me
              {assigned.length > 0 ? ` (${assigned.length})` : ''}
            </Tabs.Trigger>
            <Tabs.Indicator />
          </Tabs.List>
        </Tabs.Root>
      </Flex>

      <Flex mb='5'>
        <TicketFilterBar
          search={search}
          onSearchChange={setSearch}
          status={status}
          onStatusChange={setStatus}
          priority={priority}
          onPriorityChange={setPriority}
        />
      </Flex>

      <TicketListPanel
        tickets={items}
        isLoading={activeQuery.isPending}
        isError={activeQuery.isError}
        error={activeQuery.error}
        onRetry={() => void activeQuery.refetch()}
        emptyIcon={tab === 'unassigned' ? Layers : Inbox}
        emptyTitle={tab === 'unassigned' ? 'The queue is clear' : 'Nothing assigned to you'}
        emptyDescription={
          tab === 'unassigned'
            ? 'There are no unassigned tickets matching these filters.'
            : 'Claim a ticket from the unassigned queue to start working on it.'
        }
        showRequester
        renderActions={
          tab === 'unassigned'
            ? (ticket) => (
                <Button
                  size='xs'
                  variant='outline'
                  borderColor={palette.border}
                  loading={claimingId === ticket.id}
                  onClick={() => void handleClaim(ticket.id)}
                >
                  Claim
                </Button>
              )
            : undefined
        }
      />
    </>
  )
}
