import { Button, Flex, Stack, Text, chakra } from '@chakra-ui/react'
import { CheckCircle2, Star } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { useMe } from '../hooks/useMe.ts'
import { useSubmitTicketFeedback, useTicketFeedback } from '../hooks/useFeedback.ts'
import { errorMessage } from '../lib/errors.ts'
import { formatDateTime } from '../lib/format.ts'
import type { TicketFeedback } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'
import { Surface } from './Surface.tsx'
import { toaster } from './Toaster.tsx'

const RATING_LABELS: Record<number, string> = {
  1: 'Very poor',
  2: 'Poor',
  3: 'Okay',
  4: 'Good',
  5: 'Excellent',
}

/**
 * The customer feedback section of a ticket.
 *
 * Rendered only for the ticket's own customer, and only when the backend says
 * the ticket is resolved and unanswered (`can_submit`). Once answered it shows
 * the submitted rating read-only; staff never see the form, only a submitted
 * answer when one exists.
 */
export function FeedbackPanel({ ticketId }: { ticketId: string }) {
  const me = useMe()
  const isCustomer = me.data?.role === 'customer'
  // Staff may read a submitted answer too; the backend decides visibility.
  const feedback = useTicketFeedback(ticketId)

  // A "share feedback" notification links to `#feedback`; the section is
  // rendered asynchronously, so scroll once the answer state has actually
  // arrived and the element exists.
  useEffect(() => {
    if (window.location.hash !== '#feedback') return
    if (!feedback.data) return
    document.getElementById('feedback')?.scrollIntoView({ block: 'start' })
  }, [feedback.data])

  // Staff (and any non-customer viewer) only ever see an answer that exists.
  if (!isCustomer) {
    if (!feedback.data?.feedback) return null
    return <SubmittedFeedback feedback={feedback.data.feedback} />
  }

  if (feedback.isPending || feedback.isError || !feedback.data) return null
  const state = feedback.data

  if (state.feedback) {
    return <SubmittedFeedback feedback={state.feedback} />
  }
  if (!state.can_submit) {
    // Landing here from a feedback notification after the ticket moved on is
    // worth explaining, but a closed/never-resolved ticket shows no section.
    if (window.location.hash !== '#feedback') return null
    return (
      <Surface id='feedback' p={{ base: '5', md: '6' }} scrollMarginTop='20'>
        <Stack gap='2'>
          <Text fontSize='md' fontWeight='medium' color={palette.text}>
            Feedback unavailable
          </Text>
          <Text fontSize='sm' color={palette.textSecondary}>
            Feedback can be shared once this ticket has been resolved by the
            support team.
          </Text>
        </Stack>
      </Surface>
    )
  }

  return <FeedbackForm ticketId={ticketId} />
}

function SubmittedFeedback({ feedback }: { feedback: TicketFeedback }) {
  return (
    <Surface id='feedback' p={{ base: '5', md: '6' }} scrollMarginTop='20'>
      <Stack gap='3'>
        <Flex align='center' gap='2'>
          <CheckCircle2 size={16} color={palette.textSecondary} aria-hidden />
          <Text fontSize='md' fontWeight='medium' color={palette.text}>
            Your feedback
          </Text>
        </Flex>
        <Flex align='center' gap='2'>
          <Stars value={feedback.rating} readOnly />
          <Text fontSize='sm' color={palette.textSecondary}>
            {RATING_LABELS[feedback.rating] ?? `${feedback.rating} of 5`}
          </Text>
        </Flex>
        {feedback.comment ? (
          <Text fontSize='sm' color={palette.textSecondary} whiteSpace='pre-wrap'>
            {feedback.comment}
          </Text>
        ) : null}
        <Text fontSize='xs' color={palette.textFaint}>
          Submitted {formatDateTime(feedback.created_at)}
        </Text>
      </Stack>
    </Surface>
  )
}

