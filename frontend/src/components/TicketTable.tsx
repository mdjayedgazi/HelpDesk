import { Box, Flex, Table, Text } from '@chakra-ui/react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { formatRelative, ticketRef } from '../lib/format.ts'
import type { Ticket } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'
import { PriorityBadge, StatusBadge } from './badges.tsx'

export interface TicketTableProps {
  tickets: Ticket[]
  /** Resolve a user id to a display name; falls back to a neutral label. */
  userLabel: (id: string | null | undefined) => string
  showAssignee?: boolean
  showRequester?: boolean
  /** Optional trailing cell, e.g. a "Claim" button in the agent queue. */
  renderActions?: (ticket: Ticket) => ReactNode
}

/**
 * The operational ticket table.
 *
 * Hierarchy: the subject is the only medium-weight line; the ticket number is
 * small metadata beside it; status and priority are toned pills so the eye can
 * find open/urgent work without reading every row. On small screens the
 * status/priority pills move under the subject instead of dropping out, so the
 * row never loses the information needed to triage.
 */
export function TicketTable({
  tickets,
  userLabel,
  showAssignee = false,
  showRequester = false,
  renderActions,
}: TicketTableProps) {
  const headerStyles = {
    color: palette.textMuted,
    fontSize: 'xs',
    fontWeight: 'medium',
    letterSpacing: '0.01em',
  } as const

  return (
    <Table.ScrollArea borderWidth='0'>
      <Table.Root size='sm' variant='line' interactive>
        <Table.Header>
          <Table.Row bg={palette.surface}>
            <Table.ColumnHeader {...headerStyles}>Ticket</Table.ColumnHeader>
            {showRequester ? (
              <Table.ColumnHeader {...headerStyles} display={{ base: 'none', lg: 'table-cell' }}>
                Requester
              </Table.ColumnHeader>
            ) : null}
            <Table.ColumnHeader {...headerStyles} display={{ base: 'none', md: 'table-cell' }}>
              Status
            </Table.ColumnHeader>
            <Table.ColumnHeader {...headerStyles} display={{ base: 'none', md: 'table-cell' }}>
              Priority
            </Table.ColumnHeader>
            {showAssignee ? (
              <Table.ColumnHeader {...headerStyles} display={{ base: 'none', lg: 'table-cell' }}>
                Assignee
              </Table.ColumnHeader>
            ) : null}
            <Table.ColumnHeader
              {...headerStyles}
              textAlign='right'
              display={{ base: 'none', sm: 'table-cell' }}
            >
              Updated
            </Table.ColumnHeader>
            {renderActions ? (
              <Table.ColumnHeader {...headerStyles} textAlign='right' width='1%'>
                {' '}
              </Table.ColumnHeader>
            ) : null}
          </Table.Row>
        </Table.Header>
        <Table.Body>
          {tickets.map((ticket) => (
            <Table.Row
              key={ticket.id}
              cursor='pointer'
              transition='background var(--hd-dur-1) var(--hd-ease)'
              _hover={{ bg: palette.hover }}
            >
              <Table.Cell py='3.5' maxW='0'>
                <Flex direction='column' gap='1.5' minW='0'>
                  <Flex align='center' gap='2' minW='0'>
                    <Text
                      fontSize='2xs'
                      color={palette.textFaint}
                      fontVariantNumeric='tabular-nums'
                      flexShrink={0}
                      fontFamily='mono'
                    >
                      {ticketRef(ticket.ticket_number)}
                    </Text>
                    <Link
                      to={`/tickets/${ticket.id}`}
                      style={{ textDecoration: 'none', minWidth: 0 }}
                    >
                      <Text
                        fontSize='sm'
                        fontWeight='medium'
                        color={palette.text}
                        truncate
                        _hover={{ textDecoration: 'underline' }}
                      >
                        {ticket.title}
                      </Text>
                    </Link>
                  </Flex>
                  <Flex
                    align='center'
                    gap='1.5'
                    display={{ base: 'flex', md: 'none' }}
                    wrap='wrap'
                  >
                    <StatusBadge status={ticket.status} />
                    <PriorityBadge priority={ticket.priority} />
                    <Text fontSize='2xs' color={palette.textFaint}>
                      {formatRelative(ticket.updated_at)}
                    </Text>
                  </Flex>
                </Flex>
              </Table.Cell>
              {showRequester ? (
                <Table.Cell
                  display={{ base: 'none', lg: 'table-cell' }}
                  fontSize='sm'
                  color={palette.textSecondary}
                  whiteSpace='nowrap'
                  maxW='40'
                  truncate
                >
                  {userLabel(ticket.created_by_user_id)}
                </Table.Cell>
              ) : null}
              <Table.Cell display={{ base: 'none', md: 'table-cell' }}>
                <StatusBadge status={ticket.status} />
              </Table.Cell>
              <Table.Cell display={{ base: 'none', md: 'table-cell' }}>
                <PriorityBadge priority={ticket.priority} />
              </Table.Cell>
              {showAssignee ? (
                <Table.Cell
                  display={{ base: 'none', lg: 'table-cell' }}
                  fontSize='sm'
                  color={ticket.assignee_user_id ? palette.textSecondary : palette.textMuted}
                  whiteSpace='nowrap'
                  maxW='40'
                  truncate
                >
                  {ticket.assignee_user_id ? userLabel(ticket.assignee_user_id) : 'Unassigned'}
                </Table.Cell>
              ) : null}
              <Table.Cell
                display={{ base: 'none', sm: 'table-cell' }}
                textAlign='right'
                fontSize='2xs'
                color={palette.textMuted}
                whiteSpace='nowrap'
              >
                {formatRelative(ticket.updated_at)}
              </Table.Cell>
              {renderActions ? (
                <Table.Cell textAlign='right' width='1%' whiteSpace='nowrap'>
                  {renderActions(ticket)}
                </Table.Cell>
              ) : null}
            </Table.Row>
          ))}
        </Table.Body>
      </Table.Root>
    </Table.ScrollArea>
  )
}

export function TicketTableSurface({ children }: { children: React.ReactNode }) {
  return (
    <Box
      bg={palette.surface}
      borderWidth='1px'
      borderColor={palette.border}
      borderRadius='l3'
      overflow='hidden'
    >
      {children}
    </Box>
  )
}
