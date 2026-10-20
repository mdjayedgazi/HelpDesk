import {
  Box,
  Button,
  Center,
  Flex,
  IconButton,
  Popover,
  Portal,
  Stack,
  Text,
} from '@chakra-ui/react'
import { Bell, CheckCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import {
  useMarkAllNotificationsRead,
  useNotifications,
  useUnreadNotificationCount,
  useUpdateNotification,
} from '../hooks/useNotifications.ts'
import { errorMessage } from '../lib/errors.ts'
import type { NotificationCategory } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'
import { NotificationRow } from './NotificationRow.tsx'
import { toaster } from './Toaster.tsx'

type Filter = 'all' | 'unread'
type Category = 'all' | NotificationCategory

const RECENT_LIMIT = 20

/** Cap the badge the way the panel header caps it: `12`, `99+`. */
export function formatUnreadBadge(count: number): string | null {
  if (count <= 0) return null
  return count > 99 ? '99+' : String(count)
}

export function NotificationsMenu() {
  const navigate = useNavigate()
  const location = useLocation()
  const [filter, setFilter] = useState<Filter>('all')
  const [category, setCategory] = useState<Category>('all')
  const [open, setOpen] = useState(false)

  const unreadCount = useUnreadNotificationCount()
  const notifications = useNotifications({
    is_read: filter === 'unread' ? false : undefined,
    category: category === 'all' ? undefined : category,
    limit: RECENT_LIMIT,
  })
  const updateNotification = useUpdateNotification()
  const markAll = useMarkAllNotificationsRead()

  // A row click navigates; the popover lives in the persistent header, so close
  // it on any route/query change instead of leaving it over the new page.
  useEffect(() => {
    setOpen(false)
  }, [location.pathname, location.search, location.hash])

  const total = unreadCount.data?.count ?? 0
  const badge = formatUnreadBadge(total)
  const items = notifications.data ?? []
  const hasUnread = total > 0

  const markOne = (id: string) => {
    updateNotification.mutate(
      { id, isRead: true },
      { onError: (error) => toaster.create({ title: errorMessage(error), type: 'error' }) },
    )
  }

  const markAllRead = () => {
    markAll.mutate(undefined, {
      onSuccess: () => toaster.create({ title: 'All notifications marked as read' }),
      onError: (error) => toaster.create({ title: errorMessage(error), type: 'error' }),
    })
  }

  return (
    <Popover.Root
      open={open}
      onOpenChange={(details) => {
        setOpen(details.open)
        // Opening is a read; refresh so the panel and badge never lag a poll.
        if (details.open) {
          void notifications.refetch()
          void unreadCount.refetch()
        }
      }}
      positioning={{ placement: 'bottom-end' }}
    >
      <Popover.Trigger asChild>
        <IconButton
          variant='ghost'
          size='sm'
          color={palette.textSecondary}
          _hover={{ bg: palette.hover, color: palette.text }}
          aria-label={
            badge ? `Notifications, ${total} unread` : 'Notifications, none unread'
          }
          position='relative'
        >
          <Bell size={17} strokeWidth={1.9} aria-hidden />
          {badge ? (
            <Center
              position='absolute'
              top='0.5'
              right='0.5'
              minW='4'
              height='4'
              px='1'
              borderRadius='full'
              bg={palette.ink}
              color={palette.textOnInk}
              fontSize='2xs'
              fontWeight='semibold'
              lineHeight='1'
              borderWidth='2px'
              borderColor={palette.surface}
              pointerEvents='none'
            >
              {badge}
            </Center>
          ) : null}
        </IconButton>
      </Popover.Trigger>
      <Portal>
        <Popover.Positioner>
          <Popover.Content
            width={{ base: 'sm', md: 'md' }}
            maxW='calc(100vw - 2rem)'
            maxH='min(calc(100dvh - 4.5rem), 40rem)'
            display='flex'
            flexDirection='column'
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l3'
            boxShadow={palette.shadowMd}
            overflow='hidden'
          >
            <Popover.Header
              px='4'
              py='3'
              flexShrink={0}
              borderBottomWidth='1px'
              borderColor={palette.border}
            >
              <Flex align='center' justify='space-between' gap='3'>
                <Flex align='baseline' gap='2'>
                  <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                    Notifications
                  </Text>
                  {hasUnread ? (
                    <Text fontSize='xs' color={palette.textMuted}>
                      {total} unread
                    </Text>
                  ) : null}
                </Flex>
                {hasUnread ? (
                  <Button
                    variant='plain'
                    size='xs'
                    height='auto'
                    p='0'
                    gap='1.5'
                    fontSize='xs'
                    color={palette.textSecondary}
                    _hover={{ color: palette.text }}
                    loading={markAll.isPending}
                    onClick={markAllRead}
                  >
                    <CheckCheck size={13} aria-hidden />
                    Mark all read
                  </Button>
                ) : null}
              </Flex>

              <Stack gap='2' pt='3'>
                <FilterRow
                  options={[
                    { value: 'all', label: 'All' },
                    { value: 'unread', label: 'Unread' },
                  ]}
                  value={filter}
                  onChange={(value) => setFilter(value as Filter)}
                  ariaLabel='Filter notifications by read state'
                />
                <FilterRow
                  options={[
                    { value: 'all', label: 'Everything' },
                    { value: 'tickets', label: 'Tickets' },
                    { value: 'messages', label: 'Messages' },
                    { value: 'account_requests', label: 'Account requests' },
                  ]}
                  value={category}
                  onChange={(value) => setCategory(value as Category)}
                  ariaLabel='Filter notifications by category'
                />
              </Stack>
            </Popover.Header>
            <Popover.Body p='0' overflowY='auto' flex='1' minH='0'>
              {notifications.isPending ? (
                <Flex px='4' py='6' justify='center'>
                  <Text fontSize='xs' color={palette.textMuted}>
                    Loading…
                  </Text>
                </Flex>
              ) : notifications.isError ? (
                <Stack align='center' gap='3' px='4' py='8' textAlign='center'>
                  <Text fontSize='sm' color={palette.textSecondary}>
                    Could not load notifications
                  </Text>
                  <Text fontSize='xs' color={palette.textFaint}>
                    {errorMessage(notifications.error)}
                  </Text>
                  <Button
                    size='xs'
                    variant='outline'
                    borderColor={palette.border}
                    onClick={() => void notifications.refetch()}
                  >
                    Try again
                  </Button>
                </Stack>
              ) : items.length === 0 ? (
                <Stack align='center' gap='1' px='4' py='10' textAlign='center'>
                  <Text fontSize='sm' color={palette.textSecondary}>
                    {filter === 'unread'
                      ? hasUnread
                        ? 'Nothing here'
                        : 'You are all caught up'
                      : 'No notifications yet'}
                  </Text>
                  <Text fontSize='xs' color={palette.textFaint}>
                    New activity on your work will appear here.
                  </Text>
                </Stack>
              ) : (
                <Box>
                  {items.map((notification) => (
                    <NotificationRow
                      key={notification.id}
                      notification={notification}
                      onMarkRead={markOne}
                      marking={
                        updateNotification.isPending &&
                        updateNotification.variables?.id === notification.id
                      }
                      compact
                    />
                  ))}
                </Box>
              )}
            </Popover.Body>
            <Popover.Footer
              px='4'
              py='2.5'
              flexShrink={0}
              borderTopWidth='1px'
              borderColor={palette.border}
            >
              <Button
                variant='ghost'
                size='xs'
                width='full'
                color={palette.textSecondary}
                _hover={{ bg: palette.hover, color: palette.text }}
                onClick={() => {
                  setOpen(false)
                  void navigate('/notifications')
                }}
              >
                View all notifications
              </Button>
            </Popover.Footer>
          </Popover.Content>
        </Popover.Positioner>
      </Portal>
    </Popover.Root>
  )
}

/** A compact, accessible segmented filter used for both panel filter rows. */
function FilterRow({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: Array<{ value: string; label: string }>
  value: string
  onChange: (value: string) => void
  ariaLabel: string
}) {
  return (
    <Flex
      role='group'
      aria-label={ariaLabel}
      gap='1.5'
      flexWrap='wrap'
    >
      {options.map((option) => {
        const selected = option.value === value
        return (
          <Button
            key={option.value}
            type='button'
            aria-pressed={selected}
            size='xs'
            variant='ghost'
            height='auto'
            px='2.5'
            py='1'
            borderRadius='l2'
            fontSize='xs'
            fontWeight={selected ? 'medium' : 'regular'}
            color={selected ? palette.text : palette.textSecondary}
            bg={selected ? palette.surfaceMuted : 'transparent'}
            borderWidth='1px'
            borderColor={selected ? palette.border : 'transparent'}
            _hover={{ bg: palette.hover, color: palette.text }}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </Button>
        )
      })}
    </Flex>
  )
}
