import { Flex, IconButton, Input, InputGroup, NativeSelect, Text } from '@chakra-ui/react'
import { Search, X } from 'lucide-react'
import type { ReactNode } from 'react'

import { priorityLabels, statusLabels } from '../lib/format.ts'
import { TICKET_PRIORITIES, TICKET_STATUSES } from '../lib/types.ts'
import type { TicketPriority, TicketStatus } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'

export interface TicketFilterBarProps {
  search: string
  onSearchChange: (value: string) => void
  status: TicketStatus | ''
  onStatusChange: (value: TicketStatus | '') => void
  priority?: TicketPriority | ''
  onPriorityChange?: (value: TicketPriority | '') => void
  /** Extra controls such as an assignee filter (admin). */
  extra?: ReactNode
}

export function TicketFilterBar({
  search,
  onSearchChange,
  status,
  onStatusChange,
  priority,
  onPriorityChange,
  extra,
}: TicketFilterBarProps) {
  const selectStyles = {
    bg: palette.surface,
    borderColor: palette.border,
    borderRadius: 'l2',
    fontSize: 'sm',
    height: '9',
    _hover: { borderColor: palette.borderStrong },
    _focus: { borderColor: palette.ink },
  } as const

  return (
    <Flex gap='2.5' wrap='wrap' align='center'>
      <InputGroup
        startElement={<Search size={15} color={palette.textMuted} aria-hidden />}
        maxW={{ base: 'full', sm: '72' }}
        flex={{ base: '1 1 100%', sm: '0 1 auto' }}
      >
        <Input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder='Search tickets'
          aria-label='Search tickets by title'
          {...selectStyles}
          ps='8'
        />
      </InputGroup>

      {search ? (
        <IconButton
          aria-label='Clear search'
          size='sm'
          variant='ghost'
          color={palette.textMuted}
          _hover={{ bg: palette.hover, color: palette.text }}
          onClick={() => onSearchChange('')}
        >
          <X size={15} aria-hidden />
        </IconButton>
      ) : null}

      <NativeSelect.Root size='sm' width='auto' minW='40'>
        <NativeSelect.Field
          value={status}
          onChange={(event) => onStatusChange(event.target.value as TicketStatus | '')}
          aria-label='Filter by status'
          {...selectStyles}
        >
          <option value=''>All statuses</option>
          {TICKET_STATUSES.map((value) => (
            <option key={value} value={value}>
              {statusLabels[value]}
            </option>
          ))}
        </NativeSelect.Field>
        <NativeSelect.Indicator color={palette.textMuted} />
      </NativeSelect.Root>

      {onPriorityChange ? (
        <NativeSelect.Root size='sm' width='auto' minW='40'>
          <NativeSelect.Field
            value={priority ?? ''}
            onChange={(event) => onPriorityChange(event.target.value as TicketPriority | '')}
            aria-label='Filter by priority'
            {...selectStyles}
          >
            <option value=''>All priorities</option>
            {TICKET_PRIORITIES.map((value) => (
              <option key={value} value={value}>
                {priorityLabels[value]}
              </option>
            ))}
          </NativeSelect.Field>
          <NativeSelect.Indicator color={palette.textMuted} />
        </NativeSelect.Root>
      ) : null}

      {extra}

      {search || status || priority ? (
        <Text fontSize='xs' color={palette.textFaint} ml='auto'>
          Filters applied
        </Text>
      ) : null}
    </Flex>
  )
}
