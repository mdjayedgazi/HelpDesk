import { Stack } from '@chakra-ui/react'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { useUserDirectory } from '../hooks/useUserDirectory.ts'
import { errorMessage } from '../lib/errors.ts'
import type { Ticket } from '../lib/types.ts'
import { EmptyState, ErrorState, TableSkeleton } from './StateViews.tsx'
import { Surface } from './Surface.tsx'
import { Pagination } from './Pagination.tsx'
import { TicketTable, TicketTableSurface } from './TicketTable.tsx'

export function TicketListPanel({
  tickets,
  isLoading,
  isError,
  error,
  onRetry,
  emptyIcon,
  emptyTitle,
  emptyDescription,
  emptyAction,
  page,
  pageSize,
  onPageChange,
  showAssignee = false,
  showRequester = false,
  renderActions,
}: {
  tickets: Ticket[]
  isLoading: boolean
  isError: boolean
  error: unknown
  onRetry: () => void
  emptyIcon?: LucideIcon
  emptyTitle: string
  emptyDescription?: string
  emptyAction?: ReactNode
  page?: number
  pageSize?: number
  onPageChange?: (page: number) => void
  showAssignee?: boolean
  showRequester?: boolean
  renderActions?: (ticket: Ticket) => ReactNode
}) {
  const directory = useUserDirectory()

  if (isLoading) {
    return (
      <Surface overflow='hidden'>
        <TableSkeleton rows={7} columns={(showAssignee ? 6 : 5) + (renderActions ? 1 : 0)} />
      </Surface>
    )
  }

  if (isError) {
    return (
      <ErrorState
        title='Could not load tickets'
        description={errorMessage(error)}
        onRetry={onRetry}
      />
    )
  }

  if (tickets.length === 0) {
    return (
      <EmptyState
        icon={emptyIcon}
        title={emptyTitle}
        description={emptyDescription}
        action={emptyAction}
      />
    )
  }

  const hasNext = typeof pageSize === 'number' ? tickets.length === pageSize : false

  return (
    <Stack gap='4'>
      <TicketTableSurface>
        <TicketTable
          tickets={tickets}
          userLabel={directory.label}
          showAssignee={showAssignee}
          showRequester={showRequester}
          renderActions={renderActions}
        />
      </TicketTableSurface>
      {page && pageSize && onPageChange ? (
        <Pagination
          page={page}
          pageSize={pageSize}
          itemCount={tickets.length}
          hasNext={hasNext}
          onPageChange={onPageChange}
        />
      ) : null}
    </Stack>
  )
}
