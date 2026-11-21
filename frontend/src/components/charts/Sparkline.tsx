import { Box } from '@chakra-ui/react'
import { useId } from 'react'

/**
 * A tiny inline trend line for metric cards.
 *
 * Purely decorative support for the headline number (the card's value is the
 * accessible datum), so it is marked `aria-hidden`. It shares the same aspect
 * ratio as the full trend chart so the two never disagree about direction.
 */
export function Sparkline({
  values,
  color,
  width = 120,
  height = 32,
  label,
}: {
  values: number[]
  color: string
  width?: number
  height?: number
  label?: string
}) {
  const gradientId = useId().replace(/[:]/g, '')
  if (values.length < 2) return null

  const max = Math.max(1, ...values)
  const min = Math.min(...values)
  const span = Math.max(1, max - min)
  // Inset the plot so the end-cap dot is never clipped by the viewBox edge.
  const inset = 3
  const plotW = width - inset * 2
  const plotH = height - inset * 2
  const stepX = plotW / (values.length - 1)
  const points = values.map((value, index) => ({
    x: inset + index * stepX,
    y: inset + plotH - ((value - min) / span) * plotH,
  }))
  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
  const area = `${line} L${inset + plotW},${height} L${inset},${height} Z`

  return (
    <Box as='span' aria-hidden='true' title={label} display='inline-block' lineHeight='0'>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        role='presentation'
      >
        <defs>
          <linearGradient id={gradientId} x1='0' x2='0' y1='0' y2='1'>
            <stop offset='0%' stopColor={color} stopOpacity='0.2' />
            <stop offset='100%' stopColor={color} stopOpacity='0' />
          </linearGradient>
        </defs>
        <path d={area} fill={`url(#${gradientId})`} />
        <path
          d={line}
          fill='none'
          stroke={color}
          strokeWidth='1.5'
          strokeLinejoin='round'
          strokeLinecap='round'
          vectorEffect='non-scaling-stroke'
        />
        <circle cx={points[points.length - 1]!.x} cy={points[points.length - 1]!.y} r='2' fill={color} />
      </svg>
    </Box>
  )
}
