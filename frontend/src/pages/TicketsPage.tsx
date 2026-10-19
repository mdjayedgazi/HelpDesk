import { Button, Flex, NativeSelect } from '@chakra-ui/react'
import { Inbox, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { PageHeader } from '../components/PageHeader.tsx'
import { TicketFilterBar } from '../components/TicketFilterBar.tsx'
import { TicketListPanel } from '../components/TicketListPanel.tsx'
import { useMe } from '../hooks/useMe.ts'
import { useAgents } from '../hooks/useAdmin.ts'
import { useTickets } from '../hooks/useTickets.ts'
import { useDebounced } from '../hooks/useDebounced.ts'
import type { TicketListParams, TicketStatus, TicketPriority } from '../lib/types.ts'
import { isAdmin, isStaff } from '../lib/roles.ts'
import { palette } from '../theme/palette.ts'

const PAGE_SIZE = 20

export function TicketsPage() {
  const me = useMe()
  const role = me.data?.role ?? 'customer'
  const staff = isStaff(role)
  const admin = isAdmin(role)

  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<TicketStatus | ''>('')
  const [priority, setPriority] = useState<TicketPriority | ''>('')
  const [assignee, setAssignee] = useState('')

  const debouncedSearch = useDebounced(search)

  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, status, priority, assignee])

  const params: TicketListParams = {
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    q: debouncedSearch || undefined,
    status: status || undefined,
    priority: priority || undefined,
    assignee_user_id: assignee || undefined,
  }

  const tickets = useTickets(params)
  const agents = useAgents(admin)

  const items = tickets.data ?? []

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

      <Flex mb='5'>
        <TicketFilterBar
          search={search}
          onSearchChange={setSearch}
          status={status}
          onStatusChange={setStatus}
          priority={priority}
          onPriorityChange={setPriority}
          extra={
            admin ? (
              <NativeSelect.Root size='sm' width='auto' minW='44'>
                <NativeSelect.Field
                  value={assignee}
                  onChange={(event) => setAssignee(event.target.value)}
                  aria-label='Filter by assignee'
                  bg={palette.surface}
                  borderColor={palette.border}
                  borderRadius='l2'
                  fontSize='sm'
                  height='9'
                >
                  <option value=''>All assignees</option>
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
      </Flex>

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
