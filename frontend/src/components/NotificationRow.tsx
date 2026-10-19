import { Box, Button, Center, Flex, Stack, Text } from '@chakra-ui/react'
import {
  Flag,
  Inbox,
  Mail,
  MailOpen,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  ShieldQuestion,
  UserPlus,
  type LucideIcon,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { formatRelative } from '../lib/format.ts'
import type { Notification, NotificationType } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'

const typeIcons: Record<NotificationType, LucideIcon> = {
  TICKET_ASSIGNED: Inbox,
  NEW_COMMENT: MessageSquare,
  STATUS_CHANGED: RefreshCw,
  PRIORITY_CHANGED: Flag,
  TICKET_NEEDS_ASSIGNMENT: UserPlus,
  STAFF_MESSAGE_RECEIVED: Mail,
  OWNER_MESSAGE_RECEIVED: MailOpen,
  ESCALATION_CREATED: ShieldQuestion,
  ESCALATION_UPDATED: ShieldCheck,
}

export function NotificationRow({
  notification,
  onMarkRead,
  marking = false,
  compact = false,
}: {
  notification: Notification
  onMarkRead?: (id: string) => void
  marking?: boolean
  compact?: boolean
}) {
  const navigate = useNavigate()
  const Icon = typeIcons[notification.type]

  // Staff-message notifications deep-link into the private conversation;
  // ticket notifications open the ticket. The two channels never mix.
  const destination = notification.related_conversation_id
    ? {
        to: `/messages?conversation=${notification.related_conversation_id}`,
        label: 'Open conversation',
      }
    : notification.related_ticket_id
      ? { to: `/tickets/${notification.related_ticket_id}`, label: 'View ticket' }
      : null

  const openDestination = () => {
    if (!destination) return
    if (!notification.is_read && onMarkRead) onMarkRead(notification.id)
    void navigate(destination.to)
  }

  return (
    <Flex
      gap='3'
      px={compact ? '3' : '4'}
      py={compact ? '2.5' : '3.5'}
      align='flex-start'
      borderBottomWidth='1px'
      borderColor={palette.borderSubtle}
      bg={notification.is_read ? 'transparent' : palette.surfaceMuted}
      transition='background 0.16s ease'
      _hover={{ bg: palette.hover }}
    >
      <Center
        boxSize='7'
        flexShrink={0}
        borderRadius='full'
        borderWidth='1px'
        borderColor={palette.border}
        bg={palette.surface}
        color={palette.textSecondary}
        mt='0.5'
      >
        <Icon size={14} strokeWidth={1.9} aria-hidden />
      </Center>
      <Stack gap='0.5' flex='1' minW='0'>
        <Flex align='center' gap='2'>
          <Text
            fontSize='sm'
            fontWeight={notification.is_read ? 'regular' : 'medium'}
            color={palette.text}
            truncate
          >
            {notification.title}
          </Text>
          {!notification.is_read ? (
            <Box boxSize='1.5' borderRadius='full' bg={palette.ink} flexShrink={0} />
          ) : null}
        </Flex>
        <Text fontSize='xs' color={palette.textSecondary}>
          {notification.message}
        </Text>
        <Flex align='center' gap='3' pt='0.5'>
          <Text fontSize='xs' color={palette.textFaint}>
            {formatRelative(notification.created_at)}
          </Text>
          {destination ? (
            <Button
              variant='plain'
              size='xs'
              height='auto'
              p='0'
              fontSize='xs'
              color={palette.textSecondary}
              textDecoration='underline'
              textUnderlineOffset='2px'
              _hover={{ color: palette.text }}
              onClick={openDestination}
            >
              {destination.label}
            </Button>
          ) : null}
          {!notification.is_read && onMarkRead ? (
            <Button
              variant='plain'
              size='xs'
              height='auto'
              p='0'
              fontSize='xs'
              color={palette.textMuted}
              _hover={{ color: palette.text }}
              loading={marking}
              onClick={() => onMarkRead(notification.id)}
            >
              Mark read
            </Button>
          ) : null}
        </Flex>
      </Stack>
    </Flex>
  )
}
