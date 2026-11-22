import { Box, Button, Flex, Spinner, Stack, Text, chakra } from '@chakra-ui/react'
import { Send } from 'lucide-react'
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

const MAX_LENGTH = 5000
const MAX_SUGGESTIONS = 8

export interface MentionComposerSubmit {
  body: string
  /** The real employee ids selected as mentions, de-duplicated. */
  mentionedUserIds: string[]
}

/**
 * A reusable internal-message composer with @mention autocomplete.
 *
 * Any authenticated staff member can use it: suggestions come from the
 * staff-only `/staff-messages/directory` endpoint, which returns active
 * AGENT/ADMIN/OWNER accounts (never customers) and rejects a customer caller.
 * The selected employees are tracked as **real user ids**; the body keeps a
 * readable `@username`, but the structured id is what gets sent, so the backend
 * never has to trust display text.
 *
 * Keyboard: ArrowUp/Down move, Enter selects, Escape closes, Tab selects the
 * highlighted employee (standard autocomplete behaviour). The composer only
 * sends on a real submit when the suggestion list is closed, so pressing Enter
 * to pick an employee can never accidentally send the message.
 */
export function StaffMentionComposer({
  onSubmit,
  isPending = false,
  placeholder = 'Write a message…',
  submitLabel = 'Send message',
  maxLength = MAX_LENGTH,
  ariaLabel = 'Message',
  autoFocus = false,
}: {
  onSubmit: (input: MentionComposerSubmit) => unknown
  isPending?: boolean
  placeholder?: string
  submitLabel?: string
  maxLength?: number
  ariaLabel?: string
  autoFocus?: boolean
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const listboxId = useId()

  const [body, setBody] = useState('')
  const [error, setError] = useState<string | null>(null)
  // Structured mentions selected by the user: id -> user, in selection order.
  const [mentions, setMentions] = useState<Map<string, User>>(new Map())

  const [mention, setMention] = useState<MentionQuery | null>(null)
  const [highlighted, setHighlighted] = useState(0)

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

  const focusTextarea = useCallback(() => {
    textareaRef.current?.focus()
  }, [])

  const syncMentionFromCaret = useCallback(() => {
    const node = textareaRef.current
    if (!node) return
    setMention(activeMention(node.value, node.selectionStart))
  }, [])

  const choose = (user: User) => {
    const node = textareaRef.current
    if (!node || !mention) return
    const handle = user.username
    const next = insertMention(node.value, mention, handle)
    setBody(next.value)
    setMentions((current) => {
      const copy = new Map(current)
      copy.set(user.id, user)
      return copy
    })
    setMention(null)
    // Restore the caret just after the inserted token on the next paint.
    window.requestAnimationFrame(() => {
      node.focus()
      node.setSelectionRange(next.caret, next.caret)
    })
  }

  const handleChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setBody(event.target.value)
    setMention(activeMention(event.target.value, event.target.selectionStart))
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (open) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setHighlighted((current) => Math.min(current + 1, Math.max(0, results.length - 1)))
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        setHighlighted((current) => Math.max(current - 1, 0))
        return
      }
      if ((event.key === 'Enter' || event.key === 'Tab') && results[highlighted]) {
        event.preventDefault()
        choose(results[highlighted]!)
        return
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        setMention(null)
        return
      }
    }
    // Plain Enter submits only when the suggestion panel is closed and the user
    // is not holding Shift (Shift+Enter inserts a newline).
    if (event.key === 'Enter' && !event.shiftKey && !open) {
      event.preventDefault()
      void submit()
    }
  }

  const submit = async () => {
    const trimmed = body.trim()
    if (!trimmed) {
      setError('Please write a message before sending.')
      return
    }
    if (trimmed.length > maxLength) {
      setError(`Message must be ${maxLength} characters or fewer.`)
      return
    }
    setError(null)

    // Only send mentions whose handle still appears in the final body. This
    // keeps the structured list consistent with what the reader sees, and
    // avoids notifying someone the sender removed by editing the text.
    const mentionedUserIds: string[] = []
    for (const [id, user] of mentions) {
      if (trimmed.includes(`@${user.username}`)) mentionedUserIds.push(id)
    }

    try {
      await onSubmit({ body: trimmed, mentionedUserIds })
      setBody('')
      setMentions(new Map())
      setMention(null)
    } catch {
      // The caller surfaces the error; keep the draft so nothing is lost.
    }
  }

  const mentionChips = [...mentions.values()]

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        void submit()
      }}
    >
      <Stack gap='3'>
        <Box position='relative'>
          <TextAreaInput
            ref={textareaRef}
            value={body}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onClick={syncMentionFromCaret}
            onKeyUp={(event) => {
              // Re-detect the mention whenever the caret moves without a text
              // change (arrow keys, Home/End) so the panel tracks the caret.
              if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
                syncMentionFromCaret()
              }
            }}
            onBlur={() => {
              // Delay so a click on a suggestion registers before the panel
              // closes (pointer selection on mouse/touch).
              window.setTimeout(() => setMention(null), 120)
            }}
            placeholder={placeholder}
            minH='24'
            maxLength={maxLength}
            autoFocus={autoFocus}
            aria-label={ariaLabel}
            aria-invalid={Boolean(error)}
            aria-autocomplete='list'
            aria-expanded={open}
            aria-controls={open ? listboxId : undefined}
            aria-activedescendant={
              open && results[highlighted] ? `${listboxId}-option-${highlighted}` : undefined
            }
            role='combobox'
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
              // Keep focus in the textarea while interacting with the panel.
              onMouseDown={(event) => event.preventDefault()}
            >
              <Flex px='3' py='2' borderBottomWidth='1px' borderColor={palette.borderSubtle}>
                <Text fontSize='2xs' color={palette.textMuted} fontWeight='medium'>
                  Mention a teammate
                </Text>
              </Flex>
              <Box id={listboxId} role='listbox' aria-label='Employee suggestions' maxH='16rem' overflowY='auto'>
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
                    <SuggestionRow
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

        {mentionChips.length > 0 ? (
          <Flex gap='1.5' wrap='wrap' aria-label='Mentioned teammates'>
            {mentionChips.map((user) => (
              <Flex
                key={user.id}
                align='center'
                gap='1.5'
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

        <Flex align='center' justify='space-between' gap='3' wrap='wrap'>
          <Text
            fontSize='xs'
            color={error ? palette.text : palette.textMuted}
            role={error ? 'alert' : undefined}
          >
            {error ??
              `${body.trim().length}/${maxLength} · Type @ to mention a teammate`}
          </Text>
          <Button
            type='submit'
            size='sm'
            disabled={isPending || !body.trim()}
            aria-label={submitLabel}
            bg={palette.ink}
            color={palette.textOnInk}
            _hover={{ bg: palette.inkHover }}
            loading={isPending}
            onClick={() => focusTextarea()}
          >
            <Send size={14} aria-hidden />
            {submitLabel}
          </Button>
        </Flex>
      </Stack>
    </form>
  )
}

function SuggestionRow({
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
      // onMouseDown is prevented on the panel, so click still fires here.
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
              <HighlightedText parts={name} />
            </Text>
            <RoleBadge role={user.role} />
          </Flex>
          <Text fontSize='2xs' color={palette.textMuted} truncate>
            @<HighlightedText parts={username} /> · ID {user.id.slice(0, 8)}
          </Text>
        </Stack>
      </Flex>
    </chakra.button>
  )
}

function HighlightedText({ parts }: { parts: { before: string; match: string; after: string } }) {
  return (
    <>
      {parts.before}
      {parts.match ? (
        <Text as='mark' bg={palette.accentSoft} color={palette.accent} px='0.5' borderRadius='xs'>
          {parts.match}
        </Text>
      ) : null}
      {parts.after}
    </>
  )
}
