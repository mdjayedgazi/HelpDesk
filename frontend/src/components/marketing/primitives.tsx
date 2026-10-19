import { Box, Flex, Heading, Text, type BoxProps } from '@chakra-ui/react'
import type { ReactNode } from 'react'

import { palette } from '../../theme/palette.ts'

/**
 * Small uppercase label that introduces a marketing section.
 *
 * A monochrome `Panel` (rather than a coloured chip) keeps the identity
 * restrained while still giving each section a clear entry point.
 */
export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <Flex
      as='span'
      display='inline-flex'
      alignSelf='flex-start'
      align='center'
      gap='2'
      px='2.5'
      py='1'
      borderWidth='1px'
      borderColor={palette.border}
      borderRadius='full'
      bg={palette.surface}
      color={palette.textSecondary}
      fontSize='2xs'
      fontWeight='medium'
      letterSpacing='0.08em'
      textTransform='uppercase'
    >
      <Box boxSize='1.5' borderRadius='full' bg={palette.ink} aria-hidden />
      {children}
    </Flex>
  )
}

/** A neutral marketing card with a soft, theme-aware elevation. */
export function Panel({ children, elevated = false, ...rest }: BoxProps & { elevated?: boolean }) {
  return (
    <Box
      bg={palette.surface}
      borderWidth='1px'
      borderColor={palette.border}
      borderRadius='l4'
      boxShadow={elevated ? palette.shadowPanel : palette.shadowSm}
      {...rest}
    >
      {children}
    </Box>
  )
}

export function SectionTitle({ children, ...rest }: BoxProps) {
  return (
    <Heading
      as='h2'
      fontSize={{ base: '2xl', md: '3xl', lg: '4xl' }}
      fontWeight='semibold'
      letterSpacing='-0.03em'
      lineHeight='1.1'
      color={palette.text}
      textWrap='balance'
      {...rest}
    >
      {children}
    </Heading>
  )
}

export function SectionLead({ children, ...rest }: BoxProps) {
  return (
    <Text fontSize={{ base: 'sm', md: 'md' }} color={palette.textSecondary} lineHeight='1.7' {...rest}>
      {children}
    </Text>
  )
}

/**
 * Small monochrome status dot used across the illustrative product visuals.
 * The status is always paired with a text label, never colour alone.
 */
export function StatusDot({ filled = false }: { filled?: boolean }) {
  return (
    <Box
      boxSize='2'
      borderRadius='full'
      borderWidth='1px'
      borderColor={filled ? palette.ink : palette.borderStrong}
      bg={filled ? palette.ink : 'transparent'}
      flexShrink={0}
      aria-hidden
    />
  )
}
