import { Button, Flex, Stack, Tabs } from '@chakra-ui/react'
import { BellOff, CheckCheck } from 'lucide-react'
import { useState } from 'react'

import { PageHeader } from '../components/PageHeader.tsx'
import { NotificationRow } from '../components/NotificationRow.tsx'
import { Pagination } from '../components/Pagination.tsx'
import { EmptyState, ErrorState, TableSkeleton } from '../components/StateViews.tsx'
import { Surface } from '../components/Surface.tsx'
import { toaster } from '../components/Toaster.tsx'
import {
  useMarkAllNotificationsRead,
  useNotifications,
  useUpdateNotification,
} from '../hooks/useNotifications.ts'
import { errorMessage } from '../lib/errors.ts'
import { palette } from '../theme/palette.ts'

const PAGE_SIZE = 30

type Filter = 'all' | 'unread'

export function NotificationsPage() {
  const [filter, setFilter] = useState<Filter>('all')
  const [page, setPage] = useState(1)

  const isRead = filter === 'all' ? undefined : false
  const notifications = useNotifications({
    is_read: isRead,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  })

  const updateNotification = useUpdateNotification()
  const markAll = useMarkAllNotificationsRead()

  const items = notifications.data ?? []
  const hasNext = items.length === PAGE_SIZE

  const markOne = (id: string) => {
    updateNotification.mutate(
      { id, isRead: true },
      {
        onError: (error) => toaster.create({ title: errorMessage(error), type: 'error' }),
      },
    )
  }

  const markAllRead = () => {
    markAll.mutate(undefined, {
      onSuccess: () => toaster.create({ title: 'All notifications marked as read' }),
      onError: (error) => toaster.create({ title: errorMessage(error), type: 'error' }),
    })
  }

  const changeFilter = (value: string) => {
    setFilter(value as Filter)
    setPage(1)
  }

  return (
    <>
      <PageHeader
        title='Notifications'
        description='Updates about assignments, comments, status changes, private staff messages and account requests.'
        actions={
          filter === 'unread' || items.some((item) => !item.is_read) ? (
            <Button
              size='sm'
              variant='outline'
              borderColor={palette.border}
              loading={markAll.isPending}
              onClick={markAllRead}
            >
              <CheckCheck size={14} aria-hidden />
              Mark all read
            </Button>
          ) : null
        }
      />

      <Flex mb='4'>
        <Tabs.Root value={filter} onValueChange={(details) => changeFilter(details.value)}>
          <Tabs.List>
            <Tabs.Trigger value='all' fontSize='sm'>
              All
            </Tabs.Trigger>
            <Tabs.Trigger value='unread' fontSize='sm'>
              Unread
            </Tabs.Trigger>
            <Tabs.Indicator />
          </Tabs.List>
        </Tabs.Root>
      </Flex>

      {notifications.isPending ? (
        <Surface overflow='hidden'>
          <TableSkeleton rows={6} columns={3} />
        </Surface>
      ) : notifications.isError ? (
        <ErrorState
          title='Could not load notifications'
          description={errorMessage(notifications.error)}
          onRetry={() => void notifications.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={BellOff}
          title={filter === 'unread' ? 'No unread notifications' : 'No notifications yet'}
          description={
            filter === 'unread'
              ? 'You have read everything.'
              : 'Activity on your tickets will show up here.'
          }
        />
      ) : (
        <Stack gap='4'>
          <Surface overflow='hidden'>
            {items.map((notification) => (
              <NotificationRow
                key={notification.id}
                notification={notification}
                onMarkRead={markOne}
                marking={
                  updateNotification.isPending &&
                  updateNotification.variables?.id === notification.id
                }
              />
            ))}
          </Surface>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            itemCount={items.length}
            hasNext={hasNext}
            onPageChange={setPage}
          />
        </Stack>
      )}
    </>
  )
}
