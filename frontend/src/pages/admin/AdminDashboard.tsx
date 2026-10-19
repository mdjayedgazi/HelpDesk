import { Button, SimpleGrid, Stack, Text } from '@chakra-ui/react'
import { Inbox, Layers, Ticket as TicketIcon, UserCheck, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import { PageHeader } from '../../components/PageHeader.tsx'
import { Surface } from '../../components/Surface.tsx'
import { BreakdownBar, StatTile } from '../../components/StatTile.tsx'
import { ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { useAdminDashboard } from '../../hooks/useAdmin.ts'
import { priorityLabels, statusLabels } from '../../lib/format.ts'
import { TICKET_PRIORITIES, TICKET_STATUSES } from '../../lib/types.ts'
import { errorMessage } from '../../lib/errors.ts'
import { palette } from '../../theme/palette.ts'

export function AdminDashboard({ variant = 'admin' }: { variant?: 'admin' | 'owner' }) {
  const dashboard = useAdminDashboard()

  if (dashboard.isPending) return <LoadingState label='Loading system metrics…' />
  if (dashboard.isError || !dashboard.data) {
    return (
      <ErrorState
        title='Could not load dashboard'
        description={dashboard.error ? errorMessage(dashboard.error) : undefined}
        onRetry={() => void dashboard.refetch()}
      />
    )
  }

  const data = dashboard.data
  const maxStatus = Math.max(1, ...TICKET_STATUSES.map((s) => data.tickets_by_status[s] ?? 0))
  const maxPriority = Math.max(1, ...TICKET_PRIORITIES.map((p) => data.tickets_by_priority[p] ?? 0))

  return (
    <>
      <PageHeader
        title={variant === 'owner' ? 'Owner overview' : 'Admin overview'}
        description={
          variant === 'owner'
            ? 'Organization-wide metrics, the private Owner inbox, and account decisions awaiting your review.'
            : 'Live system metrics aggregated from all tickets and accounts.'
        }
        actions={
          <>
            {variant === 'owner' ? (
              <Button asChild size='sm' variant='outline' borderColor={palette.border}>
                <Link to='/messages'>Owner inbox</Link>
              </Button>
            ) : (
              <Button asChild size='sm' variant='outline' borderColor={palette.border}>
                <Link to='/tickets'>View tickets</Link>
              </Button>
            )}
            <Button asChild size='sm' variant='outline' borderColor={palette.border}>
              <Link to='/account-requests'>Account requests</Link>
            </Button>
            <Button asChild size='sm' variant='outline' borderColor={palette.border}>
              <Link to='/admin/users'>Manage users</Link>
            </Button>
          </>
        }
      />

      <SimpleGrid columns={{ base: 2, lg: 5 }} gap='4' mb='8'>
        <StatTile label='Total tickets' value={data.total_tickets} icon={TicketIcon} />
        <StatTile label='Open' value={data.tickets_by_status.OPEN ?? 0} icon={Inbox} />
        <StatTile label='Resolved' value={data.tickets_by_status.RESOLVED ?? 0} icon={Layers} />
        <StatTile label='Total users' value={data.total_users} icon={Users} />
        <StatTile label='Active agents' value={data.active_agents} icon={UserCheck} />
      </SimpleGrid>

      <SimpleGrid columns={{ base: 1, lg: 2 }} gap='6' alignItems='start'>
        <Surface p={{ base: '5', md: '6' }}>
          <Stack gap='5'>
            <Text fontSize='sm' fontWeight='medium' color={palette.text}>
              Tickets by status
            </Text>
            <Stack gap='4'>
              {TICKET_STATUSES.map((status) => (
                <BreakdownBar
                  key={status}
                  label={statusLabels[status]}
                  value={data.tickets_by_status[status] ?? 0}
                  max={maxStatus}
                />
              ))}
            </Stack>
          </Stack>
        </Surface>

        <Surface p={{ base: '5', md: '6' }}>
          <Stack gap='5'>
            <Text fontSize='sm' fontWeight='medium' color={palette.text}>
              Tickets by priority
            </Text>
            <Stack gap='4'>
              {TICKET_PRIORITIES.map((priority) => (
                <BreakdownBar
                  key={priority}
                  label={priorityLabels[priority]}
                  value={data.tickets_by_priority[priority] ?? 0}
                  max={maxPriority}
                />
              ))}
            </Stack>
          </Stack>
        </Surface>
      </SimpleGrid>
    </>
  )
}
