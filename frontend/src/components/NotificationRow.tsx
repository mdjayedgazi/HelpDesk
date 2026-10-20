import { Box, Button, Center, Flex, Stack, Text } from '@chakra-ui/react'
import {
  Flag,
  Inbox,
  Mail,
  MailOpen,
  Megaphone,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  ShieldQuestion,
  Ticket,
  TicketCheck,
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
  TICKET_CREATED: Ticket,
  TICKET_RESOLVED: TicketCheck,
  INTERNAL_MESSAGE_RECEIVED: Megaphone,
}

const typeCategories: Record<NotificationType, string> = {
  TICKET_ASSIGNED: 'Ticket',
  NEW_COMMENT: 'Ticket',
  STATUS_CHANGED: 'Ticket',
  PRIORITY_CHANGED: 'Ticket',
  TICKET_NEEDS_ASSIGNMENT: 'Ticket',
  TICKET_CREATED: 'Ticket',
  TICKET_RESOLVED: 'Ticket',
  STAFF_MESSAGE_RECEIVED: 'Message',
  OWNER_MESSAGE_RECEIVED: 'Message',
  INTERNAL_MESSAGE_RECEIVED: 'Message',
  ESCALATION_CREATED: 'Account request',
  ESCALATION_UPDATED: 'Account request',
}

/**
 * Where a notification should open.
 *
 * The three deep-link channels never mix: an internal-message notification goes
 * to the exact received message, a staff-conversation notification to the exact
 * thread, and everything ticket-scoped to the ticket. A resolution notification
 * additionally targets the feedback section.
 */
export function notificationDestination(
  notification: Notification,
): { to: string; label: string } | null {
  if (notification.related_internal_message_id) {
    return {
      to: `/messages?message=${notification.related_internal_message_id}`,
      label: 'Open message',
    }
  }
  if (notification.related_conversation_id) {
    return {
      to: `/messages?conversation=${notification.related_conversation_id}`,
      label: 'Open conversation',
    }
  }
  if (notification.related_account_request_id) {
    return {
      to: `/account-requests/${notification.related_account_request_id}`,
      label: 'Open request',
    }
  }
  if (notification.related_ticket_id) {
    const hash = notification.type === 'TICKET_RESOLVED' ? '#feedback' : ''
    return {
      to: `/tickets/${notification.related_ticket_id}${hash}`,
      label: notification.type === 'TICKET_RESOLVED' ? 'Share feedback' : 'View ticket',
    }
  }
  return null
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

  const destination = notificationDestination(notification)

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
      cursor={destination ? 'pointer' : undefined}
      onClick={destination ? openDestination : undefined}
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
        <Flex align='flex-start' gap='2'>
          <Text
            fontSize='sm'
            fontWeight={notification.is_read ? 'regular' : 'medium'}
            color={palette.text}
            lineClamp={2}
            flex='1'
            minW='0'
          >
            {notification.title}
          </Text>
          {!notification.is_read ? (
            <Box
              boxSize='1.5'
              borderRadius='full'
              bg={palette.ink}
              flexShrink={0}
              mt='1.5'
            />
          ) : null}
        </Flex>
        <Text
          fontSize='xs'
          color={palette.textSecondary}
          lineClamp={2}
          wordBreak='break-word'
        >
          {notification.message}
        </Text>
        <Flex align='center' gap='2.5' pt='0.5' wrap='wrap'>
          <Text fontSize='2xs' color={palette.textFaint}>
            {formatRelative(notification.created_at)}
          </Text>
          <Text fontSize='2xs' color={palette.textMuted}>
            {typeCategories[notification.type]}
          </Text>
          {!notification.is_read ? (
            <Text
              fontSize='2xs'
              fontWeight='semibold'
              letterSpacing='0.04em'
              textTransform='uppercase'
              color={palette.textSecondary}
            >
              Unread
            </Text>
          ) : null}
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
              onClick={(event) => {
                event.stopPropagation()
                openDestination()
              }}
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
              onClick={(event) => {
                event.stopPropagation()
                onMarkRead(notification.id)
              }}
            >
              Mark read
            </Button>
          ) : null}
        </Flex>
      </Stack>
    </Flex>
  )
}