function FeedbackForm({ ticketId }: { ticketId: string }) {
  const submit = useSubmitTicketFeedback(ticketId)
  const [rating, setRating] = useState(0)
  const [comment, setComment] = useState('')

  const onSubmit = async () => {
    if (rating < 1) return
    try {
      await submit.mutateAsync({ rating, comment: comment.trim() || null })
      toaster.create({
        title: 'Thank you for your feedback',
        description: 'Your rating was recorded for this ticket.',
      })
    } catch (error) {
      toaster.create({
        title: 'Could not submit feedback',
        description: errorMessage(error),
        type: 'error',
      })
    }
  }

  return (
    <Surface id='feedback' p={{ base: '5', md: '6' }} scrollMarginTop='20'>
      <Stack gap='4'>
        <Stack gap='1'>
          <Text fontSize='md' fontWeight='medium' color={palette.text}>
            Share your feedback
          </Text>
          <Text fontSize='sm' color={palette.textSecondary}>
            This ticket is resolved. How did we do?
          </Text>
        </Stack>

        <Flex align='center' gap='3'>
          <Stars value={rating} onChange={setRating} />
          <Text fontSize='sm' color={palette.textSecondary} aria-live='polite'>
            {rating > 0 ? RATING_LABELS[rating] : 'Select a rating'}
          </Text>
        </Flex>

        <chakra.textarea
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          maxLength={1000}
          rows={3}
          placeholder='Anything you would like to add? (optional)'
          aria-label='Feedback comment (optional)'
          width='full'
          resize='vertical'
          fontSize='sm'
          color={palette.text}
          bg={palette.surface}
          borderWidth='1px'
          borderColor={palette.border}
          borderRadius='l2'
          px='3'
          py='2'
          _placeholder={{ color: palette.textFaint }}
          _focusVisible={{
            outline: '2px solid',
            outlineColor: palette.ink,
            outlineOffset: '1px',
          }}
        />

        <Flex justify='flex-end'>
          <Button
            size='sm'
            bg={palette.ink}
            color={palette.textOnInk}
            _hover={{ bg: palette.inkHover }}
            disabled={rating < 1}
            loading={submit.isPending}
            onClick={() => void onSubmit()}
          >
            Submit feedback
          </Button>
        </Flex>
      </Stack>
    </Surface>
  )
}

/** A 1-5 star control. Interactive when ``onChange`` is given. */
function Stars({
  value,
  onChange,
  readOnly = false,
}: {
  value: number
  onChange?: (value: number) => void
  readOnly?: boolean
}) {
  const buttons = useRef<Array<HTMLButtonElement | null>>([])
  const selected = value >= 1 ? value : 1

  const select = (next: number) => {
    const clamped = Math.min(5, Math.max(1, next))
    onChange?.(clamped)
    buttons.current[clamped - 1]?.focus()
  }

  return (
    <Flex
      gap='1'
      role={readOnly ? 'img' : 'radiogroup'}
      aria-label={readOnly ? `Rated ${value} of 5` : 'Rate this ticket'}
      onKeyDown={(event) => {
        if (readOnly || !onChange) return
        if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
          event.preventDefault()
          select(selected + 1)
        } else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
          event.preventDefault()
          select(selected - 1)
        } else if (event.key === 'Home') {
          event.preventDefault()
          select(1)
        } else if (event.key === 'End') {
          event.preventDefault()
          select(5)
        }
      }}
    >
      {[1, 2, 3, 4, 5].map((star) => {
        const filled = star <= value
        if (readOnly) {
          return (
            <Star
              key={star}
              size={16}
              aria-hidden
              color={filled ? palette.ink : palette.border}
              fill={filled ? palette.ink : 'none'}
            />
          )
        }
        return (
          <chakra.button
            key={star}
            ref={(node: HTMLButtonElement | null) => {
              buttons.current[star - 1] = node
            }}
            type='button'
            role='radio'
            aria-checked={star === value}
            aria-label={`${star} of 5 — ${RATING_LABELS[star]}`}
            tabIndex={star === selected ? 0 : -1}
            onClick={() => select(star)}
            bg='transparent'
            border='none'
            p='0.5'
            cursor='pointer'
            borderRadius='l1'
            _focusVisible={{
              outline: '2px solid',
              outlineColor: palette.ink,
              outlineOffset: '1px',
            }}
          >
            <Star
              size={20}
              aria-hidden
              color={filled ? palette.ink : palette.textFaint}
              fill={filled ? palette.ink : 'none'}
            />
          </chakra.button>
        )
      })}
    </Flex>
  )
}
