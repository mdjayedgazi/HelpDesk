import { Box, Flex, Input, Stack, Text, chakra } from '@chakra-ui/react'
import { Check, Search, X } from 'lucide-react'
import { useId, useState } from 'react'

import { useMessageRecipients } from '../hooks/useInternalMessages.ts'
import { useDebounced } from '../hooks/useDebounced.ts'
import type { User } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'
import { RoleBadge } from './badges.tsx'
import { InlineSpinner } from './StateViews.tsx'
import { UserAvatar } from './UserAvatar.tsx'

/**
 * A searchable employee selector for the Owner Inbox.
 *
 * Search matches the display name, email, username or account id and always
 * shows the role, so two people with the same name can be told apart. The
 * candidate list comes from the Owner-only `/internal-messages/recipients`
 * endpoint (active agents and administrators only) - the backend is what
 * enforces eligibility; this control only presents it.
 */
export function EmployeePicker({
  value,
  onChange,
  placeholder = 'Search by name, email, or account ID',
  disabled = false,
  showResultsWhenEmpty = true,
}: {
  value: User | null
  onChange: (user: User | null) => void
  placeholder?: string
  disabled?: boolean
  /** Hide the result list until the user types (compact filter use). */
  showResultsWhenEmpty?: boolean
}) {
  const listboxId = useId()
  const [query, setQuery] = useState('')
  const debounced = useDebounced(query, 250)
  const { data, isPending, isError } = useMessageRecipients(
    { q: debounced.trim() || undefined, limit: 500 },
    !disabled,
  )
  const results = data ?? []

  if (value) {
    return (
      <Flex
        align='center'
        gap='3'
        borderWidth='1px'
        borderColor={palette.border}
        borderRadius='l2'
        bg={palette.surfaceMuted}
        px='3'
        py='2.5'
      >
        <UserAvatar name={value.full_name} src={value.image_url} size='xs' />
        <Stack gap='0.5' minW='0' flex='1'>
          <Flex align='center' gap='2' wrap='wrap'>
            <Text fontSize='sm' fontWeight='medium' color={palette.text} truncate>
              {value.full_name}
            </Text>
            <RoleBadge role={value.role} />
          </Flex>
          <Text fontSize='2xs' color={palette.textMuted} truncate>
            {value.email} · ID {value.id.slice(0, 8)}
          </Text>
        </Stack>
        <chakra.button
          type='button'
          onClick={() => {
            onChange(null)
            setQuery('')
          }}
          disabled={disabled}
          aria-label='Clear selected recipient'
          color={palette.textMuted}
          _hover={{ color: palette.text }}
          p='1'
          borderRadius='l1'
        >
          <X size={15} aria-hidden />
        </chakra.button>
      </Flex>
    )
  }

  return (
    <Stack gap='2'>
      <Box position='relative'>
        <Box
          position='absolute'
          left='3'
          top='50%'
          transform='translateY(-50%)'
          color={palette.textFaint}
          pointerEvents='none'
        >
          <Search size={15} aria-hidden />
        </Box>
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          role='combobox'
          aria-expanded
          aria-controls={listboxId}
          aria-label='Search recipients'
          pl='9'
          bg={palette.surface}
          borderColor={palette.border}
          borderRadius='l2'
          fontSize='sm'
          _placeholder={{ color: palette.textFaint }}
          _hover={{ borderColor: palette.borderStrong }}
          _focus={{ borderColor: palette.ink }}
        />
      </Box>

      <Box
        id={listboxId}
        role='listbox'
        aria-label='Recipient results'
        display={!showResultsWhenEmpty && query.trim() === '' ? 'none' : 'block'}
        borderWidth='1px'
        borderColor={palette.borderSubtle}
        borderRadius='l2'
        maxH='16rem'
        overflowY='auto'
      >
        {isPending ? (
          <Flex px='3' py='3' gap='2' align='center' color={palette.textMuted}>
            <InlineSpinner />
            <Text fontSize='xs'>Searching…</Text>
          </Flex>
        ) : isError ? (
          <Text px='3' py='3' fontSize='xs' color={palette.textMuted}>
            Could not load recipients. Try again.
          </Text>
        ) : results.length === 0 ? (
          <Text px='3' py='3' fontSize='xs' color={palette.textMuted}>
            {query.trim()
              ? 'No active agent or administrator matches that search.'
              : 'No active agents or administrators are available.'}
          </Text>
        ) : (
          results.map((user, index) => (
            <chakra.button
              key={user.id}
              type='button'
              role='option'
              aria-selected={false}
              onClick={() => onChange(user)}
              textAlign='start'
              width='full'
              px='3'
              py='2.5'
              borderBottomWidth={index === results.length - 1 ? '0' : '1px'}
              borderColor={palette.borderSubtle}
              _hover={{ bg: palette.hover }}
              _focusVisible={{ outline: '2px solid', outlineColor: palette.ink, outlineOffset: '-2px' }}
            >
              <Flex align='center' gap='3'>
                <UserAvatar name={user.full_name} src={user.image_url} size='xs' />
                <Stack gap='0.5' minW='0' flex='1'>
                  <Flex align='center' gap='2' wrap='wrap'>
                    <Text fontSize='sm' color={palette.text} truncate>
                      {user.full_name}
                    </Text>
                    <RoleBadge role={user.role} />
                  </Flex>
                  <Text fontSize='2xs' color={palette.textMuted} truncate>
                    {user.email} · ID {user.id.slice(0, 8)}
                  </Text>
                </Stack>
                <Check size={14} color={palette.textFaint} aria-hidden />
              </Flex>
            </chakra.button>
          ))
        )}
      </Box>
    </Stack>
  )
}
