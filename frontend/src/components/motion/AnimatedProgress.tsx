import { Box, Flex, Text } from '@chakra-ui/react'
import type { ReactNode } from 'react'

import { motionVars } from '../../theme/motion.ts'
import { palette } from '../../theme/palette.ts'
import { useEntrance } from '../../hooks/useEntrance.ts'
import { AnimatedNumber } from './AnimatedNumber.tsx'

/**
 * Fallback denominator used only when the caller supplies an unusable maximum
 * (0, negative, NaN or Infinity). Documented in the implementation report.
 */
const DEFAULT_MAX = 100

/**
 * A progress meter that grows from zero to its real value.
 *
 * The fill is a full-width bar scaled with `transform: scaleX(ratio)`, so the
 * resting position is the exact ratio of `value / max` — no rounding, no
 * invented target, and no post-arrival loop. When the underlying number
 * changes, the transform transitions from the previous ratio to the new one,
 * which is both accurate and cheap (transform + opacity only).
 *
 * The element exposes real `role="progressbar"` semantics with the same
 * numbers it draws. The percentage label counts up alongside the bar using the
 * same denominator, so the label and the fill can never disagree.
 */
export function AnimatedProgress({
  value,
  max = 100,
  color = palette.accent,
  label,
  hint,
  showValue = true,
  height = 2,
  ariaLabel,
}: {
  value: number
  /** Denominator for the fill. The bar reaches exactly `value / max`. */
  max?: number
  color?: string
  label?: ReactNode
  hint?: ReactNode
  /** Show the percentage derived from `value / max`. */
  showValue?: boolean
  height?: number | string
  ariaLabel?: string
}) {
  const entered = useEntrance()

  // One normalization pass feeds the fill, the label and ARIA. Nothing below
  // may read the raw inputs again, so the bar can never disagree with the
  // number it announces.
  //
  // - a non-finite or non-positive maximum has no meaningful scale, so it falls
  //   back to 100 (documented, and the only value that keeps a percentage
  //   honest when the caller passes 0);
  // - a non-finite current value is treated as 0 rather than NaN (which would
  //   poison the ratio and the label);
  // - the current value is clamped into [0, max] so ARIA and geometry agree even
  //   when the caller overshoots.
  const safeMax =
    Number.isFinite(max) && max > 0 ? max : DEFAULT_MAX
  const normalizedValue = Math.min(
    Math.max(Number.isFinite(value) ? value : 0, 0),
    safeMax,
  )
  const ratio = normalizedValue / safeMax
  const percent = Math.round(ratio * 100)

  // A progressbar must have an accessible name. Callers either pass an
  // explicit `ariaLabel` or a plain-string `label`; if neither is available we
  // render the meter as decorative rather than shipping an unnamed control.
  const accessibleName =
    ariaLabel ?? (typeof label === 'string' && label.trim() ? label : undefined)

  return (
    <Box minW='0'>
      {label || showValue ? (
        <Flex align='baseline' justify='space-between' gap='3' mb='1.5'>
          {label ? (
            // A Box (not a Text) because callers may pass a composed label
            // containing its own spans and icons, which cannot nest in a <p>.
            <Box fontSize='xs' color={palette.textSecondary} truncate minW='0'>
              {label}
            </Box>
          ) : (
            <span />
          )}
          {showValue ? (
            <Text
              fontSize='xs'
              fontWeight='medium'
              color={palette.text}
              fontVariantNumeric='tabular-nums'
              flexShrink={0}
            >
              <AnimatedNumber value={percent} />%
            </Text>
          ) : null}
        </Flex>
      ) : null}

      <Box
        role={accessibleName ? 'progressbar' : 'presentation'}
        aria-label={accessibleName}
        aria-valuemin={accessibleName ? 0 : undefined}
        aria-valuemax={accessibleName ? safeMax : undefined}
        aria-valuenow={accessibleName ? normalizedValue : undefined}
        aria-valuetext={accessibleName ? `${percent}%` : undefined}
        height={height}
        borderRadius='full'
        bg={palette.inset}
        overflow='hidden'
      >
        <Box
          height='100%'
          width='100%'
          bg={color}
          borderRadius='full'
          style={{
            transform: `scaleX(${entered ? ratio : 0})`,
            transformOrigin: 'left center',
            transition: `transform ${motionVars.chart} ${motionVars.easeOut}`,
          }}
        />
      </Box>

      {hint ? (
        <Box fontSize='2xs' color={palette.textMuted} mt='1.5'>
          {hint}
        </Box>
      ) : null}
    </Box>
  )
}
