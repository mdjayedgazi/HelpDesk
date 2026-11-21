import { Box, type BoxProps } from '@chakra-ui/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import { easing, duration as durations } from '../theme/motion.ts'

interface RevealProps extends Omit<BoxProps, 'children'> {
  children?: ReactNode
  /** Stagger, in milliseconds. */
  delay?: number
  /** Vertical travel, in pixels. */
  y?: number
  /** Element to render instead of a `div` (e.g. `section`, `li`). */
  as?: React.ElementType
}

/**
 * Fades and lifts its children the first time they scroll into view.
 *
 * Uses a single IntersectionObserver per instance and pure CSS transitions, so
 * there is no animation runtime to ship. Once a section has been revealed the
 * observer disconnects, so scrolling up and down never replays it. Users who
 * prefer reduced motion (or browsers without IntersectionObserver) get the
 * final state immediately — the content is never hidden behind an animation.
 */
export function Reveal({ children, delay = 0, y = 18, as, ...rest }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const node = ref.current
    if (!node) return

    const reducedMotion =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches

    if (reducedMotion || typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }

    // Anything already on screen shows immediately instead of waiting for the
    // observer's first callback. Without this, workspace pages (whose whole
    // content is revealed this way) could paint blank for a frame on mount.
    const rect = node.getBoundingClientRect()
    if (rect.top < window.innerHeight && rect.bottom > 0) {
      setVisible(true)
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setVisible(true)
            observer.disconnect()
          }
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -64px 0px' },
    )

    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return (
    <Box
      as={as}
      ref={ref}
      opacity={visible ? 1 : 0}
      transform={visible ? 'none' : `translateY(${y}px)`}
      transition={`opacity ${durations.reveal}ms ${easing.standard} ${delay}ms, transform ${durations.reveal}ms ${easing.standard} ${delay}ms`}
      {...rest}
    >
      {children}
    </Box>
  )
}
