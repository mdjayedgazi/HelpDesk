import { VisuallyHidden } from '@chakra-ui/react'
import { useEffect, useRef, useState } from 'react'

import { duration as durations, prefersReducedMotion } from '../../theme/motion.ts'

/**
 * Last value each keyed counter displayed.
 *
 * Mounting a dashboard afresh (for example navigating away and back) should not
 * restart a count-up from zero when the number has not changed — that reads as
 * a loading artefact. Keyed counters resume from the last value they showed and
 * animate only the difference. Bounded by the number of distinct keys in the
 * product, which is small and static.
 */
const lastValue = new Map<string, number>()

/**
 * Counts a real number up to its real value.
 *
 * The contract is deliberately strict:
 *
 * - the value always settles on exactly the number passed in — it never scales,
 *   rounds to a nicer figure, or animates towards a placeholder;
 * - a change from one real value to the next animates from the *previous*
 *   value, not from zero, so refetching a dashboard does not look like a reset;
 * - the animation restarts only when the target changes, never on an unrelated
 *   render;
 * - the visible digits are `aria-hidden`; a visually hidden copy of the final
 *   formatted value is the accessible datum, so assistive technology is never
 *   read a stream of intermediate numbers;
 * - with reduced motion (or no `matchMedia`/`requestAnimationFrame`, as in
 *   tests) the final value is rendered immediately.
 *
 * Non-numeric values (the em-dash placeholder used while a query is pending)
 * are rendered untouched.
 */
export function AnimatedNumber({
  value,
  duration = durations.count,
  format = (current) => Math.round(current).toLocaleString('en-US'),
  className,
  cacheKey,
}: {
  value: number | string
  /** Count-up duration in milliseconds. */
  duration?: number
  /** Formatter for the in-flight value; must be monotonic. */
  format?: (value: number) => string
  className?: string
  /**
   * Stable identity for this counter. When provided, a remount resumes from the
   * value it last displayed instead of counting up from zero again.
   */
  cacheKey?: string
}) {
  const numeric = typeof value === 'number' && Number.isFinite(value)
  // Resolve the media query once per component rather than on every render.
  const [reduced] = useState(prefersReducedMotion)

  const [display, setDisplay] = useState<number>(() => {
    if (!numeric) return 0
    const remembered = cacheKey ? lastValue.get(cacheKey) : undefined
    if (remembered !== undefined) return remembered
    return reduced ? (value as number) : 0
  })
  const currentRef = useRef<number>(
    numeric
      ? (cacheKey && lastValue.get(cacheKey) !== undefined
          ? (lastValue.get(cacheKey) as number)
          : reduced
            ? (value as number)
            : 0)
      : Number(value) || 0,
  )

  useEffect(() => {
    if (!numeric) return
    const target = value as number

    if (reduced || typeof window.requestAnimationFrame !== 'function') {
      currentRef.current = target
      setDisplay(target)
      return
    }

    const from = currentRef.current
    if (from === target) {
      if (cacheKey) lastValue.set(cacheKey, target)
      return
    }

    let frame = 0
    let start: number | null = null

    const tick = (now: number) => {
      if (start === null) start = now
      const progress = Math.min(1, (now - start) / Math.max(1, duration))
      // Cubic ease-out: quick off the mark, so the number feels responsive.
      const eased = 1 - (1 - progress) ** 3
      const next = from + (target - from) * eased
      currentRef.current = next
      setDisplay(next)
      if (progress < 1) {
        frame = window.requestAnimationFrame(tick)
      } else {
        currentRef.current = target
        setDisplay(target)
        if (cacheKey) lastValue.set(cacheKey, target)
      }
    }

    frame = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(frame)
  }, [value, duration, numeric, reduced, cacheKey])

  if (!numeric) {
    return <span className={className}>{value}</span>
  }

  return (
    <span className={className}>
      <span aria-hidden='true'>{format(display)}</span>
      <VisuallyHidden>{format(value as number)}</VisuallyHidden>
    </span>
  )
}
