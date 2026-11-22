import { Box, Flex, Input, Stack, Text, chakra } from '@chakra-ui/react'
import { Check, Search } from 'lucide-react'
import { useId, useState } from 'react'

import { useDebounced } from '../hooks/useDebounced.ts'
import { useStaffDirectory } from '../hooks/useStaffMessages.ts'
import { palette } from '../theme/palette.ts'
import { RoleBadge } from './badges.tsx'
import { InlineSpinner } from './StateViews.tsx'
import { UserAvatar } from './UserAvatar.tsx'

/**
 * A searchable employee selector for starting a staff conversation.
 *
 * Backed by the staff-only `/staff-messages/directory` endpoint, so it lists
 * active AGENT/ADMIN/OWNER accounts (never customers) and cannot be used by a
 * customer. Search is case-insensitive and matches name, username and account
 * id.
 */
export function StaffConversationPicker({
  value,
  onChange,
}: {
  value: string
  onChange: (userId: string) => void
}) {
  const listboxId = useId()
  const [query, setQuery] = useState('')
  const debounced = useDebounced(query, 200)
  const { data, isPending, isError } = useStaffDirectory({ q: debounced.trim() || undefined, limit: 20 })
  const results = data ?? []

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
          placeholder='Search teammates by name, @username, or ID'
          role='combobox'
          aria-expanded
          aria-controls={listboxId}
          aria-label='Search teammates'
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
        aria-label='Teammate results'
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
            Could not load teammates. Try again.
          </Text>
        ) : results.length === 0 ? (
          <Text px='3' py='3' fontSize='xs' color={palette.textMuted}>
            No active teammate matches that search.
          </Text>
        ) : (
          results.map((user, index) => (
            <chakra.button
              key={user.id}
              type='button'
              role='option'
              aria-selected={value === user.id}
              onClick={() => onChange(user.id)}
              textAlign='start'
              width='full'
              px='3'
              py='2.5'
              bg={value === user.id ? palette.hover : 'transparent'}
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
                    @{user.username} · ID {user.id.slice(0, 8)}
                  </Text>
                </Stack>
                {value === user.id ? <Check size={14} color={palette.accent} aria-hidden /> : null}
              </Flex>
            </chakra.button>
          ))
        )}
      </Box>
    </Stack>
  )
}
