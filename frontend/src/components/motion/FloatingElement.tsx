import { Box, type BoxProps } from '@chakra-ui/react'
import type { ReactNode } from 'react'

import { duration as durations, float } from '../../theme/motion.ts'

/**
 * Ambient vertical drift for depth-carrying elements on the landing page.
 *
 * Movement is intentionally tiny (4–8 px) and slow (6–9 s), and the timing is
 * varied per instance so a group of layers never moves in lockstep. CSS owns
 * the loop — there is no JavaScript timer — and `tokens.css` disables it for
 * `prefers-reduced-motion` and below the tablet breakpoint.
 *
 * This is for decorative hero/product layers only. Continuous motion inside the
 * working dashboard would be a distraction, so nothing in the app shell uses it.
 */
export function FloatingElement({
  children,
  distance = 6,
  duration = durations.ambient,
  delay = 0,
  slow = false,
  ...rest
}: BoxProps & {
  children?: ReactNode
  /** Vertical travel in pixels, clamped to the documented 4–8 px range. */
  distance?: number
  /** Full cycle length in milliseconds. */
  duration?: number
  /** Delay before the loop starts, so siblings desynchronise. */
  delay?: number
  /** Use the slightly slower default cycle. */
  slow?: boolean
}) {
  const travel = Math.min(Math.max(distance, float.minDistance), float.maxDistance)

  return (
    <Box
      className={slow ? 'hd-float-slow' : 'hd-float'}
      style={{
        ['--hd-float-dist' as string]: `${travel}px`,
        ['--hd-float-dur' as string]: `${duration}ms`,
        ['--hd-float-delay' as string]: `${delay}ms`,
      }}
      {...rest}
    >
      {children}
    </Box>
  )
}
