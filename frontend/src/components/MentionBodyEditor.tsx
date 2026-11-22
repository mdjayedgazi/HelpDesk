import { Box, Flex, Spinner, Stack, Text, chakra } from '@chakra-ui/react'
import { useCallback, useEffect, useId, useRef, useState } from 'react'

import { useDebounced } from '../hooks/useDebounced.ts'
import { useStaffDirectory } from '../hooks/useStaffMessages.ts'
import {
  activeMention,
  highlightMatch,
  insertMention,
  type MentionQuery,
} from '../lib/mentions.ts'
import type { User } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'
import { RoleBadge } from './badges.tsx'
import { TextAreaInput } from './FormField.tsx'
import { UserAvatar } from './UserAvatar.tsx'

const MAX_SUGGESTIONS = 8

/**
 * A controlled textarea with @mention autocomplete for forms that own their
 * own submit flow (e.g. the Owner compose dialog's review step).
 *
 * It shares the pure trigger/insertion helpers and the staff-only directory
 * query with `StaffMentionComposer`, but only manages the text field: the
 * caller keeps the value and receives the real mentioned employee ids whenever
 * the selection changes.
 */
export function MentionBodyEditor({
  id,
  value,
  onChange,
  onMentionsChange,
  placeholder = 'Write a message…',
  rows = 6,
  maxLength = 5000,
  ariaLabel = 'Message',
}: {
  id?: string
  value: string
  onChange: (value: string) => void
  onMentionsChange: (ids: string[]) => void
  placeholder?: string
  rows?: number
  maxLength?: number
  ariaLabel?: string
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const listboxId = useId()
  const [mention, setMention] = useState<MentionQuery | null>(null)
  const [highlighted, setHighlighted] = useState(0)
  const [selected, setSelected] = useState<Map<string, User>>(new Map())

  const debouncedQuery = useDebounced(mention?.query ?? '', 180)
  const directory = useStaffDirectory(
    { q: debouncedQuery || undefined, limit: MAX_SUGGESTIONS },
    Boolean(mention),
  )
  const results = (directory.data ?? []).slice(0, MAX_SUGGESTIONS)
  const open = Boolean(mention)

  useEffect(() => {
    setHighlighted(0)
  }, [debouncedQuery, mention?.start])

  // Keep the parent's structured id list in sync with what is still in the text.
  useEffect(() => {
    const ids: string[] = []
    for (const [userId, user] of selected) {
      if (value.includes(`@${user.username}`)) ids.push(userId)
    }
    onMentionsChange(ids)
  }, [selected, value, onMentionsChange])

  const syncFromCaret = useCallback(() => {
    const node = textareaRef.current
    if (!node) return
    setMention(activeMention(node.value, node.selectionStart))
  }, [])

  const choose = (user: User) => {
    const node = textareaRef.current
    if (!node || !mention) return
    const next = insertMention(node.value, mention, user.username)
    onChange(next.value)
    setSelected((current) => {
      const copy = new Map(current)
      copy.set(user.id, user)
      return copy
    })
    setMention(null)
    window.requestAnimationFrame(() => {
      node.focus()
      node.setSelectionRange(next.caret, next.caret)
    })
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!open) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlighted((current) => Math.min(current + 1, Math.max(0, results.length - 1)))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlighted((current) => Math.max(current - 1, 0))
    } else if ((event.key === 'Enter' || event.key === 'Tab') && results[highlighted]) {
      event.preventDefault()
      choose(results[highlighted]!)
    } else if (event.key === 'Escape') {
      event.preventDefault()
      setMention(null)
    }
  }

  const chips = [...selected.values()].filter((user) => value.includes(`@${user.username}`))

  return (
    <Stack gap='2'>
      <Box position='relative'>
        <TextAreaInput
          id={id}
          ref={textareaRef}
          value={value}
          rows={rows}
          maxLength={maxLength}
          placeholder={placeholder}
          aria-label={ariaLabel}
          role='combobox'
          aria-autocomplete='list'
          aria-expanded={open}
          aria-controls={open ? listboxId : undefined}
          onChange={(event) => {
            onChange(event.target.value)
            setMention(activeMention(event.target.value, event.target.selectionStart))
          }}
          onClick={syncFromCaret}
          onKeyDown={handleKeyDown}
          onKeyUp={(event) => {
            if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) syncFromCaret()
          }}
          onBlur={() => window.setTimeout(() => setMention(null), 120)}
        />
        {open ? (
          <Box
            position='absolute'
            left='0'
            right='0'
            top='calc(100% + 4px)'
            zIndex='20'
            bg={palette.elevated}
            borderWidth='1px'
            borderColor={palette.borderStrong}
            borderRadius='l3'
            boxShadow={palette.shadowLg}
            overflow='hidden'
            className='hd-menu-in'
            onMouseDown={(event) => event.preventDefault()}
          >
            <Flex px='3' py='2' borderBottomWidth='1px' borderColor={palette.borderSubtle}>
              <Text fontSize='2xs' color={palette.textMuted} fontWeight='medium'>
                Mention a teammate
              </Text>
            </Flex>
            <Box id={listboxId} role='listbox' aria-label='Employee suggestions' maxH='14rem' overflowY='auto'>
              {directory.isPending ? (
                <Flex px='3' py='3' gap='2' align='center' color={palette.textMuted}>
                  <Spinner size='xs' />
                  <Text fontSize='xs'>Searching…</Text>
                </Flex>
              ) : directory.isError ? (
                <Text px='3' py='3' fontSize='xs' color={palette.textMuted}>
                  Could not load employees. Keep typing to retry.
                </Text>
              ) : results.length === 0 ? (
                <Text px='3' py='3' fontSize='xs' color={palette.textMuted}>
                  No active employee matches “{mention?.query ?? ''}”.
                </Text>
              ) : (
                results.map((user, index) => (
                  <SuggestionOption
                    key={user.id}
                    id={`${listboxId}-option-${index}`}
                    user={user}
                    query={mention?.query ?? ''}
                    selected={index === highlighted}
                    onSelect={() => choose(user)}
                    onHover={() => setHighlighted(index)}
                  />
                ))
              )}
            </Box>
          </Box>
        ) : null}
      </Box>

      {chips.length > 0 ? (
        <Flex gap='1.5' wrap='wrap' aria-label='Mentioned teammates'>
          {chips.map((user) => (
            <Flex
              key={user.id}
              align='center'
              px='2'
              py='0.5'
              borderRadius='full'
              bg={palette.accentSoft}
              borderWidth='1px'
              borderColor={palette.accentBorder}
              color={palette.accent}
              fontSize='2xs'
              fontWeight='medium'
            >
              @{user.username}
            </Flex>
          ))}
        </Flex>
      ) : null}
    </Stack>
  )
}

