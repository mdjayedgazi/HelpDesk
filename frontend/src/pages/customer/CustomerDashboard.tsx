import { Button, Flex, SimpleGrid, Stack, Text } from '@chakra-ui/react'
import { CheckCircle2, Clock, Inbox, MessageSquare, Plus, Ticket as TicketIcon } from 'lucide-react'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'

import { PageHeader } from '../../components/PageHeader.tsx'
import { BarChart } from '../../components/charts/BarChart.tsx'
import { ChartCard, ChartEmpty } from '../../components/charts/ChartCard.tsx'
import { DonutChart } from '../../components/charts/DonutChart.tsx'
import { MetricCard } from '../../components/MetricCard.tsx'
import { SectionHeader, Surface } from '../../components/Surface.tsx'
import { TicketListPanel } from '../../components/TicketListPanel.tsx'
import { useTickets } from '../../hooks/useTickets.ts'
import { statusLabels } from '../../lib/format.ts'
import { TICKET_STATUSES, type User } from '../../lib/types.ts'
import { palette } from '../../theme/palette.ts'
import { statusTone, tones } from '../../theme/statusTone.ts'

/**
 * Customer dashboard.
 *
 * The customer only needs to know three things: what is open, what is waiting
 * on them, and what has been resolved. The page therefore leads with those
 * counts (each linking to the filtered list) and keeps a single visual
 * composition of their own tickets — never organisation-wide data.
 */
export function CustomerDashboard({ me }: { me: User }) {
  const tickets = useTickets({ limit: 100 })
  const items = useMemo(() => tickets.data ?? [], [tickets.data])

  const counts = useMemo(() => {
    const open = items.filter((t) => t.status === 'OPEN').length
    const inProgress = items.filter((t) => t.status === 'IN_PROGRESS').length
    const waiting = items.filter((t) => t.status === 'WAITING_ON_CUSTOMER').length
    const resolved = items.filter(
      (t) => t.status === 'RESOLVED' || t.status === 'CLOSED',
    ).length
    const byStatus = Object.fromEntries(
      TICKET_STATUSES.map((status) => [
        status,
        items.filter((ticket) => ticket.status === status).length,
      ]),
    ) as Record<(typeof TICKET_STATUSES)[number], number>
    return { open, inProgress, waiting, resolved, byStatus }
  }, [items])

  const firstName = me.full_name.split(' ')[0] || me.full_name
  const loading = tickets.isPending

  const statusSlices = TICKET_STATUSES.map((status) => ({
    key: status,
    label: statusLabels[status],
    value: counts.byStatus[status] ?? 0,
    color: tones[statusTone[status]].solid,
  })).filter((slice) => slice.value > 0)

  const recent = items.slice(0, 6)

  return (
    <>
      <PageHeader
        title={`Welcome back, ${firstName}`}
        description='Raise a new request, follow progress, and reply where the team needs you.'
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

      <SimpleGrid columns={{ base: 2, lg: 4 }} gap='3' mb='6'>
        <MetricCard
          delay={0}
          label='Total tickets'
          value={loading ? '—' : items.length}
          icon={TicketIcon}
          hint='Everything you have raised'
          to='/tickets'
        />
        <MetricCard
          delay={70}
          label='Open & in progress'
          value={loading ? '—' : counts.open + counts.inProgress}
          icon={Inbox}
          tone='info'
          hint={counts.inProgress > 0 ? `${counts.inProgress} in progress` : 'Being reviewed'}
          to='/tickets'
          ariaLabel={`Open and in progress: ${counts.open + counts.inProgress}`}
        />
        <MetricCard
          delay={140}
          label='Waiting on you'
          value={loading ? '—' : counts.waiting}
          icon={MessageSquare}
          tone={counts.waiting > 0 ? 'warning' : 'neutral'}
          hint={counts.waiting > 0 ? 'The team is waiting for your response' : 'Nothing needs a reply'}
          to='/tickets?status=WAITING_ON_CUSTOMER'
        />
        <MetricCard
          delay={210}
          label='Resolved'
          value={loading ? '—' : counts.resolved}
          icon={CheckCircle2}
          tone='success'
          hint='Completed requests'
          to='/tickets?status=RESOLVED'
        />
      </SimpleGrid>

      <SimpleGrid columns={{ base: 1, xl: 3 }} gap='4' mb='6' alignItems='start'>
        <Stack gap='4' gridColumn={{ xl: 'span 2' }} minW='0'>
          <SectionHeader
            title='Recent tickets'
            description='Your latest requests and their current status.'
            actions={
              <Button asChild size='xs' variant='outline' borderColor={palette.border}>
                <Link to='/tickets'>View all</Link>
              </Button>
            }
          />
          <TicketListPanel
            tickets={recent}
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

        <Stack gap='4' minW='0'>
          <ChartCard delay={0} title='Where your requests stand' question='A breakdown of your own tickets'>
            {statusSlices.length > 0 ? (
              <DonutChart
                slices={statusSlices}
                centerLabel='requests'
                ariaLabel='Your tickets by status'
              />
            ) : (
              <ChartEmpty
                title='No requests yet'
                description='Create a ticket and its progress will show up here.'
              />
            )}
          </ChartCard>

          {counts.waiting > 0 ? (
            <Surface p='4'>
              <Flex gap='3' align='flex-start'>
                <Flex
                  boxSize='8'
                  align='center'
                  justify='center'
                  borderRadius='full'
                  bg={tones.warning.soft}
                  color={tones.warning.solid}
                  flexShrink={0}
                >
                  <Clock size={15} strokeWidth={2} aria-hidden />
                </Flex>
                <Stack gap='1'>
                  <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                    The team is waiting on you
                  </Text>
                  <Text fontSize='xs' color={palette.textSecondary}>
                    {counts.waiting === 1
                      ? 'One ticket is set to awaiting your response — open it to continue the conversation.'
                      : `${counts.waiting} tickets are set to awaiting your response — open them to continue the conversation.`}
                  </Text>
                  <Button
                    asChild
                    size='xs'
                    variant='outline'
                    borderColor={palette.border}
                    mt='2'
                    alignSelf='flex-start'
                  >
                    <Link to='/tickets?status=WAITING_ON_CUSTOMER'>Open these tickets</Link>
                  </Button>
                </Stack>
              </Flex>
            </Surface>
          ) : null}

          {items.length > 0 ? (
            <ChartCard
              delay={70}
              title='Tickets by status'
              question='Counts across all of your requests'
            >
              <BarChart
                items={TICKET_STATUSES.map((status) => ({
                  key: status,
                  label: statusLabels[status],
                  value: counts.byStatus[status] ?? 0,
                  color: tones[statusTone[status]].solid,
                }))}
                ariaLabel='Your tickets by status'
              />
            </ChartCard>
          ) : null}
        </Stack>
      </SimpleGrid>
    </>
  )
}
