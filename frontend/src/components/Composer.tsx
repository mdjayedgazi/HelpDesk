import { Button, Flex, SegmentGroup, Stack, Text } from '@chakra-ui/react'
import { Lock, Send } from 'lucide-react'
import { useState } from 'react'

import { palette } from '../theme/palette.ts'
import { TextAreaInput } from './FormField.tsx'

const MAX_LENGTH = 10000

export interface ComposerSubmit {
  body: string
  is_internal: boolean
}

export function Composer({
  onSubmit,
  isPending = false,
  allowInternal = false,
  placeholder = 'Write a reply…',
  submitLabel = 'Send reply',
  maxLength = MAX_LENGTH,
}: {
  onSubmit: (input: ComposerSubmit) => unknown
  isPending?: boolean
  allowInternal?: boolean
  placeholder?: string
  submitLabel?: string
  maxLength?: number
}) {
  const [body, setBody] = useState('')
  const [mode, setMode] = useState<'public' | 'internal'>('public')
  const [error, setError] = useState<string | null>(null)

  const internal = allowInternal && mode === 'internal'

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
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
    try {
      await onSubmit({ body: trimmed, is_internal: internal })
      setBody('')
      setMode('public')
    } catch {
      // Errors are surfaced by the caller (toast / inline) — keep the draft.
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <Stack gap='3'>
        {allowInternal ? (
          <SegmentGroup.Root
            size='xs'
            value={mode}
            onValueChange={(details) => {
              if (details.value) setMode(details.value as 'public' | 'internal')
            }}
            bg={palette.surfaceMuted}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l2'
            p='0.5'
            width='fit-content'
          >
            <SegmentGroup.Indicator bg={palette.surface} borderRadius='xs' />
            <SegmentGroup.Item value='public' px='3' py='1' cursor='pointer'>
              <SegmentGroup.ItemHiddenInput />
              <SegmentGroup.ItemText fontSize='xs' fontWeight='medium'>
                Reply
              </SegmentGroup.ItemText>
            </SegmentGroup.Item>
            <SegmentGroup.Item value='internal' px='3' py='1' cursor='pointer'>
              <SegmentGroup.ItemHiddenInput />
              <Flex align='center' gap='1.5'>
                <Lock size={12} aria-hidden />
                <SegmentGroup.ItemText fontSize='xs' fontWeight='medium'>
                  Internal note
                </SegmentGroup.ItemText>
              </Flex>
            </SegmentGroup.Item>
          </SegmentGroup.Root>
        ) : null}

        <TextAreaInput
          value={body}
          onChange={(event) => setBody(event.target.value)}
          placeholder={internal ? 'Write a note only your team can see…' : placeholder}
          minH='24'
          aria-label={internal ? 'Internal note' : 'Reply message'}
          aria-invalid={Boolean(error)}
        />

        <Flex align='center' justify='space-between' gap='3' wrap='wrap'>
          <Text
            fontSize='xs'
            color={error ? palette.text : palette.textMuted}
            role={error ? 'alert' : undefined}
          >
            {error ?? `${body.trim().length}/${maxLength}`}
          </Text>
          <Button
            type='submit'
            size='sm'
            bg={palette.ink}
            color={palette.textOnInk}
            _hover={{ bg: palette.inkHover }}
            loading={isPending}
            disabled={!body.trim()}
          >
            <Send size={14} aria-hidden />
            {internal ? 'Add note' : submitLabel}
          </Button>
        </Flex>
      </Stack>
    </form>
  )
}