function SuggestionOption({
  id,
  user,
  query,
  selected,
  onSelect,
  onHover,
}: {
  id: string
  user: User
  query: string
  selected: boolean
  onSelect: () => void
  onHover: () => void
}) {
  const name = highlightMatch(user.full_name, query)
  const username = highlightMatch(user.username, query)
  return (
    <chakra.button
      id={id}
      type='button'
      role='option'
      aria-selected={selected}
      onClick={onSelect}
      onMouseEnter={onHover}
      textAlign='start'
      width='full'
      px='3'
      py='2.5'
      bg={selected ? palette.hover : 'transparent'}
      borderBottomWidth='1px'
      borderColor={palette.borderSubtle}
      _last={{ borderBottomWidth: 0 }}
      _focusVisible={{ outline: '2px solid', outlineColor: palette.focus, outlineOffset: '-2px' }}
    >
      <Flex align='center' gap='3'>
        <UserAvatar name={user.full_name} src={user.image_url} size='xs' />
        <Stack gap='0.5' minW='0' flex='1'>
          <Flex align='center' gap='2' wrap='wrap'>
            <Text fontSize='sm' color={palette.text} truncate>
              {name.before}
              {name.match ? (
                <Text as='mark' bg={palette.accentSoft} color={palette.accent} px='0.5' borderRadius='xs'>
                  {name.match}
                </Text>
              ) : null}
              {name.after}
            </Text>
            <RoleBadge role={user.role} />
          </Flex>
          <Text fontSize='2xs' color={palette.textMuted} truncate>
            @{username.before}
            {username.match ? (
              <Text as='mark' bg={palette.accentSoft} color={palette.accent} px='0.5' borderRadius='xs'>
                {username.match}
              </Text>
            ) : null}
            {username.after} · ID {user.id.slice(0, 8)}
          </Text>
        </Stack>
      </Flex>
    </chakra.button>
  )
}
