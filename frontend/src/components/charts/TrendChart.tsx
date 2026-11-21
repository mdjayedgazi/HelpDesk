import { Box, Flex, Skeleton, Text } from '@chakra-ui/react'
import { useId, useMemo, useState } from 'react'

import { useElementWidth } from '../../hooks/useElementWidth.ts'
import { useEntrance } from '../../hooks/useEntrance.ts'
import { motionVars, stagger } from '../../theme/motion.ts'
import { palette } from '../../theme/palette.ts'
import { ChartDataTable } from './ChartCard.tsx'

/**
 * Ticket-volume trend.
 *
 * A two-series area/line chart drawn with plain SVG. It is intentionally
 * dependency-free: the app already ships Chakra + Tailwind, and a real charting
 * library would add ~40 kB for one shape. Everything here is a function of the
 * data passed in (`daily` points from the backend), so there are no invented
 * numbers and no misleading scales:
 *
 * - the y axis always starts at zero and is rounded up to a "nice" step;
 * - x labels are real dates, spaced evenly, never interpolated;
 * - a hover band reveals the exact values for one day.
 *
 * On first appearance every series draws itself left-to-right (a normalised
 * `pathLength` dash offset, so it works at any width) and each area fill fades
 * in only after its line has finished. The geometry is computed from the real
 * data, so the final drawing is exactly the series passed in.
 *
 * The SVG is `aria-hidden`; the adjacent `ChartDataTable` is the accessible
 * representation, so screen readers get real rows and headers.
 */

export interface TrendSeries {
  key: string
  label: string
  /** Stroke colour; the area gradient is derived from it. */
  color: string
}

export interface TrendPoint {
  label: string
  values: Record<string, number>
}

const H = 220
const MIN_W = 280
const PAD_L = 34
const PAD_R = 8
const PAD_T = 12
const PAD_B = 26

/** Axis label font size, in px. Mirrors the `fontSize` on the <text> nodes. */
const LABEL_FONT_SIZE = 10
/**
 * Advance width of one character at 10px, in px.
 *
 * Measured in headless Chromium against this product's font stack (Inter, with
 * a system fallback) at 10px: ~8.4–9.0 px per glyph for date labels such as
 * "Nov 12". The value below is deliberately at the high end so the estimate
 * never under-reports and lets two labels collide when a fallback font is
 * wider than expected. A slightly conservative estimate costs one fewer tick;
 * an optimistic one produces overlapping text.
 */
const LABEL_CHAR_WIDTH = 9
/** Minimum clear gap between two adjacent label boxes, in px. */
const LABEL_GAP = 12

interface LabelBox {
  index: number
  /** Left edge of the painted text box. */
  left: number
  /** Right edge of the painted text box. */
  right: number
}

/**
 * Choose which x-axis labels to paint so they never collide or clip.
 *
 * The previous implementation used a fixed `ceil(n / 6)` interval and then
 * always added the final date. For a 14-day series that placed the last two
 * labels a few pixels apart. This version instead:
 *
 * 1. estimates each label's painted width from its character count;
 * 2. tries the largest sensible number of labels first and walks down;
 * 3. anchors the first label at the left edge and the last at the right edge
 *    (matching their `text-anchor`), and centres the ones between them;
 * 4. accepts a candidate only when every box is inside the plot and no two
 *    boxes overlap.
 *
 * The first and last points are always preferred. If they cannot coexist the
 * first wins, because an axis with no readable start is worse than one whose
 * end is implied by the hover readout and the data table.
 */
