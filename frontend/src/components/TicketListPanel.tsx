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

/** Server pagination metadata for a paged ticket table. */
export interface TicketPagination {
  /** The page the user requested (may differ from data while loading). */
  page: number
  pageSize: number
  /** Total matching records across all pages. */
  total: number
  /** Server-provided page count (>= 1). */
  totalPages: number
  /** True while a different page is being fetched. */
  isFetching?: boolean
  onPageChange: (page: number) => void
}

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
  pagination,
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
  /** Omit for a static, unpaginated list (dashboard worklists). */
  pagination?: TicketPagination
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
      {pagination ? (
        <Pagination
          page={pagination.page}
          pageSize={pagination.pageSize}
          total={pagination.total}
          totalPages={pagination.totalPages}
          isLoading={pagination.isFetching}
          onPageChange={pagination.onPageChange}
        />
      ) : null}
    </Stack>
  )
}
