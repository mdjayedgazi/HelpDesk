import { Box, Button, Flex, SimpleGrid, Stack, Text } from '@chakra-ui/react'
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Clock,
  Inbox,
  Layers,
  Minus,
  ShieldQuestion,
  Ticket as TicketIcon,
  UserCheck,
  Users,
} from 'lucide-react'
import { useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { PageHeader } from '../../components/PageHeader.tsx'
import { AttentionList, WorkloadList } from '../../components/dashboard/AttentionList.tsx'
import { BarChart } from '../../components/charts/BarChart.tsx'
import { ChartCard, ChartEmpty, ChartLegend } from '../../components/charts/ChartCard.tsx'
import { DonutChart } from '../../components/charts/DonutChart.tsx'
import { Sparkline } from '../../components/charts/Sparkline.tsx'
import { TrendChart } from '../../components/charts/TrendChart.tsx'
import { MetricCard } from '../../components/MetricCard.tsx'
import { Surface } from '../../components/Surface.tsx'
import { ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { useSupportAnalytics } from '../../hooks/useAdmin.ts'
import {
  assignmentCoverage,
  attentionItems,
  compareHalves,
  openShare,
  resolutionShare,
  shortDayLabel,
} from '../../lib/analytics.ts'
import { errorMessage } from '../../lib/errors.ts'
import {
  priorityLabels,
  statusLabels,
  ticketCategoryLabels,
} from '../../lib/format.ts'
import {
  TICKET_CATEGORIES,
  TICKET_PRIORITIES,
  TICKET_STATUSES,
} from '../../lib/types.ts'
import { palette } from '../../theme/palette.ts'
import { priorityTone, statusTone, tones } from '../../theme/statusTone.ts'

/**
 * Owner / administrator dashboard.
 *
 * This is the support-operations command centre. Every widget is fed by the
 * aggregate analytics endpoint (real rows, read-only) and answers one question:
 *
 * 1. How big is the operation right now?        → headline metrics
 * 2. Is work arriving faster than it is closed? → volume trend
 * 3. Where is work sitting?                     → status composition
 * 4. What pressure is building?                 → priority + categories
 * 5. What needs a human today?                  → attention strip
 * 6. Who is carrying the load?                  → team workload
 *
 * The owner view adds organisation-level shortcuts on top of the same data;
 * neither view exposes anything the API did not return.
 */
export function AdminDashboard({ variant = 'admin' }: { variant?: 'admin' | 'owner' }) {
  const analytics = useSupportAnalytics()
  const navigate = useNavigate()

  const derived = useMemo(() => {
    if (!analytics.data) return null
    return {
      attention: attentionItems(analytics.data),
      createdTrend: compareHalves(analytics.data.daily, 'created'),
      resolvedTrend: compareHalves(analytics.data.daily, 'resolved'),
      resolutionShare: resolutionShare(analytics.data),
      openShare: openShare(analytics.data),
      coverage: assignmentCoverage(analytics.data),
      createdSeries: analytics.data.daily.map((point) => point.created),
      resolvedSeries: analytics.data.daily.map((point) => point.resolved),
    }
  }, [analytics.data])

  if (analytics.isPending) return <DashboardSkeleton />
  if (analytics.isError || !analytics.data || !derived) {
    return (
      <ErrorState
        title='Could not load dashboard'
        description={analytics.error ? errorMessage(analytics.error) : undefined}
        onRetry={() => void analytics.refetch()}
      />
    )
  }

  const data = analytics.data
  const { totals } = data
  const attention = derived.attention

  const statusSlices = TICKET_STATUSES.map((status) => ({
    key: status,
    label: statusLabels[status],
    value: data.tickets_by_status[status] ?? 0,
    color: tones[statusTone[status]].solid,
  }))

  const priorityBars = TICKET_PRIORITIES.map((priority) => ({
    key: priority,
    label: priorityLabels[priority],
    value: data.tickets_by_priority[priority] ?? 0,
    color: tones[priorityTone[priority]].solid,
  }))

  const categoryBars = TICKET_CATEGORIES.map((category) => ({
    key: category,
    label: ticketCategoryLabels[category],
    value: data.tickets_by_category[category] ?? 0,
    color: palette.chart[1],
  }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value)

  const trendPoints = data.daily.map((point) => ({
    label: shortDayLabel(point.day),
    values: { created: point.created, resolved: point.resolved },
  }))

  const trendSeries = [
    {
      key: 'created',
      label: 'Created',
      color: palette.chart[0],
      fill: palette.chartSoft[0],
    },
    {
      key: 'resolved',
      label: 'Resolved',
      color: palette.chart[2],
      fill: palette.chartSoft[2],
    },
  ]

  const hasTrendData = data.daily.some(
    (point) => point.created > 0 || point.resolved > 0,
  )

  const openDetail =
    derived.openShare !== null
      ? `${derived.openShare}% of all tickets are open or in progress`
      : 'No tickets yet'

  return (
    <>
      <PageHeader
        title={variant === 'owner' ? 'Owner overview' : 'Support operations'}
        description={
          variant === 'owner'
            ? 'Organisation-wide support health, workload and the decisions waiting on you.'
            : 'Live support metrics, workload and the queues that need attention today.'
        }
        actions={
          <>
            <Button asChild size='sm' variant='outline' borderColor={palette.border}>
              <Link to='/tickets'>
                View tickets
                <ArrowRight size={14} aria-hidden />
              </Link>
            </Button>
            <Button asChild size='sm' variant='outline' borderColor={palette.border}>
              <Link to='/account-requests'>
                <ShieldQuestion size={14} aria-hidden />
                Account requests
              </Link>
            </Button>
            {variant === 'owner' ? (
              <Button asChild size='sm' variant='outline' borderColor={palette.border}>
                <Link to='/messages'>Owner inbox</Link>
              </Button>
            ) : null}
          </>
        }
      />

      {/* Headline metrics ------------------------------------------------- */}
      <SimpleGrid columns={{ base: 2, lg: 5 }} gap='3' mb='6'>
        <MetricCard
          label='Total tickets'
          value={totals.total_tickets}
          icon={TicketIcon}
          hint={`Across ${totals.active_agents} active ${
            totals.active_agents === 1 ? 'agent' : 'agents'
          }`}
          to='/tickets'
        />
        <MetricCard
          label='Open'
          value={totals.open_tickets}
          icon={Inbox}
          tone='info'
          hint={openDetail}
          to='/tickets?status=OPEN'
        />
        <MetricCard
          label='Waiting on customer'
          value={data.answered_without_resolution}
          icon={Clock}
          tone='warning'
          hint='Replied, blocked on a response'
          to='/tickets?status=WAITING_ON_CUSTOMER'
        />
        <MetricCard
          label='Resolved'
          value={totals.resolved_tickets}
          icon={Layers}
          tone='success'
          hint={
            derived.resolutionShare !== null
              ? `${derived.resolutionShare}% of finished tickets`
              : 'No finished tickets yet'
          }
          to='/tickets?status=RESOLVED'
        />
        <MetricCard
          label='Unassigned'
          value={totals.unassigned_tickets}
          icon={Users}
          tone={totals.unassigned_tickets > 0 ? 'warning' : 'neutral'}
          hint={
            data.unassigned_over_24h > 0
              ? `${data.unassigned_over_24h} older than 24h`
              : derived.coverage !== null
                ? `${derived.coverage}% of active work is assigned`
                : 'Nothing unassigned'
          }
          to='/tickets?assignee=none'
        />
      </SimpleGrid>

      {/* Trend + attention ------------------------------------------------ */}
      <SimpleGrid columns={{ base: 1, xl: 3 }} gap='4' mb='4' alignItems='start'>
        <Box gridColumn={{ xl: 'span 2' }} minW='0'>
          <ChartCard
            title='Ticket volume'
            question={`Created vs resolved over the last ${data.window_days} days`}
            legend={
              <Flex justify='space-between' gap='4' wrap='wrap' align='center'>
                <ChartLegend
                  items={[
                    { label: 'Created', color: palette.chart[0] },
                    { label: 'Resolved', color: palette.chart[2] },
                  ]}
                />
                <Flex gap='4' wrap='wrap'>
                  <TrendDelta label='Created' comparison={derived.createdTrend} />
                  <TrendDelta label='Resolved' comparison={derived.resolvedTrend} />
                </Flex>
              </Flex>
            }
          >
            {hasTrendData ? (
              <TrendChart
                points={trendPoints}
                series={trendSeries}
                ariaLabel={`Ticket volume over the last ${data.window_days} days`}
                valueLabels={['Created', 'Resolved']}
              />
            ) : (
              <ChartEmpty
                title='No ticket activity in this window'
                description='New and resolved tickets will appear here as they are processed.'
              />
            )}
          </ChartCard>
        </Box>

        <Stack gap='4' minW='0'>
          <AttentionList items={attention} />
          <SimpleGrid columns={2} gap='3'>
            <MetricCard
              label='Aging tickets'
              value={data.aging_over_7_days}
              tone={data.aging_over_7_days > 0 ? 'warning' : 'neutral'}
              hint='No update for 7+ days'
            />
            <MetricCard
              label='Active agents'
              value={totals.active_agents}
              icon={UserCheck}
              hint={`${totals.active_admins} admins`}
            />
          </SimpleGrid>
        </Stack>
      </SimpleGrid>

      {/* Composition ------------------------------------------------------ */}
      <SimpleGrid columns={{ base: 1, lg: 3 }} gap='4' mb='4' alignItems='start'>
        <ChartCard
          title='Status composition'
          question='Where every ticket currently sits'
          legend={
            <Flex align='center' gap='2'>
              <Sparkline
                values={derived.createdSeries}
                color={palette.chart[0]}
                label='Daily created tickets'
              />
              <Text fontSize='2xs' color={palette.textFaint}>
                {data.window_days}-day arrival trend
              </Text>
            </Flex>
          }
        >
          <DonutChart
            slices={statusSlices}
            centerLabel='tickets'
            totalLabel='tickets'
            ariaLabel='Tickets by status'
            onSelect={(slice) =>
              navigate(`/tickets?status=${slice.key}`)
            }
          />
        </ChartCard>

        <ChartCard title='Priority mix' question='How urgent the open workload is'>
          <BarChart
            items={priorityBars}
            ariaLabel='Tickets by priority'
            onSelect={(item) => navigate(`/tickets?priority=${item.key}`)}
          />
        </ChartCard>

        <ChartCard title='Where requests come from' question='Ticket categories by volume'>
          {categoryBars.length > 0 ? (
            <BarChart
              items={categoryBars}
              ariaLabel='Tickets by category'
            />
          ) : (
            <ChartEmpty title='No categorised tickets yet' />
          )}
        </ChartCard>
      </SimpleGrid>

      {/* Team -------------------------------------------------------------- */}
      <SimpleGrid columns={{ base: 1, lg: 2 }} gap='4' alignItems='start'>
        <Surface p={{ base: '4', md: '5' }}>
          <Stack gap='4'>
            <Flex align='flex-start' justify='space-between' gap='3' wrap='wrap'>
              <Box>
                <Text fontSize='sm' fontWeight='semibold' color={palette.text}>
                  Team workload
                </Text>
                <Text fontSize='xs' color={palette.textMuted} mt='0.5'>
                  Live assigned work, ordered by current load
                </Text>
              </Box>
              <Button asChild size='xs' variant='outline' borderColor={palette.border}>
                <Link to='/admin/users?role=agent'>Manage users</Link>
              </Button>
            </Flex>
            <WorkloadList entries={data.agent_workload} />
            <Text fontSize='2xs' color={palette.textFaint}>
              Load reflects active tickets right now. Resolution counts are shown for
              context, not as a performance ranking.
            </Text>
          </Stack>
        </Surface>

        <Surface p={{ base: '4', md: '5' }}>
          <Stack gap='4'>
            <Box>
              <Text fontSize='sm' fontWeight='semibold' color={palette.text}>
                Queue snapshot
              </Text>
              <Text fontSize='xs' color={palette.textMuted} mt='0.5'>
                A quick read of the operation right now
              </Text>
            </Box>
            <SimpleGrid columns={2} gap='3'>
              <SnapshotRow
                label='Open'
                value={data.tickets_by_status.OPEN ?? 0}
                tone={statusTone.OPEN}
                to='/tickets?status=OPEN'
              />
              <SnapshotRow
                label='In progress'
                value={data.tickets_by_status.IN_PROGRESS ?? 0}
                tone={statusTone.IN_PROGRESS}
                to='/tickets?status=IN_PROGRESS'
              />
              <SnapshotRow
                label='Waiting'
                value={data.tickets_by_status.WAITING_ON_CUSTOMER ?? 0}
                tone={statusTone.WAITING_ON_CUSTOMER}
                to='/tickets?status=WAITING_ON_CUSTOMER'
              />
              <SnapshotRow
                label='Resolved'
                value={data.tickets_by_status.RESOLVED ?? 0}
                tone={statusTone.RESOLVED}
                to='/tickets?status=RESOLVED'
              />
              <SnapshotRow
                label='Closed'
                value={data.tickets_by_status.CLOSED ?? 0}
                tone={statusTone.CLOSED}
                to='/tickets?status=CLOSED'
              />
              <SnapshotRow
                label='Urgent open'
                value={totals.urgent_open_tickets}
                tone='danger'
                to='/tickets?priority=URGENT'
              />
            </SimpleGrid>
            <Text fontSize='2xs' color={palette.textFaint}>
              Updates when a ticket changes status. Metrics are computed from live
              ticket rows — no SLA targets are configured, so none are shown.
            </Text>
          </Stack>
        </Surface>
      </SimpleGrid>
    </>
  )
}

function TrendDelta({
  label,
  comparison,
}: {
  label: string
  comparison: ReturnType<typeof compareHalves>
}) {
  if (!comparison) return null
  const Icon =
    comparison.direction === 'up'
      ? ArrowUpRight
      : comparison.direction === 'down'
        ? ArrowDownRight
        : Minus
  const color =
    comparison.direction === 'up'
      ? tones.info.solid
      : comparison.direction === 'down'
        ? tones.warning.solid
        : palette.textMuted
  return (
    <Flex align='center' gap='1.5' title={`${label}: last half vs previous half of the window`}>
      <Text fontSize='2xs' color={palette.textMuted}>
        {label}
      </Text>
      <Flex align='center' gap='1' color={color}>
        <Icon size={12} strokeWidth={2.2} aria-hidden />
        <Text fontSize='2xs' fontWeight='semibold' fontVariantNumeric='tabular-nums'>
          {comparison.changePercent === null
            ? 'new'
            : `${comparison.changePercent > 0 ? '+' : ''}${comparison.changePercent}%`}
        </Text>
      </Flex>
    </Flex>
  )
}

function SnapshotRow({
  label,
  value,
  tone,
  to,
}: {
  label: string
  value: number
  tone: keyof typeof tones
  to: string
}) {
  return (
    <Flex
      asChild
      direction='column'
      gap='1'
      p='3'
      borderWidth='1px'
      borderColor={palette.border}
      borderRadius='l2'
      textDecoration='none'
      transition='background var(--hd-dur-1) var(--hd-ease), border-color var(--hd-dur-1) var(--hd-ease)'
      _hover={{ bg: palette.hover, borderColor: palette.borderStrong }}
      _focusVisible={{ outline: '2px solid', outlineColor: palette.focus, outlineOffset: '2px' }}
    >
      <Link to={to}>
        <Flex align='center' gap='1.5'>
          <Box boxSize='1.5' borderRadius='full' bg={tones[tone].solid} aria-hidden />
          <Text fontSize='2xs' color={palette.textMuted} truncate>
            {label}
          </Text>
        </Flex>
        <Text
          fontSize='lg'
          fontWeight='semibold'
          color={palette.text}
          fontVariantNumeric='tabular-nums'
          lineHeight='1.1'
        >
          {value}
        </Text>
      </Link>
    </Flex>
  )
}

function DashboardSkeleton() {
  return (
    <>
      <PageHeader title='Support operations' description='Loading live metrics…' />
      <LoadingState label='Loading support analytics…' minHeight='30vh' />
    </>
  )
}
