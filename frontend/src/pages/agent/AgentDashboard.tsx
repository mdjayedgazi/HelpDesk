import { Button, Flex, SimpleGrid, Stack, Text } from '@chakra-ui/react'
import { ArrowRight, Clock, Flame, Inbox, Layers } from 'lucide-react'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'

import { PageHeader } from '../../components/PageHeader.tsx'
import { BarChart } from '../../components/charts/BarChart.tsx'
import { ChartCard, ChartEmpty } from '../../components/charts/ChartCard.tsx'
import { DonutChart } from '../../components/charts/DonutChart.tsx'
import { MetricCard } from '../../components/MetricCard.tsx'
import { SectionHeader } from '../../components/Surface.tsx'
import { TicketListPanel } from '../../components/TicketListPanel.tsx'
import { useAssignedTickets, useTickets } from '../../hooks/useTickets.ts'
import type { Ticket, User } from '../../lib/types.ts'
import { TICKET_PRIORITIES, TICKET_STATUSES } from '../../lib/types.ts'
import { priorityLabels, statusLabels } from '../../lib/format.ts'
import { palette } from '../../theme/palette.ts'
import { priorityTone, statusTone, tones } from '../../theme/statusTone.ts'

/**
 * Agent dashboard.
 *
 * The agent's question is narrow and personal: *what should I work on next?*
 * So the page leads with the agent's own queue, surfaces urgent work first, and
 * uses the shared queue only as context ("is there anything waiting to be
 * claimed?"). It does not show organisation-wide analytics the agent has no
 * permission to see.
 */
