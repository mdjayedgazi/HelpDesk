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
import { useNavigate } from 'react-router-dom'

import {
  useMarkAllNotificationsRead,
  useUnreadNotifications,
  useUpdateNotification,
} from '../hooks/useNotifications.ts'
import { errorMessage } from '../lib/errors.ts'
import { palette } from '../theme/palette.ts'
import { NotificationRow } from './NotificationRow.tsx'
import { toaster } from './Toaster.tsx'

export function NotificationsMenu() {
  const navigate = useNavigate()
  const { data, isLoading } = useUnreadNotifications(20)
  const updateNotification = useUpdateNotification()
  const markAll = useMarkAllNotificationsRead()

  const unread = data ?? []
  const hasUnread = unread.length > 0

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
    <Popover.Root positioning={{ placement: 'bottom-end' }}>
      <Popover.Trigger asChild>
        <IconButton
          variant='ghost'
          size='sm'
          color={palette.textSecondary}
          _hover={{ bg: palette.hover, color: palette.text }}
          aria-label={hasUnread ? `Notifications, ${unread.length} unread` : 'Notifications'}
          position='relative'
        >
          <Bell size={17} strokeWidth={1.9} aria-hidden />
          {hasUnread ? (
            <Center
              position='absolute'
              top='1'
              right='1'
              minW='4'
              height='4'
              px='1'
              borderRadius='full'
              bg={palette.ink}
              color={palette.textOnInk}
              fontSize='2xs'
              fontWeight='semibold'
              borderWidth='2px'
              borderColor={palette.surface}
            >
              {unread.length > 9 ? '9+' : unread.length}
            </Center>
          ) : null}
        </IconButton>
      </Popover.Trigger>
      <Portal>
        <Popover.Positioner>
          <Popover.Content
            width={{ base: 'sm', md: 'md' }}
            maxW='calc(100vw - 2rem)'
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l3'
            boxShadow={palette.shadowMd}
            overflow='hidden'
          >
            <Popover.Header px='4' py='3' borderBottomWidth='1px' borderColor={palette.border}>
              <Flex align='center' justify='space-between' gap='3'>
                <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                  Notifications
                </Text>
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
            </Popover.Header>
            <Popover.Body p='0'>
              {isLoading ? (
                <Flex px='4' py='6' justify='center'>
                  <Text fontSize='xs' color={palette.textMuted}>
                    Loading…
                  </Text>
                </Flex>
              ) : unread.length === 0 ? (
                <Stack align='center' gap='1' px='4' py='10' textAlign='center'>
                  <Text fontSize='sm' color={palette.textSecondary}>
                    You are all caught up
                  </Text>
                  <Text fontSize='xs' color={palette.textFaint}>
                    New activity on your tickets will appear here.
                  </Text>
                </Stack>
              ) : (
                <Box maxH='sm' overflowY='auto'>
                  {unread.map((notification) => (
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
            <Popover.Footer px='4' py='2.5' borderTopWidth='1px' borderColor={palette.border}>
              <Button
                variant='ghost'
                size='xs'
                width='full'
                color={palette.textSecondary}
                _hover={{ bg: palette.hover, color: palette.text }}
                onClick={() => navigate('/notifications')}
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
