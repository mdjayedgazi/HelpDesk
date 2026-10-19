import { Box, type BoxProps } from '@chakra-ui/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

interface RevealProps extends Omit<BoxProps, 'children'> {
  children?: ReactNode
  /** Stagger, in milliseconds. */
  delay?: number
  /** Vertical travel, in pixels. */
  y?: number
}

const EASE = 'cubic-bezier(0.22, 0.61, 0.36, 1)'

/**
 * Fades and lifts its children the first time they scroll into view.
 *
 * Uses a single IntersectionObserver per instance and pure CSS transitions, so
 * there is no animation runtime to ship. Users who prefer reduced motion (or
 * browsers without IntersectionObserver) get the final state immediately — the
 * content is never hidden behind an animation.
 */
export function Reveal({ children, delay = 0, y = 18, ...rest }: RevealProps) {
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
      ref={ref}
      opacity={visible ? 1 : 0}
      transform={visible ? 'none' : `translateY(${y}px)`}
      transition={`opacity 620ms ${EASE} ${delay}ms, transform 620ms ${EASE} ${delay}ms`}
      {...rest}
    >
      {children}
    </Box>
  )
}
