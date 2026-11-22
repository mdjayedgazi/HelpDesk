import { Box, Flex, Text } from '@chakra-ui/react'
import type { ReactNode } from 'react'

import type { TooltipPlacement } from '../../lib/tooltipPosition.ts'
import { palette } from '../../theme/palette.ts'

/**
 * A small information panel for chart hover/focus.
 *
 * It is rendered inside the chart's own relatively-positioned wrapper (not a
 * portal), so it can never be hidden behind a card or clipped by a scroll
 * container, and its position is plain inline CSS. `placement` is produced by
 * `placeTooltip`, which keeps it inside the container and flips it when needed.
 *
 * The panel is visual duplication of data that already exists in the chart
 * legend and the visually hidden table, so it is marked `aria-hidden` to stop
 * screen readers announcing it on top of the real controls.
 */
export function ChartTooltip({
  placement,
  title,
  color,
  value,
  valueSuffix,
  secondary,
  children,
}: {
  placement: TooltipPlacement
  title: string
  color: string
  value: ReactNode
  /** e.g. "tickets". */
  valueSuffix?: string
  /** A short supporting line, e.g. "38% of all tickets". */
  secondary?: ReactNode
  children?: ReactNode
}) {
  return (
    <Box
      aria-hidden='true'
      position='absolute'
      left={`${placement.left}px`}
      top={`${placement.top}px`}
      zIndex='10'
      minW='40'
      maxW='56'
      px='3'
      py='2.5'
      bg={palette.elevated}
      borderWidth='1px'
      borderColor={palette.borderStrong}
      borderRadius='l3'
      boxShadow={palette.shadowMd}
      pointerEvents='none'
      className='hd-tooltip-in'
      data-side={placement.side}
      role='presentation'
    >
      <Flex align='center' gap='2' mb='1'>
        <Box boxSize='2' borderRadius='full' bg={color} flexShrink={0} />
        <Text fontSize='2xs' fontWeight='semibold' color={palette.text} truncate>
          {title}
        </Text>
      </Flex>
      <Flex align='baseline' gap='1.5'>
        <Text
          fontSize='lg'
          fontWeight='semibold'
          color={palette.text}
          lineHeight='1.1'
          fontVariantNumeric='tabular-nums'
        >
          {value}
        </Text>
        {valueSuffix ? (
          <Text fontSize='2xs' color={palette.textMuted}>
            {valueSuffix}
          </Text>
        ) : null}
      </Flex>
      {secondary ? (
        <Text fontSize='2xs' color={palette.textMuted} mt='1' fontVariantNumeric='tabular-nums'>
          {secondary}
        </Text>
      ) : null}
      {children}
    </Box>
  )
}
