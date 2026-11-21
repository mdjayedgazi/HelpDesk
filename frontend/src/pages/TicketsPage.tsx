import { Button, Flex, NativeSelect } from '@chakra-ui/react'
import { Inbox, Plus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { PageHeader } from '../components/PageHeader.tsx'
import { TicketFilterBar } from '../components/TicketFilterBar.tsx'
import { TicketListPanel } from '../components/TicketListPanel.tsx'
import { useMe } from '../hooks/useMe.ts'
import { useAgents } from '../hooks/useAdmin.ts'
import { useTickets } from '../hooks/useTickets.ts'
import { useDebounced } from '../hooks/useDebounced.ts'
import type { TicketListParams, TicketPriority, TicketStatus } from '../lib/types.ts'
import { TICKET_PRIORITIES, TICKET_STATUSES } from '../lib/types.ts'
import { isAdmin, isStaff } from '../lib/roles.ts'
import { palette } from '../theme/palette.ts'

const PAGE_SIZE = 20

function parseStatus(value: string | null): TicketStatus | '' {
  return value && TICKET_STATUSES.includes(value as TicketStatus) ? (value as TicketStatus) : ''
}

function parsePriority(value: string | null): TicketPriority | '' {
  return value && TICKET_PRIORITIES.includes(value as TicketPriority)
    ? (value as TicketPriority)
    : ''
}

/**
 * Ticket list.
 *
 * The URL is the single source of truth for the status/priority/assignee
 * filters, so dashboard charts can deep-link to an exact filtered view and the
 * browser back/forward buttons behave correctly. Only the search box keeps local
 * state, so typing stays responsive; the debounced value is written to the URL.
 */
export function TicketsPage() {
  const me = useMe()
  const role = me.data?.role ?? 'customer'
  const staff = isStaff(role)
  const admin = isAdmin(role)

  const [searchParams, setSearchParams] = useSearchParams()
  const status = parseStatus(searchParams.get('status'))
  const priority = parsePriority(searchParams.get('priority'))
  const assignee = searchParams.get('assignee') ?? ''
  const urlSearch = searchParams.get('q') ?? ''

  const [search, setSearch] = useState(urlSearch)
  const [page, setPage] = useState(1)
  const debouncedSearch = useDebounced(search)

  // Adopt a `q` that changed outside the input (back/forward, a shared link).
  useEffect(() => {
    setSearch((current) => (current === urlSearch ? current : urlSearch))
  }, [urlSearch])

  const updateFilters = (next: {
    q?: string
    status?: TicketStatus | ''
    priority?: TicketPriority | ''
    assignee?: string
  }) => {
    const params = new URLSearchParams(searchParams)
    const write = (key: string, value: string | undefined) => {
      if (value) params.set(key, value)
      else params.delete(key)
    }
    if ('q' in next) write('q', next.q)
    if ('status' in next) write('status', next.status)
    if ('priority' in next) write('priority', next.priority)
    if ('assignee' in next) write('assignee', next.assignee)
    setSearchParams(params, { replace: true })
    setPage(1)
  }

  // Push the debounced search term into the URL (and reset paging) once it has
  // settled, so we never rewrite history on every keystroke. `setSearchParams`
  // accepts an updater, so this reads the freshest params without re-running on
  // every URL change.
  useEffect(() => {
    // Return early rather than navigating to an identical URL: `setSearchParams`
    // always pushes/replaces, so an unchanged value would cause a redundant
    // navigation on every render.
    if (debouncedSearch === (searchParams.get('q') ?? '')) return
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (debouncedSearch) next.set('q', debouncedSearch)
      else next.delete('q')
      return next
    }, { replace: true })
    setPage(1)
  }, [debouncedSearch, searchParams, setSearchParams])

  const params: TicketListParams = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
      q: debouncedSearch || undefined,
      status: status || undefined,
      priority: priority || undefined,
      // `assignee=none` is the "unassigned" deep link used by the dashboard.
      ...(assignee === 'none' ? {} : { assignee_user_id: assignee || undefined }),
    }),
    [page, debouncedSearch, status, priority, assignee],
  )

  const tickets = useTickets(params)
  const agents = useAgents(admin)

  // The backend has no "unassigned" filter, so the deep link filters the page
  // client-side. The page size is fixed, so this is an honest view of the
  // current page rather than a silent, incomplete global count.
  const items = useMemo(() => {
    const list = tickets.data ?? []
    return assignee === 'none' ? list.filter((ticket) => !ticket.assignee_user_id) : list
  }, [tickets.data, assignee])

  const hasFilters = Boolean(debouncedSearch || status || priority || assignee)

  const clearFilters = () => {
    setSearch('')
    setPage(1)
    setSearchParams(new URLSearchParams(), { replace: true })
  }

  return (
    <>
      <PageHeader
        title={staff ? 'All tickets' : 'My tickets'}
        description={
          staff
            ? 'Every ticket you can act on, with filters to help you triage quickly.'
            : 'Track the requests you have submitted and their current progress.'
        }
        actions={
          !staff ? (
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
          ) : null
        }
      />

      <Flex mb='4' wrap='wrap' gap='3' align='center'>
        <TicketFilterBar
          search={search}
          onSearchChange={setSearch}
          status={status}
          onStatusChange={(value) => updateFilters({ status: value })}
          priority={priority}
          onPriorityChange={(value) => updateFilters({ priority: value })}
          extra={
            admin ? (
              <NativeSelect.Root size='sm' width='auto' minW='44'>
                <NativeSelect.Field
                  value={assignee}
                  onChange={(event) => updateFilters({ assignee: event.target.value })}
                  aria-label='Filter by assignee'
                  bg={palette.surface}
                  borderColor={palette.border}
                  borderRadius='l2'
                  fontSize='sm'
                  height='9'
                >
                  <option value=''>All assignees</option>
                  <option value='none'>Unassigned</option>
                  {(agents.data ?? []).map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.full_name}
                    </option>
                  ))}
                </NativeSelect.Field>
                <NativeSelect.Indicator color={palette.textMuted} />
              </NativeSelect.Root>
            ) : null
          }
        />
        {hasFilters ? (
          <Button
            size='xs'
            variant='ghost'
            color={palette.textMuted}
            _hover={{ bg: palette.hover, color: palette.text }}
            onClick={clearFilters}
          >
            Clear all
          </Button>
        ) : null}
      </Flex>

      {assignee === 'none' ? (
        <Flex
          mb='4'
          px='3.5'
          py='2.5'
          borderWidth='1px'
          borderColor={palette.border}
          borderRadius='l2'
          bg={palette.surfaceMuted}
          align='center'
          gap='2'
          wrap='wrap'
        >
          <Inbox size={14} color={palette.textMuted} aria-hidden />
          <Flex as='span' fontSize='xs' color={palette.textSecondary} align='center' gap='1'>
            Showing unassigned tickets on this page. The API does not expose a
            server-side unassigned filter, so the count reflects the current page.
          </Flex>
        </Flex>
      ) : null}

      <TicketListPanel
        tickets={items}
        isLoading={tickets.isPending}
        isError={tickets.isError}
        error={tickets.error}
        onRetry={() => void tickets.refetch()}
        emptyIcon={Inbox}
        emptyTitle={staff ? 'No tickets match these filters' : 'No tickets yet'}
        emptyDescription={
          staff
            ? 'Try clearing the search or filters to see more tickets.'
            : 'Submit your first request and it will appear here.'
        }
        emptyAction={
          !staff ? (
            <Button asChild size='sm' variant='outline' borderColor={palette.border}>
              <Link to='/tickets/new'>Create a ticket</Link>
            </Button>
          ) : hasFilters ? (
            <Button size='sm' variant='outline' borderColor={palette.border} onClick={clearFilters}>
              Clear filters
            </Button>
          ) : null
        }
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
        showAssignee={staff}
        showRequester={staff}
      />
    </>
  )
}
