import { Box, Flex, Stack, Text } from '@chakra-ui/react'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { transitions } from '../theme/motion.ts'
import { palette } from '../theme/palette.ts'
import { type Tone, tones } from '../theme/statusTone.ts'
import { AnimatedNumber } from './motion/AnimatedNumber.tsx'
import { Reveal } from './Reveal.tsx'
import { Surface } from './Surface.tsx'

/**
 * A dashboard metric card.
 *
 * Hierarchy is: label → value → context. The value is the only large type on
 * the card. Numeric values count up to their real number (see
 * `AnimatedNumber`); strings such as the `—` loading placeholder are rendered
 * as-is. `hint` carries a comparison or a qualifier and is only passed when the
 * number is trustworthy (for example a same-window delta computed from real
 * daily counts). When a `to` is given the whole card links to the filtered list
 * that explains the number.
 *
 * The card enters with a small rise and lifts 2 px on hover/focus. Motion is
 * limited to `transform` and `box-shadow`, so it never reflows the grid.
 */
export function MetricCard({
  label,
  value,
  icon: Icon,
  tone = 'neutral',
  hint,
  footer,
  to,
  ariaLabel,
  delay = 0,
}: {
  label: string
  value: number | string
  icon?: LucideIcon
  tone?: Tone
  hint?: ReactNode
  footer?: ReactNode
  to?: string
  ariaLabel?: string
  /** Stagger delay for the card's entrance, in milliseconds. */
  delay?: number
}) {
  const paletteTone = tones[tone]
  const interactive = Boolean(to)
  // Scope the remembered value to the current workspace page. A single account
  // has exactly one role, so this cannot mix one role's number with another's;
  // it only stops a revisit of the same page from counting up from zero again.
  const { pathname } = useLocation()

  const body = (
    <Surface
      as='div'
      p='4'
      height='full'
      position='relative'
      transition={transitions.lift}
      _hover={
        interactive
          ? {
              borderColor: palette.borderStrong,
              bg: palette.surface,
              transform: 'translateY(-2px)',
              boxShadow: palette.shadowMd,
            }
          : undefined
      }
      _focusWithin={
        interactive
          ? {
              borderColor: palette.accentBorder,
              boxShadow: `0 0 0 1px ${palette.accentBorder}`,
            }
          : undefined
      }
    >
      <Stack gap='3' height='full' justify='space-between'>
        <Flex align='flex-start' justify='space-between' gap='2'>
          <Text
            fontSize='xs'
            color={palette.textMuted}
            fontWeight='medium'
            letterSpacing='0.01em'
            lineClamp={2}
          >
            {label}
          </Text>
          {Icon ? (
            <Flex
              boxSize='7'
              align='center'
              justify='center'
              borderRadius='l2'
              bg={tone === 'neutral' ? palette.surfaceMuted : paletteTone.soft}
              color={tone === 'neutral' ? palette.textMuted : paletteTone.solid}
              flexShrink={0}
            >
              <Icon size={14} strokeWidth={2} aria-hidden />
            </Flex>
          ) : null}
        </Flex>

        <Box>
          <Text
            fontSize={{ base: '2xl', md: '3xl' }}
            fontWeight='semibold'
            letterSpacing='-0.03em'
            lineHeight='1'
            color={palette.text}
            fontVariantNumeric='tabular-nums'
          >
            <AnimatedNumber value={value} cacheKey={`${pathname}:${to ?? ''}:${label}`} />
          </Text>
          {hint ? (
            <Text fontSize='2xs' color={palette.textMuted} mt='2' lineClamp={2}>
              {hint}
            </Text>
          ) : null}
        </Box>

        {footer ? <Box>{footer}</Box> : null}
      </Stack>
    </Surface>
  )

  const content = to ? (
    <Box
      asChild
      display='block'
      height='full'
      _focusVisible={{ outline: '2px solid', outlineColor: palette.focus, outlineOffset: '2px' }}
      borderRadius='l3'
    >
      <Link to={to} aria-label={ariaLabel ?? `${label}: ${value}`} style={{ textDecoration: 'none' }}>
        {body}
      </Link>
    </Box>
  ) : (
    body
  )

  return (
    <Reveal delay={delay} y={12} height='full'>
      {content}
    </Reveal>
  )
}
