import { Button, SimpleGrid, Stack } from '@chakra-ui/react'
import { Inbox, Layers } from 'lucide-react'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'

import { PageHeader } from '../../components/PageHeader.tsx'
import { SectionHeader } from '../../components/Surface.tsx'
import { StatTile } from '../../components/StatTile.tsx'
import { TicketListPanel } from '../../components/TicketListPanel.tsx'
import { useAssignedTickets, useTickets } from '../../hooks/useTickets.ts'
import type { User } from '../../lib/types.ts'
import { palette } from '../../theme/palette.ts'

export function AgentDashboard({ me }: { me: User }) {
  const assigned = useAssignedTickets({ limit: 100 })
  const all = useTickets({ limit: 100 })

  const assignedItems = assigned.data ?? []
  const allItems = all.data ?? []

  const stats = useMemo(() => {
    const active = assignedItems.filter(
      (t) => t.status === 'OPEN' || t.status === 'IN_PROGRESS',
    ).length
    const unassigned = allItems.filter((t) => !t.assignee_user_id).length
    return { active, unassigned }
  }, [assignedItems, allItems])

  const firstName = me.full_name.split(' ')[0] || me.full_name

  return (
    <>
      <PageHeader
        title={`Good to see you, ${firstName}`}
        description='Your assigned workload and the shared ticket queue.'
        actions={
          <Button asChild size='sm' variant='outline' borderColor={palette.border}>
            <Link to='/queue'>Open queue</Link>
          </Button>
        }
      />

      <SimpleGrid columns={{ base: 1, sm: 3 }} gap='4' mb='8'>
        <StatTile
          label='Assigned to you'
          value={assigned.isPending ? '—' : assignedItems.length}
          icon={Inbox}
        />
        <StatTile
          label='Active (open or in progress)'
          value={assigned.isPending ? '—' : stats.active}
        />
        <StatTile
          label='Unassigned in queue'
          value={all.isPending ? '—' : stats.unassigned}
          icon={Layers}
        />
      </SimpleGrid>

      <Stack gap='4'>
        <SectionHeader
          title='Recent assignments'
          description='The latest tickets assigned to you.'
          actions={
            <Button asChild size='xs' variant='outline' borderColor={palette.border}>
              <Link to='/queue'>View queue</Link>
            </Button>
          }
        />
        <TicketListPanel
          tickets={assignedItems.slice(0, 5)}
          isLoading={assigned.isPending}
          isError={assigned.isError}
          error={assigned.error}
          onRetry={() => void assigned.refetch()}
          emptyIcon={Inbox}
          emptyTitle='No tickets assigned to you'
          emptyDescription='Pick up a ticket from the shared queue to get started.'
          emptyAction={
            <Button asChild size='sm' variant='outline' borderColor={palette.border}>
              <Link to='/queue'>Open queue</Link>
            </Button>
          }
          showRequester
        />
      </Stack>
    </>
  )
}