export function AgentDashboard({ me }: { me: User }) {
  const assigned = useAssignedTickets({ limit: 100 })
  const queue = useTickets({ limit: 100 })

  const assignedItems = useMemo(() => assigned.data ?? [], [assigned.data])
  const queueItems = useMemo(() => queue.data ?? [], [queue.data])

  const stats = useMemo(() => {
    const active = assignedItems.filter(
      (ticket) => ticket.status === 'OPEN' || ticket.status === 'IN_PROGRESS',
    )
    const urgent = assignedItems.filter(
      (ticket) =>
        ticket.priority === 'URGENT' &&
        ['OPEN', 'IN_PROGRESS'].includes(ticket.status),
    )
    const waiting = assignedItems.filter(
      (ticket) => ticket.status === 'WAITING_ON_CUSTOMER',
    )
    const resolved = assignedItems.filter(
      (ticket) => ticket.status === 'RESOLVED' || ticket.status === 'CLOSED',
    )
    const unassigned = queueItems.filter((ticket) => !ticket.assignee_user_id)

    const byStatus = Object.fromEntries(
      TICKET_STATUSES.map((status) => [
        status,
        assignedItems.filter((ticket) => ticket.status === status).length,
      ]),
    ) as Record<(typeof TICKET_STATUSES)[number], number>

    const byPriority = Object.fromEntries(
      TICKET_PRIORITIES.map((priority) => [
        priority,
        assignedItems.filter((ticket) => ticket.priority === priority).length,
      ]),
    ) as Record<(typeof TICKET_PRIORITIES)[number], number>

    // The worklist: urgent first, then active, then everything else.
    const priorityRank = (ticket: Ticket) =>
      ticket.priority === 'URGENT'
        ? 0
        : ticket.status === 'OPEN' || ticket.status === 'IN_PROGRESS'
          ? 1
          : 2
    const worklist = [...assignedItems]
      .sort((a, b) => priorityRank(a) - priorityRank(b))
      .slice(0, 6)

    return { active, urgent, waiting, resolved, unassigned, byStatus, byPriority, worklist }
  }, [assignedItems, queueItems])

  const firstName = me.full_name.split(' ')[0] || me.full_name
  const loading = assigned.isPending || queue.isPending

  const statusSlices = TICKET_STATUSES.map((status) => ({
    key: status,
    label: statusLabels[status],
    value: stats.byStatus[status] ?? 0,
    color: tones[statusTone[status]].solid,
  })).filter((slice) => slice.value > 0)

  const priorityBars = TICKET_PRIORITIES.map((priority) => ({
    key: priority,
    label: priorityLabels[priority],
    value: stats.byPriority[priority] ?? 0,
    color: tones[priorityTone[priority]].solid,
  }))

  return (
    <>
      <PageHeader
        title={`Good to see you, ${firstName}`}
        description='Your assigned workload, and the shared queue waiting to be claimed.'
        actions={
          <>
            <Button asChild size='sm' bg={palette.ink} color={palette.textOnInk} _hover={{ bg: palette.inkHover }}>
              <Link to='/queue'>
                <Inbox size={14} aria-hidden />
                Open queue
              </Link>
            </Button>
            <Button asChild size='sm' variant='outline' borderColor={palette.border}>
              <Link to='/tickets'>All tickets</Link>
            </Button>
          </>
        }
      />

      <SimpleGrid columns={{ base: 2, lg: 4 }} gap='3' mb='6'>
        <MetricCard
          label='Assigned to you'
          value={loading ? '—' : assignedItems.length}
          icon={Inbox}
          hint={`${stats.active.length} still active`}
        />
        <MetricCard
          label='Urgent, still active'
          value={loading ? '—' : stats.urgent.length}
          icon={Flame}
          tone={!loading && stats.urgent.length > 0 ? 'danger' : 'neutral'}
          hint={!loading && stats.urgent.length > 0 ? 'Handle these first' : 'Nothing urgent'}
        />
        <MetricCard
          label='Waiting on customer'
          value={loading ? '—' : stats.waiting.length}
          icon={Clock}
          tone={!loading && stats.waiting.length > 0 ? 'warning' : 'neutral'}
          hint='Blocked on a reply'
        />
        <MetricCard
          label='Unassigned in queue'
          value={loading ? '—' : stats.unassigned.length}
          icon={Layers}
          tone={!loading && stats.unassigned.length > 0 ? 'info' : 'neutral'}
          hint='Ready to claim'
          to='/queue'
        />
      </SimpleGrid>

      <SimpleGrid columns={{ base: 1, xl: 3 }} gap='4' mb='6' alignItems='start'>
        <Stack gap='4' gridColumn={{ xl: 'span 2' }} minW='0'>
          <SectionHeader
            title='Work on this next'
            description='Urgent first, then active work, then the rest of your queue.'
            actions={
              <Button asChild size='xs' variant='outline' borderColor={palette.border}>
                <Link to='/queue'>
                  Full queue
                  <ArrowRight size={12} aria-hidden />
                </Link>
              </Button>
            }
          />
          <TicketListPanel
            tickets={stats.worklist}
            isLoading={assigned.isPending}
            isError={assigned.isError}
            error={assigned.error}
            onRetry={() => void assigned.refetch()}
            emptyIcon={Inbox}
            emptyTitle='Nothing assigned to you'
            emptyDescription='Pick up a ticket from the shared queue to get started.'
            emptyAction={
              <Button asChild size='sm' variant='outline' borderColor={palette.border}>
                <Link to='/queue'>Open queue</Link>
              </Button>
            }
            showRequester
            showAssignee
          />
        </Stack>

        <Stack gap='4' minW='0'>
          <ChartCard title='Your status mix' question='How your assigned tickets are split'>
            {statusSlices.length > 0 ? (
              <DonutChart
                slices={statusSlices}
                centerLabel='assigned'
                ariaLabel='Your tickets by status'
              />
            ) : (
              <ChartEmpty
                title='No assigned tickets yet'
                description='Claim a ticket from the queue to start building your workload.'
              />
            )}
          </ChartCard>

          <ChartCard title='Priority pressure' question='The urgency of the work on your plate'>
            <BarChart items={priorityBars} ariaLabel='Your tickets by priority' />
            {stats.urgent.length > 0 ? (
              <Text fontSize='2xs' color={palette.semantic.danger} mt='3'>
                {stats.urgent.length} urgent {stats.urgent.length === 1 ? 'ticket is' : 'tickets are'}{' '}
                still active.
              </Text>
            ) : null}
          </ChartCard>
        </Stack>
      </SimpleGrid>

      <Flex
        align='center'
        justify='space-between'
        gap='3'
        wrap='wrap'
        px='4'
        py='3'
        borderWidth='1px'
        borderColor={palette.border}
        borderRadius='l3'
        bg={palette.surface}
      >
        <Flex align='center' gap='2.5' minW='0'>
          <Inbox size={15} color={palette.textMuted} aria-hidden />
          <Text fontSize='xs' color={palette.textSecondary}>
            {loading
              ? 'Checking the shared queue…'
              : stats.unassigned.length > 0
                ? `${stats.unassigned.length} unassigned ${
                    stats.unassigned.length === 1 ? 'ticket is' : 'tickets are'
                  } waiting to be claimed.`
                : 'The shared unassigned queue is clear.'}
          </Text>
        </Flex>
        <Button asChild size='xs' variant='outline' borderColor={palette.border}>
          <Link to='/queue'>Open queue</Link>
        </Button>
      </Flex>
    </>
  )
}
