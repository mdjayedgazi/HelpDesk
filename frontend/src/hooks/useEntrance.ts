import { useEffect, useState } from 'react'

import { prefersReducedMotion } from '../theme/motion.ts'

/**
 * One-shot "has mounted" flag for CSS entrance transitions.
 *
 * Returns `true` immediately when the user prefers reduced motion (or when
 * `matchMedia` is unavailable), so nothing is ever hidden behind an animation.
 * The flag flips once, on the next animation frame, and never resets — charts
 * should draw themselves when they first appear, not every time React renders.
 */
export function useEntrance(): boolean {
  const [entered, setEntered] = useState(() => prefersReducedMotion())

  useEffect(() => {
    if (entered) return
    if (typeof window.requestAnimationFrame !== 'function') {
      setEntered(true)
      return
    }
    const frame = window.requestAnimationFrame(() => setEntered(true))
    return () => window.cancelAnimationFrame(frame)
  }, [entered])

  return entered
}

/**
 * A stagger-friendly delay that resolves after `delay` ms.
 *
 * Used for sibling chart rows so a small group grows in sequence. Honours
 * reduced motion by resolving instantly.
 */
export function useDelayedEntrance(delay: number): boolean {
  // Read the media query once per component rather than on every render.
  const [reduced] = useState(prefersReducedMotion)
  const [entered, setEntered] = useState(reduced)

  useEffect(() => {
    if (reduced || delay <= 0) {
      setEntered(true)
      return
    }
    const timer = window.setTimeout(() => setEntered(true), delay)
    return () => window.clearTimeout(timer)
  }, [delay, reduced])

  return entered
}
