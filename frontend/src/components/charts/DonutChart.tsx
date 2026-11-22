import { Box, Flex, Stack, Text } from '@chakra-ui/react'
import { useCallback, useMemo } from 'react'

import { useElementWidth } from '../../hooks/useElementWidth.ts'
import { useEntrance } from '../../hooks/useEntrance.ts'
import { placeTooltip } from '../../lib/tooltipPosition.ts'
import { motionVars, stagger } from '../../theme/motion.ts'
import { palette } from '../../theme/palette.ts'
import { AnimatedNumber } from '../motion/AnimatedNumber.tsx'
import { ChartDataTable } from './ChartCard.tsx'
import { ChartTooltip } from './ChartTooltip.tsx'
import { useChartTooltip } from './useChartTooltip.ts'

/**
 * Status composition donut.
 *
 * Segments are drawn as stroked arcs on a circle (no path math needed) and the
 * total sits in the middle. Hovering or focusing a legend row (or an arc)
 * highlights the matching segment and swaps the centre label to that slice,
 * which keeps the chart readable at small sizes where segment labels would not
 * fit.
 *
 * A rich tooltip follows the active slice — whether it was activated from the
 * legend, the arc itself or by keyboard focus — and reports the real count, the
 * share of every ticket, and the slice's role in the workflow. The tooltip is
 * positioned inside the chart's own wrapper, so it is never clipped by a card
 * or hidden behind the next grid cell.
 *
 * On first appearance each arc grows from zero length to exactly its real
 * share of the circle via an animated `stroke-dasharray`, and the arcs are
 * staggered so the composition assembles itself clockwise. The centre number
 * and every percentage count up from zero to the same real values used by the
 * legend, so the visual and the numbers can never disagree.
 *
 * The SVG is decorative; the legend plus `ChartDataTable` carry the meaning.
 */

export interface DonutSlice {
  key: string
  label: string
  value: number
  color: string
  /** Optional second line of context, e.g. what the status means. */
  description?: string
}

const SIZE = 168
const STROKE = 18
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS
/**
 * Conservative tooltip footprint used for edge clamping before it paints.
 * Measured against the live panel (≈224 × 114 with a note, ≈224 × 84 without),
 * rounded up so the flip decision is never optimistic.
 */
const TOOLTIP_W = 232
const TOOLTIP_H = 92
const TOOLTIP_H_WITH_NOTE = 120

/**
 * Below this container width the donut and legend no longer fit side by side:
 * the legend labels get squeezed to zero. Stacking them keeps the labels
 * readable in the narrower cards produced by a two-column dashboard grid.
 */
const STACK_BREAKPOINT = 424

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
  const entered = useEntrance()
  const { ref: measureRef, width } = useElementWidth<HTMLDivElement>()
  const tooltip = useChartTooltip<HTMLDivElement>()
  const stacked = width !== null && width < STACK_BREAKPOINT

  // One element is both the width probe and the tooltip's coordinate origin,
  // so the tooltip clamp and the layout decision always agree.
  const setContainer = useCallback(
    (node: HTMLDivElement | null) => {
      measureRef.current = node
      tooltip.containerRef.current = node
    },
    [measureRef, tooltip.containerRef],
  )

  const total = useMemo(() => slices.reduce((sum, slice) => sum + slice.value, 0), [slices])
  const active = slices.find((slice) => slice.key === tooltip.activeKey) ?? null

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

  const tooltipPlacement =
    active && tooltip.anchor
      ? placeTooltip(tooltip.anchor, {
          containerWidth: tooltip.containerRef.current?.clientWidth ?? 0,
          containerHeight: tooltip.containerRef.current?.clientHeight ?? 0,
          tooltipWidth: TOOLTIP_W,
          tooltipHeight: active.description ? TOOLTIP_H_WITH_NOTE : TOOLTIP_H,
        })
      : null

  return (
    <Box ref={setContainer} position='relative' minW='0'>
      <Flex
        direction={stacked ? 'column' : 'row'}
        align={stacked ? 'stretch' : 'center'}
        gap={stacked ? '5' : '7'}
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
                {segments.map((segment, index) => {
                  const isActive = tooltip.activeKey === segment.slice.key
                  const dimmed = tooltip.activeKey !== null && !isActive
                  // Before entrance the arc has zero dash length, so it grows out
                  // of the 12 o'clock start point instead of appearing whole.
                  const dash = entered ? segment.length : 0
                  return (
                    <circle
                      key={segment.slice.key}
                      cx={SIZE / 2}
                      cy={SIZE / 2}
                      r={RADIUS}
                      fill='none'
                      stroke={segment.slice.color}
                      strokeWidth={isActive ? STROKE + 4 : STROKE}
                      strokeDasharray={`${dash} ${CIRCUMFERENCE - dash}`}
                      strokeDashoffset={-segment.offset}
                      strokeLinecap='butt'
                      opacity={dimmed ? 0.35 : 1}
                      onPointerEnter={(event) => tooltip.showForPointer(segment.slice.key, event)}
                      onPointerLeave={tooltip.hide}
                      style={{
                        cursor: onSelect ? 'pointer' : 'default',
                        transition: `stroke-dasharray ${motionVars.chart} ${motionVars.easeOut} ${
                          stagger(index)
                        }ms, stroke-width ${motionVars.fast} ${motionVars.ease}, opacity ${
                          motionVars.fast
                        } ${motionVars.ease}`,
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
                <AnimatedNumber value={centerValue} duration={640} />
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
            const isActive = tooltip.activeKey === slice.key
            const row = (
              <Flex
                align='center'
                gap='2.5'
                px='2'
                py='1.5'
                borderRadius='l2'
                bg={isActive ? palette.hover : 'transparent'}
                transition='background var(--hd-dur-1) var(--hd-ease)'
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
                  <AnimatedNumber value={slice.value} duration={640} />
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
                _focusVisible={{
                  outline: '2px solid',
                  outlineColor: palette.focus,
                  outlineOffset: '2px',
                }}
              >
                <button
                  type='button'
                  onClick={() => onSelect(slice)}
                  onPointerEnter={(event) => tooltip.showForPointer(slice.key, event)}
                  onPointerLeave={tooltip.hide}
                  onFocus={(event) => tooltip.showForElement(slice.key, event.currentTarget)}
                  onBlur={tooltip.hide}
                  style={{ textAlign: 'left' }}
                >
                  {row}
                </button>
              </Box>
            ) : (
              <Box
                key={slice.key}
                onPointerEnter={(event) => tooltip.showForPointer(slice.key, event)}
                onPointerLeave={tooltip.hide}
              >
                {row}
              </Box>
            )
          })}
        </Stack>
      </Flex>

      {active && tooltipPlacement ? (
        <ChartTooltip
          placement={tooltipPlacement}
          title={active.label}
          color={active.color}
          value={active.value.toLocaleString('en-US')}
          valueSuffix={active.value === 1 ? 'ticket' : 'tickets'}
          secondary={`${total > 0 ? Math.round((active.value / total) * 100) : 0}% of ${total.toLocaleString('en-US')} tickets`}
        >
          {active.description ? (
            <Text fontSize='2xs' color={palette.textFaint} mt='1.5' lineHeight='1.4'>
              {active.description}
            </Text>
          ) : null}
        </ChartTooltip>
      ) : null}

      <ChartDataTable
        caption={ariaLabel}
        columns={['Status', 'Tickets', 'Share']}
        rows={slices.map((slice) => [
          slice.label,
          slice.value,
          `${total > 0 ? Math.round((slice.value / total) * 100) : 0}%`,
        ])}
      />
    </Box>
  )
}