export function selectTrendLabelIndices(
  labels: string[],
  x: (index: number) => number,
  plotLeft: number,
  plotRight: number,
): LabelBox[] {
  const n = labels.length
  if (n === 0) return []

  const widthOf = (text: string) =>
    Math.max(LABEL_FONT_SIZE, text.length * LABEL_CHAR_WIDTH)

  const boxFor = (index: number): LabelBox => {
    const cx = x(index)
    const w = widthOf(labels[index]!)
    if (index === 0) return { index, left: cx, right: cx + w }
    if (index === n - 1) return { index, left: cx - w, right: cx }
    return { index, left: cx - w / 2, right: cx + w / 2 }
  }

  const fits = (indices: number[]): LabelBox[] | null => {
    const boxes = indices.map(boxFor)
    for (const box of boxes) {
      if (box.left < plotLeft - 0.5 || box.right > plotRight + 0.5) return null
    }
    for (let i = 1; i < boxes.length; i++) {
      if (boxes[i]!.left - boxes[i - 1]!.right < LABEL_GAP) return null
    }
    return boxes
  }

  // Prefer more labels; never request more than the data can support.
  const maxCandidates = Math.min(n, 8)
  for (let count = maxCandidates; count >= 2; count--) {
    const indices = Array.from({ length: count }, (_, i) =>
      Math.round((i * (n - 1)) / (count - 1)),
    )
    const unique = [...new Set(indices)]
    if (unique.length < 2) continue
    const boxes = fits(unique)
    if (boxes) return boxes
  }

  // Two labels do not fit. Keep the first (its label is the readable anchor)
  // and fall back to a single box rather than overlapping two.
  return [boxFor(0)]
}

function niceScale(rawMax: number): { max: number; step: number } {
  if (rawMax <= 4) return { max: 4, step: 1 }
  const rough = rawMax / 4
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const residual = rough / magnitude
  const nice =
    residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 2.5 ? 2.5 : residual <= 5 ? 5 : 10
  const step = nice * magnitude
  return { max: Math.ceil(rawMax / step) * step, step }
}

