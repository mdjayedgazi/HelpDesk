import { Box, Flex, Stack, Text } from '@chakra-ui/react'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { palette } from '../theme/palette.ts'
import { type Tone, tones } from '../theme/statusTone.ts'
import { Surface } from './Surface.tsx'

/**
 * A dashboard metric card.
 *
 * Hierarchy is: label → value → context. The value is the only large type on
 * the card. `hint` carries a comparison or a qualifier and is only passed when
 * the number is trustworthy (for example a same-window delta computed from real
 * daily counts). When a `to` is given the whole card links to the filtered list
 * that explains the number.
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
}: {
  label: string
  value: number | string
  icon?: LucideIcon
  tone?: Tone
  hint?: ReactNode
  footer?: ReactNode
  to?: string
  ariaLabel?: string
}) {
  const paletteTone = tones[tone]

  const body = (
    <Surface
      as='div'
      p='4'
      height='full'
      position='relative'
      transition='border-color var(--hd-dur-2) var(--hd-ease), background var(--hd-dur-2) var(--hd-ease)'
      _hover={to ? { borderColor: palette.borderStrong, bg: palette.surface } : undefined}
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
            {value}
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

  if (!to) return body

  return (
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
  )
}

/** A compact metric used inside a single surface (e.g. a dashboard header). */
export function InlineMetric({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: number | string
  tone?: Tone
}) {
  return (
    <Flex direction='column' gap='1' minW='0'>
      <Text fontSize='2xs' color={palette.textMuted} truncate>
        {label}
      </Text>
      <Flex align='center' gap='2'>
        <Box boxSize='1.5' borderRadius='full' bg={tones[tone].solid} aria-hidden />
        <Text
          fontSize='lg'
          fontWeight='semibold'
          letterSpacing='-0.02em'
          color={palette.text}
          fontVariantNumeric='tabular-nums'
        >
          {value}
        </Text>
      </Flex>
    </Flex>
  )
}
