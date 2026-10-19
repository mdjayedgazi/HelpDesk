import { Button, SimpleGrid, Stack } from '@chakra-ui/react'
import { Inbox, Plus, Ticket as TicketIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useMemo } from 'react'

import { PageHeader } from '../../components/PageHeader.tsx'
import { SectionHeader } from '../../components/Surface.tsx'
import { StatTile } from '../../components/StatTile.tsx'
import { TicketListPanel } from '../../components/TicketListPanel.tsx'
import { useTickets } from '../../hooks/useTickets.ts'
import type { User } from '../../lib/types.ts'
import { palette } from '../../theme/palette.ts'

export function CustomerDashboard({ me }: { me: User }) {
  const tickets = useTickets({ limit: 100 })
  const items = tickets.data ?? []

  const counts = useMemo(() => {
    const open = items.filter((t) => t.status === 'OPEN').length
    const waiting = items.filter((t) => t.status === 'WAITING_ON_CUSTOMER').length
    const resolved = items.filter((t) => t.status === 'RESOLVED' || t.status === 'CLOSED').length
    return { open, waiting, resolved }
  }, [items])

  const firstName = me.full_name.split(' ')[0] || me.full_name
  const loading = tickets.isPending

  return (
    <>
      <PageHeader
        title={`Welcome back, ${firstName}`}
        description='Here is where you can raise new requests and follow their progress.'
        actions={
          <Button
            asChild
            size='sm'
            bg={palette.ink}
            color={palette.textOnInk}
            _hover={{ bg: palette.inkHover }}
          >
            <Link to='/tickets/new'>
              <Plus size={15} aria-hidden />
              New ticket
            </Link>
          </Button>
        }
      />

      <SimpleGrid columns={{ base: 2, md: 4 }} gap='4' mb='8'>
        <StatTile label='Total tickets' value={loading ? '—' : items.length} icon={TicketIcon} />
        <StatTile label='Open' value={loading ? '—' : counts.open} />
        <StatTile label='Waiting on you' value={loading ? '—' : counts.waiting} />
        <StatTile label='Resolved' value={loading ? '—' : counts.resolved} />
      </SimpleGrid>

      <Stack gap='4'>
        <SectionHeader
          title='Recent tickets'
          description='Your latest requests and their status.'
          actions={
            <Button asChild size='xs' variant='outline' borderColor={palette.border}>
              <Link to='/tickets'>View all</Link>
            </Button>
          }
        />
        <TicketListPanel
          tickets={items.slice(0, 5)}
          isLoading={loading}
          isError={tickets.isError}
          error={tickets.error}
          onRetry={() => void tickets.refetch()}
          emptyIcon={Inbox}
          emptyTitle='No tickets yet'
          emptyDescription='Submit your first request and we will take it from there.'
          emptyAction={
            <Button asChild size='sm' variant='outline' borderColor={palette.border}>
              <Link to='/tickets/new'>Create a ticket</Link>
            </Button>
          }
        />
      </Stack>
    </>
  )
}