export function TrendChart({
  points,
  series,
  height = H,
  ariaLabel,
  valueLabels,
}: {
  points: TrendPoint[]
  series: TrendSeries[]
  height?: number
  ariaLabel: string
  valueLabels?: string[]
}) {
  const [active, setActive] = useState<number | null>(null)
  const gradientId = useId().replace(/[:]/g, '')
  const { ref: measureRef, width } = useElementWidth<HTMLDivElement>()
  const entered = useEntrance()

  // The SVG viewBox is 1:1 with its rendered pixels (never `preserveAspectRatio
  // ='none'`), so text and ticks keep their proportions at every column width.
  const W = Math.max(MIN_W, width ?? 640)

  const geom = useMemo(() => {
    const rawMax = Math.max(
      1,
      ...points.flatMap((point) => series.map((entry) => point.values[entry.key] ?? 0)),
    )
    const { max, step } = niceScale(rawMax)
    const plotW = W - PAD_L - PAD_R
    const plotH = height - PAD_T - PAD_B
    const stepX = points.length > 1 ? plotW / (points.length - 1) : 0

    const x = (index: number) => PAD_L + index * stepX
    const y = (value: number) => PAD_T + plotH - (value / max) * plotH

    const lines = series.map((entry) => {
      const coords = points.map((point, index) => ({
        x: x(index),
        y: y(point.values[entry.key] ?? 0),
      }))
      const path = coords.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x},${c.y}`).join(' ')
      const area = `${path} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z`
      return { entry, path, area, coords }
    })

    const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, index) => {
      const value = index * step
      return { value, y: PAD_T + plotH - (value / max) * plotH }
    })

    const labelBoxes = selectTrendLabelIndices(
      points.map((point) => point.label),
      x,
      PAD_L,
      W - PAD_R,
    )

    return { max, plotW, plotH, x, y, stepX, lines, ticks, labelBoxes }
  }, [points, series, height, W])

  if (points.length === 0) return null

  const activePoint = active !== null ? points[active] : null

  return (
    <Box position='relative' minW='0' ref={measureRef}>
      <Flex justify='flex-end' mb='1'>
        {activePoint ? (
          <Flex
            gap='3'
            align='center'
            px='2.5'
            py='1'
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l2'
            bg={palette.surface}
            boxShadow={palette.shadowSm}
          >
            <Text fontSize='2xs' color={palette.textMuted}>
              {activePoint.label}
            </Text>
            {series.map((entry) => (
              <Flex key={entry.key} align='center' gap='1.5'>
                <Box boxSize='1.5' borderRadius='full' bg={entry.color} aria-hidden />
                <Text fontSize='2xs' color={palette.textSecondary}>
                  {entry.label}
                </Text>
                <Text
                  fontSize='2xs'
                  fontWeight='semibold'
                  color={palette.text}
                  fontVariantNumeric='tabular-nums'
                >
                  {activePoint.values[entry.key] ?? 0}
                </Text>
              </Flex>
            ))}
          </Flex>
        ) : (
          <Text fontSize='2xs' color={palette.textFaint} aria-hidden>
            Hover a day for exact counts
          </Text>
        )}
      </Flex>

      <Box position='relative'>
        {width === null ? (
          <Skeleton height={`${height}px`} width='100%' bg={palette.inset} borderRadius='l2' />
        ) : (
        <svg
          viewBox={`0 0 ${W} ${height}`}
          width='100%'
          height={height}
          role='presentation'
          aria-hidden='true'
          style={{ display: 'block', overflow: 'visible' }}
          onPointerLeave={() => setActive(null)}
        >
          <defs>
            {series.map((entry) => (
              <linearGradient
                key={entry.key}
                id={`${gradientId}-${entry.key}`}
                x1='0'
                x2='0'
                y1='0'
                y2='1'
              >
                <stop offset='0%' stopColor={entry.color} stopOpacity='0.22' />
                <stop offset='100%' stopColor={entry.color} stopOpacity='0' />
              </linearGradient>
            ))}
          </defs>

          {geom.ticks.map((tick) => (
            <g key={tick.value}>
              <line
                x1={PAD_L}
                x2={W - PAD_R}
                y1={tick.y}
                y2={tick.y}
                stroke={palette.chartGrid}
                strokeWidth='1'
                vectorEffect='non-scaling-stroke'
              />
              <text
                x={PAD_L - 8}
                y={tick.y + 3}
                textAnchor='end'
                fontSize='10'
                fill={palette.chartAxis}
              >
                {tick.value}
              </text>
            </g>
          ))}

          {geom.lines.map((line, lineIndex) => (
            <g key={line.entry.key}>
              <path
                d={line.area}
                fill={`url(#${gradientId}-${line.entry.key})`}
                style={{
                  opacity: entered ? 1 : 0,
                  transition: `opacity ${motionVars.reveal} ${motionVars.ease} ${
                    stagger(lineIndex) + 360
                  }ms`,
                }}
              />
              <path
                d={line.path}
                fill='none'
                stroke={line.entry.color}
                strokeWidth='2'
                strokeLinejoin='round'
                strokeLinecap='round'
                vectorEffect='non-scaling-stroke'
                pathLength={1}
                style={{
                  strokeDasharray: 1,
                  strokeDashoffset: entered ? 0 : 1,
                  transition: `stroke-dashoffset ${motionVars.chart} ${motionVars.easeOut} ${stagger(
                    lineIndex,
                  )}ms`,
                }}
              />
            </g>
          ))}

          {points.map((point, index) => {
            const isActive = active === index
            return (
              <g key={point.label}>
                {isActive ? (
                  <line
                    x1={geom.x(index)}
                    x2={geom.x(index)}
                    y1={PAD_T}
                    y2={height - PAD_B}
                    stroke={palette.borderStrong}
                    strokeDasharray='3 3'
                    strokeWidth='1'
                    vectorEffect='non-scaling-stroke'
                  />
                ) : null}
                {geom.lines.map((line) => (
                  <circle
                    key={line.entry.key}
                    cx={geom.x(index)}
                    cy={line.coords[index]!.y}
                    r={isActive ? 3.5 : 0}
                    fill={palette.surface}
                    stroke={line.entry.color}
                    strokeWidth='2'
                    vectorEffect='non-scaling-stroke'
                  />
                ))}
                <rect
                  x={geom.x(index) - geom.stepX / 2}
                  y={PAD_T}
                  width={Math.max(geom.stepX, 8)}
                  height={geom.plotH}
                  fill='transparent'
                  onPointerEnter={() => setActive(index)}
                  style={{ cursor: 'crosshair' }}
                />
              </g>
            )
          })}

          {geom.labelBoxes.map(({ index }) => (
            <text
              key={`label-${points[index]!.label}`}
              x={geom.x(index)}
              y={height - 8}
              textAnchor={index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle'}
              fontSize={LABEL_FONT_SIZE}
              fill={palette.chartAxis}
            >
              {points[index]!.label}
            </text>
          ))}
        </svg>
        )}
      </Box>

      <ChartDataTable
        caption={ariaLabel}
        columns={['Day', ...(valueLabels ?? series.map((entry) => entry.label))]}
        rows={points.map((point) => [
          point.label,
          ...series.map((entry) => point.values[entry.key] ?? 0),
        ])}
      />
    </Box>
  )
}
