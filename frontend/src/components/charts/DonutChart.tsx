import { Box, Flex, Stack, Text } from '@chakra-ui/react'
import { useMemo, useState } from 'react'

import { palette } from '../../theme/palette.ts'
import { ChartDataTable } from './ChartCard.tsx'

/**
 * Status composition donut.
 *
 * Segments are drawn as stroked arcs on a circle (no path math needed) and the
 * total sits in the middle. Hovering or focusing a legend row highlights the
 * matching segment and swaps the centre label to that slice, which keeps the
 * chart readable at small sizes where segment labels would not fit.
 *
 * The SVG is decorative; the legend plus `ChartDataTable` carry the meaning.
 */

export interface DonutSlice {
  key: string
  label: string
  value: number
  color: string
}

const SIZE = 168
const STROKE = 18
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export function DonutChart({
  slices,
  centerLabel,
  ariaLabel,
  onSelect,
}: {
  slices: DonutSlice[]
  centerLabel: string
  ariaLabel: string
  /** When provided, a slice and its legend row become a link to a filtered list. */
  onSelect?: (slice: DonutSlice) => void
}) {
  const [activeKey, setActiveKey] = useState<string | null>(null)

  const total = useMemo(() => slices.reduce((sum, slice) => sum + slice.value, 0), [slices])
  const active = slices.find((slice) => slice.key === activeKey) ?? null

  const segments = useMemo(() => {
    let offset = 0
    return slices
      .filter((slice) => slice.value > 0)
      .map((slice) => {
        const fraction = total > 0 ? slice.value / total : 0
        const length = fraction * CIRCUMFERENCE
        const segment = { slice, offset, length, fraction }
        offset += length
        return segment
      })
  }, [slices, total])

  if (total === 0) return null

  const centerValue = active ? active.value : total
  const centerText = active ? active.label : centerLabel
  const centerPercent = active ? Math.round((active.value / total) * 100) : null


  return (
    <Flex
      direction={{ base: 'column', sm: 'row' }}
      align={{ base: 'stretch', sm: 'center' }}
      gap={{ base: '5', sm: '7' }}
      minW='0'
    >
      <Flex align='center' justify='center' flexShrink={0}>
        <Box position='relative' width={`${SIZE}px`} height={`${SIZE}px`}>
          <svg
            viewBox={`0 0 ${SIZE} ${SIZE}`}
            width={SIZE}
            height={SIZE}
            role='presentation'
            aria-hidden='true'
            className='hd-chart-enter'
          >
            <circle
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={RADIUS}
              fill='none'
              stroke={palette.inset}
              strokeWidth={STROKE}
            />
            <g transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}>
              {segments.map((segment) => {
                const isActive = activeKey === segment.slice.key
                const dimmed = activeKey !== null && !isActive
                return (
                  <circle
                    key={segment.slice.key}
                    cx={SIZE / 2}
                    cy={SIZE / 2}
                    r={RADIUS}
                    fill='none'
                    stroke={segment.slice.color}
                    strokeWidth={isActive ? STROKE + 4 : STROKE}
                    strokeDasharray={`${segment.length} ${CIRCUMFERENCE - segment.length}`}
                    strokeDashoffset={-segment.offset}
                    strokeLinecap='butt'
                    opacity={dimmed ? 0.35 : 1}
                    style={{
                      transition: `stroke-width var(--hd-dur-1) var(--hd-ease), opacity var(--hd-dur-1) var(--hd-ease)`,
                    }}
                  />
                )
              })}
            </g>
          </svg>

          <Flex
            position='absolute'
            inset='0'
            direction='column'
            align='center'
            justify='center'
            textAlign='center'
            px='4'
            pointerEvents='none'
          >
            <Text
              fontSize='2xl'
              fontWeight='semibold'
              letterSpacing='-0.03em'
              color={palette.text}
              fontVariantNumeric='tabular-nums'
              lineHeight='1'
            >
              {centerValue}
            </Text>
            <Text fontSize='2xs' color={palette.textMuted} mt='1' lineClamp={2}>
              {centerPercent !== null ? `${centerPercent}% · ${centerText}` : centerText}
            </Text>
          </Flex>
        </Box>
      </Flex>

      <Stack gap='1' flex='1' minW='0'>
        {slices.map((slice) => {
          const percent = total > 0 ? Math.round((slice.value / total) * 100) : 0
          const isActive = activeKey === slice.key
          const row = (
            <Flex
              align='center'
              gap='2.5'
              px='2'
              py='1.5'
              borderRadius='l2'
              bg={isActive ? palette.hover : 'transparent'}
              transition='background var(--hd-dur-1) var(--hd-ease)'
              onMouseEnter={() => setActiveKey(slice.key)}
              onMouseLeave={() => setActiveKey(null)}
              onFocus={() => setActiveKey(slice.key)}
              onBlur={() => setActiveKey(null)}
              width='full'
            >
              <Box boxSize='2' borderRadius='full' bg={slice.color} flexShrink={0} aria-hidden />
              <Text fontSize='xs' color={palette.textSecondary} flex='1' minW='0' truncate>
                {slice.label}
              </Text>
              <Text
                fontSize='xs'
                color={palette.text}
                fontWeight='medium'
                fontVariantNumeric='tabular-nums'
              >
                {slice.value}
              </Text>
              <Text
                fontSize='2xs'
                color={palette.textFaint}
                fontVariantNumeric='tabular-nums'
                minW='8'
                textAlign='right'
              >
                {percent}%
              </Text>
            </Flex>
          )

          return onSelect ? (
            <Box
              key={slice.key}
              asChild
              borderRadius='l2'
              cursor='pointer'
              _hover={{ bg: palette.hover }}
            >
              <button type='button' onClick={() => onSelect(slice)} style={{ textAlign: 'left' }}>
                {row}
              </button>
            </Box>
          ) : (
            <Box key={slice.key}>{row}</Box>
          )
        })}
      </Stack>

      <ChartDataTable
        caption={ariaLabel}
        columns={['Status', 'Tickets', 'Share']}
        rows={slices.map((slice) => [
          slice.label,
          slice.value,
          `${total > 0 ? Math.round((slice.value / total) * 100) : 0}%`,
        ])}
      />
    </Flex>
  )
}
